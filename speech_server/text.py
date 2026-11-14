"""The text side of speaking: cutting streamed text into sentences as soon as each one is complete, and how much audio a sentence may take."""

import math
import re

from speech_server.settings import SpeechLength

CODEC_FRAMES_PER_SECOND = 12.5  # Qwen3-TTS-12Hz generates one audio token per 80 ms frame
CJK_CHARACTER = re.compile(r"[㐀-鿿豈-﫿]")
SPOKEN_CHARACTER = re.compile(r"[^\W_]")
# A blank line ends a sentence on its own (the harness puts one after the filler). Latin punctuation ends one only once the next character is whitespace,
# so "3.5" and "e.g." mid-word stay whole; Chinese punctuation ends one at once, since Chinese puts no space after it.
SENTENCE_END = re.compile(r"\n[ \t]*\n|[.!?…]+[\"'”’)\]]*(?=\s)|[。！？]+[”’」』）]*")
WORD_BEFORE = re.compile(r"(\S+)$")
DOTTED_INITIALS = re.compile(r"(?:[A-Za-z]\.)+[A-Za-z]")
TITLES = frozenset({"mr", "mrs", "ms", "dr", "prof", "st", "jr", "sr", "mt", "vs"})


class SentenceSplitter:
    """Collects streamed text and hands back each sentence once it is complete."""

    def __init__(self) -> None:
        self._pending = ""

    def add(self, text: str) -> list[str]:
        self._pending += text
        sentences = []
        while (end := self._first_sentence_end()) is not None:
            sentences.append(self._pending[:end])
            self._pending = self._pending[end:]
        return [spoken for spoken in map(tidied, sentences) if spoken]

    def finish(self) -> str:
        remainder, self._pending = tidied(self._pending), ""
        return remainder

    def _first_sentence_end(self) -> int | None:
        for match in SENTENCE_END.finditer(self._pending):
            if not ends_in_abbreviation(self._pending[: match.start()]):
                return match.end()
        return None


def ends_in_abbreviation(text_before_period: str) -> bool:
    word = WORD_BEFORE.search(text_before_period)
    if word is None:
        return False
    word_text = word.group(1)
    return word_text.lower() in TITLES or (len(word_text) == 1 and word_text.isupper()) or DOTTED_INITIALS.fullmatch(word_text) is not None


def tidied(sentence: str) -> str:
    """One line of text with something to say, or empty: a sentence of only punctuation would make the model babble."""
    joined = " ".join(sentence.split())
    return joined if SPOKEN_CHARACTER.search(joined) else ""


def max_audio_tokens(sentence: str, speech_length: SpeechLength) -> int:
    cjk_characters = len(CJK_CHARACTER.findall(sentence))
    other_characters = len(SPOKEN_CHARACTER.findall(sentence)) - cjk_characters
    seconds = cjk_characters * speech_length.seconds_per_cjk_character + other_characters * speech_length.seconds_per_latin_character
    return math.ceil(max(seconds, speech_length.minimum_seconds) * CODEC_FRAMES_PER_SECOND)
