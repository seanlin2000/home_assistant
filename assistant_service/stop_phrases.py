"""Stop phrases: what the user says to end a conversation, answered with silence before the model is asked (design doc v2/04 section 3.9).

Saying the wake word during an answer cuts it off, but the puck then listens again, and people still talking in the room become the next question.
A transcript that opens with a stop phrase is answered with the silence marker instead, which also closes the microphone. Speech recognition keeps
recording while the room is noisy, so whatever follows the phrase is ignored. A phrase of two or more words counts when the transcript starts with
it. A single word counts only when it is the whole first sentence, so "Stop." ends the conversation and "Stop the music" is still a request.
"""

import re
from dataclasses import dataclass

from assistant_core.prompts import PERSONA_NAME

WORD = re.compile(r"[a-z0-9']+")
SENTENCE_END = re.compile(r"[.?!]")
CURLY_APOSTROPHES = str.maketrans({"’": "'", "‘": "'"})
GREETING = "hey"


@dataclass(frozen=True)
class StopPhrases:
    multi_word: tuple[tuple[str, ...], ...] = ()
    single_words: frozenset[str] = frozenset()

    @classmethod
    def from_phrases(cls, phrases: list[str]) -> "StopPhrases":
        split = [tuple(spoken_words(phrase)) for phrase in phrases]
        return cls(multi_word=tuple(words for words in split if len(words) > 1), single_words=frozenset(words[0] for words in split if len(words) == 1))


def is_stop_request(question: str, phrases: StopPhrases) -> bool:
    return opens_with_a_phrase(spoken_words(question), phrases) or is_a_single_stop_word(spoken_words(first_sentence(question)), phrases)


def opens_with_a_phrase(words: list[str], phrases: StopPhrases) -> bool:
    return any(tuple(words[: len(phrase)]) == phrase for phrase in phrases.multi_word)


def is_a_single_stop_word(words: list[str], phrases: StopPhrases) -> bool:
    return len(words) == 1 and words[0] in phrases.single_words


def first_sentence(text: str) -> str:
    return SENTENCE_END.split(text, maxsplit=1)[0]


def spoken_words(text: str) -> list[str]:
    """The words in lowercase with straight apostrophes, after a leading "hey Jarvis" or "Jarvis", which the user sometimes repeats after the wake word."""
    words = WORD.findall(text.translate(CURLY_APOSTROPHES).lower())
    if words[:2] == [GREETING, PERSONA_NAME.lower()]:
        return words[2:]
    if words[:1] == [PERSONA_NAME.lower()]:
        return words[1:]
    return words
