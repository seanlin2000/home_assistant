"""pr-refs must resolve symbols and quoted text to real line spans, and reject any reference in a description that no longer matches the code."""

from pathlib import Path

import pytest

from pr_references.lint import lint
from pr_references.references import SymbolAnchor, TextAnchor, find_references, mismatches, parse_anchor, resolve, sections_without_references

MODULE = '''"""Doc."""
LIMIT = 3


class Box:
    def open(self) -> None:
        return None

    @staticmethod
    def build() -> "Box":
        return Box()


async def fetch(url: str) -> str:
    return url
'''

SCRIPT = """set -eu
run_step() {
    echo one
    echo two
}
run_step
"""


@pytest.fixture
def module(tmp_path: Path) -> Path:
    path = tmp_path / "m.py"
    path.write_text(MODULE)
    return path


@pytest.fixture
def script(tmp_path: Path) -> Path:
    path = tmp_path / "s.sh"
    path.write_text(SCRIPT)
    return path


def test_resolves_function_method_decorated_method_class_and_constant(module: Path) -> None:
    assert SymbolAnchor(module, "fetch").span() == (14, 15)
    assert SymbolAnchor(module, "Box.open").span() == (6, 7)
    assert SymbolAnchor(module, "Box.build").span() == (9, 11)
    assert SymbolAnchor(module, "Box").span() == (5, 11)
    assert SymbolAnchor(module, "LIMIT").span() == (2, 2)


def test_unknown_symbol_raises_lookup_error(module: Path) -> None:
    with pytest.raises(LookupError, match="missing"):
        SymbolAnchor(module, "Box.missing").span()


def test_text_anchor_spans_the_indented_block_under_the_matching_line(script: Path) -> None:
    assert TextAnchor(script, "run_step() {").span() == (2, 4)
    assert TextAnchor(script, "set -eu").span() == (1, 1)


def test_parse_anchor_distinguishes_symbols_from_quoted_text() -> None:
    assert parse_anchor("a/b.py:Box.open") == SymbolAnchor(Path("a/b.py"), "Box.open")
    assert parse_anchor('a/b.sh:"echo one"') == TextAnchor(Path("a/b.sh"), "echo one")


def test_resolve_renders_the_reference_form(module: Path, script: Path) -> None:
    assert resolve(SymbolAnchor(module, "fetch")).render() == f"`{module}:14-15` (`fetch`)"
    assert resolve(TextAnchor(script, "echo one")).render() == f'`{script}:3-3` ("echo one")'


def test_find_references_parses_both_forms_in_order() -> None:
    text = 'See `b.sh:3-3` ("echo one") and `a.py:14-15` (`fetch`) and `a.py:2-2` (`LIMIT`).'
    assert [reference.render() for reference in find_references(text)] == ["`a.py:2-2` (`LIMIT`)", "`a.py:14-15` (`fetch`)", '`b.sh:3-3` ("echo one")']


def test_references_inside_html_comments_are_ignored() -> None:
    text = "<!-- example: `a.py:1-2` (`f`) -->\n<!--\nmulti-line `b.py:1-2` (`g`)\n-->\nreal `c.py:3-4` (`h`)"
    assert [reference.render() for reference in find_references(text)] == ["`c.py:3-4` (`h`)"]


def test_correct_references_have_no_mismatches(module: Path, script: Path) -> None:
    text = f'`{module}:14-15` (`fetch`) `{module}:5-11` (`Box`) `{script}:2-4` ("echo two")'
    assert mismatches(find_references(text)) == []


def test_off_by_one_range_wrong_symbol_missing_file_and_absent_text_are_reported(module: Path, script: Path) -> None:
    text = f'`{module}:13-15` (`fetch`) `{module}:6-7` (`Box.close`) `{module.parent}/gone.py:1-1` (`x`) `{script}:1-1` ("echo one") `{module}:0-99` (`fetch`)'
    problems = [problem.split(": ", 1)[1] for problem in mismatches(find_references(text))]
    assert problems == [
        "file not found",
        "lines out of range, the file has 15 lines",
        "no definition named 'close'",
        "`fetch` actually spans lines 14-15",
        "text 'echo one' is not on lines 1-1",
    ]


def test_sections_without_references_ignores_summary_and_verification_sections() -> None:
    text = "## Summary\ntext\n## Hook\nno reference here\n## Checker\nsee `a.py:1-2` (`f`)\n## How to verify\nrun it\n## Review notes\nnone\n"
    assert sections_without_references(text) == ["Hook"]


WELL_FORMED = """## Summary

Why.

## The change

<!-- - `x.py:1-1` (`f`) **Inside a comment.** ignored
-->
- `a.py:14-15` (`fetch`) **One reference.** Then the description.
- `a.py:2-2` (`LIMIT`), `b.sh:3-3` ("echo one") **Two references.** Then the description.

## How to verify

```
uv run pytest -q
```

## Review notes

- free-form bullets are fine here
"""


def test_lint_accepts_the_template_shape() -> None:
    assert lint(WELL_FORMED) == []


def test_lint_reports_each_malformed_bullet_with_its_line() -> None:
    text = WELL_FORMED.replace(
        "- `a.py:14-15` (`fetch`) **One reference.** Then the description.",
        "- The description first. `a.py:14-15` (`fetch`)\n- `a.py:14-15` (`fetch`) No bold phrase.\n- `a.py:14-15` (`fetch`) **No period** then text.\n- `a.py:14-15` (`fetch`) **Nothing after the phrase.**",
    )
    assert [problem.line for problem in lint(text)] == [9, 10, 11, 12]
    assert {problem.message for problem in lint(text)} == {"a bullet reads: one or more references, then **a short phrase ending in a period.**, then the description"}


def test_lint_reports_missing_sections_and_change_sections_without_bullets() -> None:
    text = "## Summary\n\nWhy.\n\n## Prose only\n\nA paragraph instead of bullets.\n"
    assert [(problem.line, problem.message) for problem in lint(text)] == [
        (1, "missing section '## How to verify'"),
        (1, "missing section '## Review notes'"),
        (5, "section 'Prose only' has no bullets"),
    ]
