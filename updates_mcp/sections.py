"""The updates tool's sections: their names, which ones a call shows, and the tool description that lists them.

Some sections are off unless the user asks for them (Broadway closings). That set is a setting the server applies on every call, never a default of
the skip argument: a list default is replaced, not merged, so a model passing skip=["anime"] would turn the default-off sections back on.
"""

from typing import Literal, get_args

UpdateSection = Literal["newsletters", "warriors", "new_movies", "anime", "broadway_previews", "broadway_closings"]
SECTIONS: tuple[UpdateSection, ...] = get_args(UpdateSection)
FOLLOWED_TEAM = "Warriors"  # the warriors section's team, which its name says; a different team means renaming the section too
UPCOMING_DAYS = 60
UPCOMING_SPOKEN = "the next two months"
NEW_SINCE_DAYS = 7
SECTION_CONTENTS: dict[UpdateSection, str] = {
    "newsletters": "today's newsletters",
    "warriors": f"the {FOLLOWED_TEAM}' game today or last night, with score and recap; their next game while the season lasts",
    "new_movies": "good wide-release movies new since last week",
    "anime": f"anime movies coming in {UPCOMING_SPOKEN}",
    "broadway_previews": f"Broadway shows starting previews in {UPCOMING_SPOKEN}",
    "broadway_closings": f"Broadway shows closing in {UPCOMING_SPOKEN}",
}
SECTION_TITLES: dict[UpdateSection, str] = {
    "newsletters": "Newsletters",
    "warriors": f"{FOLLOWED_TEAM} games",
    "new_movies": "New popular movies",
    "anime": "Anime movies",
    "broadway_previews": "Broadway previews",
    "broadway_closings": "Broadway closings",
}


def shown_sections(skip: list[UpdateSection], include: list[UpdateSection], default_off: list[UpdateSection]) -> list[UpdateSection]:
    """Every section, less the default-off ones not included, less the skipped ones, in the tool's order. A section both skipped and included stays
    out: the user said to leave it out."""
    left_out = (set(default_off) - set(include)) | set(skip)
    return [section for section in SECTIONS if section not in left_out]


def tool_description(default_off: list[UpdateSection]) -> str:
    shown = [SECTION_CONTENTS[section] for section in SECTIONS if section not in default_off]
    sentences = [f"The user's updates, in this order: {'; '.join(shown)}."]
    asked_for_only = [SECTION_TITLES[section] for section in SECTIONS if section in default_off]
    if asked_for_only:
        sentences.append(f"{' and '.join(asked_for_only)} only when asked for.")
    return " ".join(sentences)


def include_description(default_off: list[UpdateSection]) -> str:
    off = ", ".join(default_off) or "none now"
    return f"sections that are off unless asked for ({off}), only when the user asks for one"
