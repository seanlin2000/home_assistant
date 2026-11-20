"""The shared passage ranker on small made-up pages: words of the page's title set aside, rare words outranking common ones, short exact rows outranking
long ones, and a selection whose headings and notes fit the budget without cutting a line short. The 49ers article in test_wikipedia_lookup.py covers
the guarantees the ranker kept from the Wikipedia tool."""

import re

from utils.passage_utils import BLOCK_SEPARATOR, LEFT_OUT_NOTE, select_passages
from utils.text_utils import word_count

LEAD = "A kill confirm is a fast attack that reliably leads into a knockout at high percents."
FILLER = "Players practise these setups often, because they change with the opponent's weight, falling speed, and the version of the game being played."


def note_pattern(template: str) -> re.Pattern[str]:
    return re.compile(re.escape(template).replace(re.escape("{count}"), r"\d+"))


NOTE = note_pattern(LEFT_OUT_NOTE)


def page(*blocks: str) -> str:
    return BLOCK_SEPARATOR.join(blocks)


def table(*rows: str) -> str:
    return "\n".join(rows)


SETUPS_PAGE = page(
    "# Kill confirm",
    LEAD,
    "## Setups",
    table("Character | Setup", "Mario | A kill confirm off a throw, the classic kill confirm", "Roy | Jab to back aerial"),
    "## History",
    *[FILLER] * 6,
)


def test_words_of_the_page_title_are_set_aside_for_the_rest_of_the_focus() -> None:
    selected = select_passages(SETUPS_PAGE, "kill confirm jab", 60, page_title="Kill confirm - SmashWiki")
    assert "Roy | Jab to back aerial" in selected and "Mario |" not in selected
    assert "Mario |" in select_passages(SETUPS_PAGE, "kill confirm jab", 60)


def test_a_focus_made_only_of_title_words_keeps_them_all() -> None:
    selected = select_passages(SETUPS_PAGE, "kill confirm", 40, page_title="Kill confirm")
    assert "Mario | A kill confirm off a throw, the classic kill confirm" in selected


def test_a_heading_above_all_the_text_names_the_page_and_the_lead_still_comes_first() -> None:
    assert select_passages(SETUPS_PAGE, "jab", 40).startswith(LEAD)


def test_a_rare_word_outranks_two_common_ones() -> None:
    rows = [f"Fighter {number} | Every character has a move here, and this table describes each of those moves at some length for the reader" for number in range(8)]
    moves_page = page(LEAD, "## Moves", table("Character | Notes", *rows, "Roy | A jab"), "## History", *[FILLER] * 4)
    selected = select_passages(moves_page, "character move jab", 50)
    assert "Roy | A jab" in selected and "Fighter 0 |" not in selected


def test_a_short_row_outranks_a_long_one_with_the_same_words() -> None:
    long_row = "Falco | A jab " + "that is followed by a long description of every other option the character has " * 4 + "and a back aerial"
    short_row = "Chrom | A jab, then a tilt, then a back aerial"
    rows_page = page(LEAD, "## Setups", table("Character | Setup", long_row, short_row), "## History", *[FILLER] * 4)
    selected = select_passages(rows_page, "jab back", word_count(LEAD) + word_count(long_row) + 8)
    assert short_row in selected and "Falco |" not in selected


VERSION_SECTIONS = [page(f"## Version {version}", table("Character | Setup", *[f"Fighter {version}{row} | Jab to back aerial at high percents" for row in range(6)])) for version in range(5)]
LONG_PAGE = page(LEAD, *VERSION_SECTIONS)


def test_headings_and_notes_are_paid_for_so_no_line_is_cut_short() -> None:
    selected = select_passages(LONG_PAGE, "jab back aerial", 80)
    whole_lines = set(LONG_PAGE.split("\n"))
    assert word_count(selected) <= 80
    assert all(line in whole_lines or NOTE.fullmatch(line) for line in selected.split("\n"))
    assert NOTE.search(selected)


def test_a_caller_note_replaces_the_default_and_its_words_are_paid_for() -> None:
    long_note = "[{count} more matching lines here did not fit; to see them, ask again with a narrower focus, such as a year]"
    selected = select_passages(LONG_PAGE, "jab back aerial", 80, left_out_note=long_note)
    assert word_count(selected) <= 80
    assert note_pattern(long_note).search(selected) and not NOTE.search(selected)
