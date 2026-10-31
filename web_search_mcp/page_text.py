"""The readable text of a downloaded page, for fetch_page and search_and_read.

trafilatura's precision mode keeps a page's main article and drops what looks like boilerplate. On a page that is a grid of cards, such as a listing of
restaurants, shows, or products, the cards are the content, and precision mode drops them all: Michelin's three-star New York listing came out on
2026-10-30 as 406 characters naming none of its five restaurants. So when the article keeps almost nothing of a page with far more text, the page's
whole visible text is read instead, navigation included; a few extra words cost less than an answer that misses the page's point.
"""

import trafilatura

from web_search_mcp.page_markdown import to_passage_format

THIN_ARTICLE_CHARS = 500  # an article this short is likely a heading and a caption left over from a page of cards
FULL_TEXT_FACTOR = 5  # the whole visible text must be this many times longer to be worth its navigation and footer


def readable_text(html: str) -> str:
    article = article_text(html)
    if len(article) >= THIN_ARTICLE_CHARS:
        return article
    full_text = visible_text(html)
    return full_text if len(full_text) > FULL_TEXT_FACTOR * len(article) else article


def article_text(html: str) -> str:
    """trafilatura's Markdown keeps the page's headings, table rows, and lists, which passage selection needs to choose between them."""
    extracted = trafilatura.extract(html, include_comments=False, include_tables=True, favor_precision=True, output_format="markdown")
    return to_passage_format(extracted or "")


def visible_text(html: str) -> str:
    return " ".join(trafilatura.html2txt(html).split())
