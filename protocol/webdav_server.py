from __future__ import annotations

import datetime as dt
import logging
import os
import tempfile
from email.utils import formatdate
from xml.etree import ElementTree as ET

from flask import Flask, Response, abort, request

import auth
from config_loader import CONF
from storage_core.cachefs import DirectoryEntry
from storage_core.service import build_services, configure_logging

logger = logging.getLogger(__name__)
app = Flask(__name__)

USERNAME = CONF.get("INSTA_USER")
PASSWORD = CONF.get("INSTA_PASS")


def _iso(epoch: int) -> str:
    return dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_path(raw_path: str) -> str:
    cleaned = raw_path.strip()
    if not cleaned:
        return "/"
    return "/" + cleaned.strip("/")


def _add_response(multistatus: ET.Element, href: str, is_collection: bool, size: int = 0, mtime: int | None = None) -> None:
    ns = "DAV:"
    response = ET.SubElement(multistatus, f"{{{ns}}}response")
    ET.SubElement(response, f"{{{ns}}}href").text = href
    propstat = ET.SubElement(response, f"{{{ns}}}propstat")
    prop = ET.SubElement(propstat, f"{{{ns}}}prop")
    resourcetype = ET.SubElement(prop, f"{{{ns}}}resourcetype")
    if is_collection:
        ET.SubElement(resourcetype, f"{{{ns}}}collection")
    ET.SubElement(prop, f"{{{ns}}}getcontentlength").text = str(size)
    if mtime is not None:
        ET.SubElement(prop, f"{{{ns}}}getlastmodified").text = formatdate(mtime, usegmt=True)
    ET.SubElement(prop, f"{{{ns}}}creationdate").text = _iso(mtime or int(dt.datetime.now(tz=dt.timezone.utc).timestamp()))
    ET.SubElement(propstat, f"{{{ns}}}status").text = "HTTP/1.1 200 OK"


def _build_propfind_xml(base_path: str, target_file, entries: list[DirectoryEntry], depth: str) -> bytes:
    ns = "DAV:"
    ET.register_namespace("d", ns)
    multistatus = ET.Element(f"{{{ns}}}multistatus")

    if base_path == "/":
        _add_response(multistatus, "/dav/", True)
    elif target_file:
        _add_response(multistatus, f"/dav{target_file.path}", False, target_file.size, target_file.mtime)

    if depth == "1":
        for entry in entries:
            href = f"/dav{entry.path}" + ("/" if entry.is_dir else "")
            _add_response(multistatus, href, entry.is_dir, entry.size, entry.mtime)

    return ET.tostring(multistatus, encoding="utf-8", xml_declaration=True)


def initialize_if_needed():
    if app.config.get("services") is not None:
        return
    configure_logging()
    token, uid, client = auth.login_smart(USERNAME, PASSWORD)
    if not token:
        raise RuntimeError("could not authenticate for WebDAV service")
    thread_id = auth.get_cached_thread(USERNAME)
    services = build_services(token, uid, thread_id, client)
    app.config["services"] = services


@app.route("/healthz")
def healthz():
    return {"ok": True}


@app.route("/dav", defaults={"subpath": ""}, methods=["OPTIONS", "PROPFIND"])
@app.route("/dav/<path:subpath>", methods=["OPTIONS", "PROPFIND", "GET", "HEAD", "PUT", "DELETE"])
def dav(subpath: str):
    initialize_if_needed()
    services = app.config.get("services")
    if services is None:
        abort(500)

    metadata_store = services["metadata_store"]
    reader = services["reader"]
    ingest = services.get("ingest")

    logical_path = _resolve_path(subpath)

    if request.method == "OPTIONS":
        resp = Response(status=204)
        resp.headers["Allow"] = "OPTIONS, PROPFIND, GET, HEAD, PUT, DELETE"
        resp.headers["DAV"] = "1"
        return resp

    if request.method == "PROPFIND":
        depth = request.headers.get("Depth", "0")

        if logical_path == "/":
            entries = metadata_store.list_directory_entries("/")
            body = _build_propfind_xml("/", None, entries, depth)
            return Response(body, status=207, mimetype="application/xml")

        meta = metadata_store.get_file_by_path(logical_path)
        if meta:
            body = _build_propfind_xml(logical_path, meta, [], depth)
            return Response(body, status=207, mimetype="application/xml")

        entries = metadata_store.list_directory_entries(logical_path)
        if not entries:
            return Response(status=404)

        body = _build_propfind_xml(logical_path, None, entries, depth)
        return Response(body, status=207, mimetype="application/xml")

    if request.method in {"GET", "HEAD"}:
        meta = metadata_store.get_file_by_path(logical_path)
        if meta is None:
            return Response(status=404)

        start = 0
        end = meta.size - 1
        range_header = request.headers.get("Range")
        status = 200
        if range_header and range_header.startswith("bytes="):
            try:
                raw = range_header.split("=", 1)[1]
                start_str, end_str = raw.split("-", 1)
                start = int(start_str) if start_str else 0
                end = int(end_str) if end_str else end
                end = min(end, meta.size - 1)
                status = 206
            except ValueError:
                return Response(status=416)

        length = max(0, end - start + 1)
        data = b"" if request.method == "HEAD" else reader.read_range(logical_path, start, length)
        response = Response(data, status=status, mimetype=meta.content_type or "application/octet-stream")
        response.headers["Accept-Ranges"] = "bytes"
        response.headers["Content-Length"] = str(length)
        if status == 206:
            response.headers["Content-Range"] = f"bytes {start}-{start + len(data) - 1}/{meta.size}"
        return response

    if request.method == "PUT":
        if ingest is None:
            return Response("PUT unavailable: missing thread binding", status=503)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".upload") as tmp:
            tmp.write(request.get_data())
            tmp_path = tmp.name

        try:
            old = metadata_store.get_file_by_path(logical_path)
            meta = ingest.ingest_file(tmp_path, logical_path)
            if old:
                metadata_store.delete_file_by_path(old.path)
            return Response(status=201, headers={"ETag": meta.checksum or ""})
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    if request.method == "DELETE":
        deleted = metadata_store.delete_file_by_path(logical_path)
        if not deleted:
            return Response(status=404)
        # Remote media delete is currently unsupported by upstream IG APIs used here.
        return Response(status=204)

    return Response(status=405)


if __name__ == "__main__":
    host = os.environ.get("DOODLE_DAV_HOST", "0.0.0.0")
    port = int(os.environ.get("DOODLE_DAV_PORT", "8080"))
    app.run(host=host, port=port, debug=False)
