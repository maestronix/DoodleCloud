import json
import time
import uuid
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from config_loader import CONF
from storage_core.models import ChunkMetadata, FileMetadata
from storage_core.metadata_store import PostgresMetadataStore


def get_connection():
    try:
        db_host = CONF.get("DB_HOST")
        sslmode = 'disable' if db_host in ['localhost', '127.0.0.1', 'postgres'] else 'require'

        return psycopg2.connect(
            host=db_host,
            database=CONF.get("DB_NAME"),
            user=CONF.get("DB_USER"),
            password=CONF.get("DB_PASS"),
            port=CONF.get("DB_PORT"),
            sslmode=sslmode
        )
    except Exception:
        return None


_store = PostgresMetadataStore()


def init_db():
    conn = get_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        # Legacy table preserved for non-breaking migrations and rollback.
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS insta_files_v2 (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255) NOT NULL,
                media_ids TEXT NOT NULL,
                is_converted BOOLEAN DEFAULT FALSE,
                created_at BIGINT
            );
            """
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

    _store.init_schema()


def _normalize_path(filename: str) -> str:
    return "/" + filename.strip("/")


def save_file_record(filename, media_ids_list, is_converted):
    try:
        file_id = str(uuid.uuid4())
        now = int(time.time())
        chunk_sizes = [0] * len(media_ids_list)
        metadata = FileMetadata(
            file_id=file_id,
            path=_normalize_path(filename),
            filename=filename,
            size=0,
            mtime=now,
            ctime=now,
            content_type=None,
            checksum=None,
            chunk_count=len(media_ids_list),
        )
        chunks = []
        offset = 0
        for idx, media_id in enumerate(media_ids_list):
            size = chunk_sizes[idx]
            chunks.append(
                ChunkMetadata(
                    file_id=file_id,
                    chunk_index=idx,
                    byte_offset=offset,
                    chunk_size=size,
                    remote_id=str(media_id),
                    checksum=None,
                )
            )
            offset += size

        _store.upsert_file(metadata)
        _store.replace_chunks(file_id, chunks)

        # Legacy row maintained for current GUI/CLI compatibility paths.
        conn = get_connection()
        if conn:
            try:
                cur = conn.cursor()
                ids_json = json.dumps(media_ids_list)
                query = "INSERT INTO insta_files_v2 (filename, media_ids, is_converted, created_at) VALUES (%s, %s, %s, %s)"
                cur.execute(query, (filename, ids_json, is_converted, now))
                conn.commit()
            finally:
                conn.close()

    except Exception as e:
        print(f"DB Save Error: {e}")


def _list_new_model():
    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT f.file_id, f.filename, f.path, f.chunk_count, f.mtime,
                   COALESCE(json_agg(c.remote_id ORDER BY c.chunk_index) FILTER (WHERE c.remote_id IS NOT NULL), '[]') AS media_ids
            FROM dc_files f
            LEFT JOIN dc_chunks c ON c.file_id = f.file_id
            GROUP BY f.file_id, f.filename, f.path, f.chunk_count, f.mtime
            ORDER BY f.mtime DESC
            """
        )
        rows = cur.fetchall()
        for row in rows:
            row["id"] = row["file_id"]
            row["is_converted"] = True
            row["created_at"] = row["mtime"]
            if isinstance(row["media_ids"], list):
                row["media_ids"] = json.dumps(row["media_ids"])
        return rows
    except Exception:
        return []
    finally:
        conn.close()


def list_files():
    files = _list_new_model()
    if files:
        return files

    conn = get_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM insta_files_v2 ORDER BY created_at DESC")
        return cur.fetchall()
    except Exception:
        return []
    finally:
        conn.close()


def delete_file_record(record_id):
    conn = get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM dc_files WHERE file_id = %s", (str(record_id),))
        cur.execute("DELETE FROM insta_files_v2 WHERE id = %s", (record_id,))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_file_by_path(path: str) -> Optional[FileMetadata]:
    return _store.get_file_by_path(path)


def get_chunks(file_id: str):
    return _store.get_chunks(file_id)


init_db()
