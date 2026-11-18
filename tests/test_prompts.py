from datetime import date

from assistant_core.prompts import (
    DETAILED_ANSWER_WORD_LIMIT,
    MAXIMUM_WORD_LIMIT,
    MINIMUM_WORD_LIMIT,
    SYSTEM_PROMPT,
    per_question_block,
    question_with_block,
    system_prompt,
    word_limit_after_tools_line,
    word_limit_for,
)


def test_system_prompt_is_the_same_for_every_question_so_it_stays_cached() -> None:
    assert system_prompt() == SYSTEM_PROMPT
    assert "today is" not in system_prompt().lower()


QUESTION_OF_30_WORDS = " ".join(["word"] * 30)


def test_per_question_block_carries_the_date_then_the_word_limit_then_the_directive_then_memory_inside_the_note_tags() -> None:
    block = per_question_block(date(2026, 9, 6), 96, "Routing for this question: SEARCH.\n", "likes trams")
    lines = block.split("\n")
    assert lines[0] == "<assistant_software_note>"
    assert lines[1].startswith("Today is Sunday, September 6, 2026.")
    assert lines[2] == "Answer word limit: about 96 spoken words."
    assert lines[3] == "Routing for this question: SEARCH."
    assert block.endswith("What you remember about this user:\nlikes trams\n</assistant_software_note>")


def test_per_question_block_without_a_directive_is_the_date_and_the_word_limit() -> None:
    assert per_question_block(date(2026, 9, 6), 20).count("\n") == 3


def test_word_limit_grows_with_the_words_asked_between_a_floor_and_a_ceiling() -> None:
    assert word_limit_for("Hi") == MINIMUM_WORD_LIMIT
    assert word_limit_for(QUESTION_OF_30_WORDS) == 96
    assert word_limit_for("Is there a cheap Michelin-recognized ramen spot near Union Square?") == word_limit_for("Is there a cheap ramen spot by the park here?")
    assert word_limit_for(" ".join(["word"] * 100)) == MAXIMUM_WORD_LIMIT


def test_each_tool_call_raises_the_word_limit_up_to_the_ceiling() -> None:
    ten_words = " ".join(["word"] * 10)
    assert word_limit_for(ten_words, 2) == 32 + 40
    assert word_limit_for(QUESTION_OF_30_WORDS, 2) == MAXIMUM_WORD_LIMIT
    assert word_limit_after_tools_line(52).endswith("the answer word limit is now about 52 spoken words.")


def test_asking_for_detail_lifts_the_limit_past_the_ceiling_whatever_the_question_length_or_tool_calls() -> None:
    assert word_limit_for("But why is it called ranked choice? Explain in detail, please.") == DETAILED_ANSWER_WORD_LIMIT
    assert word_limit_for("Tell me about Plato in more detail.", 3) == DETAILED_ANSWER_WORD_LIMIT
    assert word_limit_for("Give me an in-depth, detailed explanation of llama.cpp.") == DETAILED_ANSWER_WORD_LIMIT
    assert DETAILED_ANSWER_WORD_LIMIT > MAXIMUM_WORD_LIMIT


def test_more_details_about_one_thing_is_an_ordinary_question_not_a_request_for_detail() -> None:
    question = "Use movie tools to get more details about Crunchyroll anime night's sneak peek."
    assert word_limit_for(question) == round(3.2 * len(question.split()))


def test_asking_to_repeat_keeps_the_previous_answer_length() -> None:
    sixty_four_word_answer = " ".join(["word"] * 64)
    assert word_limit_for("Can you repeat that?", previous_answer=sixty_four_word_answer) == 64
    assert word_limit_for("Repeat what you said.", previous_answer=sixty_four_word_answer) == 64
    assert word_limit_for("The voice didn't come through for your last reply. Can you reread it to me?", previous_answer=sixty_four_word_answer) == 64
    assert word_limit_for("Say that again?", previous_answer="Yes.") == MINIMUM_WORD_LIMIT


def test_a_question_that_uses_the_word_repeat_otherwise_is_counted_as_usual() -> None:
    question = "Will the Dodgers repeat as champions next year?"
    assert word_limit_for(question, previous_answer=" ".join(["word"] * 100)) == round(3.2 * len(question.split()))


def test_question_with_block_puts_the_question_last() -> None:
    assert question_with_block("Who wrote Emma?", "Today is Sunday.") == "Today is Sunday.\nThe user said: Who wrote Emma?"
