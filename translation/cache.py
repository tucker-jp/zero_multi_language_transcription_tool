"""LRU cache for translation lookups."""

from __future__ import annotations

from collections import OrderedDict


class TranslationCache:
    """Thread-safe LRU cache for translations."""

    def __init__(self, maxsize: int = 1000):
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> str | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: str, value: str):
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = value
        else:
            if len(self._cache) >= self._maxsize:
                self._cache.popitem(last=False)
            self._cache[key] = value

    def clear(self):
        self._cache.clear()
