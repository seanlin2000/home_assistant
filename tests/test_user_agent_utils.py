"""Every API client of our own sends a User-Agent in the form Wikimedia's policy spells out, the form its API serves rather than refusing with 403."""

import re

import pytest

from reddit_mcp.settings import USER_AGENT as REDDIT_USER_AGENT
from sports_mcp.settings import USER_AGENT as SPORTS_USER_AGENT
from weather_mcp.settings import USER_AGENT as WEATHER_USER_AGENT
from wikipedia_mcp.settings import USER_AGENT as WIKIPEDIA_USER_AGENT

POLICY_USER_AGENT = re.compile(r"[\w.-]+/[\d.]+ \(https://[^)\s]+\)")  # name/version, then the contact in parentheses with its scheme


@pytest.mark.parametrize("user_agent", [WIKIPEDIA_USER_AGENT, WEATHER_USER_AGENT, SPORTS_USER_AGENT, REDDIT_USER_AGENT])
def test_each_client_names_itself_with_the_contact_in_parentheses(user_agent: str) -> None:
    assert POLICY_USER_AGENT.fullmatch(user_agent)


def test_each_client_has_its_own_name() -> None:
    assert len({WIKIPEDIA_USER_AGENT, WEATHER_USER_AGENT, SPORTS_USER_AGENT, REDDIT_USER_AGENT}) == 4
