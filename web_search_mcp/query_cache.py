"""Optional on-disk cache keyed by query string and URL. The benchmark turns it on so every candidate sees identical search results; production leaves it off."""

from typing import Any

import diskcache


class QueryCache:
    def __init__(self, cache_dir: str | None) -> None:
        self._cache = diskcache.Cache(cache_dir) if cache_dir else None

    @property
    def enabled(self) -> bool:
        return self._cache is not None

    def get_search(self, query: str) -> list[dict[str, Any]] | None:
        return self._get(f"search:{query.strip().lower()}")

    def put_search(self, query: str, results: list[dict[str, Any]]) -> None:
        self._put(f"search:{query.strip().lower()}", results)

    def get_page(self, url: str) -> str | None:
        return self._get(f"page:{url}")

    def put_page(self, url: str, text: str) -> None:
        self._put(f"page:{url}", text)

    def _get(self, key: str) -> Any:
        return None if self._cache is None else self._cache.get(key)

    def _put(self, key: str, value: Any) -> None:
        if self._cache is not None:
            self._cache.set(key, value)
