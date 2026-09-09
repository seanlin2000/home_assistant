"""manual-check must find every Mermaid block with its line, expand snippets, map render errors back to the markdown, enforce the page profiles, and leave the real manual clean."""

import subprocess
from pathlib import Path

import pytest

from deslop.checks import Finding
from manual_checks import render
from manual_checks.blocks import UNTERMINATED, MermaidBlock, expand_snippets, fenced_blocks, file_line, mermaid_blocks, outside_fences
from manual_checks.cli import check, main, markdown_files
from manual_checks.headings import Page, glossary_terms, headings, palette_lines, structure_findings
from manual_checks.render import BROWSER_HINT, MMDC_HINT, RendererUnavailable, RenderResult, find_mmdc, mmdc_renderer, parse_failure, render_findings, write_puppeteer_config

PALETTE = Path("operator_manual/_includes/palette.mmd").read_text(encoding="utf-8")
MAP_BLOCK = '```mermaid\nflowchart LR\n--8<-- "_includes/system_map.mmd"\nclass agent current\n```\n'


def section_text(title: str = "1. Title", complexity: str = "<!-- complexity: packages=2 parts=2 concepts=2 tier=standard -->") -> str:
    return (
        f"# {title}\n{complexity}\n\n## Where this fits\n{MAP_BLOCK}\n## Key definitions\n- **Wake word.** A phrase.\n\n## Packages and tools\n"
        "## How it works\n### Part\n## Run it yourself\n## Where to look in the code\n## Further reading\n"
    )


def page_for(name: str, text: str, root: Path) -> Page:
    path = root / name
    return Page(path, text, headings(text), mermaid_blocks(path, text, root))


@pytest.fixture
def manual_root(tmp_path: Path) -> Path:
    (tmp_path / "_includes").mkdir()
    (tmp_path / "_includes" / "palette.mmd").write_text(PALETTE, encoding="utf-8")
    (tmp_path / "_includes" / "system_map.mmd").write_text('--8<-- "_includes/palette.mmd"\nagent["agent"]\n', encoding="utf-8")
    (tmp_path / "glossary.md").write_text("# Glossary\n\n- **Wake word.** A phrase.\n", encoding="utf-8")
    return tmp_path


def messages(findings: list[Finding]) -> list[str]:
    return [finding.message for finding in findings]


def test_fences_report_line_language_and_body_for_backticks_and_tildes() -> None:
    text = "intro\n```mermaid\na --> b\n```\n~~~~python\nx = 1\n~~~~\n"
    assert list(fenced_blocks(text)) == [(2, "mermaid", ["a --> b"]), (5, "python", ["x = 1"])]


def test_indented_fence_inside_an_admonition_is_dedented() -> None:
    text = "!!! note\n    ```mermaid\n    a --> b\n    ```\n"
    assert list(fenced_blocks(text)) == [(2, "mermaid", ["a --> b"])]


def test_a_longer_closing_fence_closes_and_a_shorter_one_does_not() -> None:
    text = "````md\n```\ninner\n```\n````\n"
    assert list(fenced_blocks(text)) == [(1, "md", ["```", "inner", "```"])]


def test_unterminated_fence_is_reported_with_its_language_replaced() -> None:
    assert [block.language for block in fenced_blocks("```mermaid\na --> b\n")] == [UNTERMINATED]


def test_outside_fences_skips_every_line_of_a_block() -> None:
    text = "# H\n```python\n# not a heading\n```\n## H2\n"
    assert list(outside_fences(text)) == [(1, "# H"), (5, "## H2")]


def test_snippets_expand_and_errors_inside_them_map_to_the_include_line(tmp_path: Path) -> None:
    (tmp_path / "inc.mmd").write_text("x\ny\n", encoding="utf-8")
    source, lines = expand_snippets(["flowchart LR", '--8<-- "inc.mmd"', "z"], 10, tmp_path)
    assert source == ["flowchart LR", "x", "y", "z"]
    assert lines == [11, 12, 12, 13]
    block = MermaidBlock(Path("p.md"), 10, "\n".join(source), tuple(lines))
    assert file_line(block, 3) == 12
    assert file_line(block, None) == 10
    assert file_line(block, 99) == 10


def test_nested_snippets_expand_and_map_to_the_outer_include_line(tmp_path: Path) -> None:
    (tmp_path / "inner.mmd").write_text("i\n", encoding="utf-8")
    (tmp_path / "outer.mmd").write_text('--8<-- "inner.mmd"\no\n', encoding="utf-8")
    assert expand_snippets(['--8<-- "outer.mmd"'], 5, tmp_path) == (["i", "o"], [6, 6])


def test_missing_snippet_becomes_an_error_line_in_the_source(tmp_path: Path) -> None:
    source, _ = expand_snippets(['--8<-- "nope.mmd"'], 1, tmp_path)
    assert source[0].startswith("Snippet not found")


def test_only_mermaid_fences_become_blocks(tmp_path: Path) -> None:
    text = "```python\nx\n```\n```mermaid\na --> b\n```\n"
    assert [block.line for block in mermaid_blocks(Path("p.md"), text, tmp_path)] == [4]


def test_parse_failure_extracts_the_line_and_the_first_message_line() -> None:
    result = parse_failure("\nError: Parse error on line 3:\n... a -->\n")
    assert result == RenderResult(False, "Parse error on line 3:", 3)
    assert parse_failure("something else\n") == RenderResult(False, "something else", None)


def test_browser_launch_failure_raises_once_with_the_hint() -> None:
    with pytest.raises(RendererUnavailable, match=BROWSER_HINT):
        parse_failure("Error: Could not find chrome-headless-shell (ver. 1)")


def test_render_findings_report_the_file_line_of_the_failing_diagram_line() -> None:
    good = MermaidBlock(Path("a.md"), 5, "ok\n", (6,))
    bad = MermaidBlock(Path("b.md"), 20, "x\nBAD\n", (21, 22))
    renderer = lambda source: RenderResult(False, "Parse error on line 2:", 2) if "BAD" in source else RenderResult(True, "", None)
    assert render_findings([good, bad], renderer, jobs=2) == [Finding(Path("b.md"), 22, "Parse error on line 2:")]


def test_mmdc_renderer_invokes_mmdc_with_the_config_and_maps_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, "", "Error: Parse error on line 2:\n")

    monkeypatch.setattr(render.subprocess, "run", fake_run)
    config = write_puppeteer_config(tmp_path, Path("/browser"), sandbox=False)
    result = mmdc_renderer(Path("/bin/mmdc"), tmp_path, config)("a --> b\n")
    assert result == RenderResult(False, "Parse error on line 2:", 2)
    assert calls[0][:2] == ["/bin/mmdc", "-i"] and calls[0][-2:] == ["-p", str(config)] and "-q" in calls[0]
    assert '"executablePath": "/browser"' in config.read_text(encoding="utf-8") and "--no-sandbox" in config.read_text(encoding="utf-8")


def test_puppeteer_config_is_omitted_when_there_is_nothing_to_set(tmp_path: Path) -> None:
    assert write_puppeteer_config(tmp_path, None, sandbox=True) is None


def test_find_mmdc_raises_the_brew_hint_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(render.shutil, "which", lambda name: None)
    with pytest.raises(RendererUnavailable, match="brew install mermaid-cli"):
        find_mmdc()


def test_main_exits_with_the_hint_when_mmdc_is_missing(manual_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    (manual_root / "01_x.md").write_text(section_text(), encoding="utf-8")
    monkeypatch.setattr(render.shutil, "which", lambda name: None)
    monkeypatch.setattr("sys.argv", ["manual-check", "--root", str(manual_root), str(manual_root)])
    with pytest.raises(SystemExit) as raised:
        main()
    assert raised.value.code == f"manual-check: {MMDC_HINT}"
    assert capsys.readouterr().out == ""


def test_headings_come_only_from_lines_outside_fences() -> None:
    assert headings("# A\n```py\n# no\n```\n### C\n") == [(1, "A", 1), (3, "C", 5)]


def test_a_complete_section_is_clean(manual_root: Path) -> None:
    page = page_for("01_x.md", section_text(), manual_root)
    assert structure_findings(page, glossary_terms((manual_root / "glossary.md").read_text()), palette_lines(PALETTE)) == []


def test_missing_and_reordered_headings_are_reported_with_lines(manual_root: Path) -> None:
    text = section_text().replace("## Run it yourself\n", "").replace("## Key definitions\n- **Wake word.** A phrase.\n\n## Packages and tools\n", "## Packages and tools\n## Key definitions\n")
    findings = structure_findings(page_for("01_x.md", text, manual_root), {"wake word"}, palette_lines(PALETTE))
    assert messages(findings) == ["missing heading '## Run it yourself'", "heading '## Packages and tools' out of order (expected after '## Key definitions')"]
    assert [finding.line for finding in findings] == [1, 11]


def test_complexity_comment_must_exist_and_match_its_tier(manual_root: Path) -> None:
    assert messages(structure_findings(page_for("01_x.md", section_text(complexity=""), manual_root), {"wake word"}, palette_lines(PALETTE)))[0].startswith("missing complexity comment")
    wrong = section_text(complexity="<!-- complexity: packages=3 parts=3 concepts=3 tier=light -->")
    assert messages(structure_findings(page_for("01_x.md", wrong, manual_root), {"wake word"}, palette_lines(PALETTE))) == ["complexity score 9 is tier 'deep', not 'light'"]


def test_where_this_fits_needs_the_map_include_and_a_highlight(manual_root: Path) -> None:
    no_map = section_text().replace('--8<-- "_includes/system_map.mmd"\n', "a --> b\n")
    assert messages(structure_findings(page_for("01_x.md", no_map, manual_root), {"wake word"}, palette_lines(PALETTE))) == [
        "'Where this fits' diagram must include the system map: --8<-- \"_includes/system_map.mmd\""
    ]
    no_highlight = section_text().replace("class agent current\n", "")
    assert "highlights nothing" in messages(structure_findings(page_for("01_x.md", no_highlight, manual_root), {"wake word"}, palette_lines(PALETTE)))[0]


def test_palette_drift_and_unknown_classes_are_reported(manual_root: Path) -> None:
    text = section_text() + "```mermaid\nflowchart LR\nclassDef ours fill:#000\nx:::mine --> y\nclass y nope\n```\n"
    findings = structure_findings(page_for("01_x.md", text, manual_root), {"wake word"}, palette_lines(PALETTE))
    assert [message.split(":")[0] for message in messages(findings)] == [
        "classDef outside the palette (_includes/palette.mmd)",
        "class 'mine' is not one of the palette classes ['current', 'ext', 'hw', 'ours', 'third']",
        "class 'nope' is not one of the palette classes ['current', 'ext', 'hw', 'ours', 'third']",
    ]


def test_a_definition_missing_from_the_glossary_is_reported(manual_root: Path) -> None:
    text = section_text().replace("- **Wake word.** A phrase.", "- **Wake word.** A phrase.\n- **Tokens.** Pieces.")
    assert messages(structure_findings(page_for("01_x.md", text, manual_root), {"wake word"}, palette_lines(PALETTE))) == ["'Tokens' is defined here but missing from glossary.md"]


def test_introduction_uses_its_own_profile(manual_root: Path) -> None:
    text = "# Introduction\n\n## Purpose\n## How to read this manual\n## Key definitions\n## Software and hardware\n## The system map\n## Where the code lives\n## Before you run anything\n"
    assert structure_findings(page_for("index.md", text, manual_root), set(), palette_lines(PALETTE)) == []
    assert messages(structure_findings(page_for("index.md", text.replace("## Purpose\n", ""), manual_root), set(), palette_lines(PALETTE))) == ["missing heading '## Purpose'"]


def entry(title: str, marker: str) -> str:
    return f"## {title}\n{marker}\n\n### Where this fits\n{MAP_BLOCK}\n### Key definitions\n### Packages and tools\n### What changed\n### Run it yourself\n"


def test_current_changes_entries_need_a_title_shape_marker_and_unique_branch(manual_root: Path) -> None:
    good = entry("PR #7: Add x", '<!-- manual-entry branch="add-x" pr="7" date="2026-09-07" -->')
    text = "# Current working changes\n\nIntro.\n\n" + good + entry("Branch add-y: Add y", '<!-- manual-entry branch="add-y" pr="pending" date="2026-09-07" -->')
    assert structure_findings(page_for("current_changes.md", text, manual_root), set(), palette_lines(PALETTE)) == []
    bad = "# Current working changes\n\n" + entry("Add z", "no marker") + good + good.replace("### What changed\n", "")
    found = messages(structure_findings(page_for("current_changes.md", bad, manual_root), set(), palette_lines(PALETTE)))
    assert found[0].startswith("entry heading must read")
    assert found[1].startswith("entry heading must be followed by")
    assert "duplicate entry for branch 'add-x'" in found
    assert "missing heading '### What changed'" in found


def test_markdown_files_skip_the_includes_folder(manual_root: Path) -> None:
    (manual_root / "01_x.md").write_text("x", encoding="utf-8")
    assert [path.name for path in markdown_files(manual_root)] == ["01_x.md", "glossary.md"]


def test_check_without_rendering_reports_structure_only(manual_root: Path) -> None:
    (manual_root / "01_x.md").write_text(section_text().replace("## Further reading\n", ""), encoding="utf-8")
    assert messages(check(manual_root, [manual_root], render=False, sandbox=True, jobs=1)) == ["missing heading '## Further reading'"]


def test_the_real_manual_structure_is_clean() -> None:
    assert check(Path("operator_manual"), [Path("operator_manual")], render=False, sandbox=True, jobs=1) == []


def test_run_mmdc_asks_for_a_white_png_of_fixed_width_when_the_output_is_png(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(render.subprocess, "run", lambda command, **kwargs: calls.append(command) or subprocess.CompletedProcess(command, 0, "", ""))
    render.render_png(Path("/bin/mmdc"), "a --> b\n", tmp_path, None, tmp_path / "page_12.png")
    assert calls[0][calls[0].index("-o") + 1] == str(tmp_path / "page_12.png")
    assert calls[0][calls[0].index("-w") + 1] == render.PNG_WIDTH and "white" in calls[0] and "-p" not in calls[0]
    assert calls[0][calls[0].index("-c") + 1] == str(render.MERMAID_CONFIG)


def test_hook_sizes_the_svg_to_the_column_but_never_below_seventy_percent() -> None:
    from manual_checks.mkdocs_hook import sized

    svg = '<svg id="d" style="max-width: 1000px; background-color: white;" viewBox="0 0 1000 300"><g/></svg>'
    assert sized(svg) == '<svg id="d" style="width: 100%; max-width: 1000px; min-width: 700px;" viewBox="0 0 1000 300"><g/></svg>'


def test_hook_replaces_each_mermaid_fence_with_a_figure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from manual_checks import mkdocs_hook

    monkeypatch.setattr(mkdocs_hook, "cached_svg", lambda source: f"<svg>{source.strip()}</svg>")
    page = "# T\n\n```mermaid\nflowchart TB\na --> b\n```\n\ntext\n"
    result = mkdocs_hook.on_page_markdown(page, None, {"docs_dir": str(tmp_path)}, None)
    assert result == '# T\n\n<figure class="manual-diagram">\n<svg>flowchart TB\na --> b</svg>\n</figure>\n\ntext\n'
