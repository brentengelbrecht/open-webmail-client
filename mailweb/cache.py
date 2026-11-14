"""A small thread-safe LRU cache with optional time-to-live."""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Callable, Generic, Hashable, Optional, TypeVar

V = TypeVar("V")


class Cache(Generic[V]):
    def __init__(self, maxsize: int, ttl: Optional[float] = None,
                 clock: Callable[[], float] = time.monotonic):
        self._maxsize = maxsize
        self._ttl = ttl
        self._clock = clock
        self._items: "OrderedDict[Hashable, tuple[float, V]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> Optional[V]:
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            stored_at, value = entry
            if self._ttl is not None and self._clock() - stored_at > self._ttl:
                del self._items[key]
                return None
            self._items.move_to_end(key)
            return value

    def set(self, key: Hashable, value: V) -> V:
        with self._lock:
            self._items[key] = (self._clock(), value)
            self._items.move_to_end(key)
            while len(self._items) > self._maxsize:
                self._items.popitem(last=False)
        return value

    def discard(self, key: Hashable) -> None:
        with self._lock:
            self._items.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def values(self) -> list:
        with self._lock:
            return [value for _, value in self._items.values()]
