"""WAYMARK desktop authentication helpers.

MAL uses OAuth2 + PKCE. The desktop flow is non-interactive from Python:
WAYMARK starts a temporary localhost callback listener, opens the user's
default browser, and stores the resulting tokens in the protected
per-user credential store.

The MAL client ID is an application identifier, not an account credential.
It can be supplied by the packaged app or through MAL_CLIENT_ID during
development.
"""
from __future__ import annotations

import os
import secrets
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import requests

from app.backend.core.credentials import (
    delete_service_credentials,
    get_service_credentials,
    set_credentials,
)
from app.backend.core.runtime_paths import get_data_file

AUTH_URL = "https://myanimelist.net/v1/oauth2/authorize"
TOKEN_URL = "https://myanimelist.net/v1/oauth2/token"
REDIRECT_URI = "http://localhost"

_lock = threading.RLock()
_state: dict[str, Any] = {
    "status": "idle",
    "error": None,
    "message": None,
    "username": None,
    "client_id": None,
}


def build_authorization_url(client_id: str, code_challenge: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "code_challenge": code_challenge,
        "code_challenge_method": "plain",
        "redirect_uri": REDIRECT_URI,
    }
    return AUTH_URL + "?" + urllib.parse.urlencode(params)


def _get_client_id(explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    stored = get_service_credentials("app").get("mal_client_id")
    if isinstance(stored, str) and stored.strip():
        return stored.strip()
    return os.getenv("MAL_CLIENT_ID", "").strip()


def set_mal_client_id(client_id: str) -> str:
    cleaned = str(client_id or "").strip()
    if not cleaned:
        raise ValueError("MAL client ID cannot be empty.")
    set_credentials("app", {"mal_client_id": cleaned})
    return cleaned


def mal_client_id_configured() -> bool:
    return bool(_get_client_id())


def get_mal_auth_status() -> dict[str, Any]:
    with _lock:
        result = dict(_state)
    result["connected"] = bool(get_service_credentials("mal").get("access_token"))
    result["client_id_configured"] = bool(result.get("client_id")) or mal_client_id_configured()
    return result


def _finish_status(status: str, *, error: str | None = None, message: str | None = None) -> None:
    with _lock:
        _state["status"] = status
        _state["error"] = error
        _state["message"] = message


def start_mal_auth(client_id: str | None = None) -> dict[str, Any]:
    client_id = _get_client_id(client_id)
    if not client_id:
        raise RuntimeError(
            "MAL client ID is required. Enter the client ID from the MAL developer application."
        )

    with _lock:
        if _state["status"] == "waiting":
            return get_mal_auth_status()

    verifier = secrets.token_urlsafe(32)
    verifier_path = get_data_file("pkce_verifier.txt", migrate=False)
    verifier_path_obj = os.path.abspath(verifier_path)

    with open(verifier_path_obj, "w", encoding="utf-8") as handle:
        handle.write(verifier)

    url = build_authorization_url(client_id, verifier)

    class CallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            code = query.get("code", [None])[0]
            error = query.get("error", [None])[0]
            description = query.get("error_description", [None])[0]

            if error:
                _finish_status(
                    "error",
                    error=f"MAL authorization failed: {error}{': ' + description if description else ''}",
                )
                body = "<html><body><h2>WAYMARK</h2><p>Authorization was not completed. You can close this window.</p></body></html>"
                status_code = 400
            elif not code:
                _finish_status("error", error="MAL callback did not contain an authorization code.")
                body = "<html><body><h2>WAYMARK</h2><p>No authorization code was received.</p></body></html>"
                status_code = 400
            else:
                try:
                    response = requests.post(
                        TOKEN_URL,
                        data={
                            "client_id": client_id,
                            "code": code,
                            "code_verifier": verifier,
                            "grant_type": "authorization_code",
                            "redirect_uri": REDIRECT_URI,
                        },
                        timeout=20,
                    )
                    if not response.ok:
                        raise RuntimeError(
                            f"MAL token exchange failed: HTTP {response.status_code}"
                        )
                    tokens = response.json()
                    if not isinstance(tokens, dict) or not tokens.get("access_token"):
                        raise RuntimeError("MAL token response did not contain an access token.")

                    set_credentials(
                        "mal",
                        {
                            str(k): str(v)
                            for k, v in tokens.items()
                            if isinstance(v, (str, int, float, bool))
                        },
                    )

                    _finish_status("connected", message="MyAnimeList connected successfully.")
                    body = "<html><body><h2>WAYMARK</h2><p>MyAnimeList connected successfully. You can close this window and return to WAYMARK.</p></body></html>"
                    status_code = 200
                except Exception as exc:
                    _finish_status("error", error=str(exc))
                    body = f"<html><body><h2>WAYMARK</h2><p>WAYMARK could not finish the connection: {str(exc)}</p></body></html>"
                    status_code = 500
                finally:
                    try:
                        os.remove(verifier_path_obj)
                    except FileNotFoundError:
                        pass

            encoded = body.encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    # WAYMARK's MAL application uses the standard registered localhost
    # callback. Port 80 is the implicit port for http://localhost.
    redirect_uri = REDIRECT_URI
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 80), CallbackHandler)
    except OSError as exc:
        try:
            os.remove(verifier_path_obj)
        except FileNotFoundError:
            pass
        raise RuntimeError(
            "WAYMARK could not open its MAL callback listener on localhost:80. "
            "Close another program using port 80 and try again."
        ) from exc

    params = {
        "response_type": "code",
        "client_id": client_id,
        "code_challenge": verifier,
        "code_challenge_method": "plain",
        "redirect_uri": redirect_uri,
    }
    auth_url = AUTH_URL + "?" + urllib.parse.urlencode(params)

    with _lock:
        _state.update({
            "status": "waiting",
            "error": None,
            "message": "Complete MyAnimeList authorization in your browser.",
            "client_id": client_id,
        })

    def worker():
        try:
            webbrowser.open(auth_url)
            server.handle_request()
        except Exception as exc:
            _finish_status("error", error=str(exc))
        finally:
            try:
                server.server_close()
            except Exception:
                pass
            try:
                os.remove(verifier_path_obj)
            except FileNotFoundError:
                pass

    threading.Thread(target=worker, name="WAYMARK-MAL-OAuth", daemon=True).start()

    return {
        **get_mal_auth_status(),
        "authorization_url": auth_url,
        "redirect_uri": redirect_uri,
    }


def disconnect_mal() -> dict[str, Any]:
    delete_service_credentials("mal")
    _finish_status("idle", message="MyAnimeList disconnected.")
    return get_mal_auth_status()


def get_mal_credentials() -> dict[str, Any]:
    return get_service_credentials("mal")


# Backward-compatible helper for the old development entry point.
def authenticate_mal(client_id: str | None = None) -> dict:
    result = start_mal_auth(client_id)
    if result.get("status") == "waiting":
        return result
    return result


if __name__ == "__main__":
    result = start_mal_auth()
    print(result)
