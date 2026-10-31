"""An article page reads as its article; a page that is a grid of cards, which trafilatura's precision mode drops as boilerplate, reads as its whole
visible text."""

from web_search_mcp.page_text import THIN_ARTICLE_CHARS, article_text, readable_text

CARD = '<div class="col"><div class="card"><a href="/r/{n}"><img src="x.jpg"></a><h3 class="card__title"><a href="/r/{n}">Restaurant Number {n}</a></h3><a class="btn">Reserve a table</a></div></div>'
CARD_GRID = "<html><body><nav><a href='/'>Home</a></nav><main><h1>New York: 1-12 of 12 restaurants</h1><div class='row'>{cards}</div></main></body></html>".format(
    cards="".join(CARD.format(n=number) for number in range(12))
)
ARTICLE = "<html><body><nav><a href='/'>Home</a></nav><article><h1>Le Bernardin</h1><p>" + "Seafood has long been the calling card of the kitchen. " * 20 + "</p></article></body></html>"


def test_an_article_page_reads_as_its_article() -> None:
    text = readable_text(ARTICLE)

    assert text == article_text(ARTICLE) and len(text) >= THIN_ARTICLE_CHARS and "Home" not in text


def test_a_grid_of_cards_reads_as_the_whole_visible_text() -> None:
    assert "Restaurant Number" not in article_text(CARD_GRID)  # the failure the fallback is for
    assert all(f"Restaurant Number {number}" in readable_text(CARD_GRID) for number in range(12))


def test_a_short_page_with_nothing_more_to_find_keeps_its_article() -> None:
    page = "<html><body><article><p>Closed for the holidays, back on January 5.</p></article></body></html>"

    assert readable_text(page) == article_text(page)
