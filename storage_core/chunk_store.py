from __future__ import annotations

import logging
import time

import requests

import proxy
import upload
from storage_core.interfaces import ChunkStore

logger = logging.getLogger(__name__)
FALLBACK_URL = "https://i.instagram.com/api/v1/direct_v2/media_fallback/?entity_id={}&entity_type=59"


class InstagramChunkStore(ChunkStore):
    def __init__(self, auth_token: str, user_id: str):
        self.auth_token = auth_token
        self.user_id = user_id

    def fetch_chunk(self, remote_id: str) -> bytes:
        headers = {
            "User-Agent": proxy.get_device_headers()["User-Agent"],
            "Authorization": self.auth_token,
        }
        start = time.perf_counter()
        response = requests.get(FALLBACK_URL.format(remote_id), headers=headers, allow_redirects=True, timeout=60)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info("remote_fetch remote_id=%s status=%s duration_ms=%.2f", remote_id, response.status_code, elapsed_ms)
        response.raise_for_status()
        return response.content

    def store_chunk(self, chunk_data: bytes) -> str:
        # Persisting with Instagram requires a local PNG path because the upstream function
        # still uses the media upload endpoint with file path I/O.
        # TODO: remove temp-file dependency by moving upload flow to pure bytes API.
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            tmp.write(chunk_data)
            tmp.flush()
            media_id = upload.upload_image_step_1(self.auth_token, self.user_id, tmp.name)
            if not media_id:
                raise RuntimeError("failed to store chunk in Instagram backend")
            return str(media_id)
