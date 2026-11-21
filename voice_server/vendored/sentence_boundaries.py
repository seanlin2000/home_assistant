"""Sentence boundaries in a stream of text, as Home Assistant's own voices find them.

Copied from sentence-stream 1.2.0 (https://github.com/OHF-Voice/sentence-stream, Apache-2.0, LICENSE.sentence-stream.md beside this file), which
Kokoro's Wyoming server uses, so OmniVoice is given the same sentences Kokoro was. The package pins regex==2024.11.6 and so cannot be installed
beside mlx-audio. Changes from the original: remove_asterisks moved in from util.py; the stream_to_sentences helpers, which nothing here uses,
left out; formatted to this project's style. tests/test_sentence_boundaries.py checks the copy against the package on the same texts.
"""

from collections.abc import Iterable

import regex as re

SENTENCE_END = r"[.!?…]|[。！？]|[؟]|[।॥]"
ABBREVIATION_RE = re.compile(r"\b\p{Lu}(?:\p{L}{1,2})?\.$", re.UNICODE)

SENTENCE_BOUNDARY_RE = re.compile(
    rf"(?:{SENTENCE_END}+)(?=\s+[\p{{Lu}}\p{{Lt}}\p{{Lo}}]|(?:\s+\d+[.)]{{1,2}}\s+))",
    re.DOTALL,
)
BLANK_LINES_RE = re.compile(r"(?:\r?\n){2,}")
WORD_ASTERISKS = re.compile(r"\*+([^\*]+)\*+")
LINE_ASTERICKS = re.compile(r"(?<=^|\n)\s*\*+")


def remove_asterisks(text: str) -> str:
    """Remove *asterisks* surrounding **words**"""
    text = WORD_ASTERISKS.sub(r"\1", text)
    text = LINE_ASTERICKS.sub("", text)
    return text


class SentenceBoundaryDetector:  # deslop: allow-comments
    """Detect sentence boundaries from a text stream."""

    def __init__(self) -> None:
        self.remaining_text = ""
        self.current_sentence = ""

    def add_chunk(self, chunk: str) -> Iterable[str]:
        """Add text chunk to stream and yield all detected sentences."""
        self.remaining_text += chunk
        while self.remaining_text:
            match_blank_lines = BLANK_LINES_RE.search(self.remaining_text)
            match_punctuation = SENTENCE_BOUNDARY_RE.search(self.remaining_text)
            if match_blank_lines and match_punctuation:
                if match_blank_lines.start() < match_punctuation.start():
                    first_match = match_blank_lines
                else:
                    first_match = match_punctuation
            elif match_blank_lines:
                first_match = match_blank_lines
            elif match_punctuation:
                first_match = match_punctuation
            else:
                break

            match_text = self.remaining_text[: first_match.start() + 1]
            match_end = first_match.end()

            if not self.current_sentence:
                if ABBREVIATION_RE.search(match_text[-5:]):
                    # We can't know yet if this is a sentence boundary or an abbreviation
                    self.current_sentence = match_text
                elif output_text := remove_asterisks(match_text.strip()):
                    yield output_text
            elif ABBREVIATION_RE.search(self.current_sentence[-5:]):
                self.current_sentence += match_text
            else:
                if output_text := remove_asterisks(self.current_sentence.strip()):
                    yield output_text
                self.current_sentence = match_text

            if not ABBREVIATION_RE.search(self.current_sentence[-5:]):
                if output_text := remove_asterisks(self.current_sentence.strip()):
                    yield output_text
                self.current_sentence = ""

            self.remaining_text = self.remaining_text[match_end:]

    def finish(self) -> str:
        """End text stream and yield final sentence."""
        text = (self.current_sentence + self.remaining_text).strip()
        self.remaining_text = ""
        self.current_sentence = ""

        return remove_asterisks(text)
