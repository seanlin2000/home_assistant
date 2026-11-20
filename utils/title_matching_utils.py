"""Finding the title a user named among a listing's titles, however the name reached the model: part of a title ("Rocky Horror"), a title with words
around it ("Chicago the musical", "Hamilton tickets"), or a speech-to-text slip ("Hamilten"). The Broadway and movies tools match show, film, and
theater names with it.

Both names are reduced to their words first: lowercase, no accents or punctuation, "&" read as "and", and the words a listing's own kind of title is
said with (the, musical, movie) left out. Four rules are then tried from strictest to loosest, and the first that finds any title decides.
"""

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import IntEnum

SHORTEST_WORD_WITH_SLIPS = 4  # "six" and "sex" are one letter apart; a short word must be said exactly
SIMILAR_WORD_RATIO = 0.85  # "hamilten" and "hamilton" are 0.875, "hadestowne" and "hadestown" 0.95; "petra" and "opera" only 0.8
SIMILAR_NAME_RATIO = 0.75


class MatchRule(IntEnum):
    SAME_WORDS = 0
    EVERY_WORD_ASKED_IS_IN_THE_NAME = 1
    EVERY_WORD_OF_THE_NAME_WAS_ASKED = 2
    SIMILAR_NAME = 3


@dataclass(frozen=True)
class TitleMatches:
    rule: MatchRule | None  # None when no title matched
    titles: list[str]  # fewest words first, in the order given among equals


class TitleMatcher:
    """Matches names against one kind of title, leaving out the words that kind is said with."""

    def __init__(self, words_around_a_title: frozenset[str]) -> None:
        self.words_around_a_title = words_around_a_title

    def matches(self, asked: str, titles: list[str]) -> TitleMatches:
        asked_words = self.title_words(asked)
        if not asked_words:  # every title holds every word of nothing
            return TitleMatches(rule=None, titles=[])
        ruled = [(rule, title) for title in titles if (rule := match_rule(asked_words, self.title_words(title))) is not None]
        if not ruled:
            return TitleMatches(rule=None, titles=[])
        best = min(rule for rule, _ in ruled)
        return TitleMatches(rule=best, titles=sorted((title for rule, title in ruled if rule == best), key=lambda title: len(self.title_words(title))))

    def title_words(self, name: str) -> list[str]:
        plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().replace("&", " and ").replace("'", "").replace("’", "")
        words = re.sub(r"[^a-z0-9]", " ", plain).split()
        title = [word for word in words if word not in self.words_around_a_title]
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
