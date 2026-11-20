"""broadway_shows' reply as the model reads it: a heading saying which shows and in what order, then one "a | b" line per show.

The heading names the filters, so the model can tell the user when nothing matched which filter to drop. Only TodayTix's genre tags are shown, not its
marketing tags such as "Must-See", to keep each line short enough to say.
"""

from datetime import date

from broadway_mcp.shows import GENRE_TAGS, Show, ShowQuery
from utils.text_utils import spoken_month_day

TIER_LABELS = {"broadway": "Broadway", "off_broadway": "Off-Broadway", "both": "Broadway and Off-Broadway"}
TIMING_LABELS = {"running": "running now", "upcoming": "not started yet"}
ORDER_LABELS = {
    "views_count": "most viewed on TodayTix first",
    "reviews_count": "most reviewed first",
    "audience_score": "best audience score first",
    "todaytix_rating": "best TodayTix rating first",
}
SHOW_TYPE_LABELS = {"musical": "musicals", "play": "plays", "any": "shows"}
CATEGORY_NAMES = {"Musicals": "musical", "Plays": "play", "Comedy Shows": "comedy show", "Concerts": "concert", "Immersive Experiences": "immersive show"}


def shows_text(found: list[Show], query: ShowQuery, today: date) -> str:
    listed = found[: query.limit]
    lines = [heading(query, shown=len(listed), total=len(found))]
    lines.extend(show_line(rank, show, query, today) for rank, show in enumerate(listed, start=1))
    return "\n".join(lines)


def heading(query: ShowQuery, shown: int, total: int) -> str:
    what = f"{TIER_LABELS[query.venue_tier]} {SHOW_TYPE_LABELS[query.show_type]} {TIMING_LABELS[query.timing]}"
    filters = "".join(f", {part}" for part in filter_labels(query))
    if total == 0:
        return f"No {what}{filters} on TodayTix. Tell the user, and offer to drop a filter."
    return f"{what[0].upper()}{what[1:]}{filters}, {ORDER_LABELS[query.sort_by]} ({shown} of {total}):"


def filter_labels(query: ShowQuery) -> list[str]:
    labels = [f"genre {query.genre.replace('_', ' ')}"] if query.genre else []
    if query.max_price is not None:
        labels.append(f"tickets from ${query.max_price:g} or less")
    if query.ticket_deal != "any":
        labels.append(f"with {query.ticket_deal} tickets")
    return labels


def show_line(rank: int, show: Show, query: ShowQuery, today: date) -> str:
    tier = [TIER_LABELS[show.tier.value]] if query.venue_tier == "both" else []
    return " | ".join([f"{rank}. {show.name}", *label_parts(show), *tier, f"at {show.venue}", *detail_parts(show, query, today)])


def label_parts(show: Show) -> list[str]:
    """TodayTix's category, said as one show ("musical"), then its genre tags."""
    genres = [tag for tag in GENRE_TAGS.values() if tag in show.tags]  # TodayTix's own order changes from one night to the next
    return [CATEGORY_NAMES.get(show.category, show.category.lower()), *([", ".join(genres)] if genres else [])]


def detail_parts(show: Show, query: ShowQuery, today: date) -> list[str]:
    return [*price_parts(show), *popularity_parts(show, query), *deal_parts(show), *date_parts(show, today)]


def price_parts(show: Show) -> list[str]:
    return [f"from ${show.lowest_price:,.0f}"] if show.lowest_price is not None else []


def popularity_parts(show: Show, query: ShowQuery) -> list[str]:
    """The number the list is ordered by is always on the line. Each score keeps its count beside it, since a 98 from 300 reviews and a 94
    from 27,000 do not mean the same thing; views are shown only when they set the order."""
    views = [f"{show.views_count:,} recent views"] if query.sort_by == "views_count" else []
    return views + score_parts(show)


def score_parts(show: Show) -> list[str]:
    parts: list[str] = []
    if show.audience_score is not None:
        parts.append(f"audience score {show.audience_score}" + (f" from {show.reviews_count:,} Show-Score reviews" if show.reviews_count else ""))
    elif show.reviews_count:
        parts.append(f"{show.reviews_count:,} Show-Score reviews")
    return parts + todaytix_rating_parts(show)


def todaytix_rating_parts(show: Show) -> list[str]:
    if show.todaytix_rating is None:
        return []
    return [f"TodayTix rating {show.todaytix_rating:.1f} of 5" + (f" from {show.todaytix_ratings_count:,} ratings" if show.todaytix_ratings_count else "")]


def deal_parts(show: Show) -> list[str]:
    """Named as TodayTix's programs, since the flags say the show runs one, not that a seat is free right now."""
    deals = [deal for deal, offered in (("rush tickets", show.has_rush), ("lottery", show.has_lottery)) if offered]
    return [f"TodayTix {' and '.join(deals)}"] if deals else []


def date_parts(show: Show, today: date) -> list[str]:
    details: list[str] = []
    if show.start_date is not None and show.start_date > today:
        details.append(f"starts {spoken_month_day(show.start_date, today)}")
    elif show.start_date is None:
        details.append("dates not announced")
    if show.end_date is not None:
        details.append(f"closes {spoken_month_day(show.end_date, today)}")
    return details
