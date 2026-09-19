from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

PROJECT_ROOT = os.getenv(
    "WAYMARK_PROJECT_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")),
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.backend.core import desktop_api
from app.backend.core.runtime_paths import get_data_file

HOST = "127.0.0.1"
PORT = int(os.getenv("WAYMARK_BRIDGE_PORT", "8765"))
BRIDGE_TOKEN = os.getenv("WAYMARK_BRIDGE_TOKEN", "").strip()


def send(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _authorized(handler) -> bool:
    return bool(BRIDGE_TOKEN) and handler.headers.get("X-WAYMARK-Bridge-Token", "") == BRIDGE_TOKEN



PROFILE_FILE = get_data_file("profile.json")


def _read_profile():
    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _write_profile(data):
    path = Path(PROFILE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temp, path)


def profile_get():
    data = _read_profile()
    name = str(data.get("display_name") or "").strip()
    return {"display_name": name}


def profile_set(display_name):
    name = str(display_name or "").strip()
    if not name:
        raise ValueError("A display name is required.")
    if len(name) > 40:
        raise ValueError("Display name must be 40 characters or fewer.")
    data = {"display_name": name}
    _write_profile(data)
    return {"display_name": name}


def dispatch(action, payload):
    if action in ("health", "status"):
        return desktop_api.status()
    if action == "setup_status":
        return desktop_api.setup_status()
    if action == "setup_complete":
        return desktop_api.setup_complete()
    if action == "mal_auth_start":
        return desktop_api.mal_auth_start(payload.get("client_id"))
    if action == "mal_auth_status":
        return desktop_api.mal_auth_status()
    if action == "mal_disconnect":
        return desktop_api.mal_disconnect()
    if action == "serializd_connect":
        return desktop_api.serializd_connect(payload.get("token", ""))
    if action == "serializd_disconnect":
        return desktop_api.serializd_disconnect()
    if action == "profile_get":
        return profile_get()
    if action == "profile_set":
        return profile_set(payload.get("display_name", ""))

    if action == "search_catalogs":
        return desktop_api.search_catalogs(payload.get("query", ""), bool(payload.get("is_anime", False)), payload.get("media_type", "tv"))
    if action == "select_search_result":
        return desktop_api.select_result(payload.get("service", ""), payload.get("results", []), payload.get("index", 0))
    if action == "library":
        return desktop_api.library()
    if action == "history":
        return desktop_api.history(payload.get("limit", 20))
    if action == "watch_seasons":
        return desktop_api.watch_seasons(payload.get("show_id"))
    if action == "serializd_seasons":
        return desktop_api.serializd_seasons(payload.get("show_id"))
    if action == "watch_episodes":
        return desktop_api.watch_episodes(payload.get("show_id"), payload.get("season_number"))
    if action == "watch_execute":
        return desktop_api.watch_execute(payload)
    if action == "watch_execute_batch":
        return desktop_api.watch_execute_batch(payload)
    if action == "review_seasons":
        return desktop_api.review_seasons(payload.get("show_id"))
    if action == "review_episodes":
        return desktop_api.review_episodes(payload.get("show_id"), payload.get("season_number"))
    if action == "review_existing":
        return desktop_api.review_existing(payload)
    if action == "review_execute":
        return desktop_api.review_execute(payload)
    if action == "review_update":
        return desktop_api.review_update(payload)
    if action == "review_delete":
        return desktop_api.review_delete(payload)
    if action == "mal_status":
        return desktop_api.mal_status(payload.get("mal_id"))
    if action == "mal_update":
        return desktop_api.mal_update(payload)
    if action == "serializd_rate":
        return desktop_api.serializd_rate(payload)
    if action == "serializd_progress":
        return desktop_api.serializd_progress(payload)
    raise ValueError(f"Unknown bridge action: {action}")


class Handler(BaseHTTPRequestHandler):
    server_version = "WAYMARKBridge/M23"

    def log_message(self, fmt, *args):
        print(f"[bridge] {fmt % args}", flush=True)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            if BRIDGE_TOKEN and not _authorized(self):
                return send(self, 401, {"ok": False, "error": "Unauthorized."})
            return send(self, 200, {"ok": True, "service": "waymark-bridge", "version": "M23", "core_loaded": True})
        if path == "/api/status":
            if not _authorized(self):
                return send(self, 401, {"ok": False, "error": "Unauthorized."})
            return send(self, 200, {"ok": True, "result": desktop_api.status()})
        return send(self, 404, {"ok": False, "error": "Not found."})

    def do_POST(self):
        if urlparse(self.path).path != "/api/invoke":
            return send(self, 404, {"ok": False, "error": "Not found."})
        if not _authorized(self):
            return send(self, 401, {"ok": False, "error": "Unauthorized."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length).decode("utf-8") if length else "{}")
            payload = request.get("payload") or {}
            action = request.get("action")
            if not isinstance(action, str) or not action.strip():
                raise ValueError("WAYMARK action is required.")
            if not isinstance(payload, dict):
                raise ValueError("WAYMARK payload must be an object.")
            result = dispatch(action, payload)
            send(self, 200, {"ok": True, "phase": "M23", "action": action, "result": result})
        except ValueError as exc:
            send(self, 400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            print(f"[bridge] {type(exc).__name__}: {exc}", flush=True)
            send(self, 500, {"ok": False, "error": str(exc), "error_type": type(exc).__name__})


def main():
    if not BRIDGE_TOKEN:
        raise RuntimeError("WAYMARK_BRIDGE_TOKEN is required when starting the desktop bridge.")
    print("WAYMARK production-hardened backend bridge starting...", flush=True)
    print(f"Project root: {PROJECT_ROOT}", flush=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"WAYMARK bridge listening on http://{HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
