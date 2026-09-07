"""deslop must flag untyped parameters and comment-heavy functions, honour the opt-out marker, and leave the repository itself clean."""

import textwrap
from pathlib import Path

import pytest

from deslop.checks import Finding, check_source
from deslop.cli import check_paths, format_finding, main, python_files

RATIO_HINT = "(add '# deslop: allow-comments' to exempt)"


def findings_for(text: str) -> list[str]:
    return [finding.message for finding in check_source(Path("x.py"), textwrap.dedent(text))]


def lines_for(text: str) -> list[int]:
    return [finding.line for finding in check_source(Path("x.py"), textwrap.dedent(text))]


def test_untyped_positional_parameter_is_reported_with_def_line_and_name() -> None:
    findings = check_source(Path("x.py"), "\ndef f(a, b: int) -> int:\n    return b\n")
    assert findings == [Finding(Path("x.py"), 2, "f: parameter 'a' has no type annotation")]


def test_self_and_cls_are_skipped_on_methods_but_not_on_module_functions() -> None:
    source = """
        class A:
            def m(self, x: int) -> None: ...

            @classmethod
            def c(cls, x: int) -> None: ...

            @staticmethod
            def s(x) -> None: ...

        def f(self) -> None: ...
        """
    assert findings_for(source) == ["s: parameter 'x' has no type annotation", "f: parameter 'self' has no type annotation"]


def test_star_args_and_kwargs_need_annotations_too() -> None:
    assert findings_for("def f(*args, **kwargs) -> None: ...") == ["f: parameter 'args' has no type annotation", "f: parameter 'kwargs' has no type annotation"]
    assert findings_for("def g(*args: int, **kwargs: str) -> None: ...") == []


def test_keyword_only_and_positional_only_parameters_are_checked() -> None:
    assert findings_for("def f(a: int, /, b, *, c) -> None: ...") == ["f: parameter 'b' has no type annotation", "f: parameter 'c' has no type annotation"]


def test_lambda_parameters_are_exempt() -> None:
    assert findings_for("double = lambda x: x * 2") == []


def test_nested_function_parameters_are_checked_at_the_inner_def_line() -> None:
    source = """
        def outer(a: int) -> int:
            def inner(b):
                return b

            return inner(a)
        """
    assert findings_for(source) == ["inner: parameter 'b' has no type annotation"]
    assert lines_for(source) == [3]


def test_async_def_parameters_are_checked() -> None:
    assert findings_for("async def f(a) -> None: ...") == ["f: parameter 'a' has no type annotation"]


def test_default_value_does_not_exempt_and_string_annotation_counts() -> None:
    assert findings_for('def f(a=None, b: "Foo" = None) -> None: ...') == ["f: parameter 'a' has no type annotation"]


def test_one_line_docstring_over_one_code_line_passes() -> None:
    source = '''
        def f() -> int:
            """Doc."""
            return 1
        '''
    assert findings_for(source) == []


def test_two_docstring_lines_over_one_code_line_fails_with_counts() -> None:
    source = '''
        def f() -> int:
            """Doc.
            """
            return 1
        '''
    assert findings_for(source) == [f"f: 2 comment lines exceed 1 code lines {RATIO_HINT}"]


def test_comment_only_lines_count_and_trailing_comments_are_code() -> None:
    balanced = """
        def f() -> int:
            # one
            # two
            x = 1  # trailing
            return x
        """
    unbalanced = """
        def f() -> int:
            # one
            # two
            # three
            x = 1  # trailing
            return x
        """
    assert findings_for(balanced) == []
    assert findings_for(unbalanced) == [f"f: 3 comment lines exceed 2 code lines {RATIO_HINT}"]


def test_hash_inside_string_literals_is_not_a_comment() -> None:
    source = '''
        def f() -> str:
            text = """
        # a
        # b
        # c
        # d
        """
            return text
        '''
    assert findings_for(source) == []


def test_multiline_docstring_counts_every_physical_line_including_closing_quotes() -> None:
    source = '''
        def f() -> int:
            """Summary.

            Details.
            """
            a = 1
            b = 2
            return a + b
        '''
    assert findings_for(source) == [f"f: 4 comment lines exceed 3 code lines {RATIO_HINT}"]


def test_nested_function_lines_belong_only_to_the_inner_function() -> None:
    source = """
        def outer() -> int:
            x = 1
            y = 2

            def inner() -> int:
                # a
                # b
                return 3

            return x + y + inner()
        """
    assert findings_for(source) == [f"inner: 2 comment lines exceed 1 code lines {RATIO_HINT}"]


def test_marker_on_def_line_above_def_and_above_decorator_suppresses() -> None:
    on_def_line = '''
        def f() -> int:  # deslop: allow-comments
            """Doc.
            """
            return 1
        '''
    above_def = '''
        # deslop: allow-comments
        def f() -> int:
            """Doc.
            """
            return 1
        '''
    above_decorator = '''
        # deslop: allow-comments
        @decorator
        def f() -> int:
            """Doc.
            """
            return 1
        '''
    assert findings_for(on_def_line) == findings_for(above_def) == findings_for(above_decorator) == []


def test_marker_does_not_suppress_annotation_findings() -> None:
    source = '''
        # deslop: allow-comments
        def f(a):
            """Doc.
            """
            return 1
        '''
    assert findings_for(source) == ["f: parameter 'a' has no type annotation"]


def test_marker_line_is_not_counted_as_a_comment_in_the_enclosing_function() -> None:
    source = '''
        def outer() -> int:
            x = 1

            # deslop: allow-comments
            def inner() -> int:
                """Doc.
                """
                return 1

            return x + inner()
        '''
    assert findings_for(source) == []


def test_marker_inside_docstring_has_no_effect() -> None:
    source = '''
        def f() -> int:
            """deslop: allow-comments
            """
            return 1
        '''
    assert findings_for(source) == [f"f: 2 comment lines exceed 1 code lines {RATIO_HINT}"]


def test_pass_and_ellipsis_bodies_with_docstring_pass_and_docstring_only_body_fails() -> None:
    source = '''
        def f() -> None:
            """Doc."""
            pass

        def g() -> None:
            """Doc."""
            ...

        def h() -> None:
            """Doc."""
        '''
    assert findings_for(source) == [f"h: 1 comment lines exceed 0 code lines {RATIO_HINT}"]


def test_class_body_comments_and_module_docstring_are_ignored() -> None:
    source = '''
        """Module doc.
        More.
        """
        # module comment

        class A:
            # class comment
            def m(self) -> int:
                return 1
        '''
    assert findings_for(source) == []


def test_multiline_signature_continuation_lines_are_not_code() -> None:
    source = '''
        def f(
            a: int,
            b: int,
        ) -> int:
            """Doc.
            """
            return a + b
        '''
    assert findings_for(source) == [f"f: 2 comment lines exceed 1 code lines {RATIO_HINT}"]


def test_comment_between_signature_and_first_statement_is_counted() -> None:
    source = """
        def f() -> int:
            # why
            # why more
            return 1
        """
    assert findings_for(source) == [f"f: 2 comment lines exceed 1 code lines {RATIO_HINT}"]


def test_python_files_skips_venv_vm_and_pycache(tmp_path: Path) -> None:
    for folder in (".venv/lib", "vm", "pkg/__pycache__", "pkg"):
        (tmp_path / folder).mkdir(parents=True, exist_ok=True)
        (tmp_path / folder / "m.py").write_text("x = 1\n")
    assert [path.relative_to(tmp_path) for path in python_files(tmp_path)] == [Path("pkg/m.py")]


def test_format_finding_is_path_colon_line_colon_message() -> None:
    assert format_finding(Finding(Path("a/b.py"), 7, "f: oops")) == "a/b.py:7: f: oops"


def test_unparseable_file_is_a_single_finding() -> None:
    findings = check_source(Path("x.py"), "def f(:\n    pass\n")
    assert len(findings) == 1
    assert findings[0].line == 1
    assert findings[0].message.startswith("cannot parse:")


def test_main_exits_one_on_findings_and_zero_when_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("def f(a):\n    return a\n")
    monkeypatch.setattr("sys.argv", ["deslop", str(bad)])
    with pytest.raises(SystemExit) as failure:
        main()
    assert failure.value.code == 1
    assert capsys.readouterr().out == f"{bad}:1: f: parameter 'a' has no type annotation\n"
    bad.write_text("def f(a: int) -> int:\n    return a\n")
    with pytest.raises(SystemExit) as success:
        main()
    assert success.value.code == 0


def test_repository_is_clean() -> None:
    assert [format_finding(finding) for finding in check_paths([Path(".")])] == []
