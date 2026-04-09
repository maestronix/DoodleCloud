from __future__ import annotations

from storage_core.cache import LRUChunkCache
from storage_core.codec import bytes_to_png
from storage_core.models import ChunkMetadata, FileMetadata
from storage_core.range_reader import RangeFileReader
from tests.fakes import FakeChunkStore, InMemoryMetadataStore


def build_reader(payload: bytes, chunk_size: int = 8):
    store = InMemoryMetadataStore()
    file_id = "f1"
    meta = FileMetadata(
        file_id=file_id,
        path="/media/video.bin",
        filename="video.bin",
        size=len(payload),
        mtime=1,
        ctime=1,
        content_type="application/octet-stream",
        checksum=None,
        chunk_count=(len(payload) + chunk_size - 1) // chunk_size,
    )
    store.upsert_file(meta)

    chunks = []
    remote = {}
    for idx in range(meta.chunk_count):
        start = idx * chunk_size
        part = payload[start : start + chunk_size]
        rid = f"r{idx}"
        remote[rid] = bytes_to_png(part)
        chunks.append(
            ChunkMetadata(
                file_id=file_id,
                chunk_index=idx,
                byte_offset=start,
                chunk_size=len(part),
                remote_id=rid,
                checksum=None,
            )
        )
    store.replace_chunks(file_id, chunks)

    chunk_store = FakeChunkStore(remote)
    reader = RangeFileReader(store, chunk_store, LRUChunkCache(max_bytes=1024 * 1024), prefetch_chunks=0)
    return reader, chunk_store, store


def test_lookup_by_path():
    reader, _, store = build_reader(b"abcdef")
    assert store.get_file_by_path("/media/video.bin") is not None
    assert reader.read_range("/media/video.bin", 0, 3) == b"abc"


def test_range_mapping_across_boundary():
    reader, _, _ = build_reader(b"abcdefghijklmnopqrstuvwxyz", chunk_size=5)
    data = reader.read_range("/media/video.bin", 4, 10)
    assert data == b"efghijklmn"


def test_small_random_seeks():
    reader, _, _ = build_reader(b"0123456789ABCDEFGHIJ", chunk_size=4)
    assert reader.read_range("/media/video.bin", 0, 2) == b"01"
    assert reader.read_range("/media/video.bin", 11, 3) == b"BCD"
    assert reader.read_range("/media/video.bin", 7, 4) == b"789A"


def test_cache_hit_on_repeated_reads():
    reader, chunk_store, _ = build_reader(b"abcdefghijklmno", chunk_size=5)
    assert reader.read_range("/media/video.bin", 0, 5) == b"abcde"
    assert reader.read_range("/media/video.bin", 0, 5) == b"abcde"
    assert chunk_store.fetch_count["r0"] == 1


def test_nonexistent_file_and_missing_chunk_handling():
    reader, chunk_store, _ = build_reader(b"abcdefgh", chunk_size=4)
    try:
        reader.read_range("/missing", 0, 1)
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass

    del chunk_store.mapping["r1"]
    try:
        reader.read_range("/media/video.bin", 4, 2)
        assert False, "expected chunk failure"
    except KeyError:
        pass


def test_cache_eviction():
    reader, chunk_store, _ = build_reader(b"abcdefghijklmnopqrstuvwxyz", chunk_size=6)
    reader.cache.max_bytes = 12
    reader.read_range("/media/video.bin", 0, 6)
    reader.read_range("/media/video.bin", 6, 6)
    reader.read_range("/media/video.bin", 12, 6)
    reader.read_range("/media/video.bin", 0, 6)
    assert chunk_store.fetch_count["r0"] >= 2
