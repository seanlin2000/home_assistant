"""The User-Agent our own API clients send (Wikipedia, Met.no and Open-Meteo, ESPN, Arctic Shift), as opposed to the current-Chrome agent page
reads send (utils/browser_utils.py).

It names the application and gives the repository as the way to reach its owner, so no personal address leaves the network. The form is the one
Wikimedia's User-Agent policy spells out: name/version, then the contact in parentheses with its scheme. It matters: on 2026-10-31 Wikimedia
refused the contact written bare, without parentheses or https, with "403 Please respect our robot policy".
"""

PROJECT_CONTACT = "https://github.com/seanlin2000/home_assistant"


def descriptive_user_agent(client_name: str) -> str:
    return f"studio-assistant-{client_name}/1.0 ({PROJECT_CONTACT})"
