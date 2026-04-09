from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Iterable, Optional

from storage_core.interfaces import MetadataStore
from storage_core.models import ChunkMetadata, FileMetadata

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DirectoryEntry:
    path: str
    is_dir: bool
    size: int
    mtime: int


class CachedMetadataStore(MetadataStore):
    """
    Warm in-memory metadata index.
    - Loads all file + chunk metadata at startup.
    - Serves path/chunk lookups from memory to reduce postgres reads.
    - Delegates writes to backing store and updates in-memory state.
    """

    def __init__(self, backing: MetadataStore):
        self.backing = backing
        self._lock = threading.RLock()
        self._files_by_id: dict[str, FileMetadata] = {}
        self._file_id_by_path: dict[str, str] = {}
        self._chunks_by_file: dict[str, list[ChunkMetadata]] = {}

    def init_schema(self) -> None:
        self.backing.init_schema()

    def warm_load(self) -> None:
        all_files = self.backing.list_all_files()
        with self._lock:
            self._files_by_id = {f.file_id: f for f in all_files}
            self._file_id_by_path = {f.path: f.file_id for f in all_files}
            self._chunks_by_file = {f.file_id: self.backing.get_chunks(f.file_id) for f in all_files}
        logger.info("cachefs_warm_loaded files=%s", len(all_files))

    def upsert_file(self, metadata: FileMetadata) -> None:
        self.backing.upsert_file(metadata)
        with self._lock:
            self._files_by_id[metadata.file_id] = metadata
            self._file_id_by_path[metadata.path] = metadata.file_id

    def replace_chunks(self, file_id: str, chunks: Iterable[ChunkMetadata]) -> None:
        chunk_list = list(chunks)
        self.backing.replace_chunks(file_id, chunk_list)
        with self._lock:
            self._chunks_by_file[file_id] = sorted(chunk_list, key=lambda x: x.chunk_index)

    def get_file_by_path(self, path: str) -> Optional[FileMetadata]:
        with self._lock:
            file_id = self._file_id_by_path.get(path)
            if not file_id:
                return None
            return self._files_by_id.get(file_id)

    def get_file_by_id(self, file_id: str) -> Optional[FileMetadata]:
        with self._lock:
            return self._files_by_id.get(file_id)

    def list_children(self, parent_path: str) -> list[FileMetadata]:
        normalized = "/" if parent_path == "/" else parent_path.rstrip("/")
        prefix = normalized.rstrip("/") + "/"
        with self._lock:
            return sorted(
                [f for f in self._files_by_id.values() if f.path.startswith(prefix)],
                key=lambda x: x.path,
            )

    def get_chunks(self, file_id: str) -> list[ChunkMetadata]:
        with self._lock:
            return list(self._chunks_by_file.get(file_id, []))

    def list_all_files(self) -> list[FileMetadata]:
        with self._lock:
            return list(self._files_by_id.values())

    def delete_file_by_path(self, path: str) -> bool:
        ok = self.backing.delete_file_by_path(path)
        if not ok:
            return False
        with self._lock:
            file_id = self._file_id_by_path.pop(path, None)
            if file_id:
                self._files_by_id.pop(file_id, None)
                self._chunks_by_file.pop(file_id, None)
        return True

    def list_directory_entries(self, parent_path: str) -> list[DirectoryEntry]:
        normalized = "/" if parent_path == "/" else parent_path.rstrip("/")
        prefix = "" if normalized == "/" else f"{normalized}/"

        dirs: dict[str, DirectoryEntry] = {}
        files: dict[str, DirectoryEntry] = {}

        with self._lock:
            for f in self._files_by_id.values():
                if not f.path.startswith(prefix):
                    continue
                rel = f.path[len(prefix):] if prefix else f.path.lstrip("/")
                if not rel:
                    continue
                if "/" in rel:
                    dirname = rel.split("/", 1)[0]
                    dpath = (prefix + dirname).rstrip("/")
                    if not dpath.startswith("/"):
                        dpath = "/" + dpath
                    dirs[dpath] = DirectoryEntry(path=dpath, is_dir=True, size=0, mtime=f.mtime)
                else:
                    files[f.path] = DirectoryEntry(path=f.path, is_dir=False, size=f.size, mtime=f.mtime)

        return sorted([*dirs.values(), *files.values()], key=lambda x: x.path)
