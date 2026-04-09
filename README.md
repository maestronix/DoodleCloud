# DoodleCloud ☁️

> **Instagram/CDN-backed virtual storage with range reads and WebDAV exposure.**

DoodleCloud now focuses on a storage-core architecture suitable for streaming and mounted workloads (for example, rclone over WebDAV), while still using Instagram-hosted doodle media as the remote chunk backend.

## What changed

- Added a proper metadata index with file paths and per-chunk offset mapping (`dc_files`, `dc_chunks`).
- Added a **CacheFS metadata layer** that preloads postgres metadata/chunk index on startup and serves reads from memory.
- Added a range-capable file reader that fetches only required chunks.
- Added chunk cache with bounded size + optional TTL eviction.
- Added ingest service that stores chunk metadata with byte offsets.
- Added protocol module (`protocol/webdav_server.py`) exposing byte-range reads for rclone-compatible WebDAV clients.
- Added WebDAV `PUT` and `DELETE` paths to delegate writes/deletes through storage-core operations.

## Core modules

- `storage_core/metadata_store.py` – metadata/index layer.
- `storage_core/cachefs.py` – in-memory metadata cachefs index.
- `storage_core/chunk_store.py` – Instagram/CDN chunk fetch/store adapter.
- `storage_core/range_reader.py` – range-to-chunk mapping, stitching, read-ahead.
- `storage_core/cache.py` – LRU chunk cache.
- `storage_core/ingest.py` – file writer/ingest pipeline.
- `protocol/webdav_server.py` – external protocol layer.

## Running the WebDAV service

```bash
python protocol/webdav_server.py
```

Default endpoint: `http://127.0.0.1:8080/dav`

## Testing

```bash
pytest -q
```

The tests validate path lookup, byte-range mapping, chunk-boundary reads, random seeks, cache behavior, and error handling.

## Notes on limitations

Instagram/CDN remote fetch latency and API reliability remain fundamental constraints. The new architecture makes behavior correct and debuggable while minimizing remote reads through range fetching + cache.

Remote chunk hard-delete is still backend-limited by upstream API behavior; metadata delete is supported and immediate.
