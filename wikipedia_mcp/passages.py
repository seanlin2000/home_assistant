"""Picks the parts of a rendered article (wikipedia_mcp.article) that answer a question, within a word budget.

A short article is returned whole. A long one keeps the opening prose, then the lines that share the most words with the focus, then re-reads them in
article order under their headings, with each kept table row preceded by its table's header row. Every line under a heading that names a focus word
counts as related, so asking for "starting quarterbacks" keeps the rows of the "Starting quarterbacks" table even though no row says so. A year in the
focus reads as "from then on", because list questions name a starting year ("since 2000") far more often than a single one, and the year asked about
still comes first: lines naming only earlier years are left out, and lines naming that year or a later one rank first.
"""

import re
from collections import Counter
from dataclasses import dataclass

from utils.text_utils import clip_to_words, word_count
from wikipedia_mcp.article import BLOCK_SEPARATOR, CELL_SEPARATOR

HEADING_MARK = "#"
YEAR = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")
WORD = re.compile(r"[a-z0-9]+")
MIN_FOCUS_WORD_LENGTH = 3
YEAR_MATCH_WEIGHT = 2
LEFT_OUT_NOTE = "[{count} more matching lines here did not fit; to see them, ask again with a narrower focus, such as a year]"
LEAD_SHARE_OF_BUDGET = 4  # the opening prose may take up to a quarter of the words, leaving the rest for what the focus asks about
STOPWORDS = frozenset(
    {"the", "and", "for", "with", "since", "from", "what", "who", "whom", "how", "many", "much", "did", "does", "was", "were", "have", "has", "are", "list", "which", "when", "where"}
    | {"about", "after", "before", "during", "their", "there", "this", "that", "ever", "all", "any", "most", "than", "into", "been", "being", "wikipedia"}
)


@dataclass(frozen=True)
class FocusTerms:
    words: frozenset[str]
    earliest_year: int | None

    @classmethod
    def from_text(cls, focus: str) -> "FocusTerms":
        years = [int(year) for year in YEAR.findall(focus)]
        words = frozenset(normalized(word) for word in WORD.findall(focus.lower()) if len(word) >= MIN_FOCUS_WORD_LENGTH and word not in STOPWORDS and not YEAR.fullmatch(word))
        return cls(words=words, earliest_year=min(years) if years else None)

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

    def relevance(self, terms: FocusTerms) -> int:
        """A header row has none of its own: it is kept only with a row of its table."""
        if self.is_table_header:
            return 0
        years = [int(year) for year in YEAR.findall(self.text)]
        if terms.earliest_year is not None and years and max(years) < terms.earliest_year:
            return 0
        shared_words = len(terms.words & words_of(self.text))
        under_related_heading = 1 if terms.words & words_of(" ".join(self.headings)) else 0
        names_a_year_asked_about = YEAR_MATCH_WEIGHT if terms.earliest_year is not None and years else 0
        return shared_words + under_related_heading + names_a_year_asked_about


def select_passages(article_text: str, focus: str, max_words: int) -> str:
    terms = FocusTerms.from_text(focus)
    if word_count(article_text) <= max_words or terms.is_empty:
        return clip_to_words(article_text, max_words)
    passages = parse_passages(article_text)
    opening = opening_prose_indexes(passages, max_words // LEAD_SHARE_OF_BUDGET)
    related = related_indexes(passages, terms, max_words - sum(passages[index].word_count for index in opening))
    if not related:
        return clip_to_words(article_text, max_words)
    return clip_to_words("\n".join(lines_in_article_order(passages, opening | related, left_out_lines(passages, terms, related))), max_words)


def parse_passages(article_text: str) -> list[Passage]:
    passages: list[Passage] = []
    open_headings: list[str] = []
    for block_index, block in enumerate(article_text.split(BLOCK_SEPARATOR)):
        if block.startswith(HEADING_MARK):
            open_headings = [heading for heading in open_headings if heading_level(heading) < heading_level(block)] + [block]
            continue
        passages.extend(block_passages(block, tuple(open_headings), block_index, len(passages)))
    return passages


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


def related_indexes(passages: list[Passage], terms: FocusTerms, budget: int) -> set[int]:
    """Most related first, earlier first among equals, and a row brings its header row along. A line that does not fit is passed over for shorter ones,
    but the rest of its table or list is passed over with it: a list with a gap in the middle reads as complete and would be counted wrong."""
    scored = [(passage.relevance(terms), index) for index, passage in enumerate(passages) if not passage.is_opening_prose]
    kept: set[int] = set()
    full_blocks: set[int] = set()
    used = 0
    for _, index in sorted((item for item in scored if item[0] > 0), key=lambda item: (-item[0], item[1])):
        wanted = {index} | ({passages[index].header_index} if passages[index].header_index is not None else set())
        cost = sum(passages[wanted_index].word_count for wanted_index in wanted - kept)
        if passages[index].block_index in full_blocks:
            continue
        if used + cost > budget:
            full_blocks.add(passages[index].block_index)
            continue
        kept |= wanted
        used += cost
    return kept


def left_out_lines(passages: list[Passage], terms: FocusTerms, kept: set[int]) -> Counter[int]:
    """How many related lines each partly kept table or list lost to the budget, so a cut list is never read as the whole list."""
    kept_blocks = {passages[index].block_index for index in kept}
    return Counter(
        passage.block_index for index, passage in enumerate(passages) if index not in kept and passage.block_index in kept_blocks and not passage.is_opening_prose and passage.relevance(terms) > 0
    )


def lines_in_article_order(passages: list[Passage], kept: set[int], left_out: Counter[int]) -> list[str]:
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


def heading_level(heading: str) -> int:
    return len(heading) - len(heading.lstrip(HEADING_MARK))


def words_of(text: str) -> set[str]:
    return {normalized(word) for word in WORD.findall(text.lower())}


def normalized(word: str) -> str:
    """Plurals match their singular ("quarterbacks", "quarterback"); nothing subtler is needed to tell a related line from an unrelated one."""
    return word[:-1] if word.endswith("s") and len(word) > MIN_FOCUS_WORD_LENGTH else word
