"""The local deploy's decisions (ops/deploy_here.py): what it keeps, when it rolls back, and when it waits, with the checkout, the restarts and the
smoke test replaced by fakes."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from ops import deploy, deploy_here, paths

OLD = "a" * 40
NEW = "b" * 40


def summary(applied: bool, plan: list[str] | None = None, to: str = NEW, tests: str | None = "passed", note: str | None = None) -> dict:
    result = {"from": OLD, "to": to, "changed": 3, "plan": plan or [], "reasons": {}, "tests": tests, "applied": applied}
    if note:
        result["note"] = note
    return result


class FakeMac:
    """Stands in for the checkout, the restarts and Home Assistant: each switch_to and smoke test takes the next scripted result."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, switches: list[dict], answers: list[int]) -> None:
        self.switches: Iterator[dict] = iter(switches)
        self.answers: Iterator[int] = iter(answers)
        self.switched_to: list[tuple[str, bool]] = []
        self.waits = 0
        monkeypatch.setattr(deploy_here, "refuse_a_branch_checkout", lambda: None)
        monkeypatch.setattr(deploy, "git", self.git)
        monkeypatch.setattr(deploy, "switch_to", self.switch_to)
        monkeypatch.setattr(deploy_here.smoke, "main", lambda flags: next(self.answers))
        monkeypatch.setattr(deploy_here, "wait_until_ready", self.wait_until_ready)

    def git(self, *args: str) -> str:
        if args[0] == "rev-parse":
            return OLD if args[-1].startswith("HEAD") else args[-1].removesuffix("^{commit}")
        return "a commit subject"

    def switch_to(self, ref: str, run_tests: bool, dry_run: bool) -> dict:
        self.switched_to.append((ref, run_tests))
        result = next(self.switches)
        if result["applied"] or result["tests"] != "passed":
            paths.maintenance_flag().touch()
        return result

    def wait_until_ready(self, _is_ready: object) -> bool:
        self.waits += 1
        return True


@pytest.fixture(autouse=True)
def log_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("STUDIO_LOG_DIR", str(tmp_path))
    return tmp_path


def recorded_good() -> str:
    return paths.last_good_ref().read_text().strip()


def test_a_commit_that_answers_is_kept_and_the_health_check_resumes(monkeypatch: pytest.MonkeyPatch) -> None:
    mac = FakeMac(monkeypatch, [summary(applied=True, plan=["restart:mcp"])], answers=[0])

    assert deploy_here.deploy_here("origin/main", [], run_tests=True) == deploy_here.DEPLOYED
    assert recorded_good() == NEW
    assert not paths.maintenance_flag().exists()
    assert mac.waits == 1


def test_a_mac_already_at_the_commit_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeMac(monkeypatch, [summary(applied=False, tests=None, note="already at this commit")], answers=[])

    assert deploy_here.deploy_here("origin/main", [], run_tests=True) == deploy_here.DEPLOYED


def test_failing_tests_keep_the_old_commit_and_turn_the_health_check_back_on(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeMac(monkeypatch, [summary(applied=False, tests="failed: 1 test")], answers=[])

    assert deploy_here.deploy_here("origin/main", [], run_tests=True) == deploy_here.NOT_DEPLOYED
    assert not paths.maintenance_flag().exists()
    assert recorded_good() == OLD


def test_a_commit_that_does_not_answer_is_rolled_back_without_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    mac = FakeMac(monkeypatch, [summary(applied=True, plan=["restart:harness"]), summary(applied=True, plan=["restart:harness"], to=OLD)], answers=[1, 0])

    assert deploy_here.deploy_here("origin/main", [], run_tests=True) == deploy_here.NOT_DEPLOYED
    assert mac.switched_to == [("origin/main", True), (OLD, False)]
    assert recorded_good() == OLD
    assert not paths.maintenance_flag().exists()


def test_when_the_rollback_does_not_answer_either_the_health_check_stays_off(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeMac(monkeypatch, [summary(applied=True, plan=["restart:harness"]), summary(applied=True, plan=["restart:harness"], to=OLD)], answers=[1, 1])

    assert deploy_here.deploy_here("origin/main", [], run_tests=True) == deploy_here.NEEDS_A_PERSON
    assert paths.maintenance_flag().exists()


def test_the_first_deploy_records_the_running_commit_so_a_failure_has_somewhere_to_return(monkeypatch: pytest.MonkeyPatch) -> None:
    mac = FakeMac(monkeypatch, [summary(applied=True), summary(applied=True, to=OLD)], answers=[1, 0])
    assert not paths.last_good_ref().exists()

    deploy_here.deploy_here("origin/main", [], run_tests=True)

    assert mac.switched_to[1] == (OLD, False)


def test_an_earlier_good_commit_is_not_replaced_by_the_running_one(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeMac(monkeypatch, [summary(applied=False, tests="failed: 1 test")], answers=[])
    paths.last_good_ref().write_text("c" * 40 + "\n")

    deploy_here.deploy_here("origin/main", [], run_tests=True)

    assert recorded_good() == "c" * 40


@pytest.mark.parametrize("plan", [["restart:dashboard"], ["deploy_component"], ["restart_searxng"], []])
def test_restarts_off_the_answer_path_ask_the_test_question_without_waiting(monkeypatch: pytest.MonkeyPatch, plan: list[str]) -> None:
    mac = FakeMac(monkeypatch, [summary(applied=True, plan=plan)], answers=[0])

    deploy_here.deploy_here("origin/main", [], run_tests=True)

    assert mac.waits == 0


def test_waiting_stops_as_soon_as_the_harness_is_ready() -> None:
    reports = iter([False, False, True])

    assert deploy_here.wait_until_ready(lambda: next(reports), timeout_seconds=5, poll_seconds=0)


def test_waiting_gives_up_after_its_timeout() -> None:
    assert not deploy_here.wait_until_ready(lambda: False, timeout_seconds=0, poll_seconds=0)
