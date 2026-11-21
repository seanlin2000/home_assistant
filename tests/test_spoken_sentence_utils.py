"""Long sentences are cut at their commas into pieces of at most 150 characters; every example is a sentence the assistant spoke in November 2026."""

from utils.spoken_sentence_utils import MAX_SPOKEN_PIECE_CHARACTERS, split_long_sentence

NEAR_THE_LIMIT = "It's a Crunchyroll theatrical event: a sneak peek screening of select episodes of new seasons before they hit streaming, plus a look at the slate."
JUST_OVER_THE_LIMIT = "In double overtime, the Detroit Pistons edged the Washington Wizards 144 to 140, on a 52-point night from Cade Cunningham; Trae Young had 37 for Washington."
MOVIES_LIST = (
    'Among films playing in Manhattan this week, these are the most widely released with critics scores above 70 percent on Rotten Tomatoes: "You Can See '
    'Everything," a documentary at 96 percent, in 16 theaters; "Godzilla Minus Zero" at 90 percent and "Wild Horse Nine" at 94 percent, both in 11 theaters; '
    '"Wildwood" at 97 percent, 10 theaters; "I Play Rocky" at 87 percent and "Wicker" at 94 percent, both 9 theaters; "Club Kid" at 98 percent, 7 theaters; '
    '"The Only Living Pickpocket in New York" at 98 percent, 6 theaters; and "Paper Tiger" at 86 percent and "Ramayana" at 77 percent, 5 theaters each.'
)
NO_COMMA = (
    "The Post reported in late October that Mamdani had personally signed exactly one City Council bill in his first ten months — an August law letting "
    "restaurants keep sidewalk outdoor dining open year-round."
)


def test_a_sentence_within_the_limit_is_spoken_whole() -> None:
    assert len(NEAR_THE_LIMIT) == 146
    assert split_long_sentence(NEAR_THE_LIMIT) == [NEAR_THE_LIMIT]


def test_a_sentence_just_over_the_limit_is_cut_at_the_last_comma_that_fits() -> None:
    assert split_long_sentence(JUST_OVER_THE_LIMIT) == [
        "In double overtime, the Detroit Pistons edged the Washington Wizards 144 to 140,",
        "on a 52-point night from Cade Cunningham; Trae Young had 37 for Washington.",
    ]


def test_a_long_list_becomes_pieces_within_the_limit_that_read_back_as_the_sentence() -> None:
    pieces = split_long_sentence(MOVIES_LIST)

    assert len(pieces) == 6
    assert all(len(piece) <= MAX_SPOKEN_PIECE_CHARACTERS for piece in pieces)
    assert " ".join(pieces) == MOVIES_LIST


def test_a_long_sentence_without_a_comma_stays_whole() -> None:
    assert split_long_sentence(NO_COMMA) == [NO_COMMA]


def test_a_comma_inside_a_number_is_not_a_place_to_cut() -> None:
    sentence = "The stadium seats 1,200,000 fans over a season, " + "and the team plays eighty-one home games across six long months of the regular season every single year, rain or shine."

    assert len(sentence) > MAX_SPOKEN_PIECE_CHARACTERS
    assert split_long_sentence(sentence) == [
        "The stadium seats 1,200,000 fans over a season,",
        "and the team plays eighty-one home games across six long months of the regular season every single year, rain or shine.",
    ]
