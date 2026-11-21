"""Long sentences cut into shorter spoken pieces for a text-to-speech model that makes each piece whole before any of it plays (OmniVoice), so
the first sound of a long sentence is not held back by the time it takes to make the whole sentence."""

MAX_SPOKEN_PIECE_CHARACTERS = 150
CLAUSE_BREAK = ", "


def split_long_sentence(sentence: str) -> list[str]:
    """A sentence over MAX_SPOKEN_PIECE_CHARACTERS cut at its commas into pieces of at most that length, each piece taking as many whole clauses
    as fit. Each piece keeps its trailing comma, so it is still read as a pause. A clause longer than the limit on its own stays whole: there is no
    comma in it to cut at, and cutting mid-clause would break the phrasing."""
    if len(sentence) <= MAX_SPOKEN_PIECE_CHARACTERS:
        return [sentence]
    return pack_clauses(split_into_clauses(sentence))


def split_into_clauses(sentence: str) -> list[str]:
    """ "a, b, c" as ["a,", "b,", "c"]. Only a comma followed by a space counts, so numbers such as 1,000 stay whole."""
    parts = sentence.split(CLAUSE_BREAK)
    return [part + "," for part in parts[:-1]] + [parts[-1]]


def pack_clauses(clauses: list[str]) -> list[str]:
    pieces = [clauses[0]]
    for clause in clauses[1:]:
        joined = f"{pieces[-1]} {clause}"
        if len(joined) <= MAX_SPOKEN_PIECE_CHARACTERS:
            pieces[-1] = joined
        else:
            pieces.append(clause)
    return pieces
