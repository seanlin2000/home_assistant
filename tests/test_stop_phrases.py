"""Stop phrases: a transcript that opens with one is answered with silence before the model is asked (design doc v2/04 section 3.9)."""

import pytest

from assistant_service.settings import load_harness_config
from assistant_service.stop_phrases import StopPhrases, is_stop_request

PHRASES = StopPhrases.from_phrases(load_harness_config().answer.stop_phrases)


@pytest.mark.parametrize(
    "question",
    [
        "Be quiet.",
        "Be quiet. So anyway the movie was really long and",
        "we're done, thanks",
        "We’re done.",
        "We are done here",
        "That's all for now.",
        "Stop talking please, he said the train was late",
        "Jarvis, stop talking.",
        "Hey Jarvis stop.",
        "Stop.",
        "Cancel!",
        "Quiet. He said the movie was",
    ],
)
def test_a_transcript_opening_with_a_stop_phrase_is_a_stop_request(question: str) -> None:
    assert is_stop_request(question, PHRASES)


@pytest.mark.parametrize(
    "question",
    [
        "Stop the music.",
        "Cancel my timer.",
        "What's the weather? We're done eating.",
        "Can you be quiet tonight about the game?",
        "Stopwatch for five minutes.",
        "Never mind.",
        "Shut up.",
        "Forget it.",
        "",
    ],
)
def test_other_transcripts_go_to_the_model(question: str) -> None:
    assert not is_stop_request(question, PHRASES)


def test_phrases_split_by_word_count() -> None:
    phrases = StopPhrases.from_phrases(["Be quiet", "stop"])
    assert phrases.multi_word == (("be", "quiet"),)
    assert phrases.single_words == frozenset({"stop"})
