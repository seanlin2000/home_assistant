"""wikipedia_lookup's passage selection: the shared ranker of utils.passage_utils, with a left-out note that tells the model how to see the rest,
since wikipedia_lookup's focus argument can ask for it."""

from utils.passage_utils import select_passages as select_page_passages

LEFT_OUT_NOTE = "[{count} more matching lines here did not fit; to see them, ask again with a narrower focus, such as a year]"


def select_passages(article_text: str, focus: str, max_words: int, article_title: str = "") -> str:
    return select_page_passages(article_text, focus, max_words, article_title, LEFT_OUT_NOTE)
