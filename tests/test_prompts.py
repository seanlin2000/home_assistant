from datetime import date

from assistant_core.prompts import MAXIMUM_WORD_LIMIT, MINIMUM_WORD_LIMIT, SYSTEM_PROMPT, per_question_block, question_with_block, system_prompt, word_limit_for


def test_system_prompt_is_the_same_for_every_question_so_it_stays_cached() -> None:
    assert system_prompt() == SYSTEM_PROMPT
    assert "today is" not in system_prompt().lower()


QUESTION_OF_200_CHARACTERS = "x" * 200


def test_per_question_block_carries_the_date_then_the_word_limit_then_the_directive_then_memory() -> None:
    block = per_question_block(date(2026, 9, 6), QUESTION_OF_200_CHARACTERS, "Routing for this question: SEARCH.\n", "likes trams")
    lines = block.split("\n")
    assert "today is Sunday, September 6, 2026." in lines[0]
    assert lines[1] == "Answer word limit: about 120 spoken words."
    assert lines[2] == "Routing for this question: SEARCH."
    assert block.endswith("What you remember about this user:\nlikes trams")


def test_per_question_block_without_a_directive_is_the_date_and_the_word_limit() -> None:
    assert per_question_block(date(2026, 9, 6), "Who wrote Emma?").count("\n") == 1


def test_word_limit_grows_with_the_question_between_a_floor_and_a_ceiling() -> None:
    assert word_limit_for("Hi") == MINIMUM_WORD_LIMIT
    assert word_limit_for(QUESTION_OF_200_CHARACTERS) == 120
    assert word_limit_for("x" * 1000) == MAXIMUM_WORD_LIMIT


def test_question_with_block_puts_the_question_last() -> None:
    assert question_with_block("Who wrote Emma?", "Today is Sunday.") == "Today is Sunday.\nQuestion: Who wrote Emma?"
