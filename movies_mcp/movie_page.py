"""Reads what a movie's Fandango page says about it, and the Rotten Tomatoes scores Fandango shows on it.

The page (fandango.com/<slug>/movie-overview) carries a schema.org Movie in JSON-LD with the synopsis and the directors, and a carousel of the cast and
crew, directors first, then the actors, then the crew. The scores are not in the page: its script reads them from fandango.com/napi/fanAndCriticRatings,
which answers only a session that has opened a Fandango page, as the listing does.
"""

import html
import json
import re
from typing import Any

from movies_mcp.movies import MoviePage, RottenTomatoesScores

JSON_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
CAST_MEMBER = re.compile(r'cast-carousel__name[^>]*>\s*([^<]+?)\s*</strong>\s*(?:<span class="cast-carousel__role[^>]*>\s*([^<]*?)\s*</span>)?', re.S)
CREW_ROLE = re.compile(r"(?i)director|producer|editor|design|cinematograph|writer|screenplay|music|composer|costume|casting|decorat")
MOST_CAST_LISTED = 5


class MoviePageUnreadable(ValueError):
    """The page had no schema.org Movie to read."""


def movie_page_from_html(page_html: str) -> MoviePage:
    movie = schema_movie(page_html)
    directors = [person["name"] for person in movie.get("director") or [] if person.get("name")]
    return MoviePage(description=html.unescape(movie.get("description") or "").strip(), directors=directors, cast=actors(page_html))


def schema_movie(page_html: str) -> dict[str, Any]:
    movies = [data for data in map(parsed_json, JSON_LD.findall(page_html)) if isinstance(data, dict) and data.get("@type") == "Movie"]
    if not movies:
        raise MoviePageUnreadable("no schema.org Movie on the page")
    return movies[0]


def parsed_json(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return None


def actors(page_html: str) -> list[str]:
    """The carousel's people whose role is a character, or blank, which is how Fandango lists an actor without one ("BTS")."""
    people = [(html.unescape(name), html.unescape(role)) for name, role in CAST_MEMBER.findall(page_html)]
    return [name for name, role in people if not CREW_ROLE.search(role)][:MOST_CAST_LISTED]


def scores_from_ratings(body: dict[str, Any]) -> RottenTomatoesScores | None:
    """The fanAndCriticRatings answer: {"data": {"criticsScore": 75, "audienceScore": 94, "certifiedFresh": true, ...}}; None when it has neither score."""
    data = body.get("data") or {}
    critics, audience = data.get("criticsScore"), data.get("audienceScore")
    if critics is None and audience is None:
        return None
    return RottenTomatoesScores(critics_score=critics, audience_score=audience, certified_fresh=bool(data.get("certifiedFresh")))
