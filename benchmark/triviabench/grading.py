"""Grade a spoken answer against a TriviaQA answer key without a judge: normalise both sides the way TriviaQA does, then look for an alias.

The assistant answers in one to three spoken sentences and says numbers as words ("nineteen sixty-six"), so an exact match alone would fail almost
every answer. An answer is correct when it equals an alias, or contains one as whole words. An alias the question itself contains does not count
when merely contained, because a spoken answer usually repeats the question's words.
"""

import re
import unicodedata
from enum import StrEnum

ARTICLES = {"a", "an", "the"}
UNITS = {
    "zero": 0,
    "oh": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
SCALES = {"hundred": 100, "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}
ORDINALS = {
    "first": "1st",
    "second": "2nd",
    "third": "3rd",
    "fourth": "4th",
    "fifth": "5th",
    "sixth": "6th",
    "seventh": "7th",
    "eighth": "8th",
    "ninth": "9th",
    "tenth": "10th",
    "eleventh": "11th",
    "twelfth": "12th",
    "thirteenth": "13th",
    "fourteenth": "14th",
    "fifteenth": "15th",
    "sixteenth": "16th",
    "seventeenth": "17th",
    "eighteenth": "18th",
    "nineteenth": "19th",
    "twentieth": "20th",
}
NUMBER_WORDS = set(UNITS) | set(TENS) | set(SCALES)
MINIMUM_CONTAINED_WORD_ALIAS_LENGTH = 3  # "ii" or "us" inside a sentence is a coincidence, not an answer


class Match(StrEnum):
    EXACT = "exact"
    CONTAINED = "contained"
    NONE = "none"


def grade_answer(answer: str, aliases: list[str], question: str) -> Match:
    normalized_answer = normalize_answer(answer)
    normalized_aliases = {normalize_answer(alias) for alias in aliases} - {""}
    if normalized_answer in normalized_aliases:
        return Match.EXACT
    question_text = normalize_answer(question)
    countable = [alias for alias in normalized_aliases if is_countable_when_contained(alias) and not contains_words(question_text, alias)]
    return Match.CONTAINED if any(contains_words(normalized_answer, alias) for alias in countable) else Match.NONE


def normalize_answer(text: str) -> str:
    """TriviaQA's normalisation (lower case, no punctuation, no articles), plus ASCII folding and spoken numbers read as digits."""
    decomposed = unicodedata.normalize("NFKD", text.replace("&", " and "))
    spaced = "".join(" " if is_separator(character) else character for character in decomposed)
    folded = spaced.encode("ascii", "ignore").decode("ascii").lower()
    words = [word for word in folded.split() if word not in ARTICLES]
    return " ".join(spoken_numbers_as_digits(words))


def is_separator(character: str) -> bool:
    """Punctuation and symbols of any script split words, so "d'Ivoire", "d’Ivoire", and "sixty-six" split the same way."""
    return unicodedata.category(character)[0] in ("P", "S")


def is_countable_when_contained(alias: str) -> bool:
    return alias.isdigit() or len(alias) >= MINIMUM_CONTAINED_WORD_ALIAS_LENGTH


def contains_words(text: str, phrase: str) -> bool:
    return re.search(rf"(^| ){re.escape(phrase)}( |$)", text) is not None


def spoken_numbers_as_digits(words: list[str]) -> list[str]:
    """Replace each run of number words with its digits: "nineteen sixty six" -> "1966", "two thousand and eight" -> "2008", "third" -> "3rd"."""
    converted: list[str] = []
    index = 0
    while index < len(words):
        run_end = end_of_number_run(words, index)
        if run_end == index:
            converted.append(ORDINALS.get(words[index], words[index]))
            index += 1
            continue
        converted.append(str(number_from_words(words[index:run_end])))
        index = run_end
    return converted


def end_of_number_run(words: list[str], start: int) -> int:
    """The index just past the number words starting at start. "and" joins number words ("two hundred and five") but never starts or ends a run,
    "oh" only counts inside a run ("nineteen oh five"), and digits start a run only before a scale word ("3 million")."""
    if not starts_number_run(words, start):
        return start
    end = start + 1
    while end < len(words):
        if words[end] in NUMBER_WORDS:
            end += 1
        elif words[end] == "and" and end + 1 < len(words) and words[end + 1] in NUMBER_WORDS:
            end += 2
        else:
            break
    return end


def starts_number_run(words: list[str], start: int) -> bool:
    word = words[start]
    if word.isdigit():
        return start + 1 < len(words) and words[start + 1] in SCALES
    return word in NUMBER_WORDS and word != "oh"


def number_from_words(words: list[str]) -> int:
    values = [word for word in words if word != "and"]
    split = year_split(values)
    if split is None:
        return cardinal_from_words(values)
    return cardinal_from_words(values[:split]) * 100 + cardinal_from_words(values[split:])


def year_split(words: list[str]) -> int | None:
    """Where a year said in two halves divides ("nineteen | sixty six", "twenty | twelve", "eighteen | oh five"), or None when the words are an
    ordinary number. The leading half is 10 to 99, and the trailing half is a teen, a tens word, or "oh" and a digit, so "sixty six" stays 66."""
    if len(words) < 2 or any(word in SCALES or word.isdigit() for word in words):
        return None
    split = 2 if words[0] in TENS and len(words) > 2 and UNITS.get(words[1], 10) < 10 else 1
    trailing_half = words[split:]
    leading_value = cardinal_from_words(words[:split])
    trailing_is_two_digits = trailing_half[0] == "oh" or cardinal_from_words(trailing_half[:1]) >= 10
    return split if 10 <= leading_value <= 99 and trailing_is_two_digits else None


def cardinal_from_words(words: list[str]) -> int:
    total = 0
    current = 0
    for word in words:
        if word == "hundred":
            current = max(current, 1) * 100
        elif word in SCALES:
            total += max(current, 1) * SCALES[word]
            current = 0
        else:
            current += int(word) if word.isdigit() else UNITS.get(word, 0) + TENS.get(word, 0)
    return total + current
