"""Turns one newsletter email into an Issue (design doc v2/14 section 3.3): checks that Gmail authenticated the sender, names the publication, and
walks the HTML's blocks into sections, leaving out ads, captions, footers, email addresses, and emoji.

Each publisher writes real headings, paragraphs, lists, and quotations inside layout tables, so a walk over those blocks keeps every article, where
trafilatura's guess at the main content dropped WSJ's headline and flattened NYT's lead story into one table cell.
"""

import hashlib
import re
from collections.abc import Iterable, Iterator
from datetime import datetime
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr
from typing import NamedTuple

from lxml import html as lxml_html
from lxml.html import HtmlElement

from newsletters_mcp.issue import Issue, Section
from utils.text_utils import HIDDEN_CHARACTERS

GMAIL_AUTHENTICATION_SERVER = "mx.google.com"
DMARC_PASS = re.compile(r"\bdmarc=pass\b", re.IGNORECASE)
HEADINGS = frozenset({"h1", "h2", "h3", "h4"})
TEXT_BLOCKS = HEADINGS | {"p", "li", "blockquote"}
TABLE_CELLS = frozenset({"td", "th"})
NEVER_READ = frozenset({"head", "script", "style", "title"})
SMALL_TEXT_PIXELS = 12.0  # photo credits and captions: WSJ's are 12 px, NYT's credits 11 px; body text is 13 px and up
FONT_SIZE = re.compile(r"font(?:-size)?\s*:[^;]*?(\d+(?:\.\d+)?)px", re.IGNORECASE)  # "font-size: 12px", or the shorthand "font: 11px/11px georgia"
HIDDEN_STYLE = re.compile(r"display\s*:\s*none|max-height\s*:\s*0|mso-hide\s*:\s*all", re.IGNORECASE)  # the inbox preview line, padded with blanks
ADVERTISEMENT_CLASS = "native-ad"  # WSJ's sponsored items: "nl-native-ad", "native-ad-flashline"
EMOJI = re.compile("[\U0001f000-\U0001faff⌀-⏿☀-➿⬀-⯿︎️⃣]")
EMAIL_ADDRESS = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
DROPPED_LINE = re.compile(
    r"^(ad|advertisement|sponsored by)$|view in browser|read in browser|unsubscribe|sign up (for|here)|subscribe here|if you[’']re not subscribed",
    re.IGNORECASE,
)
FOOTER_START = re.compile(r"^(sign up here|you received this|you are receiving|you are currently subscribed|follow us|if you received this|about us$)", re.IGNORECASE)
FOOTNOTE = re.compile(r"^\[(\d+)\]\s")
SUBJECT_PREFIX = re.compile(r"^(\S+(?: \S+){0,2}):\s+(.+)$")  # "The Morning: Taking credit"
OPENING_SECTION = "Opening"
CELL_SEPARATOR = " | "
WORD_BREAKING_TAGS = frozenset({"br", "div", "p", "td", "th", "tr", "table", "li", "h1", "h2", "h3", "h4", "blockquote"})


class SkippedMessage(ValueError):
    """A message the pull leaves out, with the reason to log; the reason names the sender's domain, never an address."""


class Block(NamedTuple):
    tag: str  # "h1" to "h4", "p", "li", "blockquote", or "tr"
    text: str


def issue_from_email(raw: bytes, received: datetime) -> Issue:
    message = BytesParser(policy=policy.default).parsebytes(raw)
    if not gmail_passed_dmarc(message):
        raise SkippedMessage(f"no dmarc=pass from {GMAIL_AUTHENTICATION_SERVER}, sent from {sender_domain(message)}")
    html = html_body(message)
    publication, headline = publication_and_headline(message, html)
    return Issue(
        publication=publication,
        subject=clean_text(str(message["Subject"] or "")),
        headline=headline,
        received=received.astimezone(),
        message_id=str(message["Message-ID"] or "").strip() or hashlib.sha256(raw).hexdigest(),
        sections=sections_from_html(html),
    )


def gmail_passed_dmarc(message: EmailMessage) -> bool:
    """Only the topmost Authentication-Results header counts: Gmail's own server writes it last, on top, and a sender can plant any header below."""
    results = message.get_all("Authentication-Results") or []
    if not results:
        return False
    topmost = str(results[0])
    return topmost.split(";", 1)[0].strip().lower() == GMAIL_AUTHENTICATION_SERVER and bool(DMARC_PASS.search(topmost))


def sender_domain(message: EmailMessage) -> str:
    return parseaddr(str(message["From"] or ""))[1].rpartition("@")[2] or "an unknown sender"


def html_body(message: EmailMessage) -> str:
    body = message.get_body(preferencelist=("html",))
    if body is None:
        raise SkippedMessage(f"no HTML part, sent from {sender_domain(message)}")
    return body.get_content()


def publication_and_headline(message: EmailMessage, html: str) -> tuple[str, str]:
    """The subject's prefix names the publication ("Money Stuff: …") when the email confirms it, as List-Id or as "the Money Stuff newsletter" in
    its text; otherwise the sender's display name does ("WSJ Markets A.M."), since a WSJ headline such as "Nvidia: …" has a prefix too."""
    subject = clean_text(str(message["Subject"] or ""))
    display_name = parseaddr(str(message["From"] or ""))[0] or sender_domain(message)
    match = SUBJECT_PREFIX.match(subject)
    if match and prefix_is_confirmed(match.group(1), str(message["List-Id"] or ""), html):
        return match.group(1), match.group(2)
    return clean_text(display_name), subject


def prefix_is_confirmed(prefix: str, list_id: str, html: str) -> bool:
    lowered = prefix.lower()
    return lowered in list_id.lower() or f"{lowered} newsletter" in " ".join(lxml_html.fromstring(html).text_content().lower().split())


def sections_from_html(html: str) -> list[Section]:
    sections = sections_from_blocks(kept_blocks(blocks_of(lxml_html.fromstring(html))))
    return [section for section in with_footnotes_moved(sections) if section.paragraphs]


def blocks_of(element: HtmlElement) -> Iterator[Block]:
    """Every heading, paragraph, list item, and quotation, and every table row of text; a block inside another is part of it, not a second block."""
    if is_left_out(element):
        return
    if element.tag in TEXT_BLOCKS:
        yield Block(element.tag, visible_text(element))
    elif element.tag == "tr" and is_row_of_text(element):
        yield from row_block(element)
    else:
        for child in element:
            yield from blocks_of(child)


def is_left_out(element: HtmlElement) -> bool:
    if not isinstance(element.tag, str) or element.tag in NEVER_READ:
        return True
    return ADVERTISEMENT_CLASS in (element.get("class") or "") or bool(HIDDEN_STYLE.search(element.get("style") or ""))


def is_row_of_text(row: HtmlElement) -> bool:
    """An innermost row: either one holding no other block, such as WSJ's headline, or a data row of several cells, such as a market quote."""
    if any(descendant.tag == "tr" for descendant in row.iterdescendants()):
        return False
    cells_with_text = [cell for cell in row if cell.tag in TABLE_CELLS and visible_text(cell)]
    return len(cells_with_text) >= 2 or not any(descendant.tag in TEXT_BLOCKS for descendant in row.iterdescendants())


def row_block(row: HtmlElement) -> Iterator[Block]:
    """A row that holds small text is a photo caption ending in its credit, and is left out whole."""
    if contains_small_text(row):
        return
    cells = [visible_text(cell) for cell in row if cell.tag in TABLE_CELLS]
    yield Block("tr", CELL_SEPARATOR.join(cell for cell in cells if cell) or visible_text(row))


def visible_text(element: HtmlElement) -> str:
    """Text nodes joined as the browser shows them: inline links and bold run straight on, and a line break or a block starts a new word."""
    return clean_text("".join(spaced(text) for text in element.xpath(".//text()") if not is_small(text_owner(text))))


def spaced(text: str) -> str:
    return f" {text}" if text.is_tail and text.getparent().tag in WORD_BREAKING_TAGS else text


def contains_small_text(element: HtmlElement) -> bool:
    return any(text.strip() and is_small(text_owner(text)) for text in element.xpath(".//text()"))


def text_owner(text: str) -> HtmlElement:
    """The element a text node sits in: lxml hands a tail to the element before it, whose parent holds it."""
    owner = text.getparent()
    return owner.getparent() if text.is_tail else owner


def is_small(element: HtmlElement) -> bool:
    size = font_size(element)
    return size is not None and size <= SMALL_TEXT_PIXELS


def font_size(element: HtmlElement) -> float | None:
    """The nearest size set on the element or around it; a zero size, which layouts set on a cell to hide its whitespace, is passed over."""
    for candidate in (element, *element.iterancestors()):
        sizes = [float(size) for size in FONT_SIZE.findall(candidate.get("style") or "") if float(size) > 0]
        if sizes:
            return sizes[-1]
    return None


def clean_text(text: str) -> str:
    return " ".join(EMOJI.sub("", HIDDEN_CHARACTERS.sub("", text)).split())


def kept_blocks(blocks: Iterable[Block]) -> Iterator[Block]:
    """Everything from the first footer line on is left out, and so is any line naming an email address or asking the reader to subscribe."""
    for block in blocks:
        if FOOTER_START.search(block.text):
            return
        if block.text and not DROPPED_LINE.search(block.text) and not EMAIL_ADDRESS.search(block.text):
            yield block


def sections_from_blocks(blocks: Iterable[Block]) -> list[Section]:
    """A heading starts a section, except that a heading with nothing under it joins the next: NYT's "TODAY'S NUMBER" and "5,000" become one."""
    sections = [Section(title=OPENING_SECTION, paragraphs=[])]
    for block in blocks:
        current = sections[-1]
        if block.tag in HEADINGS and not current.paragraphs and current.title != OPENING_SECTION:
            current.title = f"{current.title}: {block.text}"
        elif block.tag in HEADINGS:
            sections.append(Section(title=block.text, paragraphs=[]))
        else:
            current.paragraphs.append(markdown_paragraph(block))
    return sections


def markdown_paragraph(block: Block) -> str:
    prefixes = {"blockquote": "> ", "li": "- "}
    return prefixes.get(block.tag, "") + block.text


def with_footnotes_moved(sections: list[Section]) -> list[Section]:
    """Money Stuff prints its footnotes "[1] …" after the last section; each moves to the end of the section that cites it."""
    footnotes = [paragraph for section in sections for paragraph in section.paragraphs if FOOTNOTE.match(paragraph)]
    moved = [Section(title=section.title, paragraphs=[p for p in section.paragraphs if not FOOTNOTE.match(p)]) for section in sections]
    for footnote in footnotes:
        citing_section(moved, FOOTNOTE.match(footnote).group(1)).paragraphs.append(footnote)
    return moved


def citing_section(sections: list[Section], number: str) -> Section:
    marker = f"[{number}]"
    return next((section for section in sections if any(marker in paragraph for paragraph in section.paragraphs)), sections[-1])
