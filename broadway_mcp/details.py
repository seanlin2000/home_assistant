"""broadway_show_details' reply as the model reads it: everything the snapshot holds about the one show the user named, with TodayTix's description.

When the name was matched loosely, the reply says which show it matched, so the model can tell the user it is not the one they meant ("Romeo and
Juliet" finds a parody). When several shows match, it lists them and asks the model to ask the user. A show missing from the listing or without a
description sends the model to the web, the only place left to learn what it is about.
"""

from datetime import date

from broadway_mcp.render import TIER_LABELS, date_parts, deal_parts, label_parts, price_parts, score_parts
from broadway_mcp.show_names import ShowsNamed
from broadway_mcp.shows import Show, has_closed, is_running
from utils.text_utils import spoken_month_day
from utils.title_matching_utils import MatchRule

MAX_LISTED_MATCHES = 5
NOT_LISTED = 'No show on TodayTix\'s New York listing matches "{asked}", so it is probably not playing in New York now. Tell the user; if they want to know what the show is about, search the web.'
NO_DESCRIPTION = "TodayTix has no description of this show; if the user wants to know what it is about, search the web."


def show_details_text(named: ShowsNamed, asked: str, today: date) -> str:
    if not named.shows:
        return NOT_LISTED.format(asked=asked)
    if len(named.shows) > 1:
        return several_matches_text(named.shows, asked)
    show = named.shows[0]
    return "\n".join([one_show_heading(show, named.rule, asked), facts_line(show, today), f"About: {show.description}" if show.description else NO_DESCRIPTION])


def several_matches_text(shows: list[Show], asked: str) -> str:
    listed = shows[:MAX_LISTED_MATCHES]
    more = f" ({len(shows) - len(listed)} more not listed)" if len(shows) > len(listed) else ""
    lines = [f'{len(shows)} shows on TodayTix match "{asked}"{more}. Ask the user which one they mean:']
    lines.extend(f"{rank}. {show.name} | {TIER_LABELS[show.tier.value]} | at {show.venue}" for rank, show in enumerate(listed, start=1))
    return "\n".join(lines)


def one_show_heading(show: Show, rule: MatchRule | None, asked: str) -> str:
    if rule == MatchRule.SAME_WORDS:
        return f"{show.name}, from TodayTix:"
    return f'TodayTix\'s closest match for "{asked}" is {show.name}:'


def facts_line(show: Show, today: date) -> str:
    return " | ".join([*label_parts(show), TIER_LABELS[show.tier.value], f"at {show.venue}", *price_parts(show), *score_parts(show), *deal_parts(show), *run_parts(show, today)])


def run_parts(show: Show, today: date) -> list[str]:
    if has_closed(show, today):
        return [f"closed {spoken_month_day(show.end_date, today)}"]
    return (["running now"] if is_running(show, today) else []) + date_parts(show, today)
