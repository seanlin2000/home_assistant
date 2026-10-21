"""Word-budget helpers shared by the page reader, the Wikipedia tool, and the sports tools."""


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


def clip_to_whole_lines(text: str, max_words: int) -> str:
    """The lines that fit in max_words, never part of one: a game or a season cut halfway reads as a wrong number. The first line is always kept."""
    kept: list[str] = []
    used = 0
    for line in text.split("\n"):
        used += len(line.split())
        if kept and used > max_words:
            break
        kept.append(line)
    return "\n".join(kept)


def word_count(text: str) -> int:
    return len(text.split())
