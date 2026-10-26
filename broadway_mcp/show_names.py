"""Finding the show a user named in TodayTix's listing, with the title matching the listings tools share (utils/title_matching_utils.py). The words
left out of a show's title are the ones people put around one: the, musical, show, Broadway."""

from pydantic import BaseModel

from broadway_mcp.shows import Show
from utils.title_matching_utils import MatchRule, TitleMatcher

SHOW_TITLES = TitleMatcher(frozenset({"the", "a", "an", "musical", "show", "play", "on", "broadway", "off"}))


class ShowsNamed(BaseModel):
    rule: MatchRule | None  # None when no show matched
    shows: list[Show]  # shortest name first, then most viewed


def shows_named(shows: list[Show], asked: str) -> ShowsNamed:
    most_viewed_first = sorted(shows, key=lambda show: -show.views_count)
    matches = SHOW_TITLES.matches(asked, [show.name for show in most_viewed_first])
    position = {title: index for index, title in enumerate(matches.titles)}
    found = sorted((show for show in most_viewed_first if show.name in position), key=lambda show: position[show.name])
    return ShowsNamed(rule=matches.rule, shows=found)
