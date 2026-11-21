"""voice_server's copy of sentence-stream's splitter against the package itself, which .venv still has for Kokoro: the same text, fed in the same
pieces, must give the same sentences."""

import pytest
from sentence_stream import SentenceBoundaryDetector as PackagedDetector

from voice_server.vendored.sentence_boundaries import SentenceBoundaryDetector as CopiedDetector

TEXTS = [
    "Let me check.\n\nThe Knicks beat the Celtics 108 to 102. Jalen Brunson scored 31 points! Was it close? Yes.",
    "Dr. Smith met Mr. Jones at 5 p.m. on Jan. 3. They talked about the U.S. economy.",
    "Here are three:\n\n1. **Hamilton** at the Richard Rodgers.\n2. *Wicked* at the Gershwin.\n3. Chicago.",
    "It costs $1,000.50 today… Tomorrow it may be more. 你好。再见！",
    "No ending punctuation at all",
    "",
]


def sentences(detector: object, text: str, piece_length: int) -> list[str]:
    found = [sentence for start in range(0, len(text), piece_length) for sentence in detector.add_chunk(text[start : start + piece_length])]
    return found + [detector.finish()]


@pytest.mark.parametrize("text", TEXTS)
@pytest.mark.parametrize("piece_length", [1, 3, 7, 1000])
def test_the_copy_splits_exactly_as_the_package_does(text: str, piece_length: int) -> None:
    assert sentences(CopiedDetector(), text, piece_length) == sentences(PackagedDetector(), text, piece_length)
