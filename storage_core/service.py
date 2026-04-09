from __future__ import annotations

import logging
import os

from storage_core.cache import LRUChunkCache
from storage_core.cachefs import CachedMetadataStore
from storage_core.chunk_store import InstagramChunkStore
from storage_core.ingest import FileIngestService
from storage_core.metadata_store import PostgresMetadataStore
from storage_core.range_reader import RangeFileReader


def configure_logging() -> None:
    level = os.environ.get("DOODLE_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def build_services(auth_token: str, user_id: str, target_thread_id: str | None = None, client=None):
    backing_metadata_store = PostgresMetadataStore()
    backing_metadata_store.init_schema()
    metadata_store = CachedMetadataStore(backing_metadata_store)
    metadata_store.warm_load()

    chunk_store = InstagramChunkStore(auth_token=auth_token, user_id=user_id)
    cache = LRUChunkCache(
        max_bytes=int(os.environ.get("DOODLE_CACHE_MAX_BYTES", str(256 * 1024 * 1024))),
        ttl_seconds=int(os.environ.get("DOODLE_CACHE_TTL_SECONDS", "0")) or None,
    )
    reader = RangeFileReader(
        metadata_store=metadata_store,
        chunk_store=chunk_store,
        cache=cache,
        prefetch_chunks=int(os.environ.get("DOODLE_READAHEAD_CHUNKS", "2")),
    )

    ingest = None
    if target_thread_id and client:
        ingest = FileIngestService(metadata_store, chunk_store, auth_token, target_thread_id, client)

    return {
        "metadata_store": metadata_store,
        "metadata_store_backing": backing_metadata_store,
        "chunk_store": chunk_store,
        "cache": cache,
        "reader": reader,
        "ingest": ingest,
    }
