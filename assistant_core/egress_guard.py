"""The egress guard: private details from memory never leave the house in a tool's arguments unless you said them yourself in this exchange
(design doc v2/12 section 3.4).

The private terms are the distinctive words of the past-conversation summaries retrieved for this exchange. Until memory exists (M6) there are none,
so the guard passes every call; it is built now so the injection category measures it from the start.
"""

import re

WORD = re.compile(r"[a-z0-9]+(?:['’][a-z]+)?")
MINIMUM_TERM_CHARS = 4
# Words too common to identify anyone or anything; a summary's distinctive words are what remains.
STOP_WORDS = frozenset(
    (
        "about after again also because been before being best both could does doing done down each even every from have having here into just last like made make many more most much must "
        "next only other over said same should some such than that their them then there these they this those through time today tomorrow very want week were what when where which while will with would year your asked talked conversation assistant user"
    ).split()
)


def words_of(text: str) -> set[str]:
    return set(WORD.findall(text.lower()))


def private_terms_in(summaries: list[str]) -> frozenset[str]:
    """The words of the retrieved summaries that could identify something: long enough, not common, or a number of two digits or more."""
    terms = set()
    for summary in summaries:
        terms.update(word for word in words_of(summary) if is_distinctive(word))
    return frozenset(terms)


def is_distinctive(word: str) -> bool:
    if word.isdigit():
        return len(word) >= 2
    return len(word) >= MINIMUM_TERM_CHARS and word not in STOP_WORDS


def leaked_terms(arguments: dict, private_terms: frozenset[str], spoken_this_exchange: str) -> list[str]:
    """The private terms a tool call would send out that the user did not say in this exchange."""
    outgoing = words_of(" ".join(str(value) for value in arguments.values()))
    return sorted((private_terms & outgoing) - words_of(spoken_this_exchange))
