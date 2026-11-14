from datetime import date

from assistant_core.prompts import MAXIMUM_WORD_LIMIT, MINIMUM_WORD_LIMIT, SYSTEM_PROMPT, per_question_block, question_with_block, system_prompt, word_limit_after_tools_line, word_limit_for


def test_system_prompt_is_the_same_for_every_question_so_it_stays_cached() -> None:
    assert system_prompt() == SYSTEM_PROMPT
    assert "today is" not in system_prompt().lower()


QUESTION_OF_30_WORDS = " ".join(["word"] * 30)


def test_per_question_block_carries_the_date_then_the_word_limit_then_the_directive_then_memory_inside_the_note_tags() -> None:
    block = per_question_block(date(2026, 9, 6), QUESTION_OF_30_WORDS, "Routing for this question: SEARCH.\n", "likes trams")
    lines = block.split("\n")
    assert lines[0] == "<assistant_software_note>"
    assert lines[1].startswith("Today is Sunday, September 6, 2026.")
    assert lines[2] == "Answer word limit: about 96 spoken words."
    assert lines[3] == "Routing for this question: SEARCH."
    assert block.endswith("What you remember about this user:\nlikes trams\n</assistant_software_note>")


def test_per_question_block_without_a_directive_is_the_date_and_the_word_limit() -> None:
    assert per_question_block(date(2026, 9, 6), "Who wrote Emma?").count("\n") == 3


def test_word_limit_grows_with_the_words_asked_between_a_floor_and_a_ceiling() -> None:
    assert word_limit_for("Hi") == MINIMUM_WORD_LIMIT
    assert word_limit_for(QUESTION_OF_30_WORDS) == 96
    assert word_limit_for("Is there a cheap Michelin-recognized ramen spot near Union Square?") == word_limit_for("Is there a cheap ramen spot by the park here?")
    assert word_limit_for(" ".join(["word"] * 100)) == MAXIMUM_WORD_LIMIT


def test_each_tool_call_raises_the_word_limit_up_to_the_ceiling() -> None:
    ten_words = " ".join(["word"] * 10)
    assert word_limit_for(ten_words, 2) == 32 + 40
    assert word_limit_for(QUESTION_OF_30_WORDS, 2) == MAXIMUM_WORD_LIMIT
    assert word_limit_after_tools_line(ten_words, 1).endswith("the answer word limit is now about 52 spoken words.")


def test_question_with_block_puts_the_question_last() -> None:
    assert question_with_block("Who wrote Emma?", "Today is Sunday.") == "Today is Sunday.\nThe user said: Who wrote Emma?"
