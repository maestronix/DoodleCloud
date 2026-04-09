from __future__ import annotations

from dataclasses import asdict
from typing import Iterable, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from config_loader import CONF
from storage_core.interfaces import MetadataStore
from storage_core.models import ChunkMetadata, FileMetadata


class PostgresMetadataStore(MetadataStore):
    def __init__(self):
        self._conn_params = {
            "host": CONF.get("DB_HOST"),
            "database": CONF.get("DB_NAME"),
            "user": CONF.get("DB_USER"),
            "password": CONF.get("DB_PASS"),
            "port": CONF.get("DB_PORT"),
        }

    def _connect(self):
        db_host = self._conn_params["host"]
        sslmode = "disable" if db_host in ["localhost", "127.0.0.1", "postgres"] else "require"
        return psycopg2.connect(sslmode=sslmode, **self._conn_params)

    def init_schema(self) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dc_files (
                    file_id TEXT PRIMARY KEY,
                    path TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL,
                    size BIGINT NOT NULL,
                    mtime BIGINT NOT NULL,
                    ctime BIGINT NOT NULL,
                    content_type TEXT,
                    checksum TEXT,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dc_chunks (
                    file_id TEXT NOT NULL REFERENCES dc_files(file_id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    byte_offset BIGINT NOT NULL,
                    chunk_size INTEGER NOT NULL,
                    remote_id TEXT NOT NULL,
                    checksum TEXT,
                    PRIMARY KEY(file_id, chunk_index)
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_dc_files_path ON dc_files(path);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_dc_chunks_file_offset ON dc_chunks(file_id, byte_offset);")
            conn.commit()

    def upsert_file(self, metadata: FileMetadata) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dc_files(file_id, path, filename, size, mtime, ctime, content_type, checksum, chunk_count, created_at, updated_at)
                VALUES (%(file_id)s, %(path)s, %(filename)s, %(size)s, %(mtime)s, %(ctime)s, %(content_type)s, %(checksum)s, %(chunk_count)s, %(ctime)s, %(mtime)s)
                ON CONFLICT(file_id) DO UPDATE SET
                    path = EXCLUDED.path,
                    filename = EXCLUDED.filename,
                    size = EXCLUDED.size,
                    mtime = EXCLUDED.mtime,
                    content_type = EXCLUDED.content_type,
                    checksum = EXCLUDED.checksum,
                    chunk_count = EXCLUDED.chunk_count,
                    updated_at = EXCLUDED.updated_at;
                """,
                asdict(metadata),
            )
            conn.commit()

    def replace_chunks(self, file_id: str, chunks: Iterable[ChunkMetadata]) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM dc_chunks WHERE file_id = %s", (file_id,))
            for chunk in chunks:
                cur.execute(
                    """
                    INSERT INTO dc_chunks(file_id, chunk_index, byte_offset, chunk_size, remote_id, checksum)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        chunk.file_id,
                        chunk.chunk_index,
                        chunk.byte_offset,
                        chunk.chunk_size,
                        chunk.remote_id,
                        chunk.checksum,
                    ),
                )
            conn.commit()

    def _to_file(self, row: Optional[dict]) -> Optional[FileMetadata]:
        if row is None:
            return None
        return FileMetadata(
            file_id=row["file_id"],
            path=row["path"],
            filename=row["filename"],
            size=row["size"],
            mtime=row["mtime"],
            ctime=row["ctime"],
            content_type=row.get("content_type"),
            checksum=row.get("checksum"),
            chunk_count=row["chunk_count"],
        )

    def get_file_by_path(self, path: str) -> Optional[FileMetadata]:
        with self._connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM dc_files WHERE path = %s", (path,))
            return self._to_file(cur.fetchone())

    def get_file_by_id(self, file_id: str) -> Optional[FileMetadata]:
        with self._connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM dc_files WHERE file_id = %s", (file_id,))
            return self._to_file(cur.fetchone())

    def list_children(self, parent_path: str) -> list[FileMetadata]:
        normalized = "/" if parent_path == "/" else parent_path.rstrip("/")
        like_prefix = normalized.rstrip("/") + "/%"
        with self._connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM dc_files
                WHERE path LIKE %s
                ORDER BY path ASC
                """,
                (like_prefix,),
            )
            return [self._to_file(row) for row in cur.fetchall() if row]


    def list_all_files(self) -> list[FileMetadata]:
        with self._connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM dc_files ORDER BY path ASC")
            return [self._to_file(row) for row in cur.fetchall() if row]

    def delete_file_by_path(self, path: str) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM dc_files WHERE path = %s", (path,))
            conn.commit()
            return cur.rowcount > 0

    def get_chunks(self, file_id: str) -> list[ChunkMetadata]:
        with self._connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM dc_chunks WHERE file_id = %s ORDER BY chunk_index ASC",
                (file_id,),
            )
            rows = cur.fetchall()
            return [
                ChunkMetadata(
                    file_id=row["file_id"],
                    chunk_index=row["chunk_index"],
                    byte_offset=row["byte_offset"],
                    chunk_size=row["chunk_size"],
                    remote_id=row["remote_id"],
                    checksum=row.get("checksum"),
                )
                for row in rows
            ]
