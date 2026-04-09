from __future__ import annotations

import logging
import threading
import time
from bisect import bisect_right

from storage_core.codec import png_to_bytes
from storage_core.interfaces import ChunkCache, ChunkStore, FileReader, MetadataStore
from storage_core.models import ChunkMetadata

logger = logging.getLogger(__name__)


class RangeFileReader(FileReader):
    def __init__(
        self,
        metadata_store: MetadataStore,
        chunk_store: ChunkStore,
        cache: ChunkCache,
        prefetch_chunks: int = 2,
    ):
        self.metadata_store = metadata_store
        self.chunk_store = chunk_store
        self.cache = cache
        self.prefetch_chunks = max(prefetch_chunks, 0)

    def _chunk_for_offset(self, chunks: list[ChunkMetadata], offset: int) -> int:
        starts = [c.byte_offset for c in chunks]
        idx = bisect_right(starts, offset) - 1
        return max(idx, 0)

    def _fetch_decoded_chunk(self, chunk: ChunkMetadata) -> bytes:
        cache_key = f"{chunk.remote_id}:decoded"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        raw = self.chunk_store.fetch_chunk(chunk.remote_id)
        decoded = png_to_bytes(raw)
        self.cache.put(cache_key, decoded)
        return decoded

    def _prefetch(self, chunks: list[ChunkMetadata], from_index: int) -> None:
        upper = min(len(chunks), from_index + self.prefetch_chunks + 1)
        for idx in range(from_index + 1, upper):
            chunk = chunks[idx]
            threading.Thread(target=self._fetch_decoded_chunk, args=(chunk,), daemon=True).start()

    def read_range(self, path: str, start: int, length: int) -> bytes:
        t0 = time.perf_counter()
        file_meta = self.metadata_store.get_file_by_path(path)
        if file_meta is None:
            raise FileNotFoundError(path)

        if start < 0 or length < 0:
            raise ValueError("start and length must be non-negative")
        if start >= file_meta.size or length == 0:
            return b""

        end = min(file_meta.size, start + length)
        logger.info("range_request path=%s start=%s end=%s len=%s", path, start, end, end - start)

        chunks = self.metadata_store.get_chunks(file_meta.file_id)
        if not chunks:
            return b""

        current_offset = start
        idx = self._chunk_for_offset(chunks, current_offset)
        touched_chunks = []
        assembled = bytearray()

        while current_offset < end and idx < len(chunks):
            chunk = chunks[idx]
            chunk_start = chunk.byte_offset
            chunk_end = chunk.byte_offset + chunk.chunk_size

            if current_offset >= chunk_end:
                idx += 1
                continue
            if end <= chunk_start:
                break

            chunk_data = self._fetch_decoded_chunk(chunk)
            touched_chunks.append(chunk.chunk_index)
            self._prefetch(chunks, idx)

            rel_start = max(current_offset - chunk_start, 0)
            rel_end = min(end - chunk_start, len(chunk_data))
            assembled.extend(chunk_data[rel_start:rel_end])
            current_offset = chunk_start + rel_end
            idx += 1

        dt_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "range_assembly path=%s touched=%s bytes=%s duration_ms=%.2f",
            path,
            touched_chunks,
            len(assembled),
            dt_ms,
        )
        if dt_ms > 1500:
            logger.warning("high_latency_range path=%s duration_ms=%.2f", path, dt_ms)
        return bytes(assembled)
