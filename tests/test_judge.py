import pytest

from benchmark.judge import build_parser


def test_judge_without_export_or_import_is_a_usage_error_naming_both_flags(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args(["version_5"])
    usage_error = capsys.readouterr().err
    assert exit_info.value.code == 2
    assert "--export" in usage_error and "--import" in usage_error


def test_judge_accepts_export_and_import_as_separate_steps() -> None:
    assert build_parser().parse_args(["version_5", "--export"]).export is True
    assert build_parser().parse_args(["version_5", "--import"]).import_verdicts is True


def test_judge_refuses_export_and_import_together() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["version_5", "--export", "--import"])
