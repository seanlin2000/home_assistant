"""Records the newest Chrome that Macs have fully rolled out, for the browser user agent (utils/browser_utils.py), from Google's VersionHistory API.

The API is public and needs no key. Chrome reaches Macs in stages, and each serving release carries `fraction`, the share of its rollout group it is
offered to: on 2026-10-30 build 156.0.8078.80 was at 1 while 157.0.8103.26 had just started at 0.005. The agent names the newest release at a full
rollout, the version most Macs run, rather than one only a few have.
"""

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from utils.browser_utils import CHROME_RELEASE_PATH, ChromeRelease
from utils.snapshot_utils import ListingsUnavailable, write_snapshot

SERVING_RELEASES_URL = "https://versionhistory.googleapis.com/v1/chrome/platforms/mac/channels/stable/versions/all/releases"
SERVING_NOW = {"filter": "endtime=none"}  # only releases still being offered
FULL_ROLLOUT = 1.0
VERSION_FORM = re.compile(r"^\d+(?:\.\d+)+$")  # "156.0.8078.80"; anything else is skipped, never guessed at
OK = 200
TIMEOUT_SECONDS = 15.0


class ChromeReleasesUnavailable(ListingsUnavailable):
    """The VersionHistory API did not answer, or answered without a fully rolled-out release; the last record stays."""


async def refresh_chrome_release(path: Path = CHROME_RELEASE_PATH, transport: httpx.AsyncBaseTransport | None = None) -> ChromeRelease:
    """Reads the serving releases and replaces the record. A failed read raises before anything is written."""
    release = newest_full_rollout(await read_serving_releases(transport))
    write_snapshot(path, release)
    return release


async def read_serving_releases(transport: httpx.AsyncBaseTransport | None) -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=transport) as client:
            response = await client.get(SERVING_RELEASES_URL, params=SERVING_NOW)
    except httpx.HTTPError as error:
        raise ChromeReleasesUnavailable(f"no answer from the VersionHistory API ({type(error).__name__})") from error
    if response.status_code != OK:
        raise ChromeReleasesUnavailable(f"the VersionHistory API answered {response.status_code}")
    try:
        return list(response.json()["releases"])
    except (ValueError, KeyError, TypeError) as error:
        raise ChromeReleasesUnavailable(f"the VersionHistory API's answer was not in the expected shape ({type(error).__name__}: {error})") from error


def newest_full_rollout(releases: list[dict[str, Any]]) -> ChromeRelease:
    full_rollouts = [release["version"] for release in releases if release.get("fraction", 0) >= FULL_ROLLOUT and VERSION_FORM.match(str(release.get("version", "")))]
    if not full_rollouts:
        raise ChromeReleasesUnavailable(f"none of the {len(releases)} serving releases is at a full rollout")
    version = max(full_rollouts, key=version_numbers)
    return ChromeRelease(refreshed_at=datetime.now(UTC), major=version_numbers(version)[0], version=version)


def version_numbers(version: str) -> tuple[int, ...]:
    """Splits "156.0.8078.80" into (156, 0, 8078, 80), so 156.0.8078.100 sorts after 156.0.8078.80 as numbers do and strings do not."""
    return tuple(int(part) for part in version.split("."))
