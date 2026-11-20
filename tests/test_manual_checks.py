"""manual-check must find every Mermaid block with its line, expand snippets, map render errors back to the markdown, enforce the page profiles, and leave the real manual clean."""

import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from mkdocs.exceptions import PluginError

from deslop.checks import Finding
from diagrams import mmdc, screenshot
from diagrams.grid import ARROW_GAP, COLUMN_GAP, EDGE_PATH, LABEL_CLEARANCE, MARGIN, NODE_TRANSFORM, ROW_GAP, containers_of, crossings, grid_rows, lay_out_on_grid, node_markups, shape_size, split_link
from diagrams.layout import polish
from diagrams.mmdc import BROWSER_HINT, MMDC_HINT, RendererUnavailable, RenderResult, find_mmdc, parse_failure, write_puppeteer_config
from diagrams.polish import TITLE_INSET, Box, Title, band_layers, blend_label_backgrounds, round_corners
from manual_checks import diagram_cache, render
from manual_checks.blocks import UNTERMINATED, MermaidBlock, expand_snippets, fenced_blocks, file_line, mermaid_blocks, outside_fences
from manual_checks.cli import check, main, markdown_files
from manual_checks.headings import Page, glossary_terms, headings, palette_lines, structure_findings
from manual_checks.render import mmdc_renderer, render_findings

PALETTE = Path("operator_manual/_includes/palette.mmd").read_text(encoding="utf-8")
MAP_BLOCK = '```mermaid\nflowchart LR\n--8<-- "_includes/system_map.mmd"\nclass agent current\n```\n'


def section_text(title: str = "Title", complexity: str = "<!-- complexity: packages=2 parts=2 concepts=2 tier=standard -->") -> str:
    return (
        f"# {title}\n{complexity}\n\n## Where this fits\n{MAP_BLOCK}\n## Key definitions\n| Term | Meaning |\n|---|---|\n| Wake word | A phrase. |\n\n## Packages and tools\n"
        "## How it works\n### Part\n## Run it yourself\n## Where to look in the code\n## Further reading\n"
    )


GLOSSARY = "# Glossary\n\nOne lead-in line.\n\n| Term | Meaning | Explained in |\n|---|---|---|\n| Wake word | A phrase. | [Voice](05_x.md#how-it-works) |\n"


def page_for(name: str, text: str, root: Path) -> Page:
    path = root / name
    return Page(path, text, headings(text), mermaid_blocks(path, text, root))


@pytest.fixture
def manual_root(tmp_path: Path) -> Path:
    (tmp_path / "_includes").mkdir()
    (tmp_path / "_includes" / "palette.mmd").write_text(PALETTE, encoding="utf-8")
    (tmp_path / "_includes" / "system_map.mmd").write_text('--8<-- "_includes/palette.mmd"\nagent["agent"]\n', encoding="utf-8")
    (tmp_path / "glossary.md").write_text(GLOSSARY, encoding="utf-8")
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

    monkeypatch.setattr(mmdc.subprocess, "run", fake_run)
    config = write_puppeteer_config(tmp_path, Path("/browser"), sandbox=False)
    result = mmdc_renderer(Path("/bin/mmdc"), tmp_path, config)("a --> b\n")
    assert result == RenderResult(False, "Parse error on line 2:", 2)
    assert calls[0][:2] == ["/bin/mmdc", "-i"] and calls[0][-2:] == ["-p", str(config)] and "-q" in calls[0]
    assert '"executablePath": "/browser"' in config.read_text(encoding="utf-8") and "--no-sandbox" in config.read_text(encoding="utf-8")


def test_puppeteer_config_is_omitted_when_there_is_nothing_to_set(tmp_path: Path) -> None:
    assert write_puppeteer_config(tmp_path, None, sandbox=True) is None


def test_find_mmdc_raises_the_brew_hint_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mmdc.shutil, "which", lambda name: None)
    with pytest.raises(RendererUnavailable, match="brew install mermaid-cli"):
        find_mmdc()


def test_main_exits_with_the_hint_when_mmdc_is_missing(manual_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    (manual_root / "01_x.md").write_text(section_text(), encoding="utf-8")
    monkeypatch.setattr(mmdc.shutil, "which", lambda name: None)
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
    text = (
        section_text()
        .replace("## Run it yourself\n", "")
        .replace("## Key definitions\n| Term | Meaning |\n|---|---|\n| Wake word | A phrase. |\n\n## Packages and tools\n", "## Packages and tools\n## Key definitions\n")
    )
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


def test_glossary_terms_are_the_table_rows_without_the_header() -> None:
    assert glossary_terms(GLOSSARY + "| KV cache | Memory. | [LLMs](02_x.md#memory-cost) |\n") == {"wake word", "kv cache"}


def test_a_definition_missing_from_the_glossary_is_reported(manual_root: Path) -> None:
    text = section_text().replace("| Wake word | A phrase. |", "| Wake word | A phrase. |\n| Tokens | Pieces. |")
    assert messages(structure_findings(page_for("01_x.md", text, manual_root), {"wake word"}, palette_lines(PALETTE))) == ["'Tokens' is defined here but missing from glossary.md"]


def test_key_definitions_written_as_a_list_are_reported(manual_root: Path) -> None:
    text = section_text().replace("| Term | Meaning |\n|---|---|\n| Wake word | A phrase. |", "- **Wake word.** A phrase.")
    assert messages(structure_findings(page_for("01_x.md", text, manual_root), {"wake word"}, palette_lines(PALETTE))) == ["Key definitions is a two-column table (| Term | Meaning |), not a list"]


def test_a_numbered_page_title_is_reported(manual_root: Path) -> None:
    page = page_for("04_x.md", section_text(title="4. The Agent"), manual_root)
    assert messages(structure_findings(page, {"wake word"}, palette_lines(PALETTE))) == ["title '# 4. The Agent' is numbered: the nav orders the pages, so the title is the page's name alone"]


def test_cross_references_by_section_number_are_reported_on_every_page_outside_fences(manual_root: Path) -> None:
    text = section_text() + "See section [6](06_x.md) and sections 2 and 3.\n```text\nsection 9 inside a fence\n```\nSee [Home Assistant](06_x.md).\n"
    findings = structure_findings(page_for("01_x.md", text, manual_root), {"wake word"}, palette_lines(PALETTE))
    assert [message.split(":")[0] for message in messages(findings)] == ["cross-reference by section number 'section [6](06_x.md)'", "cross-reference by section number 'sections 2'"]
    glossary = GLOSSARY.replace("A phrase.", "A phrase, see Section 5.")
    assert messages(structure_findings(page_for("glossary.md", glossary, manual_root), set(), palette_lines(PALETTE)))[0].startswith("cross-reference by section number 'Section 5'")


def test_introduction_uses_its_own_profile(manual_root: Path) -> None:
    text = "# Introduction\n\n## Purpose\n## How to read this manual\n## Key definitions\n## Software and hardware\n## The system map\n## Where the code lives\n## Before you run anything\n"
    assert structure_findings(page_for("index.md", text, manual_root), set(), palette_lines(PALETTE)) == []
    assert messages(structure_findings(page_for("index.md", text.replace("## Purpose\n", ""), manual_root), set(), palette_lines(PALETTE))) == ["missing heading '## Purpose'"]


def entry(title: str, marker: str) -> str:
    return f"## {title}\n{marker}\n\n### Where this fits\n{MAP_BLOCK}\n### Key definitions\n### Packages and tools\n### What changed\n### Run it yourself\n"


def test_current_changes_entries_need_a_title_shape_marker_and_unique_branch(manual_root: Path) -> None:
    good = entry("PR #7: Add x", '<!-- manual-entry branch="add-x" pr="7" date="2026-09-07" -->')
    text = "# Current Working Changes\n\nIntro.\n\n" + good + entry("Branch add-y: Add y", '<!-- manual-entry branch="add-y" pr="pending" date="2026-09-07" -->')
    assert structure_findings(page_for("current_changes.md", text, manual_root), set(), palette_lines(PALETTE)) == []
    bad = "# Current Working Changes\n\n" + entry("Add z", "no marker") + good + good.replace("### What changed\n", "")
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


def test_render_png_polishes_the_svg_and_screenshots_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shots: list[tuple[Path, Path, bool]] = []
    monkeypatch.setattr(render, "cached", lambda source: None)
    monkeypatch.setattr(render, "store", lambda source, svg: svg)
    monkeypatch.setattr(render, "render_svg", lambda *args: '<svg><rect class="basic label-container" rx="5" ry="5"/></svg>')
    monkeypatch.setattr(render, "screenshot", lambda svg_path, png_path, sandbox: shots.append((svg_path, png_path, sandbox)))
    render.render_png(Path("/bin/mmdc"), "a --> b\n", tmp_path, None, tmp_path / "page_12.png", sandbox=False)
    assert shots == [(tmp_path / "page_12.svg", tmp_path / "page_12.png", False)]
    assert 'rx="8" ry="8"' in (tmp_path / "page_12.svg").read_text(encoding="utf-8")


CLUSTER_TITLE_WIDTH = 80


def cluster(name: str, x: float, y: float, width: float, height: float, label_x: float, label_y: float) -> str:
    return (
        f'<g class="cluster" id="{name}" data-look="classic"><rect style="" x="{x}" y="{y}" width="{width}" height="{height}"/>'
        f'<g class="cluster-label" transform="translate({label_x}, {label_y})"><foreignObject width="{CLUSTER_TITLE_WIDTH}" height="21">'
        f'<div xmlns="http://www.w3.org/1999/xhtml" style="display: table-cell; white-space: nowrap; line-height: 1.5;"><span class="nodeLabel"><p>{name} title</p></span></div></foreignObject></g></g>'
    )


FRAME = '<svg style="max-width: 600px; background-color: white;" viewBox="4 4 600 400">'
EDGE = '<path d="M300,80L300,200" class="flowchart-link"/>'


def test_stacked_layers_become_full_width_bands_with_titles_in_a_left_gutter() -> None:
    svg = FRAME + cluster("top", 100, 0, 200, 80, 180, 8) + cluster("bottom", 20, 200, 500, 80, 250, 208) + EDGE
    banded = band_layers(svg)
    assert 'x="-192" y="29" width="712" height="51"' in banded and "translate(-176, 44)" in banded
    assert 'x="-192" y="229" width="712" height="51"' in banded and "translate(-176, 244)" in banded
    assert 'viewBox="-196 -4 800 408"' in banded and "max-width: 800px" in banded
    assert (
        '<foreignObject width="180" height="21" style="overflow: visible;"><div xmlns="http://www.w3.org/1999/xhtml" style="display: block; width: 180px; white-space: normal; overflow-wrap: anywhere;'
        in banded
    )


def test_the_gutter_clears_edges_and_labels_that_stick_out_to_the_left() -> None:
    label = '<g class="edgeLabel" transform="translate(-40, 100)"><g class="label" transform="translate(-30, -10)"><foreignObject width="60" height="20">'
    svg = FRAME + cluster("top", 100, 0, 200, 80, 180, 8) + cluster("bottom", 100, 200, 200, 80, 180, 208) + '<path d="M-20,80L-20,200" class="flowchart-link"/>' + label
    assert 'x="-282"' in band_layers(svg)


def test_side_by_side_layers_become_full_height_columns_with_titles_in_a_top_strip() -> None:
    svg = FRAME + cluster("left", 0, 100, 150, 200, 60, 108) + cluster("right", 300, 20, 150, 500, 360, 28)
    banded = band_layers(svg)
    assert 'x="0" y="-33" width="150" height="553"' in banded and "translate(16, -17)" in banded
    assert 'x="300" y="-33" width="150" height="553"' in banded and "translate(316, -17)" in banded
    assert 'viewBox="-4 -37 608 441"' in banded


def test_long_titles_wrap_to_the_gutter_width() -> None:
    title = Title("What Home Assistant calls: native services on the Mac", natural_width=360, natural_height=21)
    assert title.wrapped(180) == ["What Home Assistant calls:", "native services on the Mac"]
    assert title.wrapped_height(180) == 42


def test_overlapping_or_single_layers_are_left_alone() -> None:
    nested = FRAME + cluster("outer", 0, 0, 400, 400, 200, 8) + cluster("inner", 50, 50, 100, 100, 100, 58)
    assert band_layers(nested) == nested
    single = FRAME + cluster("only", 0, 0, 400, 400, 200, 8)
    assert band_layers(single) == single


def test_polish_rounds_node_and_container_corners() -> None:
    svg = '<g class="cluster" id="c" data-look="classic"><rect style="" x="0" y="0" width="1" height="1"/></g><rect class="basic label-container" rx="5" ry="5"/>'
    assert polish(svg, "flowchart TB\n") == round_corners(svg)
    assert '<rect rx="12" ry="12" style="" x="0"' in polish(svg, "") and 'rx="8" ry="8"' in polish(svg, "")


def test_polish_rounds_a_highlighted_container_and_keeps_its_stroke() -> None:
    highlight = "stroke:#f59e0b !important;stroke-width:4px !important"
    svg = cluster("haos", 0, 0, 100, 100, 10, 8).replace('style=""', f'style="{highlight}"')
    rounded = round_corners(svg)
    assert f'<rect rx="12" ry="12" style="{highlight}" x="0"' in rounded
    assert round_corners(rounded) == rounded


def edge_label(x: float, y: float, text: str) -> str:
    return (
        f'<g class="edgeLabel" transform="translate({x}, {y})"><g class="label" data-id="L_{text}_0" transform="translate(-20, -10)"><foreignObject width="40" height="20">'
        f'<div xmlns="http://www.w3.org/1999/xhtml" class="labelBkg" style="display: table-cell; white-space: nowrap;"><span class="edgeLabel"><p>{text}</p></span></div></foreignObject></g></g>'
    )


def test_an_edge_label_is_filled_with_the_colour_of_the_innermost_container_behind_it_or_the_page_outside_them() -> None:
    stylesheet = "<style>#d .cluster rect{fill:rgba(148, 163, 184, 0.07);stroke:#cbd5e1;}</style>"
    clusters = (
        cluster("outer", 0, 0, 400, 300, 20, 8) + cluster("inner", 50, 50, 200, 100, 70, 58) + cluster("marked", 300, 200, 80, 80, 310, 208).replace('style=""', 'style="fill:#fef3c7 !important"')
    )
    labels = edge_label(500, 20, "outside") + edge_label(20, 200, "outer") + edge_label(100, 100, "inner") + edge_label(340, 240, "marked")
    blended = blend_label_backgrounds(FRAME + stylesheet + clusters + labels)
    slate = "inset 0 0 0 999px rgba(148, 163, 184, 0.07)"
    for name, shadows in (("outside", ""), ("outer", f" box-shadow: {slate};"), ("inner", f" box-shadow: {slate}, {slate};"), ("marked", f" box-shadow: inset 0 0 0 999px #fef3c7, {slate};")):
        fill = f"background-color: #ffffff;{shadows}"
        assert f'white-space: nowrap; {fill}"><span class="edgeLabel" style="{fill}"><p style="{fill}">{name}</p>' in blended
    # Each label repaints, over white, the fills of every container behind it, topmost first: none outside, two stacked slate layers in the inner box, and a container's own fill on top of its parent's.


def test_screenshot_sizes_the_window_from_the_svg_and_passes_the_sandbox_flags(tmp_path: Path) -> None:
    svg = '<svg id="d" style="max-width: 640.5px; background-color: white;" viewBox="0 0 640.5 300"><g/></svg>'
    assert screenshot.natural_size(svg) == (642, 302)
    command = screenshot.chrome_command(Path("/chrome"), tmp_path / "d.html", tmp_path / "d.png", 642, 302, sandbox=False)
    assert command[0] == "/chrome" and "--window-size=642,302" in command and "--no-sandbox" in command and command[-1].startswith("file://")
    with pytest.raises(ValueError):
        screenshot.natural_size("<svg/>")


def test_hook_sizes_the_svg_to_the_column_but_never_below_seventy_percent() -> None:
    from manual_checks.mkdocs_hook import sized

    svg = '<svg id="d" style="max-width: 1000px; background-color: white;" viewBox="0 0 1000 300"><g/></svg>'
    assert sized(svg) == '<svg id="d" style="width: 100%; max-width: 1000px; min-width: 700px;" viewBox="0 0 1000 300"><g/></svg>'


def test_hook_replaces_each_mermaid_fence_with_a_figure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from manual_checks import mkdocs_hook

    monkeypatch.setattr(mkdocs_hook, "cached_svg", lambda source: f"<svg>{source.strip()}</svg>")
    page = "# T\n\n```mermaid\nflowchart TB\na --> b\n```\n\ntext\n"
    result = mkdocs_hook.on_page_markdown(page, mkdocs_page("t.md"), {"docs_dir": str(tmp_path)}, None)
    assert result == '# T\n\n<figure class="manual-diagram">\n<svg>flowchart TB\na --> b</svg>\n</figure>\n\ntext\n'


def test_hook_fails_the_build_at_the_page_line_of_a_diagram_that_will_not_render(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from manual_checks import mkdocs_hook

    def fail_on_second_diagram_line(source: str) -> str:
        raise mmdc.RenderFailed(RenderResult(False, "Parse error on line 2:", 2))

    monkeypatch.setattr(mkdocs_hook, "cached_svg", fail_on_second_diagram_line)
    page = "# T\n\ntext\n\n```mermaid\nflowchart TB\na -->\n```\n"
    with pytest.raises(PluginError, match=r"^guide/t\.md:7: Parse error on line 2:$"):
        mkdocs_hook.on_page_markdown(page, mkdocs_page("guide/t.md"), {"docs_dir": str(tmp_path)}, None)


def mkdocs_page(src_uri: str) -> SimpleNamespace:
    return SimpleNamespace(file=SimpleNamespace(src_uri=src_uri))


def grid_node(name: str, width: float, height: float) -> str:
    return (
        f'<g class="node default" id="d-flowchart-{name}-0" data-look="classic" transform="translate(0, 0)">'
        f'<rect class="basic label-container" style="" rx="8" ry="8" x="{-width / 2}" y="{-height / 2}" width="{width}" height="{height}"/></g>'
    )


def cylinder_node(name: str, radius: float, ry: float, body: float) -> str:
    path = f"M0,{ry} a{radius},{ry} 0,0,0 {2 * radius},0 a{radius},{ry} 0,0,0 {-2 * radius},0 l0,{body} a{radius},{ry} 0,0,0 {2 * radius},0 l0,{-body}"
    centring = f'transform="translate({-radius}, {-(body + 2 * ry) / 2})"'
    return f'<g class="node default" id="d-flowchart-{name}-0" data-look="classic" transform="translate(0, 0)">' f'<path d="{path}" class="basic label-container outer-path" style="" {centring}/></g>'


def diamond_node(name: str, width: float, height: float) -> str:
    points = f"{width / 2},0 {width},{-height / 2} {width / 2},{-height} 0,{-height / 2}"
    return (
        f'<g class="node default" id="d-flowchart-{name}-0" data-look="classic" transform="translate(0, 0)">'
        f'<polygon points="{points}" class="label-container" transform="translate({-width / 2}, {height / 2})"/></g>'
    )


def stadium_node(name: str, width: float, height: float) -> str:
    outline = f"M{-width / 2},{-height / 2} L{width / 2},{-height / 2} L{width / 2},{height / 2} L{-width / 2},{height / 2} Z"
    return (
        f'<g class="node default" id="d-flowchart-{name}-0" data-look="classic" transform="translate(0, 0)">'
        f'<g class="basic label-container outer-path"><path d="{outline}" stroke="none"/><path d="{outline}" fill="none"/></g></g>'
    )


def grid_edge(source: str, target: str) -> str:
    return f'<path d="M0,0L1,1" id="d-L_{source}_{target}_0" class="flowchart-link" marker-end="url(#end)"/>'


def grid_label(source: str, target: str, width: float, height: float) -> str:
    return (
        f'<g class="edgeLabel" transform="translate(0, 0)"><g class="label" data-id="L_{source}_{target}_0" transform="translate({-width / 2}, {-height / 2})">'
        f'<foreignObject width="{width}" height="{height}"></foreignObject></g></g>'
    )


def narrow_titled_cluster(name: str, title_width: float) -> str:
    return cluster(name, 0, 0, 10, 10, 0, 0).replace(f'<foreignObject width="{CLUSTER_TITLE_WIDTH}"', f'<foreignObject width="{title_width}"')
    # The grid lays a container out from the cells of its members, so of the cluster Mermaid drew only its title's width matters.


def transforms(svg: str) -> dict[str, tuple[float, float]]:
    return {match["name"]: (float(match["x"]), float(match["y"])) for match in NODE_TRANSFORM.finditer(svg)}


def drawn_paths(svg: str) -> dict[str, list[tuple[float, float]]]:
    return {match["link"]: [tuple(float(number) for number in point.split(",")) for point in match["d"].lstrip("M").split("L")] for match in EDGE_PATH.finditer(svg)}


PLAIN_SOURCE = 'flowchart TB\n%% grid: a  .\n%% grid: b  c\n%% a note that is not a grid line\na("a")\nb("b")\nc("c")\na --> b\nb --> c\n'
PLAIN_SVG = FRAME + grid_node("a", 100, 40) + grid_node("b", 60, 40) + grid_node("c", 80, 60) + grid_edge("a", "b") + grid_edge("b", "c")


def test_grid_rows_read_the_cells_of_every_grid_comment_and_nothing_else() -> None:
    assert grid_rows(PLAIN_SOURCE) == [["a", "."], ["b", "c"]]
    assert grid_rows("flowchart TB\na --> b\n") == []


def test_split_link_finds_the_two_node_ids_however_many_underscores_they_hold() -> None:
    assert split_link("web_search_searxng", {"web_search", "searxng"}) == ("web_search", "searxng")
    assert split_link("a_b", {"c"}) is None


def test_containers_hold_everything_declared_inside_them_and_name_their_own_children() -> None:
    source = 'subgraph outer["O"]\n  a("a")\n  subgraph inner["I"]\n    b("b")\n  end\nend\n'
    inner, outer = containers_of(source)
    assert (inner.id, inner.members, inner.children) == ("inner", frozenset({"b"}), ())
    assert (outer.id, outer.members, outer.children) == ("outer", frozenset({"a", "b"}), ("inner",))


def test_each_box_is_centred_in_a_cell_as_wide_as_its_widest_box_and_as_tall_as_its_tallest() -> None:
    laid_out = lay_out_on_grid(PLAIN_SVG, PLAIN_SOURCE)
    assert transforms(laid_out) == {"a": (74, 44), "b": (74, 158), "c": (240, 158)}
    assert 'viewBox="0 0 304 212"' in laid_out and "max-width: 304px" in laid_out


def test_a_cylinder_and_a_diamond_drawn_from_a_corner_are_still_centred_in_their_cells() -> None:
    source = 'flowchart TB\n%% grid: a\n%% grid: b\n%% grid: c\na("a")\nb[("b")]\nc{"c"}\na --> b\nb --> c\n'
    svg = FRAME + grid_node("a", 100, 40) + cylinder_node("b", 30, 10, 50) + diamond_node("c", 80, 80) + grid_edge("a", "b") + grid_edge("b", "c")
    laid_out = lay_out_on_grid(svg, source)
    assert transforms(laid_out) == {"a": (74, 44), "b": (74, 163), "c": (74, 302)}
    assert drawn_paths(laid_out)["a_b"] == [(74, 64), (74, 124)]
    assert drawn_paths(laid_out)["b_c"] == [(74, 198), (74, 258)]


def test_an_edge_leaving_a_diamond_at_an_offset_starts_on_its_sloped_outline() -> None:
    source = 'flowchart TB\n%% grid: d  .\n%% grid: .  t\nd{"d"}\nt("t")\nd --> t\n'
    svg = FRAME + diamond_node("d", 80, 80) + grid_node("t", 60, 40) + grid_edge("d", "t")
    assert drawn_paths(lay_out_on_grid(svg, source))["d_t"] == [(84, 84), (84, 136), (195, 136), (195, 164)]
    # The diamond is centred at (64, 64) with half-width 40, so its outline at the offset x of 84 sits at y 84, not at the bounding box's bottom of 104.


def test_edges_between_neighbouring_cells_are_one_straight_line_each() -> None:
    paths = drawn_paths(lay_out_on_grid(PLAIN_SVG, PLAIN_SOURCE))
    assert paths["a_b"] == [(74, 64), (74, 134)]
    assert paths["b_c"] == [(104, 158), (196, 158)]


def test_a_wide_edge_label_widens_the_gap_it_sits_in_and_lands_in_the_middle_of_it() -> None:
    svg = PLAIN_SVG + grid_label("b", "c", 120, 20)
    laid_out = lay_out_on_grid(svg, PLAIN_SOURCE)
    assert transforms(laid_out)["c"] == (312, 158)
    assert '<g class="edgeLabel" transform="translate(186, 158)' in laid_out


def test_an_edge_whose_target_column_is_blocked_takes_the_channel_beside_that_column() -> None:
    source = 'flowchart TB\n%% grid: a  b\n%% grid: e  c\n%% grid: d  .\na("a")\nb("b")\nc("c")\nd("d")\ne("e")\nb --> d\n'
    svg = FRAME + "".join(grid_node(name, 60, 40) for name in ("a", "b", "c", "d", "e")) + grid_edge("b", "d")
    points = drawn_paths(lay_out_on_grid(svg, source))["b_d"]
    assert points == [(175, 64), (175, 96), (122, 96), (122, 200), (69, 200), (69, 228)]
    assert all(first[0] == second[0] or first[1] == second[1] for first, second in zip(points, points[1:]))


def test_a_leftward_edge_across_empty_cells_is_one_straight_line() -> None:
    source = 'flowchart TB\n%% grid: t  .  s\n%% grid: .  m  .\nt("t")\ns("s")\nm("m")\ns --> t\n'
    svg = FRAME + grid_node("t", 60, 40) + grid_node("s", 60, 40) + grid_node("m", 60, 40) + grid_edge("s", "t")
    assert drawn_paths(lay_out_on_grid(svg, source))["s_t"] == [(296, 44), (88, 44)]
    blocked = drawn_paths(lay_out_on_grid(svg, source.replace("t  .  s\n%% grid: .  m  .", "t  m  s")))["s_t"]
    assert blocked == [(311, 64), (311, 76), (69, 76), (69, 68)]
    # With m in the cell between, the line would cross a box, so it drops into the gutter below the row instead.


def test_two_neighbours_sending_each_other_something_get_two_lines_forty_pixels_apart() -> None:
    source = 'flowchart TB\n%% grid: a  b\na("a")\nb("b")\na --> b\nb -.-> a\n'
    svg = FRAME + grid_node("a", 60, 60) + grid_node("b", 60, 60) + grid_edge("a", "b") + grid_edge("b", "a")
    paths = drawn_paths(lay_out_on_grid(svg, source))
    assert paths == {"a_b": [(84, 34), (156, 34)], "b_a": [(160, 74), (88, 74)]}
    # Both boxes are centred at y 54: a to b, written first, runs 20 px above that line and b to a 20 px below it.


def test_the_edge_of_a_pair_written_first_runs_above_the_centre_line_whichever_way_it_points() -> None:
    source = 'flowchart TB\n%% grid: a  b\na("a")\nb("b")\nb --> a\na --> b\n'
    svg = FRAME + grid_node("a", 60, 60) + grid_node("b", 60, 60) + grid_edge("b", "a") + grid_edge("a", "b")
    paths = drawn_paths(lay_out_on_grid(svg, source))
    assert paths == {"b_a": [(160, 34), (88, 34)], "a_b": [(84, 74), (156, 74)]}
    # A side box on the left of a column gets its request, the leftward edge, above its reply, as a box on the right does.


def test_the_edge_of_a_vertical_pair_written_first_runs_left_of_the_centre_line_whichever_way_it_points() -> None:
    source = 'flowchart TB\n%% grid: a\n%% grid: b\na("a")\nb("b")\nb --> a\na --> b\n'
    svg = FRAME + grid_node("a", 160, 40) + grid_node("b", 160, 40) + grid_edge("b", "a") + grid_edge("a", "b")
    assert drawn_paths(lay_out_on_grid(svg, source)) == {"b_a": [(84, 128), (84, 68)], "a_b": [(124, 64), (124, 124)]}
    # Both boxes are centred at x 104: the upward edge, written first, takes the left line 20 px from centre.


def test_a_box_and_the_box_below_it_sending_each_other_something_get_two_lines_with_each_label_outside_its_own() -> None:
    source = 'flowchart TB\n%% grid: a\n%% grid: b\na("a")\nb("b")\na --> b\nb --> a\n'
    svg = FRAME + grid_node("a", 160, 40) + grid_node("b", 160, 40) + grid_edge("a", "b") + grid_edge("b", "a") + grid_label("a", "b", 40, 20) + grid_label("b", "a", 40, 20)
    laid_out = lay_out_on_grid(svg, source)
    assert drawn_paths(laid_out) == {"a_b": [(84, 64), (84, 124)], "b_a": [(124, 128), (124, 68)]}
    assert '<g class="edgeLabel" transform="translate(50, 94)' in laid_out and '<g class="edgeLabel" transform="translate(158, 94)' in laid_out
    # Both boxes are centred at x 104: the downward edge runs 20 px left of that line with its label ending 14 px left of it, the upward edge 20 px right with its label starting 14 px right of it, and the two labels sit level.


def test_a_column_gap_line_sets_the_least_gap_between_columns_and_a_wider_label_still_widens_it() -> None:
    source = PLAIN_SOURCE.replace("%% a note", "%% column-gap: 150\n%% a note")
    assert transforms(lay_out_on_grid(PLAIN_SVG, source))["c"] == (314, 158)
    assert transforms(lay_out_on_grid(PLAIN_SVG + grid_label("b", "c", 200, 20), source))["c"] == (392, 158)
    assert transforms(lay_out_on_grid(PLAIN_SVG, PLAIN_SOURCE.replace("%% a note", "%% column-gap: 30\n%% a note")))["c"] == (240, 158)
    # Without the line c sits at x 240 across the default 76 px gap; 150 px moves it 74 px right, a 200 px label needs 228 px, and a value below the default leaves the default in place.


def test_a_result_returning_to_an_earlier_row_leaves_and_enters_by_the_right_side_with_its_label_on_the_last_leg() -> None:
    source = 'flowchart TB\n%% grid: a  .\n%% grid: c  .\n%% grid: .  b\na("a")\nb("b")\nc("c")\nb --> a\n'
    svg = FRAME + grid_node("a", 60, 40) + grid_node("b", 80, 40) + grid_node("c", 60, 40) + grid_edge("b", "a") + grid_label("b", "a", 40, 20)
    laid_out = lay_out_on_grid(svg, source)
    assert transforms(laid_out) == {"a": (54, 44), "b": (200, 252), "c": (54, 148)}
    assert drawn_paths(laid_out)["b_a"] == [(240, 252), (278, 252), (278, 44), (88, 44)]
    assert '<g class="edgeLabel" transform="translate(183, 44)' in laid_out
    # b's right side is x 240 and a's is x 84; the channel sits half a column gap (38 px) past b's column, and the label is centred on the leg into a.


def test_an_edge_label_slides_along_its_line_off_a_container_border() -> None:
    source = 'flowchart TB\n%% grid: a\n%% grid: b\nsubgraph box["box title"]\n  b("b")\nend\na("a")\nb("b")\na --> b\n'
    svg = FRAME + cluster("box", 0, 0, 10, 10, 0, 0) + grid_node("a", 60, 40) + grid_node("b", 60, 40) + grid_edge("a", "b") + grid_label("a", "b", 40, 20)
    laid_out = lay_out_on_grid(svg, source)
    assert drawn_paths(laid_out)["a_b"] == [(80, 64), (80, 187)]
    assert 'y="128"' in laid_out and '<g class="edgeLabel" transform="translate(80, 107.05)' in laid_out
    # The middle of the line (y 125.5) is on the container's top border at y 128, so the label moves up to 35% of the way along; the column is 76 px wide to fit the 80 px title.


def test_an_edge_label_stays_off_another_edge_crossing_its_line() -> None:
    source = 'flowchart TB\n%% grid: .  x  .\n%% grid: a  .  b\n%% grid: .  y  .\na("a")\nb("b")\nx("x")\ny("y")\na --> b\nx --> y\n'
    svg = FRAME + "".join(grid_node(name, 60, 40) for name in "abxy") + grid_edge("a", "b") + grid_edge("x", "y") + grid_label("a", "b", 40, 20)
    laid_out = lay_out_on_grid(svg, source)
    assert drawn_paths(laid_out) == {"a_b": [(84, 148), (292, 148)], "x_y": [(190, 64), (190, 228)]}
    assert '<g class="edgeLabel" transform="translate(156.8, 148)' in laid_out
    # The middle of a to b (x 188) is where x to y crosses it at x 190, so the label slides left to 35% of the way along.


GROUP_SOURCE = 'flowchart TB\n%% grid: x  o  y\n%% grid: .  a+b  .\nx("x")\no("o")\ny("y")\na("a")\nb("b")\no --> a\no --> b\n'
GROUP_SVG = FRAME + "".join(grid_node(name, 60, 40) for name in "xoyab") + grid_edge("o", "a") + grid_edge("o", "b") + grid_label("o", "a", 40, 20) + grid_label("o", "b", 40, 20)


def test_a_group_stands_side_by_side_under_the_box_above_without_widening_its_column() -> None:
    laid_out = lay_out_on_grid(GROUP_SVG, GROUP_SOURCE)
    assert transforms(laid_out) == {"x": (54, 44), "o": (190, 44), "y": (326, 44), "a": (144, 148), "b": (236, 148)}
    assert 'viewBox="0 0 380 192"' in laid_out
    # The row above keeps the spacing of 60 px columns; the pair, 60 + 32 + 60 px wide, is centred on o at x 190 and reaches into the empty cells beside it.


def test_two_straight_legs_from_one_box_drop_to_the_two_members_of_a_group() -> None:
    assert drawn_paths(lay_out_on_grid(GROUP_SVG, GROUP_SOURCE)) == {"o_a": [(167, 64), (167, 124)], "o_b": [(213, 64), (213, 124)]}
    # Each leg drops through the middle of the stretch o shares with its member: o spans x 160 to 220, a 114 to 174, b 206 to 266.


def test_the_labels_of_two_straight_legs_sit_outside_the_pair() -> None:
    laid_out = lay_out_on_grid(GROUP_SVG, GROUP_SOURCE)
    assert '<g class="edgeLabel" transform="translate(133, 94)' in laid_out and '<g class="edgeLabel" transform="translate(247, 94)' in laid_out
    # The 40 px labels end at x 153, left of the leg at 167, and start at x 227, right of the leg at 213.


def test_several_edges_from_one_box_into_the_row_below_leave_from_its_centre_share_one_bus_and_land_centred() -> None:
    source = 'flowchart TB\n%% grid: p  .  q\n%% grid: .  o  .\n%% grid: a  b  c\np("p")\nq("q")\no("o")\na("a")\nb("b")\nc("c")\np --> o\nq --> o\no --> a\no --> b\no --> c\n'
    svg = FRAME + "".join(grid_node(name, 60, 40) for name in "pqoabc") + "".join(grid_edge(start, end) for start, end in ("po", "qo", "oa", "ob", "oc"))
    paths = drawn_paths(lay_out_on_grid(svg, source))
    assert paths["o_a"] == [(190, 168), (190, 200), (54, 200), (54, 228)]
    assert paths["o_b"] == [(190, 168), (190, 228)]
    assert paths["o_c"] == [(190, 168), (190, 200), (326, 200), (326, 228)]
    assert paths["p_o"][-1] == (175, 124) and paths["q_o"][-1] == (205, 124)
    # o is centred at x 190: its three legs leave that point, run along one line at y 200, and drop into the centres of a and c (x 54 and 326), while the two edges arriving from above still land a quarter of o's width apart.


def test_several_edges_from_one_box_into_the_row_above_share_one_bus_rising_into_the_centre_of_each_target() -> None:
    source = 'flowchart TB\n%% grid: a  b  c\n%% grid: .  o  .\na("a")\nb("b")\nc("c")\no("o")\no --> a\no --> b\no --> c\n'
    svg = FRAME + "".join(grid_node(name, 60, 40) for name in "abco") + "".join(grid_edge("o", target) for target in "abc")
    paths = drawn_paths(lay_out_on_grid(svg, source))
    assert paths["o_a"] == [(190, 128), (190, 96), (54, 96), (54, 68)]
    assert paths["o_b"] == [(190, 128), (190, 68)]
    assert paths["o_c"] == [(190, 128), (190, 96), (326, 96), (326, 68)]
    # o's top is at y 128 and the row above ends at 64: the legs leave o's centre, share one line in the middle of that gutter, and rise into the centres of a and c, their arrowheads 4 px below them.


def test_a_bus_leg_into_the_row_above_never_returns_by_the_right() -> None:
    source = 'flowchart TB\n%% grid: a  b  .\n%% grid: .  .  o\na("a")\nb("b")\no("o")\no --> a\no --> b\n'
    svg = FRAME + "".join(grid_node(name, 60, 40) for name in "abo") + "".join(grid_edge("o", target) for target in "ab")
    paths = drawn_paths(lay_out_on_grid(svg, source))
    assert paths["o_b"] == [(326, 128), (326, 96), (190, 96), (190, 68)]
    assert paths["o_a"] == [(326, 128), (326, 96), (54, 96), (54, 68)]
    # Alone, o to b would loop out of o's right side and into b's; as a leg of o's bus it shares the trunk with o to a.


def test_a_labelled_edge_keeps_its_own_line_out_of_a_bus() -> None:
    source = 'flowchart TB\n%% grid: .  o  .\n%% grid: a  b  c\no("o")\na("a")\nb("b")\nc("c")\no --> a\no --> b\no --> c\n'
    svg = FRAME + "".join(grid_node(name, 60, 40) for name in "oabc") + "".join(grid_edge("o", target) for target in "abc") + grid_label("o", "a", 40, 20)
    paths = drawn_paths(lay_out_on_grid(svg, source))
    assert paths["o_a"][0][0] == paths["o_b"][0][0] - 15
    assert paths["o_c"][0][0] == paths["o_b"][0][0]
    # The labelled leg to a leaves a quarter of o's 60 px width left of centre, so its label cannot be read as belonging to the trunk the unlabelled legs share.


SPANNING_SOURCE = 'flowchart TB\n%% grid: .  h  h  .\n%% grid: a  b  c  d\nh("h")\na("a")\nb("b")\nc("c")\nd("d")\nh -- "x" --> a\nd -- "y" --> h\n'
SPANNING_SVG = FRAME + "".join(grid_node(name, 60, 40) for name in "habcd") + grid_edge("h", "a") + grid_edge("d", "h") + grid_label("h", "a", 40, 20) + grid_label("d", "h", 40, 20)


def test_a_box_written_in_two_neighbouring_cells_is_centred_over_them_without_widening_either_column() -> None:
    assert transforms(lay_out_on_grid(SPANNING_SVG, SPANNING_SOURCE)) == {"h": (258, 44), "a": (54, 164), "b": (190, 164), "c": (326, 164), "d": (462, 164)}
    # h sits midway between b and c (x 190 and 326), and the columns keep the 60 px of the boxes below it.


def test_a_spanning_box_labelled_edges_cross_half_a_row_gap_from_it_and_land_in_the_centre_of_the_other_box() -> None:
    laid_out = lay_out_on_grid(SPANNING_SVG, SPANNING_SOURCE)
    paths = drawn_paths(laid_out)
    assert paths["h_a"] == [(243, 64), (243, 96), (54, 96), (54, 140)]
    assert paths["d_h"] == [(462, 144), (462, 96), (273, 96), (273, 68)]
    assert '<g class="edgeLabel" transform="translate(88, 118)' in laid_out and '<g class="edgeLabel" transform="translate(496, 116)' in laid_out
    # The row gap grows from 64 px to 80 so the 20 px labels fit beside the legs into a and out of d, right of each line, below the run 32 px under h; h's own ends stay a quarter of its width either side of its centre, and d's edge never returns by the right.


def test_a_box_tucked_under_a_box_it_has_no_edge_with_is_entered_and_left_by_its_side() -> None:
    source = 'flowchart TB\n%% grid: a  b  c\n%% grid: .  t  .\na("a")\nb("b")\nc("c")\nt("t")\na -- "x" --> t\nt -- "y" --> c\n'
    svg = FRAME + "".join(grid_node(name, 60, 40) for name in "abct") + grid_edge("a", "t") + grid_edge("t", "c") + grid_label("a", "t", 40, 20) + grid_label("t", "c", 40, 20)
    laid_out = lay_out_on_grid(svg, source)
    paths = drawn_paths(laid_out)
    assert paths["a_t"] == [(54, 64), (54, 148), (156, 148)]
    assert paths["t_c"] == [(220, 148), (326, 148), (326, 68)]
    assert '<g class="edgeLabel" transform="translate(88, 106)' in laid_out and '<g class="edgeLabel" transform="translate(360, 104)' in laid_out
    # t hangs under b with no edge between them, so no line touches t's top: a's edge drops down a's centre into t's left side, t's edge leaves its right side and rises into c's centre, each label right of its vertical line.


def test_a_box_under_the_box_that_feeds_it_keeps_the_staircase() -> None:
    source = 'flowchart TB\n%% grid: a  b  c\n%% grid: .  t  .\na("a")\nb("b")\nc("c")\nt("t")\na -- "x" --> t\nb --> t\nt -- "y" --> c\n'
    svg = (
        FRAME + "".join(grid_node(name, 60, 40) for name in "abct") + "".join(grid_edge(start, end) for start, end in ("at", "bt", "tc")) + grid_label("a", "t", 40, 20) + grid_label("t", "c", 40, 20)
    )
    paths = drawn_paths(lay_out_on_grid(svg, source))
    assert paths["a_t"] == [(69, 64), (69, 96), (175, 96), (175, 124)]
    assert paths["t_c"] == [(205, 128), (205, 96), (311, 96), (311, 68)]


def test_an_outcome_that_only_receives_from_the_row_above_keeps_the_staircase() -> None:
    source = 'flowchart TB\n%% grid: a  b  c\n%% grid: .  t  .\na("a")\nb("b")\nc("c")\nt("t")\na -- "x" --> t\nc -- "y" --> t\n'
    svg = FRAME + "".join(grid_node(name, 60, 40) for name in "abct") + grid_edge("a", "t") + grid_edge("c", "t") + grid_label("a", "t", 20, 20) + grid_label("c", "t", 20, 20)
    paths = drawn_paths(lay_out_on_grid(svg, source))
    assert paths["a_t"][-1] == (175, 124) and paths["c_t"][-1] == (205, 124)
    # t hangs under b but hands nothing back to the row above, so it is an outcome, not a detour: both edges still enter its top.


CROWDED_SOURCE = 'flowchart TB\n%% grid: r  .  m\n%% grid: s  c  a\nr("r")\nm("m")\ns("s")\nc("c")\na("a")\nr -- "x" --> s\nr -- "y" --> c\nm --> s\nm --> c\nm --> a\n'
CROWDED_SVG = (
    FRAME
    + "".join(grid_node(name, 60, 40) for name in "rmsca")
    + "".join(grid_edge(start, end) for start, end in ("rs", "rc", "ms", "mc", "ma"))
    + grid_label("r", "s", 40, 20)
    + grid_label("r", "c", 40, 20)
)


def test_a_bus_sharing_its_gutter_with_another_edge_splits_into_runs_on_levels_of_their_own_crossing_once() -> None:
    paths = drawn_paths(lay_out_on_grid(CROWDED_SVG, CROWDED_SOURCE))
    assert paths["m_s"] == [(306, 64), (306, 112), (74, 112), (74, 180)]
    assert paths["r_c"] == [(64, 64), (64, 132), (175, 132), (175, 180)]
    assert paths["m_c"] == [(316, 64), (316, 152), (205, 152), (205, 180)]
    assert paths["r_s"] == [(54, 64), (54, 180)] and paths["m_a"] == [(326, 64), (326, 180)]
    assert crossings(list(paths.values())) == 1
    # As a bus, m to s would run along r to c at one height and land on r to s's straight line into the centre of s. Instead each run has a level: m to s, reaching furthest, runs highest and lands right of s's centre, facing m.
    # m's legs leave side by side, the furthest-reaching outermost, so they nest without crossing; r to c crosses m to s once, the crossing {r, m} x {s, c} cannot avoid, and no two edges share a stretch of line.


def test_a_crowded_gutter_grows_to_hold_a_label_band_and_one_level_per_run() -> None:
    assert transforms(lay_out_on_grid(CROWDED_SVG, CROWDED_SOURCE))["s"] == (54, 204)
    # r ends at y 64 and s starts at 184: 48 px for the 20 px labels and their clearance, two 20 px steps between the three levels, and 32 px below the lowest.


def test_the_labels_of_legs_into_a_crowded_gutter_sit_outside_the_pair_and_above_its_levels() -> None:
    laid_out = lay_out_on_grid(CROWDED_SVG, CROWDED_SOURCE)
    assert '<g class="edgeLabel" transform="translate(20, 88)' in laid_out and '<g class="edgeLabel" transform="translate(98, 88)' in laid_out
    # The straight leg at x 54 has its label on the left and the staircase leaving at x 64 on the right, both centred between r's bottom (y 64) and the highest level (y 112).


FAN_IN_SOURCE = 'flowchart TB\n%% grid: a  b  c\n%% grid: .  t  .\na("a")\nb("b")\nc("c")\nt("t")\na -- "x" --> t\nb -- "y" --> t\nc -- "z" --> t\n'
FAN_IN_SVG = FRAME + "".join(grid_node(name, 60, 40) for name in "abct") + "".join(grid_edge(source, "t") for source in "abc") + "".join(grid_label(source, "t", 40, 20) for source in "abc")


def test_labelled_edges_converging_on_one_box_turn_on_one_level_below_a_label_band() -> None:
    laid_out = lay_out_on_grid(FAN_IN_SVG, FAN_IN_SOURCE)
    paths = drawn_paths(laid_out)
    assert paths["a_t"] == [(69, 64), (69, 112), (175, 112), (175, 140)]
    assert paths["b_t"] == [(190, 64), (190, 140)]
    assert paths["c_t"] == [(311, 64), (311, 112), (205, 112), (205, 140)]
    assert transforms(laid_out)["t"] == (190, 164)
    # The row gap grows from 64 px to 80: 48 px for the 20 px labels and their clearance above the shared level at y 112, and 32 px below it; a and c land a quarter of t's width either side of b's straight drop.


def test_the_labels_of_converging_edges_sit_right_of_their_own_lines_above_the_turn() -> None:
    laid_out = lay_out_on_grid(FAN_IN_SVG, FAN_IN_SOURCE)
    for center_x in (103, 224, 345):
        assert f'<g class="edgeLabel" transform="translate({center_x}, 88)' in laid_out
    # Each 40 px label starts 14 px right of its line (x 69, 190, 311) and is centred between the boxes' bottom (y 64) and the level (y 112), so no label sits on the level another line runs along.


def test_converging_edges_whose_labels_fit_on_their_own_lines_keep_the_plain_gutter() -> None:
    source = 'flowchart TB\n%% grid: a  .  c\n%% grid: .  t  .\na("a")\nc("c")\nt("t")\na -- "x" --> t\nc -- "z" --> t\n'
    svg = FRAME + "".join(grid_node(name, 60, 40) for name in "act") + "".join(grid_edge(source, "t") for source in "ac") + "".join(grid_label(source, "t", 20, 20) for source in "ac")
    laid_out = lay_out_on_grid(svg, source)
    assert drawn_paths(laid_out)["a_t"] == [(69, 64), (69, 96), (175, 96), (175, 124)]
    assert transforms(laid_out)["t"] == (190, 148)
    assert '<g class="edgeLabel" transform="translate(122, 96)' in laid_out and '<g class="edgeLabel" transform="translate(258, 96)' in laid_out
    # With an empty column between the two sources each short label finds room on its own turn, so the gutter keeps its 64 px and the labels stay on their lines.


GRID_CONTAINER_SOURCE = 'flowchart TB\n%% grid: a  b\n%% grid: .  c\nsubgraph box["box title"]\n  b("b")\n  c("c")\nend\na --> b\nb --> c\n'
GRID_CONTAINER_SVG = FRAME + narrow_titled_cluster("box", 40) + grid_node("a", 60, 40) + grid_node("b", 60, 40) + grid_node("c", 60, 40) + grid_edge("a", "b") + grid_edge("b", "c")


def test_a_container_wraps_the_cells_of_everything_inside_it_with_its_title_in_a_strip_above_them() -> None:
    laid_out = lay_out_on_grid(GRID_CONTAINER_SVG, GRID_CONTAINER_SOURCE)
    assert 'x="160" y="24" width="96" height="225"' in laid_out and "translate(176, 36)" in laid_out
    assert transforms(laid_out) == {"a": (54, 107), "b": (208, 107), "c": (208, 211)}
    # The 40 px title is narrower than the 60 px boxes, so the container is as wide as their column and its padding.


def test_a_one_column_container_widens_its_column_until_its_title_fits_on_one_line() -> None:
    source = 'flowchart TB\n%% grid: a\nsubgraph box["box title"]\n  a("a")\nend\n'
    laid_out = lay_out_on_grid(FRAME + cluster("box", 0, 0, 10, 10, 0, 0) + grid_node("a", 60, 40), source)
    assert drawn_rects(laid_out)["box"][2] == CLUSTER_TITLE_WIDTH + 2 * TITLE_INSET
    assert drawn_shapes(laid_out)["a"].width == 60
    # The 60 px box alone would make the container 96 px wide and wrap the 80 px title; the column grows instead, and the box keeps its own width.


def test_an_edge_from_a_box_in_no_container_runs_down_and_into_the_side_of_a_target_inside_one() -> None:
    source = 'flowchart TB\n%% grid: s  .\n%% grid: .  t\nsubgraph away["A"]\n  t("t")\nend\ns("s")\nt("t")\ns --> t\n'
    laid_out = lay_out_on_grid(FRAME + narrow_titled_cluster("away", 20) + grid_node("s", 60, 40) + grid_node("t", 60, 40) + grid_edge("s", "t"), source)
    (leave_x, leave_y), (corner_x, corner_y), (end_x, end_y) = drawn_paths(laid_out)["s_t"]
    target_x, target_y = transforms(laid_out)["t"]
    assert leave_x == corner_x and leave_y < corner_y
    assert corner_y == end_y == target_y and end_x == target_x - 30 - ARROW_GAP
    # The edge crosses the container's left border once, as a sketch draws it, instead of a staircase dropping through the title strip into t's top.


def test_a_container_title_slides_right_past_an_edge_dropping_into_its_top_row() -> None:
    source = 'flowchart TB\n%% grid: a  .\n%% grid: b  c\nsubgraph box["box title"]\n  b("b")\n  c("c")\nend\na("a")\nb("b")\nc("c")\na --> b\nb --> c\n'
    svg = FRAME + cluster("box", 0, 0, 10, 10, 0, 0) + grid_node("a", 60, 40) + grid_node("b", 60, 40) + grid_node("c", 60, 40) + grid_edge("a", "b") + grid_edge("b", "c")
    laid_out = lay_out_on_grid(svg, source)
    assert drawn_paths(laid_out)["a_b"] == [(72, 64), (72, 187)]
    assert "translate(86, 140)" in laid_out
    # The edge into b crosses the title strip at x 72, so the title moves from the container's left inset (x 40) to just right of the crossing.


def test_no_edge_enters_a_container_title_strip() -> None:
    laid_out = lay_out_on_grid(GRID_CONTAINER_SVG, GRID_CONTAINER_SOURCE)
    strip = (160, 24, 160 + 96, 24 + 45)
    points = [point for path in drawn_paths(laid_out).values() for point in path]
    assert points and not any(strip[0] <= x <= strip[2] and strip[1] <= y <= strip[3] for x, y in points)


CLUSTER_RECT_DRAWN = re.compile(r'<g class="cluster" id="(?P<id>\w+)"[^>]*><rect[^>]*x="(?P<x>[\d.\-]+)" y="(?P<y>[\d.\-]+)" width="(?P<width>[\d.]+)" height="(?P<height>[\d.]+)"')
MACHINES_SOURCE = 'flowchart TB\n%% grid: s  .\n%% grid: {corner}  t\nsubgraph home["H"]\n  s("s")\nend\nsubgraph away["A"]\n  t("t")\nend\ns --> t\n'
MACHINES_SVG = FRAME + cluster("home", 0, 0, 100, 100, 10, 8) + cluster("away", 200, 0, 100, 100, 210, 8) + grid_node("s", 60, 40) + grid_node("t", 60, 40) + grid_edge("s", "t")


def drawn_rects(svg: str) -> dict[str, tuple[float, float, float, float]]:
    return {match["id"]: (float(match["x"]), float(match["y"]), float(match["width"]), float(match["height"])) for match in CLUSTER_RECT_DRAWN.finditer(svg)}


def test_an_empty_cell_naming_a_container_stays_empty_but_the_container_reaches_over_it() -> None:
    reaching, plain = lay_out_on_grid(MACHINES_SVG, MACHINES_SOURCE.format(corner=".home")), lay_out_on_grid(MACHINES_SVG, MACHINES_SOURCE.format(corner="."))
    assert set(transforms(reaching)) == {"s", "t"}
    assert drawn_rects(reaching)["home"][1] + drawn_rects(reaching)["home"][3] == drawn_rects(reaching)["away"][1] + drawn_rects(reaching)["away"][3]
    assert drawn_rects(plain)["home"][1] + drawn_rects(plain)["home"][3] < drawn_rects(plain)["away"][1] + drawn_rects(plain)["away"][3]


def test_an_edge_run_inside_its_container_leaves_by_the_side_and_enters_the_target_side_on() -> None:
    laid_out = lay_out_on_grid(MACHINES_SVG, MACHINES_SOURCE.format(corner=".home"))
    (leave_x, leave_y), (corner_x, corner_y), (end_x, end_y) = drawn_paths(laid_out)["s_t"]
    target_x, target_y = transforms(laid_out)["t"]
    assert leave_x == corner_x and leave_y < corner_y
    assert corner_y == end_y == target_y and end_x == target_x - 30 - ARROW_GAP


def test_an_edge_dropping_out_of_its_container_bottom_keeps_the_staircase_into_the_target_top() -> None:
    laid_out = lay_out_on_grid(MACHINES_SVG, MACHINES_SOURCE.format(corner="."))
    points = drawn_paths(laid_out)["s_t"]
    assert len(points) == 4 and points[-1][1] < transforms(laid_out)["t"][1]


def test_top_level_containers_in_one_row_share_top_and_bottom_edges_when_one_holds_a_nested_container() -> None:
    source = 'flowchart TB\n%% grid: a  b  c\nsubgraph left["L"]\n  a("a")\n  subgraph inner["I"]\n    b("b")\n  end\nend\nsubgraph right["R"]\n  c("c")\nend\n'
    svg = FRAME + cluster("left", 0, 0, 100, 100, 10, 8) + cluster("inner", 0, 0, 50, 50, 10, 8) + cluster("right", 200, 0, 100, 100, 210, 8) + "".join(grid_node(name, 60, 40) for name in "abc")
    rects = drawn_rects(lay_out_on_grid(svg, source))
    assert rects["left"][1] == rects["right"][1] < rects["inner"][1]
    assert rects["left"][1] + rects["left"][3] == rects["right"][1] + rects["right"][3] > rects["inner"][1] + rects["inner"][3]


def test_containers_side_by_side_share_the_room_above_and_between_them_instead_of_stacking_it() -> None:
    source = "flowchart TB\n%% grid: a  b\n%% grid: c  d\n" + "".join(f'subgraph {name}box["{name}"]\n  {name}("{name}")\nend\n' for name in "abcd")
    svg = FRAME + "".join(cluster(f"{name}box", 0, 0, 10, 10, 0, 0) for name in "abcd") + "".join(grid_node(name, 60, 40) for name in "abcd")
    rects = drawn_rects(lay_out_on_grid(svg, source))
    assert rects["abox"][0] == rects["cbox"][0] == MARGIN and rects["abox"][1] == rects["bbox"][1] == MARGIN
    assert rects["cbox"][1] - (rects["abox"][1] + rects["abox"][3]) == ROW_GAP and rects["bbox"][0] - (rects["abox"][0] + rects["abox"][2]) == COLUMN_GAP


PEERS_SOURCE = 'flowchart LR\n%% grid: a  b  c  d\n%% peers: a b c\na("a")\nb[("b")]\nc("c")\nd("d")\na --> b\nb --> c\n'
PEERS_SVG = FRAME + grid_node("a", 100, 40) + cylinder_node("b", 30, 10, 50) + grid_node("c", 60, 30) + grid_node("d", 80, 30) + grid_edge("a", "b") + grid_edge("b", "c")


def drawn_shapes(svg: str) -> dict[str, Box]:
    return {name: shape_size(markup) for name, markup in node_markups(svg).items()}


def test_peers_take_the_widest_width_and_the_tallest_height_about_their_own_centres() -> None:
    shapes = drawn_shapes(lay_out_on_grid(PEERS_SVG, PEERS_SOURCE))
    assert shapes["a"] == shapes["c"] == Box(-50, -35, 100, 70)
    assert (shapes["b"].width, shapes["b"].height, shapes["b"].center_x, shapes["b"].center_y) == (100, 70, 0, 0)
    assert shapes["d"] == Box(-40, -15, 80, 30)


def test_a_decision_diamond_cannot_be_a_peer() -> None:
    with pytest.raises(ValueError):
        lay_out_on_grid(FRAME + grid_node("a", 60, 40) + diamond_node("d", 80, 80), 'flowchart LR\n%% grid: a  d\n%% peers: a d\na("a")\nd{"d"}\n')


def test_a_stadium_peer_takes_the_peers_size_with_fully_round_ends_about_its_centre() -> None:
    drawn = lay_out_on_grid(FRAME + grid_node("a", 100, 40) + stadium_node("s", 60, 30), 'flowchart LR\n%% grid: a  s\n%% peers: a s\na("a")\ns(["s"])\n')
    stadium = node_markups(drawn)["s"]
    assert shape_size(stadium) == Box(-50, -20, 100, 40)
    assert re.findall(r'd="([^"]*)"', stadium)[:2] == ["M-30,-20 L30,-20 A20,20 0 0 1 30,20 L-30,20 A20,20 0 0 1 -30,-20 Z"] * 2


def test_the_gaps_between_peers_are_evened_to_the_widest_one() -> None:
    labelled = PEERS_SVG + grid_label("a", "b", 40, 20) + grid_label("b", "c", 100, 20)
    centres = [x for x, _ in transforms(lay_out_on_grid(labelled, PEERS_SOURCE)).values()]
    assert centres[1] - centres[0] == centres[2] - centres[1] == 100 + 100 + 2 * LABEL_CLEARANCE


def test_a_diagram_without_a_grid_is_still_laid_out_in_bands() -> None:
    svg = FRAME + cluster("top", 100, 0, 200, 80, 180, 8) + cluster("bottom", 20, 200, 500, 80, 250, 208) + EDGE
    assert polish(svg, "flowchart TB\na --> b\n") == round_corners(band_layers(svg))


def test_a_diagram_already_in_the_cache_is_not_drawn_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    drawn: list[str] = []
    monkeypatch.setattr(render, "cached", lambda source: "<svg/>" if source == "seen\n" else None)
    monkeypatch.setattr(render, "store", lambda source, svg: svg)
    monkeypatch.setattr(render, "render_svg", lambda mmdc, source, *args: drawn.append(source) or "<svg/>")
    assert render.render_source(Path("/bin/mmdc"), "seen\n", tmp_path, None) == RenderResult(True, "", None)
    assert render.render_source(Path("/bin/mmdc"), "new\n", tmp_path, None) == RenderResult(True, "", None)
    assert drawn == ["new\n"]


def test_one_source_included_by_many_pages_is_rendered_once_and_reported_at_every_line() -> None:
    blocks = [MermaidBlock(Path("a.md"), 5, "map\n", (6,)), MermaidBlock(Path("b.md"), 9, "map\n", (10,)), MermaidBlock(Path("c.md"), 3, "fine\n", (4,))]
    rendered: list[str] = []

    def renderer(source: str) -> RenderResult:
        rendered.append(source)
        return RenderResult(False, "Parse error on line 1:", 1) if source == "map\n" else RenderResult(True, "", None)

    assert render_findings(blocks, renderer, jobs=2) == [Finding(Path("a.md"), 6, "Parse error on line 1:"), Finding(Path("b.md"), 10, "Parse error on line 1:")]
    assert sorted(rendered) == ["fine\n", "map\n"]


def test_the_cache_key_changes_with_the_source_and_with_the_code_that_draws_it() -> None:
    assert diagram_cache.cache_key("a\n") != diagram_cache.cache_key("b\n")
    assert diagram_cache.svg_id("a\n").startswith("diagram-") and len(diagram_cache.svg_id("a\n")) == 20


EDGE_LABEL_PLACED = re.compile(r'<g class="edgeLabel" transform="translate\((?P<x>[\d.\-]+), (?P<y>[\d.\-]+)\)"><g class="label" data-id="L_(?P<link>\w+)_\d+"')


def label_centres(svg: str) -> dict[str, tuple[float, float]]:
    return {match["link"]: (float(match["x"]), float(match["y"])) for match in EDGE_LABEL_PLACED.finditer(svg)}


HANGING_SOURCE = 'flowchart TB\n%% grid: s\n%% grid: p>\n%% grid: <k\nsubgraph box["box title"]\n  s("s")\n  p("p")\nend\nk("k")\ns --> p\np --> s\ns --> k\nk --> s\n'
HANGING_SVG = FRAME + narrow_titled_cluster("box", 40) + "".join(grid_node(name, 160, 40) for name in "spk") + "".join(grid_edge(*pair) for pair in ("sp", "ps", "sk", "ks"))


def test_a_box_marked_to_one_side_hangs_under_that_half_of_its_column_and_its_pair_runs_down_the_shared_stretch() -> None:
    laid_out = lay_out_on_grid(HANGING_SVG, HANGING_SOURCE)
    stage_x, piper_x, kokoro_x = (transforms(laid_out)[name][0] for name in "spk")
    paths = drawn_paths(laid_out)
    assert (piper_x - stage_x, kokoro_x - stage_x) == (80, -80)
    assert [paths[link][0][0] - stage_x for link in ("s_p", "p_s", "s_k", "k_s")] == [20, 60, -60, -20]
    assert drawn_rects(laid_out)["box"][0] + drawn_rects(laid_out)["box"][2] == piper_x + 80 + 18
    # Each marked box moves half its width, so its inner edge sits on the column's centre; k's pair passes p's row 20 px clear of p, and the container reaches around p, not just its column.


ENTRY_SOURCE = 'flowchart TB\n%% grid: .  d  .\n%% grid: a  m  b\nsubgraph box["box title"]\n  a("a")\n  m("m")\n  b("b")\nend\nd("d")\nd --> a\nb --> d\na --> m\n'
ENTRY_SVG = (
    FRAME
    + narrow_titled_cluster("box", 40)
    + grid_node("d", 160, 40)
    + "".join(grid_node(name, 80, 40) for name in "amb")
    + "".join(grid_edge(*pair) for pair in ("da", "bd", "am"))
    + grid_label("d", "a", 40, 20)
    + grid_label("b", "d", 40, 20)
)


def test_a_device_over_a_box_it_does_not_feed_enters_the_container_under_itself_and_turns_below_the_title() -> None:
    laid_out = lay_out_on_grid(ENTRY_SVG, ENTRY_SOURCE)
    centres, paths, (_, box_top, _, _) = transforms(laid_out), drawn_paths(laid_out), drawn_rects(laid_out)["box"]
    title_bottom, row_top = box_top + 45 - 12, centres["a"][1] - 20
    assert paths["d_a"] == [
        (centres["d"][0] - 40, centres["d"][1] + 20),
        (centres["d"][0] - 40, (title_bottom + row_top) / 2),
        (centres["a"][0], (title_bottom + row_top) / 2),
        (centres["a"][0], row_top - ARROW_GAP),
    ]
    assert paths["b_d"] == [
        (centres["b"][0], row_top),
        (centres["b"][0], (title_bottom + row_top) / 2),
        (centres["d"][0] + 40, (title_bottom + row_top) / 2),
        (centres["d"][0] + 40, centres["d"][1] + 20 + ARROW_GAP),
    ]
    # Both lines cross the container's top under d, a quarter of its width from its centre, turn midway between the title and the row, and meet a and b in the centre of their tops.


def test_the_label_of_an_edge_entering_from_a_device_sits_right_of_its_line_above_the_container() -> None:
    laid_out = lay_out_on_grid(ENTRY_SVG, ENTRY_SOURCE)
    labels, device_x, box_top = label_centres(laid_out), transforms(laid_out)["d"][0], drawn_rects(laid_out)["box"][1]
    assert labels["d_a"][0] == device_x - 40 + LABEL_CLEARANCE + 20 and labels["b_d"][0] == device_x + 40 + LABEL_CLEARANCE + 20
    assert labels["d_a"][1] == labels["b_d"][1] < box_top


def test_a_device_over_a_box_it_feeds_keeps_the_staircase_above_the_container() -> None:
    laid_out = lay_out_on_grid(ENTRY_SVG + grid_edge("d", "m"), ENTRY_SOURCE + "d --> m\n")
    assert drawn_paths(laid_out)["d_a"][1][1] < drawn_rects(laid_out)["box"][1]


def test_a_container_reaches_far_enough_to_hold_the_labels_beside_a_vertical_pair() -> None:
    source = 'flowchart TB\n%% grid: a\n%% grid: b\nsubgraph box["box title"]\n  a("a")\n  b("b")\nend\na --> b\nb --> a\n'
    svg = (
        FRAME
        + narrow_titled_cluster("box", 40)
        + grid_node("a", 60, 40)
        + grid_node("b", 60, 40)
        + grid_edge("a", "b")
        + grid_edge("b", "a")
        + grid_label("a", "b", 50, 20)
        + grid_label("b", "a", 50, 20)
    )
    laid_out = lay_out_on_grid(svg, source)
    box_x, _, box_width, _ = drawn_rects(laid_out)["box"]
    labels = label_centres(laid_out)
    assert labels["a_b"][0] - 25 - box_x == box_x + box_width - (labels["b_a"][0] + 25) == LABEL_CLEARANCE
    # 60 px boxes leave no room beside a 40 px pair for 50 px labels; the container grows until each label is as far from its border as from its own line.


def test_the_labels_of_a_pair_passing_a_row_sit_below_the_last_border_it_crosses() -> None:
    source = 'flowchart TB\n%% grid: a  .\n%% grid: .  c\n%% grid: b  .\nsubgraph box["box title"]\n  a("a")\n  c("c")\nend\nb("b")\na --> b\nb --> a\n'
    svg = (
        FRAME
        + narrow_titled_cluster("box", 40)
        + "".join(grid_node(name, 160, 40) for name in "acb")
        + grid_edge("a", "b")
        + grid_edge("b", "a")
        + grid_label("a", "b", 40, 20)
        + grid_label("b", "a", 40, 20)
    )
    laid_out = lay_out_on_grid(svg, source)
    labels, (_, box_y, _, box_height), b_top = label_centres(laid_out), drawn_rects(laid_out)["box"], transforms(laid_out)["b"][1] - 20
    assert labels["a_b"][1] == labels["b_a"][1] == (box_y + box_height + b_top - ARROW_GAP) / 2
    # Halfway down the whole pair would put the labels in c's row; they sit halfway between the container's bottom and b instead.


FAN_SOURCE = 'flowchart TB\n%% grid: .  a\n%% grid: s  b\n%% grid: s  c\n%% grid: .  d\ns("s")\na("a")\nb("b")\nc("c")\nd("d")\ns -- "x" --> a\ns --> b\ns --> c\ns --> d\n'
FAN_SVG = FRAME + "".join(grid_node(name, 60, 40) for name in "sabcd") + "".join(grid_edge("s", target) for target in "abcd") + grid_label("s", "a", 40, 20)


def test_a_box_written_in_the_same_column_of_two_rows_is_centred_between_them_without_heightening_either() -> None:
    centres = transforms(lay_out_on_grid(FAN_SVG, FAN_SOURCE))
    assert centres["s"] == (54, (centres["b"][1] + centres["c"][1]) / 2)
    assert [centres[name][1] for name in "abcd"] == [44, 148, 252, 356]
    # The rows keep the 40 px of the boxes beside s and the 64 px gap between them; s sits level with the middle of b and c.


def test_a_box_feeding_boxes_above_and_below_it_in_the_next_column_fans_out_through_one_trunk_into_their_sides() -> None:
    laid_out = lay_out_on_grid(FAN_SVG, FAN_SOURCE)
    paths = drawn_paths(laid_out)
    assert {link: points[:2] for link, points in paths.items()} == {link: [(84, 200), (108, 200)] for link in ("s_a", "s_b", "s_c", "s_d")}
    assert [paths[link][2:] for link in ("s_a", "s_d")] == [[(108, 44), (172, 44)], [(108, 356), (172, 356)]]
    assert label_centres(laid_out)["s_a"] == (142, 44)
    # Every leg leaves s's right side, turns on one trunk 24 px past s's column, and runs into the side of its box, arrowhead 4 px short; the gap grows to 24 + 40 + 28 px so the label sits on its branch between the trunk and a's column.


def test_in_a_left_to_right_figure_a_box_feeding_the_box_level_with_it_and_one_below_keeps_its_straight_line_and_an_elbow() -> None:
    source = 'flowchart LR\n%% grid: s  a\n%% grid: .  b\ns("s")\na("a")\nb("b")\ns --> a\ns --> b\n'
    svg = FRAME + "".join(grid_node(name, 60, 40) for name in "sab") + grid_edge("s", "a") + grid_edge("s", "b")
    assert drawn_paths(lay_out_on_grid(svg, source)) == {"s_a": [(84, 44), (156, 44)], "s_b": [(69, 64), (69, 148), (156, 148)]}
    # Outside every container, the edge to b drops out of s a quarter of its width right of centre and turns into b's side, as a sketch draws a step that follows on later; top to bottom it would keep its staircase.


def test_an_edge_down_a_column_passes_beside_the_box_in_between_and_lands_on_a_box_widened_to_catch_it() -> None:
    source = 'flowchart TB\n%% grid: w\n%% grid: o\n%% grid: g\nw("w")\no("o")\ng("g")\nw --> g\no --> g\n'
    svg = FRAME + grid_node("w", 60, 40) + grid_node("o", 60, 40) + grid_node("g", 80, 40) + grid_edge("w", "g") + grid_edge("o", "g")
    laid_out = lay_out_on_grid(svg, source)
    assert drawn_paths(laid_out) == {"w_g": [(140, 44), (168, 44), (168, 228)], "o_g": [(110, 168), (110, 228)]}
    assert 'width="172" height="40"' in laid_out
    # w's line leaves its right side, runs 28 px clear of o, and drops into g's top; g grows from 80 px to 172 so the line lands 28 px inside its corner.


def test_in_a_left_to_right_figure_an_edge_up_to_a_later_column_runs_along_its_row_and_rises_into_the_bottom() -> None:
    source = 'flowchart LR\n%% grid: .  .  v\n%% grid: u  .  .\nu("u")\nv("v")\nu -- "x" --> v\n'
    svg = FRAME + grid_node("u", 60, 40) + grid_node("v", 60, 40) + grid_edge("u", "v") + grid_label("u", "v", 40, 20)
    laid_out = lay_out_on_grid(svg, source)
    assert drawn_paths(laid_out)["u_v"] == [(84, 148), (266, 148), (266, 68)]
    assert label_centres(laid_out)["u_v"] == (266, 108)
    # The line leaves u's right side, runs under the empty cells, and rises into v's centre; its label sits on the rise, beside the box it reaches.


def test_elbows_from_one_box_to_rows_further_down_leave_at_points_of_their_own_the_nearer_row_closest_to_the_targets() -> None:
    source = 'flowchart LR\n%% grid: s  .  .\n%% grid: .  a  .\n%% grid: .  .  b\ns("s")\na("a")\nb("b")\ns -- "x" --> a\ns -- "y" --> b\n'
    svg = FRAME + "".join(grid_node(name, 60, 40) for name in "sab") + grid_edge("s", "a") + grid_edge("s", "b") + grid_label("s", "a", 20, 20) + grid_label("s", "b", 20, 20)
    laid_out = lay_out_on_grid(svg, source)
    paths = drawn_paths(laid_out)
    assert paths == {"s_a": [(69, 64), (69, 148), (156, 148)], "s_b": [(39, 64), (39, 252), (292, 252)]}
    assert crossings(list(paths.values())) == 0
    assert label_centres(laid_out) == {"s_a": (93, 106), "s_b": (63, 200)}
    # s is centred at x 54 and 60 px wide: the edge to the nearer row leaves a quarter of the width right of centre, the one to the farther row a quarter left, so it drops outside the first and runs under its corner. Each label sits right of its own drop, the farther one's below the nearer one's turn.


SIDE_FAN_IN_SOURCE = (
    'flowchart TB\n%% grid: d  .  t\n%% grid: .  f  .\n%% grid: .  g  .\nsubgraph mac["M"]\n  d("d")\n  subgraph folder["F"]\n    f("f")\n    g("g")\n  end\nend\nt("t")\nd --> t\nf --> t\ng --> t\n'
)
SIDE_FAN_IN_SVG = (
    FRAME + narrow_titled_cluster("mac", 20) + narrow_titled_cluster("folder", 20) + "".join(grid_node(name, 60, 40) for name in "dfgt") + "".join(grid_edge(start, "t") for start in "dfg")
)
ARROWHEAD_LINKS = re.compile(r'<path d="[^"]*" id="d-L_(?P<link>\w+)_0"[^>]*marker-end=')


def test_files_in_one_column_read_by_a_box_level_with_the_topmost_or_above_join_one_trunk_outside_their_folder() -> None:
    laid_out = lay_out_on_grid(SIDE_FAN_IN_SVG, SIDE_FAN_IN_SOURCE)
    paths, rects = drawn_paths(laid_out), drawn_rects(laid_out)
    assert paths["f_t"] == [(256, 274), (298, 274), (298, 107)] and paths["g_t"] == [(256, 378), (298, 378), (298, 274)]
    assert rects["folder"][0] + rects["folder"][2] + 24 == 298 == rects["mac"][0] + rects["mac"][2] - 18
    # Each file leaves its right side for a trunk 24 px past the folder, inside the machine, which reaches 18 px past the trunk; each leg climbs only to the leg above, so no stretch is drawn twice.


def test_a_fan_in_joins_the_straight_line_already_entering_the_target_side_under_its_one_arrowhead() -> None:
    laid_out = lay_out_on_grid(SIDE_FAN_IN_SVG, SIDE_FAN_IN_SOURCE)
    assert drawn_paths(laid_out)["d_t"] == [(102, 107), (388, 107)]
    assert {match["link"] for match in ARROWHEAD_LINKS.finditer(laid_out)} == {"d_t"}
    # The trunk ends on d's line at y 107, and only that line carries an arrowhead into t.


def test_a_fan_in_with_no_line_to_join_enters_the_target_side_from_the_top_of_its_trunk() -> None:
    source = 'flowchart TB\n%% grid: .  t\n%% grid: f  .\n%% grid: g  .\nf("f")\ng("g")\nt("t")\nf --> t\ng --> t\n'
    svg = FRAME + "".join(grid_node(name, 60, 40) for name in "fgt") + "".join(grid_edge(start, "t") for start in "fg")
    laid_out = lay_out_on_grid(svg, source)
    assert drawn_paths(laid_out) == {"f_t": [(84, 148), (108, 148), (108, 44), (156, 44)], "g_t": [(84, 252), (108, 252), (108, 148)]}
    assert {match["link"] for match in ARROWHEAD_LINKS.finditer(laid_out)} == {"f_t"}
    # Outside any container the trunk runs 24 px past the column, and the topmost leg carries on into t's side with the one arrowhead.


def test_boxes_above_a_joined_box_in_its_column_join_one_trunk_on_the_right_into_its_side() -> None:
    source = 'flowchart TB\n%% grid: a\n%% grid: b\n%% grid: t\n%% join: t\nsubgraph gate["G"]\n  a("a")\n  b("b")\n  t("t")\nend\na --> t\nb --> t\n'
    svg = FRAME + narrow_titled_cluster("gate", 20) + "".join(grid_node(name, 60, 40) for name in "abt") + grid_edge("a", "t") + grid_edge("b", "t")
    laid_out = lay_out_on_grid(svg, source)
    assert drawn_paths(laid_out) == {"a_t": [(102, 107), (126, 107), (126, 211)], "b_t": [(102, 211), (126, 211), (126, 315), (106, 315)]}
    assert {match["link"] for match in ARROWHEAD_LINKS.finditer(laid_out)} == {"b_t"}
    assert drawn_rects(laid_out)["gate"][0] + drawn_rects(laid_out)["gate"][2] == 126 + 18
    assert laid_out.count('width="60" height="40"') == 3
    # Each box leaves its right side for a trunk 24 px past the column, inside the container, which reaches 18 px past it; a's leg ends on b's, and b's enters t's right side with the one arrowhead. Without the join, a's line would pass beside b and widen t to land on it.
