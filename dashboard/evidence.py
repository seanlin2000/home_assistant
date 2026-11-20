"""Split a tool result into its sources and measure how much of the answer each one holds (design doc v2/13 section 3.4).

A source holding most of the answer's distinctive words, the content words the question did not already contain, is likely where the answer came
from. The page highlights those words in each source and stars the sources that hold at least half of them.
"""

import re
from urllib.parse import urlparse

from pydantic import BaseModel

from web_search_mcp.register import NOT_FOUND_INSTRUCTION

STARRED_COVERAGE = 0.5
UNTRUSTED_WRAPPER = re.compile(r"^<untrusted source=\"[^\"]*\">\n(.*)\n</untrusted>$", re.DOTALL)
SOURCE_START = re.compile(r"^\[(\d+)\] (.*)$", re.MULTILINE)
URL_LINE = re.compile(r"^\s*(?:URL: )?(https?://\S+)\s*$", re.MULTILINE)
NOT_READ_MARK = " (not read)"
WORD = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*")
MIN_TERM_LENGTH = 3
STOPWORDS = frozenset("""about above after again against all also and any are around because been before being below between both but can could did does doing down
    during each few for from further had has have having her here hers him his how into its itself just let like may more most much must not now off
    once only other our ours out over own said same she should since some such than that the their theirs them then there these they this those
    through too under until upon very was were what when where which while who whom whose why will with would yes yet you your yours one two per
    according roughly approximately likely currently""".split())


class Source(BaseModel):
    rank: int | None = None
    title: str
    url: str | None = None
    site: str | None = None
    text: str
    read: bool = True
    coverage: float = 0.0
    starred: bool = False


class ToolEvidence(BaseModel):
    header: str = ""
    sources: list[Source]
    footer: str = ""
    terms: list[str]


def tool_evidence(result: str, answer: str, question: str) -> ToolEvidence:
    """The sources in one tool result, each scored against the answer's distinctive words."""
    text = without_untrusted_wrapper(result)
    terms = distinctive_terms(answer, question)
    body, footer = without_footer(text)
    header, sources = split_sources(body)
    for source in sources:
        score_source(source, terms)
    return ToolEvidence(header=header, sources=sources, footer=footer, terms=terms)


def without_untrusted_wrapper(result: str) -> str:
    match = UNTRUSTED_WRAPPER.match(result.strip())
    return match.group(1) if match else result


def without_footer(text: str) -> tuple[str, str]:
    """Search results end with an instruction to the model, which belongs to no source."""
    stripped = text.rstrip()
    if stripped.endswith(NOT_FOUND_INSTRUCTION):
        return stripped.removesuffix(NOT_FOUND_INSTRUCTION).rstrip(), NOT_FOUND_INSTRUCTION
    return text, ""


def distinctive_terms(answer: str, question: str) -> list[str]:
    """The answer's content words, in order and without repeats, minus stopwords and the words the question already used."""
    asked = set(words_in(question))
    terms: list[str] = []
    for word in words_in(answer):
        if word not in asked and word not in STOPWORDS and word not in terms and (len(word) >= MIN_TERM_LENGTH or word.isdigit()):
            terms.append(word)
    return terms


def words_in(text: str) -> list[str]:
    return [word.strip(".,") for word in WORD.findall(text.lower())]


def split_sources(text: str) -> tuple[str, list[Source]]:
    """Search results number their sources "[1] Title"; any other result (a calculation, a forecast, an article) is one source of its own."""
    starts = list(SOURCE_START.finditer(text))
    if not starts:
        return "", [whole_result_source(text)]
    ends = [start.start() for start in starts[1:]] + [len(text)]
    return text[: starts[0].start()].strip(), [numbered_source(start, text[start.end() : end]) for start, end in zip(starts, ends)]


def whole_result_source(text: str) -> Source:
    url = first_url(text)
    return Source(title=text.strip().splitlines()[0] if text.strip() else "", url=url, site=site_of(url), text=text.strip())


def numbered_source(start: re.Match, body: str) -> Source:
    """The URL line moves out of the text into the source's link, so the text is what the page said."""
    title = start.group(2)
    url = first_url(body)
    text = URL_LINE.sub("", body, count=1).strip() if url else body.strip()
    return Source(rank=int(start.group(1)), title=title.removesuffix(NOT_READ_MARK), url=url, site=site_of(url), text=text, read=not title.endswith(NOT_READ_MARK))


def first_url(text: str) -> str | None:
    match = URL_LINE.search(text)
    return match.group(1) if match else None


def site_of(url: str | None) -> str | None:
    return urlparse(url).netloc.removeprefix("www.") if url else None


def score_source(source: Source, terms: list[str]) -> None:
    if not terms:
        return
    present = set(words_in(f"{source.title} {source.text}"))
    source.coverage = round(sum(term in present for term in terms) / len(terms), 2)
    source.starred = source.coverage >= STARRED_COVERAGE
