from datetime import date

from assistant_core.prompts import SYSTEM_PROMPT, per_question_block, question_with_block, system_prompt


def test_system_prompt_is_the_same_for_every_question_so_it_stays_cached() -> None:
    assert system_prompt() == SYSTEM_PROMPT
    assert "today is" not in system_prompt().lower()


def test_per_question_block_carries_the_date_then_the_directive_then_memory() -> None:
    block = per_question_block(date(2026, 9, 6), "Routing for this question: SEARCH.\n", "likes trams")
    lines = block.split("\n")
    assert "today is Sunday, September 6, 2026." in lines[0]
    assert lines[1] == "Routing for this question: SEARCH."
    assert block.endswith("What you remember about this user:\nlikes trams")


def test_per_question_block_without_a_directive_is_only_the_date() -> None:
    assert per_question_block(date(2026, 9, 6)).count("\n") == 0


def test_question_with_block_puts_the_question_last() -> None:
    assert question_with_block("Who wrote Emma?", "Today is Sunday.") == "Today is Sunday.\nQuestion: Who wrote Emma?"
