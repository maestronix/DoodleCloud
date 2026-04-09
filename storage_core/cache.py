from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from storage_core.interfaces import ChunkCache

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    value: bytes
    inserted_at: float


class LRUChunkCache(ChunkCache):
    def __init__(self, max_bytes: int = 512 * 1024 * 1024, ttl_seconds: Optional[int] = None):
        self.max_bytes = max_bytes
        self.ttl_seconds = ttl_seconds
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._used_bytes = 0

    def _is_expired(self, entry: CacheEntry) -> bool:
        if self.ttl_seconds is None:
            return False
        return (time.time() - entry.inserted_at) > self.ttl_seconds

    def get(self, key: str) -> Optional[bytes]:
        entry = self._entries.get(key)
        if entry is None:
            logger.debug("cache miss key=%s", key)
            return None
        if self._is_expired(entry):
            logger.debug("cache expired key=%s", key)
            self._used_bytes -= len(entry.value)
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        logger.debug("cache hit key=%s size=%s", key, len(entry.value))
        return entry.value

    def put(self, key: str, value: bytes) -> None:
        if len(value) > self.max_bytes:
            logger.warning("cache bypass key=%s value_too_large=%s", key, len(value))
            return

        if key in self._entries:
            old = self._entries.pop(key)
            self._used_bytes -= len(old.value)

        self._entries[key] = CacheEntry(value=value, inserted_at=time.time())
        self._used_bytes += len(value)
        self._entries.move_to_end(key)

        while self._used_bytes > self.max_bytes and self._entries:
            evicted_key, evicted_entry = self._entries.popitem(last=False)
            self._used_bytes -= len(evicted_entry.value)
            logger.debug("cache evict key=%s size=%s", evicted_key, len(evicted_entry.value))
