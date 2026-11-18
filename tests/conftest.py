"""Shared for every test: none reads the Keychain, spends a Brave search, counts one in the real usage file, records a Brave failure in the real
failures file, touches the real newsletters folder, or wakes a launchd agent, whatever is on the machine running them."""

from pathlib import Path

import pytest

import utils.keychain_utils
import utils.launchd_utils
import web_search_mcp.brave_client
import web_search_mcp.search_engines


@pytest.fixture(autouse=True)
def no_brave_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The environment variable reaches a tool server a test starts as its own process, which the patch cannot."""
    monkeypatch.setattr(web_search_mcp.search_engines, "brave_api_key", lambda: None)
    monkeypatch.setenv("WEB_SEARCH_ENGINES", "searxng")


@pytest.fixture(autouse=True)
def brave_usage_in_a_temporary_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    usage_file = tmp_path / "brave-searches.txt"
    monkeypatch.setattr(web_search_mcp.brave_client, "USAGE_FILE", usage_file)
    return usage_file


@pytest.fixture(autouse=True)
def brave_failures_in_a_temporary_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    failures_file = tmp_path / "brave-failures.txt"
    monkeypatch.setattr(web_search_mcp.brave_client, "FAILURES_FILE", failures_file)
    return failures_file


@pytest.fixture(autouse=True)
def woken_agents(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The agents code asked launchd to run, in order; launchd itself is never asked."""
    woken: list[str] = []
    monkeypatch.setattr(utils.launchd_utils, "wake_agent", woken.append)
    return woken


@pytest.fixture(autouse=True)
def no_keychain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every Keychain read finds nothing, so no test sees a real secret or the Gmail address."""
    monkeypatch.setattr(utils.keychain_utils, "find_generic_password", lambda arguments: None)


@pytest.fixture(autouse=True)
def newsletters_in_a_temporary_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """The environment variable also reaches a tool server or health check a test starts."""
    folder = tmp_path / "newsletters"
    monkeypatch.setenv("NEWSLETTERS_DIR", str(folder))
    return folder
