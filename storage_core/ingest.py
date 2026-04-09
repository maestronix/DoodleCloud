from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import time
import uuid

import auth

from storage_core.codec import bytes_to_png
from storage_core.interfaces import ChunkStore, MetadataStore
from storage_core.models import ChunkMetadata, FileMetadata

logger = logging.getLogger(__name__)
DEFAULT_CHUNK_SIZE = 20 * 1024 * 1024


class FileIngestService:
    def __init__(self, metadata_store: MetadataStore, chunk_store: ChunkStore, auth_token: str, target_thread_id: str, client):
        self.metadata_store = metadata_store
        self.chunk_store = chunk_store
        self.auth_token = auth_token
        self.target_thread_id = target_thread_id
        self.client = client

    def ingest_file(self, source_path: str, target_path: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> FileMetadata:
        now = int(time.time())
        filename = os.path.basename(target_path)
        stat = os.stat(source_path)
        file_id = str(uuid.uuid4())
        content_type = mimetypes.guess_type(filename)[0]

        chunks: list[ChunkMetadata] = []
        digest = hashlib.sha256()
        offset = 0
        chunk_index = 0

        with open(source_path, "rb") as f:
            while True:
                payload = f.read(chunk_size)
                if not payload:
                    break
                digest.update(payload)
                png_bytes = bytes_to_png(payload)
                media_id = self.chunk_store.store_chunk(png_bytes)
                chunks.append(
                    ChunkMetadata(
                        file_id=file_id,
                        chunk_index=chunk_index,
                        byte_offset=offset,
                        chunk_size=len(payload),
                        remote_id=media_id,
                        checksum=hashlib.sha256(payload).hexdigest(),
                    )
                )

                item_id, otid = auth.get_random_message(self.client, self.target_thread_id)
                if item_id:
                    import upload

                    upload.attach_doodle_step_2(media_id, self.auth_token, self.target_thread_id, item_id, otid)

                offset += len(payload)
                chunk_index += 1

        metadata = FileMetadata(
            file_id=file_id,
            path=target_path,
            filename=filename,
            size=stat.st_size,
            mtime=int(stat.st_mtime),
            ctime=now,
            content_type=content_type,
            checksum=digest.hexdigest(),
            chunk_count=len(chunks),
        )
        self.metadata_store.upsert_file(metadata)
        self.metadata_store.replace_chunks(file_id, chunks)
        logger.info("ingested path=%s chunks=%s size=%s", target_path, len(chunks), stat.st_size)
        return metadata
