"""Word-budget helpers shared by the page reader and the Wikipedia tool."""


def clip_to_words(text: str, max_words: int) -> str:
    """The first max_words words with the line breaks between them kept, so table rows stay one to a line. The line that overflows is cut at the
    budget so the reader still sees where it was heading."""
    kept: list[str] = []
    remaining = max_words
    for line in text.split("\n"):
        words = line.split()
        if remaining <= 0:
            break
        kept.append(" ".join(words[:remaining]))
        remaining -= len(words)
    return "\n".join(line for line in kept if line)


def word_count(text: str) -> int:
    return len(text.split())
