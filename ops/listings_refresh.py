"""The nightly listings refresh: reads each listings source once and replaces its snapshot, which the tools then read all day.

launchd runs it at 4:30 every morning, and once when the agent is loaded (scripts/services.sh installs it as "listings"); run it by hand with
`uv run listings-refresh`. Each source's outcome is one line in ~/Library/Logs/studio-assistant/listings.log. A source that fails keeps its last good
snapshot, and the command exits 1 so the failure shows in launchd's record.
"""

import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable

from broadway_mcp.settings import broadway_settings_from_environment
from broadway_mcp.todaytix import refresh_broadway_snapshot
from movies_mcp.fandango import refresh_movies_snapshot
from movies_mcp.settings import movies_settings_from_environment
from utils.snapshot_utils import ListingsUnavailable

_LOGGER = logging.getLogger("listings_refresh")
Refresh = Callable[[], Awaitable[str]]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    refreshes = {"broadway": refresh_broadway, "movies": refresh_movies}
    failures = asyncio.run(failed_refreshes(refreshes))
    sys.exit(1 if failures else 0)


async def failed_refreshes(refreshes: dict[str, Refresh]) -> list[str]:
    """Every source is tried, whatever happened to the ones before it; the names of those that failed."""
    outcomes = {name: await refreshed(name, refresh) for name, refresh in refreshes.items()}
    return [name for name, succeeded in outcomes.items() if not succeeded]


async def refreshed(name: str, refresh: Refresh) -> bool:
    try:
        _LOGGER.info("%s: %s", name, await refresh())
        return True
    except (ListingsUnavailable, OSError) as error:
        _LOGGER.error("%s: refresh failed, the last snapshot stays: %s", name, error)
        return False


async def refresh_broadway() -> str:
    settings = broadway_settings_from_environment()
    snapshot = await refresh_broadway_snapshot(settings)
    broadway_count = sum(show.tier == "broadway" for show in snapshot.shows)
    return f"{len(snapshot.shows)} shows ({broadway_count} Broadway, {len(snapshot.shows) - broadway_count} Off-Broadway) written to {settings.snapshot_path}"


async def refresh_movies() -> str:
    settings = movies_settings_from_environment()
    snapshot = await refresh_movies_snapshot(settings)
    return f"{len(snapshot.movies)} movies at {len(snapshot.theaters)} Manhattan theaters, {snapshot.first_day} to {snapshot.last_day}, written to {settings.snapshot_path}"


if __name__ == "__main__":
    main()
