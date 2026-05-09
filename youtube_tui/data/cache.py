from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Optional


class TTLCache:
    def __init__(self, max_size: int = 128) -> None:
        self._max_size = max_size
        self._store: "OrderedDict[Any, tuple[float, Any]]" = OrderedDict()

    def get(self, key: Any) -> Optional[Any]:
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at <= time.monotonic():
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return value

    def put(self, key: Any, value: Any, ttl_s: float) -> None:
        expires_at = time.monotonic() + ttl_s
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (expires_at, value)
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    def __len__(self) -> int:
        return len(self._store)

    def clear(self) -> None:
        self._store.clear()
