"""Picks the parts of a long page that answer a question, within a word budget. Wikipedia articles (wikipedia_mcp.article) and ordinary web pages
(web_search_mcp.page_markdown) are both written in the format read here: blocks separated by a blank line, a heading block starting with one "#" per
level, table cells joined by " | " with one row per line, and list items starting with "- ".

A short page is returned whole. A long one keeps the opening prose, up to a quarter of the budget, then the lines that best match the focus, then
re-reads them in page order under their headings, with each kept table row preceded by its table's header row. A table or list cut by the budget is
cut at the end, never in the middle, and says how many matching lines it lost, so a cut list is never read as the whole list.

Lines are ranked with BM25, the scoring behind most text search engines:

- a focus word counts for more the fewer lines it appears on, so "jab" outweighs "character" on a page where every table has a Character column;
- a long line does not win only by having more words, because a word's weight falls with the line's length;
- a focus word in a heading counts for every line under it, so asking for "starting quarterbacks" keeps the rows of the "Starting quarterbacks"
  table even though no row says so;
- focus words a few words apart score extra, so "Jab to back aerial" outranks a line that says "jab" in one sentence and "back" in another.

Focus words that appear in the page's title are set aside, because the title names what every line of the page is about; when that would leave no
words, they all stay. A year in the focus reads as "from then on", because list questions name a starting year ("since 2000") far more often than a
single one: lines naming only earlier years are left out, and lines naming that year or a later one rank first, in BM25 order among themselves.
Plurals match their singular.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import cached_property
from itertools import combinations
from typing import NamedTuple

from utils.text_utils import clip_to_words, word_count

BLOCK_SEPARATOR = "\n\n"
CELL_SEPARATOR = " | "
LIST_ITEM_PREFIX = "- "
HEADING_MARK = "#"
HEADING = re.compile(rf"^{HEADING_MARK}{{1,6}}(?:\s|$)")  # "## Moves", never a hashtag or "#1 single"
PAGE_TITLE_LEVEL = 1  # a level-1 heading above all the text names the page; Wikipedia articles start their headings at level 2
YEAR = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")
WORD = re.compile(r"[a-z0-9]+")
MIN_FOCUS_WORD_LENGTH = 3
LEFT_OUT_NOTE = "[{count} more matching lines here did not fit; to see them, ask again with a narrower focus, such as a year]"
NOTE_WORDS = len(LEFT_OUT_NOTE.split())
LEAD_SHARE_OF_BUDGET = 4  # the opening prose may take up to a quarter of the words, leaving the rest for what the focus asks about
TERM_SATURATION = 1.2  # BM25's k1: a word's second appearance in a line adds less than its first
LENGTH_NORMALIZATION = 0.75  # BM25's b: how strongly a line longer than the page's average is discounted
HEADING_MATCH_SHARE = 0.5  # a focus word in a heading counts half as much as in the line itself, since it is shared by every line below it
PROXIMITY_WINDOW = 3  # "jab to back": focus words at most this many words apart count as one phrase
STOPWORDS = frozenset(
    {"the", "and", "for", "with", "since", "from", "what", "who", "whom", "how", "many", "much", "did", "does", "was", "were", "have", "has", "are", "list", "which", "when", "where"}
    | {"about", "after", "before", "during", "their", "there", "this", "that", "ever", "all", "any", "most", "than", "into", "been", "being", "wikipedia"}
)


@dataclass(frozen=True)
class FocusTerms:
    words: frozenset[str]
    earliest_year: int | None

    @classmethod
    def from_text(cls, focus: str, page_title: str) -> "FocusTerms":
        years = [int(year) for year in YEAR.findall(focus)]
        words = frozenset(normalized(word) for word in WORD.findall(focus.lower()) if len(word) >= MIN_FOCUS_WORD_LENGTH and word not in STOPWORDS and not YEAR.fullmatch(word))
        return cls(words=(words - words_of(page_title)) or words, earliest_year=min(years) if years else None)

    @property
    def is_empty(self) -> bool:
        return not self.words and self.earliest_year is None


@dataclass(frozen=True)
class Passage:
    text: str
    headings: tuple[str, ...]  # the heading lines it sits under, outermost first
    block_index: int  # paragraphs are blocks of one line; every row of a table, or item of a list, shares its block
    header_index: int | None  # for a table row below the first, the index of its table's header row
    is_table_header: bool
    is_opening_prose: bool

    @property
    def word_count(self) -> int:
        return word_count(self.text)

    @cached_property
    def words(self) -> tuple[str, ...]:
        return tuple(normalized(word) for word in WORD.findall(self.text.lower()))

    @cached_property
    def heading_words(self) -> set[str]:
        return words_of(" ".join(self.headings))

    @cached_property
    def years(self) -> list[int]:
        return [int(year) for year in YEAR.findall(self.text)]


class Relevance(NamedTuple):
    """Compared field by field, so a line naming a year asked about outranks every line that does not, whatever their word scores."""

    names_a_year_asked_about: bool
    word_score: float


NO_RELEVANCE = Relevance(names_a_year_asked_about=False, word_score=0.0)


@dataclass(frozen=True)
class RelevanceScorer:
    """BM25 with the page's own lines as the collection, plus the heading and proximity bonuses and the year rule the module docstring describes."""

    terms: FocusTerms
    word_weights: dict[str, float]  # each focus word's inverse document frequency over the page's lines
    average_line_length: float

    @classmethod
    def for_page(cls, passages: list[Passage], terms: FocusTerms) -> "RelevanceScorer":
        line_count = len(passages)
        lines_with = Counter(word for passage in passages for word in set(passage.words) if word in terms.words)
        word_weights = {word: inverse_document_frequency(line_count, lines_with[word]) for word in terms.words}
        average_line_length = sum(len(passage.words) for passage in passages) / max(line_count, 1)
        return cls(terms=terms, word_weights=word_weights, average_line_length=max(average_line_length, 1.0))

    def relevance(self, passage: Passage) -> Relevance:
        """A header row has none of its own: it is kept only with a row of its table."""
        if passage.is_table_header or self._names_only_earlier_years(passage):
            return NO_RELEVANCE
        names_a_year_asked_about = self.terms.earliest_year is not None and bool(passage.years)
        return Relevance(names_a_year_asked_about, self._term_score(passage) + self._proximity_score(passage) + self._heading_score(passage))

    def _names_only_earlier_years(self, passage: Passage) -> bool:
        return self.terms.earliest_year is not None and bool(passage.years) and max(passage.years) < self.terms.earliest_year

    def _term_score(self, passage: Passage) -> float:
        length_factor = 1 - LENGTH_NORMALIZATION + LENGTH_NORMALIZATION * len(passage.words) / self.average_line_length
        counts = Counter(word for word in passage.words if word in self.terms.words)
        return sum(self.word_weights[word] * count * (TERM_SATURATION + 1) / (count + TERM_SATURATION * length_factor) for word, count in counts.items())

    def _proximity_score(self, passage: Passage) -> float:
        """Each pair of different focus words found close together adds the weight of the rarer-scoring one, once per pair."""
        positions = [(position, word) for position, word in enumerate(passage.words) if word in self.terms.words]
        close_pairs = {frozenset((first[1], second[1])) for first, second in combinations(positions, 2) if first[1] != second[1] and second[0] - first[0] <= PROXIMITY_WINDOW}
        return sum(min(self.word_weights[word] for word in pair) for pair in close_pairs)

    def _heading_score(self, passage: Passage) -> float:
        return HEADING_MATCH_SHARE * sum(self.word_weights[word] for word in self.terms.words & passage.heading_words)


@dataclass
class BudgetedSelection:
    """Keeps lines in the order offered while their cost fits. A line's cost counts everything printed with it: its table's header row, any heading
    not yet paid for, and the left-out note its table or list will need if the line leaves matching lines of that block behind; the note is paid
    back when the block's last matching line is kept. A line that does not fit is passed over for shorter ones, but the rest of its table or list is
    passed over with it, because a list with a gap in the middle reads as complete and would be counted wrong."""

    passages: list[Passage]
    budget: int
    unkept_matches: Counter[int]  # by block, the matching lines not yet kept
    kept: set[int] = field(default_factory=set)
    closed_blocks: set[int] = field(default_factory=set)
    noted_blocks: set[int] = field(default_factory=set)
    paid_headings: set[tuple[str, ...]] = field(default_factory=set)
    used: int = 0

    def offer(self, index: int) -> None:
        block_index = self.passages[index].block_index
        if block_index in self.closed_blocks:
            return
        wanted = self._lines_brought_by(index) - self.kept
        new_headings = self._headings_above(index) - self.paid_headings
        cost = sum(self.passages[line].word_count for line in wanted) + sum(word_count(heading[-1]) for heading in new_headings) + self._note_cost_change(block_index)
        if self.used + cost > self.budget:
            self.closed_blocks.add(block_index)
            return
        self.kept |= wanted
        self.paid_headings |= new_headings
        self.used += cost
        self._count_kept_match(block_index)

    def _lines_brought_by(self, index: int) -> set[int]:
        header_index = self.passages[index].header_index
        return {index} | ({header_index} if header_index is not None else set())

    def _headings_above(self, index: int) -> set[tuple[str, ...]]:
        headings = self.passages[index].headings
        return {headings[: depth + 1] for depth in range(len(headings))}

    def _note_cost_change(self, block_index: int) -> int:
        leaves_matches_behind = self.unkept_matches[block_index] > 1
        if leaves_matches_behind and block_index not in self.noted_blocks:
            return NOTE_WORDS
        return -NOTE_WORDS if not leaves_matches_behind and block_index in self.noted_blocks else 0

    def _count_kept_match(self, block_index: int) -> None:
        self.unkept_matches[block_index] -= 1
        if self.unkept_matches[block_index] > 0:
            self.noted_blocks.add(block_index)
        else:
            self.noted_blocks.discard(block_index)


def select_passages(text: str, focus: str, max_words: int, page_title: str = "") -> str:
    terms = FocusTerms.from_text(focus, page_title)
    if word_count(text) <= max_words or terms.is_empty:
        return clip_to_words(text, max_words)
    passages = parse_passages(text)
    scorer = RelevanceScorer.for_page(passages, terms)
    lines = lines_within_budget(passages, [scorer.relevance(passage) for passage in passages], max_words)
    return clip_to_words("\n".join(lines), max_words) if lines else clip_to_words(text, max_words)


def lines_within_budget(passages: list[Passage], relevances: list[Relevance], max_words: int) -> list[str]:
    """The opening prose, then the best-matching lines in the words left. The selection already pays for every heading and note it prints; should
    the printed lines still run over, because a heading is printed again when a kept line from another section sits between its lines, the overflow
    is taken off the budget and the lines picked again, so no line is ever cut short."""
    opening = opening_prose_indexes(passages, max_words // LEAD_SHARE_OF_BUDGET)
    budget = max_words - sum(passages[index].word_count for index in opening)
    while budget > 0:
        related = related_indexes(passages, relevances, budget)
        if not related:
            return []
        lines = lines_in_page_order(passages, opening | related, left_out_lines(passages, relevances, related))
        overflow = word_count("\n".join(lines)) - max_words
        if overflow <= 0:
            return lines
        budget -= overflow
    return []


def parse_passages(text: str) -> list[Passage]:
    passages: list[Passage] = []
    open_headings: list[str] = []
    for block_index, block in enumerate(text.split(BLOCK_SEPARATOR)):
        if is_page_title(block, passages):
            continue
        if is_heading(block):
            open_headings = [heading for heading in open_headings if heading_level(heading) < heading_level(block)] + [block]
            continue
        passages.extend(block_passages(block, tuple(open_headings), block_index, len(passages)))
    return passages


def is_page_title(block: str, passages_so_far: list[Passage]) -> bool:
    """The page's own name, above all its text, is not a section: the lines below it are still the opening prose."""
    return not passages_so_far and is_heading(block) and heading_level(block) == PAGE_TITLE_LEVEL


def block_passages(block: str, headings: tuple[str, ...], block_index: int, first_index: int) -> list[Passage]:
    lines = block.split("\n")
    has_header_row = CELL_SEPARATOR in lines[0] and len(lines) > 1
    return [
        Passage(
            text=line,
            headings=headings,
            block_index=block_index,
            header_index=first_index if has_header_row and position > 0 else None,
            is_table_header=has_header_row and position == 0,
            is_opening_prose=not headings and len(lines) == 1,  # a lead paragraph; the infobox beside it is a table like any other
        )
        for position, line in enumerate(lines)
    ]


def opening_prose_indexes(passages: list[Passage], budget: int) -> set[int]:
    kept: set[int] = set()
    used = 0
    for index, passage in enumerate(passages):
        if not passage.is_opening_prose or (kept and used + passage.word_count > budget):
            continue
        kept.add(index)
        used += passage.word_count
    return kept


def related_indexes(passages: list[Passage], relevances: list[Relevance], budget: int) -> set[int]:
    """Most related first, earlier first among equals (a reversed sort stays stable)."""
    matching = matching_indexes(passages, relevances)
    selection = BudgetedSelection(passages, budget, Counter(passages[index].block_index for index in matching))
    for index in sorted(matching, key=relevances.__getitem__, reverse=True):
        selection.offer(index)
    return selection.kept


def matching_indexes(passages: list[Passage], relevances: list[Relevance]) -> list[int]:
    return [index for index, passage in enumerate(passages) if relevances[index] > NO_RELEVANCE and not passage.is_opening_prose]


def left_out_lines(passages: list[Passage], relevances: list[Relevance], kept: set[int]) -> Counter[int]:
    """How many matching lines each partly kept table or list lost to the budget."""
    kept_blocks = {passages[index].block_index for index in kept}
    return Counter(passages[index].block_index for index in matching_indexes(passages, relevances) if index not in kept and passages[index].block_index in kept_blocks)


def lines_in_page_order(passages: list[Passage], kept: set[int], left_out: Counter[int]) -> list[str]:
    lines: list[str] = []
    printed_headings: tuple[str, ...] = ()
    ordered = sorted(kept)
    for position, index in enumerate(ordered):
        headings = passages[index].headings
        lines.extend(headings[shared_prefix_length(printed_headings, headings) :])
        printed_headings = headings
        lines.append(passages[index].text)
        block_index = passages[index].block_index
        next_block_index = passages[ordered[position + 1]].block_index if position + 1 < len(ordered) else None
        if block_index != next_block_index and left_out[block_index]:
            lines.append(LEFT_OUT_NOTE.format(count=left_out[block_index]))
    return lines


def shared_prefix_length(printed: tuple[str, ...], wanted: tuple[str, ...]) -> int:
    length = 0
    while length < min(len(printed), len(wanted)) and printed[length] == wanted[length]:
        length += 1
    return length


def inverse_document_frequency(line_count: int, lines_with_word: int) -> float:
    """BM25's form, which stays positive even for a word on most lines."""
    return math.log(1 + (line_count - lines_with_word + 0.5) / (lines_with_word + 0.5))


def is_heading(line: str) -> bool:
    return HEADING.match(line) is not None


def heading_level(heading: str) -> int:
    return len(heading) - len(heading.lstrip(HEADING_MARK))


def words_of(text: str) -> set[str]:
    return {normalized(word) for word in WORD.findall(text.lower())}


def normalized(word: str) -> str:
    """Plurals match their singular ("quarterbacks", "quarterback"); nothing subtler is needed to tell a related line from an unrelated one."""
    return word[:-1] if word.endswith("s") and len(word) > MIN_FOCUS_WORD_LENGTH else word
