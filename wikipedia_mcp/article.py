"""Turns an article's Parsoid HTML into plain text that keeps what a list or record question needs: section headings, prose, and every table row.

The generic page reader (trafilatura, tuned for precision) drops table rows, and on Wikipedia the answer to "who started at quarterback in 2001" or
"which seasons did they win" lives in a table. Here each wikitable and infobox becomes one line per row, cells joined by " | ", under the headings it sat
under, in the shared format of utils.passage_utils, which reads it back when it picks the parts of a long article that answer the question. Citations, navigation boxes, figures, edit links,
and the closing reference sections are left out.
"""

from collections.abc import Callable

import lxml.html
from lxml.html import HtmlElement

from utils.passage_utils import BLOCK_SEPARATOR, CELL_SEPARATOR, HEADING_MARK, LIST_ITEM_PREFIX

HEADING_TAGS = ("h2", "h3", "h4", "h5", "h6")
RENDERED_TABLE_CLASSES = ("wikitable", "infobox")
CLUTTER_XPATH = " | ".join(
    (
        "//sup[contains(@class, 'reference')]",
        "//style",
        "//script",
        "//figure",
        "//*[contains(concat(' ', @class, ' '), ' thumb ')]",  # older image frames, such as the location maps inside infoboxes
        "//*[contains(@class, 'mw-editsection')]",
        "//*[contains(@class, 'navbox')]",
        "//*[contains(@class, 'hatnote')]",
        "//*[contains(@class, 'metadata')]",
        "//*[contains(@class, 'noprint')]",
        "//*[contains(@class, 'mw-empty-elt')]",
        "//*[contains(@class, 'reflist')]",
        "//*[contains(@class, 'mw-references-wrap')]",
        "//*[contains(translate(@style, ' ', ''), 'display:none')]",  # hidden sort keys inside table cells
    )
)
SEPARATED_INLINE_TAGS = ("sup", "sub", "br")
# The closing sections hold citations and links to other pages; nothing in them answers a question.
SKIPPED_SECTION_HEADINGS = frozenset(
    {"references", "see also", "notes", "external links", "further reading", "citations", "sources", "bibliography", "footnotes", "works cited", "explanatory notes"}
    | {"notes and references", "general references", "cited sources", "general and cited references"}
)


def render_article(html: str) -> str:
    body = lxml.html.document_fromstring(html).body
    for clutter in body.xpath(CLUTTER_XPATH):
        clutter.drop_tree()
    separate_inline_markers(body)
    return BLOCK_SEPARATOR.join(blocks_of(body))


def separate_inline_markers(body: HtmlElement) -> None:
    """A superscript or a line break sits flush against its neighbours in the HTML ("San Francisco 49ers<sup>N</sup>(1, 1–0)"); without a space the text
    reads "49ersN(1," and the team's name no longer matches a question about it."""
    for marker in body.iter(*SEPARATED_INLINE_TAGS):
        marker.text = f" {marker.text or ''}"
        marker.tail = f" {marker.tail or ''}"


def blocks_of(container: HtmlElement) -> list[str]:
    blocks: list[str] = []
    for child in container:
        render = BLOCK_RENDERERS.get(child.tag) if isinstance(child.tag, str) else None
        if render is not None:
            blocks.extend(render(child))
    return blocks


def heading_block(heading: HtmlElement) -> list[str]:
    level = int(heading.tag[1])
    return [f"{HEADING_MARK * level} {clean_text(heading)}"]


def section_blocks(section: HtmlElement) -> list[str]:
    return [] if section_heading(section).lower() in SKIPPED_SECTION_HEADINGS else blocks_of(section)


def table_blocks(table: HtmlElement) -> list[str]:
    """Layout tables are skipped; a data table's caption, when it has one, comes first as its own block so the rows below it keep their header row first."""
    if not any(name in table.classes for name in RENDERED_TABLE_CLASSES):
        return []
    caption = " ".join(table.xpath("string(./caption)").split())
    rows = [row for row in (table_row(tr) for tr in table.xpath("./tr | ./thead/tr | ./tbody/tr | ./tfoot/tr")) if row]
    return ([caption] if caption else []) + (["\n".join(rows)] if rows else [])


def list_blocks(listing: HtmlElement) -> list[str]:
    items = [f"{LIST_ITEM_PREFIX}{text}" for text in (clean_text(item) for item in listing.xpath("./li")) if text]
    return ["\n".join(items)] if items else []


def paragraph_block(paragraph: HtmlElement) -> list[str]:
    text = clean_text(paragraph)
    return [text] if text else []


def table_row(row: HtmlElement) -> str:
    """Merged cells appear once, in the first row they span; the rows below carry only their own cells."""
    return CELL_SEPARATOR.join(clean_text(cell) for cell in row.xpath("./th | ./td")).rstrip(" |")


def section_heading(section: HtmlElement) -> str:
    return " ".join(section.xpath("string((./h2 | ./h3 | ./h4 | ./h5 | ./h6 | ./div/h2 | ./div/h3 | ./div/h4 | ./div/h5 | ./div/h6)[1])").split())


def clean_text(element: HtmlElement) -> str:
    return " ".join(element.text_content().split())


BLOCK_RENDERERS: dict[str, Callable[[HtmlElement], list[str]]] = {
    **{tag: heading_block for tag in HEADING_TAGS},
    "section": section_blocks,
    "div": blocks_of,  # heading wrappers, column layouts, and collapsible boxes hold blocks of their own
    "table": table_blocks,
    "ul": list_blocks,
    "ol": list_blocks,
    "p": paragraph_block,
    "blockquote": paragraph_block,
}
