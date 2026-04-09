from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Optional

from storage_core.models import ChunkMetadata, FileMetadata


class MetadataStore(ABC):
    @abstractmethod
    def init_schema(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def upsert_file(self, metadata: FileMetadata) -> None:
        raise NotImplementedError

    @abstractmethod
    def replace_chunks(self, file_id: str, chunks: Iterable[ChunkMetadata]) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_file_by_path(self, path: str) -> Optional[FileMetadata]:
        raise NotImplementedError

    @abstractmethod
    def get_file_by_id(self, file_id: str) -> Optional[FileMetadata]:
        raise NotImplementedError

    @abstractmethod
    def list_children(self, parent_path: str) -> list[FileMetadata]:
        raise NotImplementedError

    @abstractmethod
    def get_chunks(self, file_id: str) -> list[ChunkMetadata]:
        raise NotImplementedError

    @abstractmethod
    def list_all_files(self) -> list[FileMetadata]:
        raise NotImplementedError

    @abstractmethod
    def delete_file_by_path(self, path: str) -> bool:
        raise NotImplementedError


class ChunkStore(ABC):
    @abstractmethod
    def fetch_chunk(self, remote_id: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def store_chunk(self, chunk_data: bytes) -> str:
        raise NotImplementedError


class ChunkCache(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[bytes]:
        raise NotImplementedError

    @abstractmethod
    def put(self, key: str, value: bytes) -> None:
        raise NotImplementedError


class FileReader(ABC):
    @abstractmethod
    def read_range(self, path: str, start: int, length: int) -> bytes:
        raise NotImplementedError
