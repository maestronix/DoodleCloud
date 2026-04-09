from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FileMetadata:
    file_id: str
    path: str
    filename: str
    size: int
    mtime: int
    ctime: int
    content_type: Optional[str]
    checksum: Optional[str]
    chunk_count: int


@dataclass(frozen=True)
class ChunkMetadata:
    file_id: str
    chunk_index: int
    byte_offset: int
    chunk_size: int
    remote_id: str
    checksum: Optional[str]


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start
