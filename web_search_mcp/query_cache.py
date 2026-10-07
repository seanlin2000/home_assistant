"""Optional on-disk cache keyed by query string, URL, forecast location, and Wikipedia topic or title. The benchmark turns it on so every candidate sees identical
search results, the same forecast, and the same article revisions; production leaves it off."""

from typing import Any

import diskcache


class QueryCache:
    def __init__(self, cache_dir: str | None) -> None:
        self._cache = diskcache.Cache(cache_dir) if cache_dir else None

    @property
    def enabled(self) -> bool:
        return self._cache is not None

    def get_search(self, query: str, time_range: str | None) -> list[dict[str, Any]] | None:
        return self._get(search_key(query, time_range))

    def put_search(self, query: str, time_range: str | None, results: list[dict[str, Any]]) -> None:
        self._put(search_key(query, time_range), results)

    def get_page(self, url: str) -> str | None:
        return self._get(f"page:{url}")

    def put_page(self, url: str, text: str) -> None:
        self._put(f"page:{url}", text)

    def get_forecast(self, location_key: str) -> dict[str, Any] | None:
        return self._get(f"forecast:{location_key}")

    def put_forecast(self, location_key: str, forecast: dict[str, Any]) -> None:
        self._put(f"forecast:{location_key}", forecast)

    def get_article_titles(self, topic: str) -> list[str] | None:
        return self._get(f"wiki:search:{topic.strip().lower()}")

    def put_article_titles(self, topic: str, titles: list[str]) -> None:
        self._put(f"wiki:search:{topic.strip().lower()}", titles)

    def get_article_html(self, title: str) -> str | None:
        return self._get(f"wiki:article:{title}")

    def put_article_html(self, title: str, html: str) -> None:
        self._put(f"wiki:article:{title}", html)

    def _get(self, key: str) -> Any:
        return None if self._cache is None else self._cache.get(key)

    def _put(self, key: str, value: Any) -> None:
        if self._cache is not None:
            self._cache.set(key, value)


def search_key(query: str, time_range: str | None) -> str:
    """A search without a time range keeps the key it always had, so a benchmark cache filled before time ranges existed still answers it."""
    return f"search:{query.strip().lower()}" + (f" time_range:{time_range}" if time_range else "")
