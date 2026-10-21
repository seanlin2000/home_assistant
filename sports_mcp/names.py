"""Text from ESPN cut down before it reaches the model.

The sports tools do not mark the exchange untrusted (design doc v2/03 section 3.4), so every name, note and status line they pass on keeps only
letters, digits, spaces and a few punctuation marks, and only a few words: enough for "Kristaps Porziņģis" or "NBA Finals - Game 7", too little
for a paragraph of instructions planted in ESPN's database.
"""

NAME_PUNCTUATION = set(" .'-")
NOTE_PUNCTUATION = NAME_PUNCTUATION | set(",:/()")
NAME_WORDS = 4
NAME_CHARS = 40
NOTE_WORDS = 8
NOTE_CHARS = 60


def cleaned_name(text: str) -> str:
    """A player's or team's name."""
    return cut_down(text, NAME_PUNCTUATION, NAME_WORDS, NAME_CHARS)


def cleaned_note(text: str) -> str:
    """A game's note ("NBA FINALS - GAME 7"), series summary, or status ("1:52 - 4th Quarter")."""
    return cut_down(text, NOTE_PUNCTUATION, NOTE_WORDS, NOTE_CHARS)


def cut_down(text: str, punctuation: set[str], max_words: int, max_chars: int) -> str:
    kept = "".join(character if character.isalnum() or character in punctuation else " " for character in text)
    return " ".join(kept.split()[:max_words])[:max_chars].strip()
