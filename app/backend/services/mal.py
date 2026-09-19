"""MyAnimeList API adapter used by WAYMARK."""
from __future__ import annotations

import requests

from app.backend.core.credentials import get_credential, migrate_legacy_mal_token

BASE_URL = "https://api.myanimelist.net/v2"
REQUEST_TIMEOUT = 20


def get_access_token() -> str:
    """Return the current-user MAL access token from the protected store."""
    token = get_credential("mal", "access_token", env_names=("MAL_ACCESS_TOKEN",))
    if token:
        return token
    if migrate_legacy_mal_token():
        token = get_credential("mal", "access_token", env_names=("MAL_ACCESS_TOKEN",))
    if not token:
        raise RuntimeError("MAL is not connected. Complete MAL authentication before using MAL features.")
    return token


def _request(method: str, path: str, **kwargs):
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    headers = dict(kwargs.pop("headers", {}) or {})
    headers["Authorization"] = f"Bearer {get_access_token()}"
    response = requests.request(method, f"{BASE_URL}{path}", headers=headers, **kwargs)
    if not response.ok:
        raise RuntimeError(f"MAL request failed: HTTP {response.status_code}")
    return response


def search_anime(query):
    return _request("GET", "/anime", params={"q": query, "limit": 5, "fields": "id,title"}).json()["data"]


def get_my_status(anime_id):
    return _request("GET", f"/anime/{anime_id}", params={"fields": "my_list_status"}).json()


def update_progress(anime_id, episodes_watched, is_rewatching=None):
    data = {"num_watched_episodes": episodes_watched}
    if is_rewatching is not None:
        data["is_rewatching"] = str(is_rewatching).lower()
    return _request("PATCH", f"/anime/{anime_id}/my_list_status", data=data).json()


def update_status(anime_id, status):
    return _request("PATCH", f"/anime/{anime_id}/my_list_status", data={"status": status}).json()


def update_score(anime_id, score):
    return _request("PATCH", f"/anime/{anime_id}/my_list_status", data={"score": score}).json()


def get_my_anime_list():
    return _request("GET", "/users/@me/animelist", params={"limit": 1000, "fields": "list_status"}).json()["data"]


if __name__ == "__main__":
    anime_list = get_my_anime_list()
    print(f"Your MAL list contains {len(anime_list)} anime.\n")
    for item in anime_list[:10]:
        anime = item["node"]
        status = item["list_status"]
        print(f'{anime["id"]}: {anime["title"]} | {status["status"]} | Episodes: {status["num_episodes_watched"]}')
