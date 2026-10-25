"""broadway_shows' reply as the model reads it: a heading saying which shows and in what order, then one "a | b" line per show.

The heading names the filters, so the model can tell the user when nothing matched which filter to drop. Only TodayTix's genre tags are shown, not its
marketing tags such as "Must-See", to keep each line short enough to say.
"""

from datetime import date, datetime

from broadway_mcp.shows import GENRE_TAGS, Show, ShowQuery

TIER_LABELS = {"broadway": "Broadway", "off_broadway": "Off-Broadway", "both": "Broadway and Off-Broadway"}
TIMING_LABELS = {"running": "running now", "upcoming": "not started yet"}
ORDER_LABELS = {"views_count": "most viewed on TodayTix first", "reviews_count": "most reviewed first", "audience_score": "best audience score first"}
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
    parts = [f"{rank}. {show.name}", CATEGORY_NAMES.get(show.category, show.category.lower())]
    genres = [tag for tag in GENRE_TAGS.values() if tag in show.tags]  # TodayTix's own order changes from one night to the next
    if genres:
        parts.append(", ".join(genres))
    if query.venue_tier == "both":
        parts.append(TIER_LABELS[show.tier.value])
    parts.append(show.venue)
    parts.extend(detail_parts(show, today))
    return " | ".join(parts)


def detail_parts(show: Show, today: date) -> list[str]:
    details = [f"from ${show.lowest_price:,.0f}"] if show.lowest_price is not None else []
    if show.audience_score is not None:
        details.append(f"audience score {show.audience_score}")
    deals = [deal for deal, offered in (("rush", show.has_rush), ("lottery", show.has_lottery)) if offered]
    if deals:
        details.append(f"{' and '.join(deals)} tickets")
    if show.start_date is not None and show.start_date > today:
        details.append(f"starts {spoken_date(show.start_date, today)}")
    elif show.start_date is None:
        details.append("dates not announced")
    if show.end_date is not None:
        details.append(f"closes {spoken_date(show.end_date, today)}")
    return details


def spoken_date(day: date, today: date) -> str:
    return f"{day:%B} {day.day}" if day.year == today.year else f"{day:%B} {day.day}, {day.year}"


def age_note(refreshed_at: datetime, today: date, stale_after_days: int) -> str:
    refreshed_on = refreshed_at.astimezone().date()
    days_old = (today - refreshed_on).days
    if days_old <= stale_after_days:
        return ""
    return f"These listings were last refreshed {days_old} days ago, on {spoken_date(refreshed_on, today)}; tell the user they may be out of date."
