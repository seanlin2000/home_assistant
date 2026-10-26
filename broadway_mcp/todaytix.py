"""Reads TodayTix's New York listing for the nightly refresh and keeps the Broadway and Off-Broadway shows as rows.

The listing is the JSON TodayTix's own site reads (api.todaytix.com/api/v2/shows), undocumented and keyless: one request returned all 287 New York
products on 2026-10-25. Entries that are not shows running at a theater are dropped here, so the tool never has to: museums and other attractions,
and stale entries with no theater, such as a production that closed or a season subscription.
"""

from datetime import UTC, date, datetime
from typing import Any

import httpx

from broadway_mcp.settings import BroadwaySettings
from broadway_mcp.shows import BroadwaySnapshot, Show, Tier
from utils.snapshot_utils import write_snapshot

OK = 200
SHOW_PRODUCT_TYPE = "SHOW"
TIER_TAGS = {"Broadway": Tier.BROADWAY, "Off Broadway": Tier.OFF_BROADWAY}  # Broadway first: one show carried both tags on 2026-10-25
NO_DATE = "null"  # TodayTix sends an open-ended run's end date as this string, not as JSON null


class TodayTixUnavailable(RuntimeError):
    """TodayTix did not answer, refused, or answered in a shape the refresh cannot read."""


async def refresh_broadway_snapshot(settings: BroadwaySettings, transport: httpx.AsyncBaseTransport | None = None) -> BroadwaySnapshot:
    """Reads the listing and replaces the snapshot. A failed read raises before anything is written, so the last good snapshot stays."""
    products = await read_products(settings, transport)
    snapshot = BroadwaySnapshot(refreshed_at=datetime.now(UTC), shows=[show for product in products if (show := show_from_product(product)) is not None])
    write_snapshot(settings.snapshot_path, snapshot)
    return snapshot


async def read_products(settings: BroadwaySettings, transport: httpx.AsyncBaseTransport | None) -> list[dict[str, Any]]:
    """Every New York product, a page at a time in case the listing outgrows one request."""
    products: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=settings.timeout_seconds, follow_redirects=False, headers={"User-Agent": settings.user_agent}, transport=transport) as client:
        while True:
            page, total = await read_page(client, settings, offset=len(products))
            products.extend(page)
            if not page or len(products) >= total:
                return products


async def read_page(client: httpx.AsyncClient, settings: BroadwaySettings, offset: int) -> tuple[list[dict[str, Any]], int]:
    params = {"location": settings.location_id, "limit": settings.products_per_request, "offset": offset}
    try:
        response = await client.get(settings.shows_url, params=params)
    except httpx.HTTPError as error:
        raise TodayTixUnavailable(f"no answer from TodayTix ({type(error).__name__})") from error
    if response.status_code != OK:
        raise TodayTixUnavailable(f"TodayTix answered {response.status_code}")
    try:
        body = response.json()
        return list(body["data"]), int(body["pagination"]["total"])
    except (ValueError, KeyError, TypeError) as error:
        raise TodayTixUnavailable(f"TodayTix's listing was not in the expected shape ({type(error).__name__}: {error})") from error


def show_from_product(product: dict[str, Any]) -> Show | None:
    """The product as a show, or None when it is not a Broadway or Off-Broadway show at a theater."""
    tag_names = [tag["name"] for tag in product.get("subcategories") or []]
    tier = next((TIER_TAGS[name] for name in TIER_TAGS if name in tag_names), None)
    venue = (product.get("venue") or "").strip()
    if tier is None or not venue or product.get("productType") != SHOW_PRODUCT_TYPE:
        return None
    review_summary = product.get("reviewSummary") or {}
    return Show(
        name=" ".join(product["displayName"].split()),
        tier=tier,
        category=(product.get("category") or {}).get("name", ""),
        tags=[name for name in tag_names if name not in TIER_TAGS],
        venue=venue,
        start_date=listed_date(product.get("startDate")),
        end_date=listed_date(product.get("endDate")),
        views_count=product.get("recentPdpViewsCount") or 0,
        reviews_count=review_summary.get("reviewsCount"),
        audience_score=review_summary.get("score"),
        todaytix_rating=product.get("avgRating"),
        todaytix_ratings_count=product.get("ratingCount"),
        lowest_price=(product.get("lowPriceForRegularTickets") or {}).get("value"),
        has_rush=bool(product.get("isRushActive")),
        has_lottery=bool(product.get("isLotteryActive")),
        description=plain_description(product.get("description")),
    )


def plain_description(text: str | None) -> str:
    """TodayTix writes titles in markdown italics (*Wicked*); the only markdown its descriptions use, and nothing a voice should read out."""
    return " ".join((text or "").replace("*", "").split())


def listed_date(text: str | None) -> date | None:
    return None if text in (None, "", NO_DATE) else date.fromisoformat(text)
