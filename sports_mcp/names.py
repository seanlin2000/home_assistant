"""Text from ESPN cut down before it reaches the model.

The sports tools' results reach the model marked untrusted (config/tools.toml), and every name, note and status line in them also keeps only
letters, digits, spaces and a few punctuation marks, and only a few words: enough for "Kristaps Porziņģis" or "NBA Finals - Game 7", too little
for a paragraph of instructions planted in ESPN's database. A box score figure keeps only digits and the marks figures use. A game's recap is the
one longer text: the Associated Press headline and opening sentence, held to a sentence each.
"""

NAME_PUNCTUATION = set(" .'-")
NOTE_PUNCTUATION = NAME_PUNCTUATION | set(",:/()")
STAT_CHARACTERS = set("0123456789.-/+:")
NAME_WORDS = 4
NAME_CHARS = 40
NOTE_WORDS = 8
NOTE_CHARS = 60
STAT_CHARS = 8
RECAP_HEADLINE_WORDS = 16
RECAP_HEADLINE_CHARS = 120
RECAP_SUMMARY_WORDS = 50  # the AP's opening sentence, which names the winner, the score and the top scorers, runs 30 to 45 words
RECAP_SUMMARY_CHARS = 320


def cleaned_name(text: str) -> str:
    """A player's or team's name."""
    return cut_down(text, NAME_PUNCTUATION, NAME_WORDS, NAME_CHARS)


def cleaned_note(text: str) -> str:
    """A game's note ("NBA FINALS - GAME 7"), series summary, or status ("1:52 - 4th Quarter")."""
    return cut_down(text, NOTE_PUNCTUATION, NOTE_WORDS, NOTE_CHARS)


def cleaned_stat(text: str) -> str:
    """One box score figure ("7-14", "21/29", "+13", "29:45"): digits and the marks figures use, with the sign of a plus-minus kept."""
    return "".join(character for character in str(text) if character in STAT_CHARACTERS)[:STAT_CHARS]


def cleaned_recap_headline(text: str) -> str:
    return cut_down(text, NOTE_PUNCTUATION, RECAP_HEADLINE_WORDS, RECAP_HEADLINE_CHARS)


def cleaned_recap_summary(text: str) -> str:
    return cut_down(text, NOTE_PUNCTUATION, RECAP_SUMMARY_WORDS, RECAP_SUMMARY_CHARS)


def cut_down(text: str, punctuation: set[str], max_words: int, max_chars: int) -> str:
    kept = "".join(character if character.isalnum() or character in punctuation else " " for character in text)
    return " ".join(kept.split()[:max_words])[:max_chars].strip()
