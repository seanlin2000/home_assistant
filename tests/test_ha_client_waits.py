"""Waiting for Home Assistant after a restart: first for the old instance to stop, then for the new one to run with the component loaded, so a
deploy's test question never reaches a Home Assistant that refuses it with "invalid agent ID"."""

from typing import Any

import pytest

from ops.ha_client import HomeAssistant, component_is_loaded, wait_for_component, wait_until_stopped
from scripts.deploy_component import restart_and_wait

UP_AND_LOADED = ("RUNNING", "loaded")
UP_NOT_YET_LOADED = ("RUNNING", "setup_in_progress")
STARTING = ("STARTING", "not_loaded")
STOPPED = None  # the websocket does not connect


class ScriptedHomeAssistant(HomeAssistant):
    """Answers websocket calls from a script of (core state, component state) steps, moving one step per call; records each POST."""

    def __init__(self, *steps: tuple[str, str] | None) -> None:
        super().__init__("ha.test", "token", base="http://ha.test")
        self.steps = list(steps)
        self.step = 0
        self.posts: list[str] = []

    def current(self) -> tuple[str, str] | None:
        return self.steps[min(self.step, len(self.steps) - 1)]

    async def ws(self, message: dict[str, Any]) -> Any:
        state = self.current()
        self.step += 1
        if state is None:
            raise OSError("connection refused")
        if message["type"] == "get_config":
            return {"state": state[0]}
        return [{"domain": "studio_assistant", "state": state[1]}]

    async def post(self, path: str, payload: Any = None, ok_statuses: tuple[int, ...] = (200, 201)) -> Any:
        self.posts.append(path)
        return []


async def test_the_component_counts_as_loaded_only_while_home_assistant_runs() -> None:
    assert await component_is_loaded(ScriptedHomeAssistant(UP_AND_LOADED))
    assert not await component_is_loaded(ScriptedHomeAssistant(UP_NOT_YET_LOADED))
    assert not await component_is_loaded(ScriptedHomeAssistant(("STOPPING", "loaded")))
    assert not await component_is_loaded(ScriptedHomeAssistant(STOPPED))


async def test_waiting_for_the_component_rides_out_a_start_that_answers_before_the_component_loads() -> None:
    ha = ScriptedHomeAssistant(STOPPED, STARTING, UP_NOT_YET_LOADED, UP_AND_LOADED)
    await wait_for_component(ha, timeout_seconds=5, poll_seconds=0)
    assert ha.current() == UP_AND_LOADED


async def test_waiting_for_the_component_gives_up_with_a_timeout() -> None:
    with pytest.raises(TimeoutError, match="did not load the studio_assistant component"):
        await wait_for_component(ScriptedHomeAssistant(UP_NOT_YET_LOADED), timeout_seconds=0.05, poll_seconds=0.01)


async def test_waiting_for_the_stop_says_whether_it_was_seen() -> None:
    assert await wait_until_stopped(ScriptedHomeAssistant(UP_AND_LOADED, UP_AND_LOADED, STOPPED), timeout_seconds=5, poll_seconds=0)
    assert not await wait_until_stopped(ScriptedHomeAssistant(UP_AND_LOADED), timeout_seconds=0.05, poll_seconds=0.01)


async def test_a_restart_waits_past_the_old_instance_still_running_with_the_component_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    """The old instance answers "loaded" right after the restart call; returning then is what let the 2026-11-14 test question in too early."""
    monkeypatch.setattr("ops.ha_client.asyncio.sleep", no_wait)
    ha = ScriptedHomeAssistant(UP_AND_LOADED, UP_AND_LOADED, STOPPED, STOPPED, STARTING, UP_NOT_YET_LOADED, UP_AND_LOADED)
    await restart_and_wait(ha)
    assert ha.posts == ["/api/services/homeassistant/restart"]
    assert ha.step >= 6  # read through to the new instance, not the old one


async def no_wait(seconds: float) -> None:
    return None
