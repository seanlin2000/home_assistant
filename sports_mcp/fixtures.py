"""Recorded ESPN answers served instead of ESPN, for the benchmark's category J (design doc v2/01 section 3.3).

Each answer is one JSON file named after its address and query, so benchmark/record_sports_fixtures.py and this transport agree on the name. An
address with no recording answers 404, which the tools report as ESPN not answering, so a missing recording shows in the run.
"""

import re
from pathlib import Path
from urllib.parse import urlencode

import httpx

NOT_A_FILE_NAME_CHARACTER = re.compile(r"[^A-Za-z0-9=&.+-]")
NOT_RECORDED = 404


def fixture_file_name(url: httpx.URL) -> str:
    query = urlencode(sorted(url.params.multi_items()))
    return NOT_A_FILE_NAME_CHARACTER.sub("_", f"{url.host}{url.path}" + (f"__{query}" if query else "")) + ".json"


class FixtureTransport(httpx.AsyncBaseTransport):
    def __init__(self, fixtures_dir: Path) -> None:
        self._fixtures_dir = fixtures_dir

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = self._fixtures_dir / fixture_file_name(request.url)
        if not path.is_file():
            return httpx.Response(NOT_RECORDED, request=request)
        return httpx.Response(200, content=path.read_bytes(), headers={"content-type": "application/json"}, request=request)
