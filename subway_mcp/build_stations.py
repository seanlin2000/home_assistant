"""Builds the checked-in station table from New York State's open-data copy of MTA's station list (design doc v2/15 section 3.2).

Run by hand when MTA opens, closes, or renames a station, and review the change in a pull request:

    uv run python -m subway_mcp.build_stations

Each dataset row is one stop (a platform for one or more lines). Stops that share a complex_id are one station a rider can transfer within, so the
table is grouped by complex. Which lines a station has today is never read from here; daytime_routes only explains a line that is missing.
"""

import json
from pathlib import Path
from typing import Any

import httpx

from subway_mcp.settings import SubwaySettings

STATIONS_DATASET_URL = "https://data.ny.gov/resource/39hk-dx4f.json"
DATASET_ROW_LIMIT = 5000  # 496 stops in 2026; the dataset's API returns 1,000 rows unless asked for more
STATIONS_PATH = Path(__file__).parent / "stations.json"
BOROUGH_NAMES = {"M": "Manhattan", "Bk": "Brooklyn", "Q": "Queens", "Bx": "Bronx", "SI": "Staten Island"}


def fetch_station_rows(settings: SubwaySettings) -> list[dict[str, Any]]:
    response = httpx.get(STATIONS_DATASET_URL, params={"$limit": DATASET_ROW_LIMIT}, headers={"User-Agent": settings.user_agent}, timeout=settings.timeout_seconds)
    response.raise_for_status()
    return response.json()


def station_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per complex, its stops in dataset order, the complexes ordered by their first stop's ID so a rebuild diffs cleanly."""
    complexes: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        complexes.setdefault(row["complex_id"], []).append(stop_entry(row))
    stations = [{"complex_id": complex_id, "stops": stops} for complex_id, stops in complexes.items()]
    return sorted(stations, key=lambda station: station["stops"][0]["stop_id"])


def stop_entry(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "stop_id": row["gtfs_stop_id"],
        "name": row["stop_name"],
        "daytime_lines": row.get("daytime_routes", "").split(),
        "north_label": row.get("north_direction_label", ""),
        "south_label": row.get("south_direction_label", ""),
        "borough": BOROUGH_NAMES[row["borough"]],
    }


def write_station_table(stations: list[dict[str, Any]], path: Path) -> None:
    path.write_text(json.dumps(stations, indent=1, ensure_ascii=False) + "\n")


def main() -> None:
    stations = station_table(fetch_station_rows(SubwaySettings()))
    write_station_table(stations, STATIONS_PATH)
    print(f"wrote {len(stations)} stations to {STATIONS_PATH}")


if __name__ == "__main__":
    main()
