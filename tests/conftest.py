"""Shared for every test: none reads the Keychain, spends a Brave search, or counts one in the real usage file, whatever is on the machine running them."""

from pathlib import Path

import pytest

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
