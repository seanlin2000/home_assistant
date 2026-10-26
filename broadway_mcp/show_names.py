"""Finding the show a user named in TodayTix's listing, however the name reached the model: part of a title ("Rocky Horror"), a title with words
around it ("Chicago the musical", "Hamilton tickets"), or a speech-to-text slip ("Hamilten").

Both names are reduced to their words first: lowercase, no accents or punctuation, "&" read as "and", and the words people put around a title
(the, musical, Broadway) left out. Four rules are then tried from strictest to loosest, and the first that finds any show decides.
"""

import re
import unicodedata
from difflib import SequenceMatcher
from enum import IntEnum

from pydantic import BaseModel

from broadway_mcp.shows import Show

WORDS_AROUND_A_TITLE = frozenset({"the", "a", "an", "musical", "show", "play", "on", "broadway", "off"})
SHORTEST_WORD_WITH_SLIPS = 4  # "six" and "sex" are one letter apart; a short word must be said exactly
SIMILAR_WORD_RATIO = 0.85  # "hamilten" and "hamilton" are 0.875, "hadestowne" and "hadestown" 0.95; "petra" and "opera" only 0.8
SIMILAR_NAME_RATIO = 0.75


class MatchRule(IntEnum):
    SAME_WORDS = 0
    EVERY_WORD_ASKED_IS_IN_THE_NAME = 1
    EVERY_WORD_OF_THE_NAME_WAS_ASKED = 2
    SIMILAR_NAME = 3


class ShowsNamed(BaseModel):
    rule: MatchRule | None  # None when no show matched
    shows: list[Show]  # shortest name first, then most viewed


def shows_named(shows: list[Show], asked: str) -> ShowsNamed:
    asked_words = title_words(asked)
    if not asked_words:  # every show's name holds every word of nothing
        return ShowsNamed(rule=None, shows=[])
    ruled = [(rule, show) for show in shows if (rule := match_rule(asked_words, title_words(show.name))) is not None]
    if not ruled:
        return ShowsNamed(rule=None, shows=[])
    best = min(rule for rule, _ in ruled)
    found = sorted((show for rule, show in ruled if rule == best), key=lambda show: (len(title_words(show.name)), -show.views_count))
    return ShowsNamed(rule=best, shows=found)


def title_words(name: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().replace("&", " and ").replace("'", "")
    words = re.sub(r"[^a-z0-9]", " ", plain).split()
    title = [word for word in words if word not in WORDS_AROUND_A_TITLE]
    return title or words  # a title made only of such words ("The Play") keeps them


def match_rule(asked: list[str], name: list[str]) -> MatchRule | None:
    if asked == name:
        return MatchRule.SAME_WORDS
    if all(word_in(word, name) for word in asked):
        return MatchRule.EVERY_WORD_ASKED_IS_IN_THE_NAME
    if set(name) <= set(asked):  # exact words only: a one-word title like Petra would otherwise be found in "Phantom of the Opera"
        return MatchRule.EVERY_WORD_OF_THE_NAME_WAS_ASKED
    if SequenceMatcher(None, " ".join(asked), " ".join(name)).ratio() >= SIMILAR_NAME_RATIO:
        return MatchRule.SIMILAR_NAME
    return None


def word_in(word: str, words: list[str]) -> bool:
    return any(word == other or (len(word) >= SHORTEST_WORD_WITH_SLIPS and SequenceMatcher(None, word, other).ratio() >= SIMILAR_WORD_RATIO) for other in words)
