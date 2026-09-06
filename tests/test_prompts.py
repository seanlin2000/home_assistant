from datetime import date

from assistant_core.prompts import SYSTEM_PROMPT, system_prompt


def test_system_prompt_puts_the_date_on_the_second_line_and_keeps_the_rest_intact() -> None:
    text = system_prompt(date(2026, 9, 6))
    lines = text.split("\n")
    assert lines[0] == SYSTEM_PROMPT.split("\n")[0]
    assert lines[1].startswith("Today is Sunday, September 6, 2026.")
    assert text.endswith(SYSTEM_PROMPT.split("\n\n", 1)[1])


def test_system_prompt_defaults_to_today() -> None:
    assert f"{date.today():%B %-d, %Y}" in system_prompt()
