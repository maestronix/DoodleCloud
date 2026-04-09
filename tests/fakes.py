from __future__ import annotations

from typing import Iterable, Optional

from storage_core.interfaces import ChunkStore, MetadataStore
from storage_core.models import ChunkMetadata, FileMetadata


class InMemoryMetadataStore(MetadataStore):
    def __init__(self):
        self.files: dict[str, FileMetadata] = {}
        self.path_index: dict[str, str] = {}
        self.chunks: dict[str, list[ChunkMetadata]] = {}

    def init_schema(self) -> None:
        return

    def upsert_file(self, metadata: FileMetadata) -> None:
        self.files[metadata.file_id] = metadata
        self.path_index[metadata.path] = metadata.file_id

    def replace_chunks(self, file_id: str, chunks: Iterable[ChunkMetadata]) -> None:
        self.chunks[file_id] = sorted(chunks, key=lambda c: c.chunk_index)

    def get_file_by_path(self, path: str) -> Optional[FileMetadata]:
        file_id = self.path_index.get(path)
        return self.files.get(file_id) if file_id else None

    def get_file_by_id(self, file_id: str) -> Optional[FileMetadata]:
        return self.files.get(file_id)

    def list_children(self, parent_path: str) -> list[FileMetadata]:
        prefix = "/" if parent_path == "/" else parent_path.rstrip("/") + "/"
        return sorted([f for f in self.files.values() if f.path.startswith(prefix)], key=lambda x: x.path)

    def get_chunks(self, file_id: str) -> list[ChunkMetadata]:
        return list(self.chunks.get(file_id, []))

    def list_all_files(self) -> list[FileMetadata]:
        return list(self.files.values())

    def delete_file_by_path(self, path: str) -> bool:
        file_id = self.path_index.pop(path, None)
        if not file_id:
            return False
        self.files.pop(file_id, None)
        self.chunks.pop(file_id, None)
        return True


class FakeChunkStore(ChunkStore):
    def __init__(self, mapping: dict[str, bytes]):
        self.mapping = mapping
        self.fetch_count: dict[str, int] = {}

    def fetch_chunk(self, remote_id: str) -> bytes:
        self.fetch_count[remote_id] = self.fetch_count.get(remote_id, 0) + 1
        if remote_id not in self.mapping:
            raise KeyError(remote_id)
        return self.mapping[remote_id]

    def store_chunk(self, chunk_data: bytes) -> str:
        key = f"id_{len(self.mapping)}"
        self.mapping[key] = chunk_data
        return key
