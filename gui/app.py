import logging
import os
import sys
import tempfile

from flask import Flask, jsonify, render_template, request

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

import auth
import database
from config_loader import CONF
from storage_core.service import build_services, configure_logging

app = Flask(__name__)
logger = logging.getLogger(__name__)

UPLOAD_FOLDER = os.path.join(parent_dir, 'upload')
DOWNLOAD_FOLDER = os.path.join(parent_dir, 'download')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

USERNAME = CONF.get("INSTA_USER")
PASSWORD = CONF.get("INSTA_PASS")
client = None
auth_token = None
user_id = None
services = None


def ensure_session():
    global client, auth_token, user_id, services

    if auth_token and services:
        return True

    token, uid, cl = auth.login_smart(USERNAME, PASSWORD)
    if not token:
        return False

    auth_token = token
    user_id = uid
    client = cl

    thread_id = auth.get_cached_thread(USERNAME)
    services = build_services(auth_token, user_id, thread_id, client)
    return True


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/status', methods=['GET'])
def status():
    ok = ensure_session()
    if not ok:
        return jsonify({"status": "disconnected"})

    thread_id = auth.get_cached_thread(USERNAME)
    return jsonify({"status": "connected", "username": USERNAME, "thread_selected": bool(thread_id)})


@app.route('/api/threads', methods=['GET'])
def get_threads():
    if not ensure_session():
        return jsonify({"error": "Not logged in"}), 401

    try:
        resp = client.private_request("direct_v2/inbox/", params={"limit": "20"})
        threads_raw = resp.get('inbox', {}).get('threads', [])

        threads = []
        for t in threads_raw:
            title = t.get('thread_title')
            if not title:
                users = t.get('users', [])
                title = ", ".join([u['username'] for u in users]) or "Unknown Chat"

            threads.append({"id": t.get('thread_id'), "title": title})

        return jsonify(threads)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/threads', methods=['POST'])
def select_thread():
    data = request.json
    thread_id = data.get('thread_id')

    if not thread_id:
        return jsonify({"error": "No ID"}), 400

    auth.update_cache(USERNAME, thread_id=thread_id)
    if ensure_session():
        global services
        services = build_services(auth_token, user_id, thread_id, client)
    return jsonify({"status": "success"})


@app.route('/api/files', methods=['GET'])
def list_files():
    files = database.list_files()
    for f in files:
        f['parts'] = f.get('chunk_count', 1)
    return jsonify(files)


@app.route('/api/upload', methods=['POST'])
def upload_file():
    if not ensure_session():
        return jsonify({"error": "Not logged in"}), 401
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    thread_id = auth.get_cached_thread(USERNAME)
    if not thread_id:
        return jsonify({"error": "NO_THREAD_SELECTED"}), 400

    ingest = services.get("ingest") if services else None
    if ingest is None:
        return jsonify({"error": "Ingest service unavailable"}), 500

    with tempfile.NamedTemporaryFile(delete=False, dir=UPLOAD_FOLDER) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    target_path = f"/{file.filename}"
    try:
        meta = ingest.ingest_file(tmp_path, target_path)
        logger.info("upload complete path=%s file_id=%s", meta.path, meta.file_id)
        return jsonify({"status": "success", "filename": meta.filename, "path": meta.path, "size": meta.size})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.route('/api/download', methods=['POST'])
def download_route():
    if not ensure_session():
        return jsonify({"error": "Not logged in"}), 401

    data = request.json
    path = data.get('path') or f"/{data.get('filename', '').strip('/')}"
    filename = os.path.basename(path)
    save_path = os.path.join(DOWNLOAD_FOLDER, filename)

    reader = services.get("reader") if services else None
    meta_store = services.get("metadata_store") if services else None
    if not reader or not meta_store:
        return jsonify({"error": "Reader service unavailable"}), 500

    try:
        meta = meta_store.get_file_by_path(path)
        if not meta:
            return jsonify({"error": "Not found"}), 404
        data_bytes = reader.read_range(path, 0, meta.size)
        with open(save_path, 'wb') as f_out:
            f_out.write(data_bytes)
        return jsonify({"status": "success", "saved_to": save_path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/delete', methods=['POST'])
def delete_route():
    data = request.json
    if database.delete_file_record(data.get('id')):
        return jsonify({"status": "success"})
    return jsonify({"error": "Database error"}), 500


if __name__ == '__main__':
    configure_logging()
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', '5000'))
    print(f"[*] Starting Web Interface on http://{host}:{port}")
    app.run(host=host, debug=True, use_reloader=False, port=port)
