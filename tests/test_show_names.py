"""How broadway_show_details finds the show a user named: part of a title, a title with words around it, and speech-to-text slips find the show;
a show TodayTix does not list finds nothing rather than a show with a similar word. The names are the benchmark's snapshot of 2026-10-25."""

import pytest

from benchmark.mcp_process import BROADWAY_SNAPSHOT_PATH
from broadway_mcp.show_names import MatchRule, shows_named, title_words
from broadway_mcp.shows import BroadwaySnapshot
from utils.snapshot_utils import read_snapshot

SHOWS = read_snapshot(BROADWAY_SNAPSHOT_PATH, BroadwaySnapshot).shows


@pytest.mark.parametrize(
    ("asked", "rule", "found"),
    [
        ("Rocky Horror", MatchRule.SAME_WORDS, "The Rocky Horror Show"),
        ("Chicago the musical", MatchRule.SAME_WORDS, "Chicago"),
        ("and Juliet", MatchRule.SAME_WORDS, "& Juliet"),
        ("Oh Mary", MatchRule.SAME_WORDS, "Oh, Mary!"),
        ("Mormon", MatchRule.EVERY_WORD_ASKED_IS_IN_THE_NAME, "The Book of Mormon"),
        ("cursed child", MatchRule.EVERY_WORD_ASKED_IS_IN_THE_NAME, "Harry Potter and the Cursed Child"),
        ("Awake and Sing", MatchRule.EVERY_WORD_ASKED_IS_IN_THE_NAME, "Clifford Odets' Awake and Sing!"),
        ("Hamilten", MatchRule.EVERY_WORD_ASKED_IS_IN_THE_NAME, "Hamilton"),
        ("Hamilton tickets", MatchRule.EVERY_WORD_OF_THE_NAME_WAS_ASKED, "Hamilton"),
        ("Wicked witch", MatchRule.EVERY_WORD_OF_THE_NAME_WAS_ASKED, "Wicked"),
        ("Hades Town", MatchRule.SIMILAR_NAME, "Hadestown"),
    ],
)
def test_a_title_said_in_part_around_or_with_a_slip_finds_its_show(asked: str, rule: MatchRule, found: str) -> None:
    named = shows_named(SHOWS, asked)
    assert (named.rule, [show.name for show in named.shows]) == (rule, [found])


@pytest.mark.parametrize("asked", ["Phantom of the Opera", "Les Miserables", "Mamma Mia", "Moulin Rouge", "Rent", "Cats", "Sweeney Todd", "", "?!"])
def test_a_show_todaytix_does_not_list_finds_nothing(asked: str) -> None:
    assert shows_named(SHOWS, asked).shows == []


def test_a_word_in_two_titles_finds_both_shortest_first() -> None:
    assert [show.name for show in shows_named(SHOWS, "Juliet").shows] == ["& Juliet", "Drunk Romeo & Juliet NYC"]


def test_title_words_drop_punctuation_accents_and_the_words_around_a_title() -> None:
    assert title_words("Clifford Odets' Awake and Sing!") == ["clifford", "odets", "awake", "and", "sing"]
    assert title_words("Café Society on Broadway") == ["cafe", "society"]
    assert title_words("The Play") == ["the", "play"]
