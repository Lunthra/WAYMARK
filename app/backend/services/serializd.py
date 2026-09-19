"""WAYMARK Serializd adapter.

This module contains the Serializd-specific API details that WAYMARK Core
should not need to know about.

Serializd does not publish a public developer API. The endpoints here are
based on the authenticated web/mobile requests we verified while building
WAYMARK. They may change without notice.

No API calls are made merely by importing this module.
"""

from __future__ import annotations

import os
import time
import threading
from datetime import datetime, timezone
from typing import Any

import requests
from app.backend.core.credentials import (
    delete_service_credentials,
    get_service_credentials,
    set_credentials,
)


BASE_URL = "https://serializddesktop.onrender.com/api"
# The public Serializd API host used by current third-party clients.
# Keep BASE_URL unchanged for the already-verified Watch/History/Search paths.
RATING_BASE_URL = "https://serializd.onrender.com/api"
MOBILE_URL = "https://serializddesktop.onrender.com/mobile/page"
ORIGIN = "https://www.serializd.com"
REFERER = "https://www.serializd.com/"
REQUEST_TIMEOUT = 30
REQUEST_DELAY = 0.4
CACHE_TTL_SHOW = 300.0
CACHE_TTL_SEASON = 300.0
CACHE_TTL_WATCHED_LIBRARY = 30.0
CACHE_TTL_WATCHED_EPISODES = 20.0
CACHE_TTL_DIARY = 45.0
CACHE_TTL_SEARCH = 60.0
SERIALIZD_PERF_LOG = os.getenv("WAYMARK_SERIALIZD_PERF_LOG", "1").strip().lower() not in {"0", "false", "no", "off"}


class SerializdError(Exception):
    """Raised when a Serializd request fails."""


_session = requests.Session()
_cache_lock = threading.RLock()
_cache: dict[str, tuple[float, Any]] = {}


def _cache_get(key: str) -> Any | None:
    now = time.monotonic()
    with _cache_lock:
        item = _cache.get(key)
        if not item:
            return None
        expires, value = item
        if expires <= now:
            _cache.pop(key, None)
            return None
        return value


def _cache_set(key: str, value: Any, ttl: float) -> Any:
    with _cache_lock:
        _cache[key] = (time.monotonic() + ttl, value)
    return value


def _cache_delete_prefix(prefix: str) -> None:
    with _cache_lock:
        for key in list(_cache):
            if key.startswith(prefix):
                _cache.pop(key, None)


def _invalidate_show(show_id: int, season_id: int | None = None) -> None:
    sid = int(show_id)
    prefixes = [f"show:{sid}", f"season:{sid}:" , f"watched_episode:{sid}:"]
    for prefix in prefixes:
        _cache_delete_prefix(prefix)
    _cache_delete_prefix("watched_library:")
    _cache_delete_prefix("diary:")


# ============================================================
# CONNECTION
# ============================================================


def get_access_token() -> str:
    """Return the Serializd bearer token from the protected user store.

    SERIALIZD_TOKEN remains a development-only fallback so the existing
    development environment continues to work. Released users never need
    an .env file.
    """
    stored = get_service_credentials("serializd").get("access_token")
    if isinstance(stored, str) and stored.strip():
        return stored.strip()

    token = os.getenv("SERIALIZD_TOKEN", "").strip()
    if token:
        return token

    raise SerializdError(
        "Serializd is not connected. Connect Serializd from WAYMARK setup."
    )


def set_access_token(token: str) -> None:
    cleaned = str(token or "").strip()
    if not cleaned:
        raise ValueError("Serializd token cannot be empty.")
    set_credentials("serializd", {"access_token": cleaned})
    _cache_delete_prefix("username")


def disconnect() -> None:
    delete_service_credentials("serializd")
    _cache_delete_prefix("username")
    _cache_delete_prefix("user_information")


def get_connection_status() -> dict[str, Any]:
    token = get_service_credentials("serializd").get("access_token")
    return {
        "connected": isinstance(token, str) and bool(token.strip()),
        "username": None,
    }


def connect_with_token(token: str) -> dict[str, Any]:
    set_access_token(token)
    try:
        info = get_user_information()
    except Exception:
        disconnect()
        raise
    username = None
    if isinstance(info, dict):
        user = info.get("user") if isinstance(info.get("user"), dict) else info
        username = user.get("username") or user.get("name") or user.get("handle")
    return {
        "connected": True,
        "username": username,
        "user": info,
    }


def _headers() -> dict[str, str]:
    """Build the browser-like headers used by Serializd."""

    return {
        "Authorization": f"Bearer {get_access_token()}",
        "Accept": "application/json, text/plain, */*",
        "Origin": ORIGIN,
        "Referer": REFERER,
        "X-Requested-With": "serializd_vercel",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0"
        ),
    }


def _request(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> Any:
    """Perform an authenticated Serializd request using a pooled session."""
    started = time.monotonic()
    response = _session.request(
        method,
        url,
        headers=_headers(),
        params=params,
        json=json,
        timeout=REQUEST_TIMEOUT,
    )
    elapsed = time.monotonic() - started
    if SERIALIZD_PERF_LOG:
        print(f"[serializd] {method.upper()} {url} -> {response.status_code} in {elapsed:.2f}s", flush=True)

    if response.status_code < 200 or response.status_code >= 300:
        raise SerializdError(
            f"Serializd request failed: HTTP {response.status_code} "
            f"{response.text[:500]}"
        )

    if not response.content:
        return None

    try:
        return response.json()
    except ValueError as exc:
        raise SerializdError(
            f"Serializd returned non-JSON data: {response.text[:500]}"
        ) from exc


# ============================================================
# ACCOUNT
# ============================================================


def get_user_information() -> dict[str, Any]:
    """Return the authenticated Serializd user's account information."""

    return _request(
        "GET",
        f"{BASE_URL}/user_information",
        params={"shouldGetUserContext": "true"},
    )


def get_username() -> str:
    """Return the authenticated Serializd username."""

    cached = _cache_get("username")
    if cached:
        return str(cached)
    info = get_user_information()
    username = info.get("username")

    if not username:
        raise SerializdError("Serializd username was not returned.")

    return str(_cache_set("username", username, 600.0))


# ============================================================
# LIBRARY / HISTORY
# ============================================================


def get_watched_library() -> list[dict[str, Any]]:
    """Return all shows in the user's Serializd watched library."""

    cached = _cache_get("watched_library:all")
    if isinstance(cached, list):
        return cached

    username = get_username()
    first_page = 1
    page = first_page
    results: list[dict[str, Any]] = []

    while True:
        data = _request(
            "GET",
            f"{BASE_URL}/user/{username}/watchedpage_v2/{page}",
            params={
                "sort_by": "date_added_desc",
                "filters": "{}",
            },
        )

        results.extend(data.get("items", []))

        total_pages = int(data.get("totalPages", page))

        if page >= total_pages:
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    return _cache_set("watched_library:all", results, CACHE_TTL_WATCHED_LIBRARY)


def find_in_watched_library(query: str) -> list[dict[str, Any]]:
    """Find watched-library shows whose title contains query."""

    query = query.strip().lower()

    if not query:
        return []

    return [
        item
        for item in get_watched_library()
        if query in item.get("showName", "").lower()
    ]


def get_show_watch_state(show_id: int) -> dict[str, Any] | None:
    """Return the live watched-library record for one Serializd show.

    This is a live read from watchedpage_v2. The returned record contains the
    season IDs that Serializd associates with the user's watched library. It
    does not copy the library into local storage.
    """

    show_id = int(show_id)

    for item in get_watched_library():
        try:
            item_show_id = int(item.get("showId"))
        except (TypeError, ValueError):
            continue

        if item_show_id == show_id:
            return item

    return None


def get_diary(page: int = 1) -> dict[str, Any]:
    """Return one page of the user's Serializd diary."""
    page = max(1, int(page))
    key = f"diary:page:{page}"
    cached = _cache_get(key)
    if isinstance(cached, dict):
        return cached

    username = get_username()

    return _cache_set(key, _request(
        "GET",
        f"{BASE_URL}/user/{username}/diary",
        params={"page": page},
    ), CACHE_TTL_DIARY)


def get_full_diary() -> list[dict[str, Any]]:
    """Return all diary entries across all diary pages."""

    cached = _cache_get("diary:all")
    if isinstance(cached, list):
        return cached

    page = 1
    entries: list[dict[str, Any]] = []

    while True:
        data = get_diary(page)
        entries.extend(data.get("reviews", []))

        total_pages = int(data.get("totalPages", page))

        if page >= total_pages:
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    return _cache_set("diary:all", entries, CACHE_TTL_DIARY)


# ============================================================
# CATALOG SEARCH
# ============================================================


def search_catalog(query: str) -> list[dict[str, Any]]:
    """Search the Serializd TV catalog by title.

    This searches Serializd's catalog, not only the authenticated
    user's watched library. Results are returned as dictionaries
    containing fields such as id, name, summary, image, backdrop,
    popularity, and firstAirDate.
    """

    query = query.strip()

    if not query:
        return []

    key = f"search:{query.casefold()}"
    cached = _cache_get(key)
    if isinstance(cached, list):
        return cached

    data = _request(
        "GET",
        f"{BASE_URL}/search/shows",
        params={"search_query": query},
    )

    if not isinstance(data, dict):
        raise SerializdError(
            "Serializd catalog search returned an unexpected response."
        )

    return _cache_set(key, data.get("results", []), CACHE_TTL_SEARCH)


# ============================================================
# SHOW / SEASON / EPISODE METADATA
# ============================================================


def get_show(show_id: int) -> dict[str, Any]:
    """Return Serializd show metadata from the verified mobile detail endpoint.

    The Serializd web request that exposes the community average rating uses
    ``/mobile/page/show_v2_part_1/{show_id}?optimize=false`` rather than the
    generic ``/api/show/{show_id}`` endpoint.

    This is read-only. The response is normalized so WAYMARK callers can
    continue using ``get_show(show_id)`` without knowing the private endpoint.
    """

    show_id = int(show_id)
    cache_key = f"show:{show_id}"
    cached = _cache_get(cache_key)
    if isinstance(cached, dict):
        return cached

    data = _request(
        "GET",
        f"{MOBILE_URL}/show_v2_part_1/{show_id}",
        params={"optimize": "false"},
    )

    if not isinstance(data, dict):
        raise SerializdError(
            "Serializd mobile show detail returned an unexpected response."
        )

    show_details = data.get("showDetails")

    if isinstance(show_details, dict):
        details = dict(show_details)
    else:
        details = dict(data)

    # Preserve the verified community rating fields.
    for key in ("averageRating", "ratings"):
        if key in data:
            details[key] = data[key]

    if isinstance(show_details, dict):
        for key in ("averageRating", "ratings"):
            if key in show_details:
                details[key] = show_details[key]

    return _cache_set(cache_key, details, CACHE_TTL_SHOW)

def get_season(
    show_id: int,
    season_number: int,
) -> dict[str, Any]:
    """Return season metadata, including its episode list."""

    show_id = int(show_id)
    season_number = int(season_number)
    key = f"season:{show_id}:{season_number}"
    cached = _cache_get(key)
    if isinstance(cached, dict):
        return cached
    return _cache_set(key, _request(
        "GET",
        f"{BASE_URL}/show/{show_id}/season/{season_number}",
    ), CACHE_TTL_SEASON)


def get_episode(
    show_id: int,
    season_number: int,
    episode_number: int,
) -> dict[str, Any] | None:
    """Return one episode object from a Serializd season."""

    season = get_season(show_id, season_number)

    for episode in season.get("episodes", []):
        if int(episode.get("episodeNumber", -1)) == int(episode_number):
            return episode

    return None


def resolve_episode(
    show_id: int,
    season_number: int,
    episode_number: int,
) -> dict[str, Any]:
    """Resolve an episode or raise a clear error."""

    episode = get_episode(
        show_id,
        season_number,
        episode_number,
    )

    if episode is None:
        raise SerializdError(
            f"Episode S{int(season_number):02d}E{int(episode_number):02d} "
            f"was not found for Serializd show {int(show_id)}."
        )

    return episode


# ============================================================
# WATCH STATE
# ============================================================


def mark_episode_watched(
    show_id: int,
    season_id: int,
    episode_number: int,
) -> dict[str, Any]:
    """Mark one episode as watched on Serializd."""

    payload = {
        "episode_numbers": [int(episode_number)],
        "season_id": int(season_id),
        "show_id": int(show_id),
    }

    result = _request(
        "POST",
        f"{BASE_URL}/episode_log/add",
        json=payload,
    )

    _invalidate_show(int(show_id), int(season_id) if "season_id" in locals() and season_id is not None else None)
    time.sleep(REQUEST_DELAY)
    return result


def mark_season_watched(
    show_id: int,
    season_id: int,
) -> dict[str, Any]:
    """Mark an entire Serializd season as watched."""
    payload = {
        "season_ids": [int(season_id)],
        "show_id": int(show_id),
    }
    result = _request(
        "POST",
        f"{BASE_URL}/watched_v2",
        json=payload,
    )
    _invalidate_show(int(show_id), int(season_id) if "season_id" in locals() and season_id is not None else None)
    time.sleep(REQUEST_DELAY)
    return result


def mark_series_watched(show_id: int) -> dict[str, Any]:
    """Mark all available seasons of a Serializd series as watched."""
    show = _request(
        "GET",
        f"{BASE_URL}/show/{int(show_id)}",
    )
    seasons = show.get("seasons", []) if isinstance(show, dict) else []
    season_ids: list[int] = []
    for season in seasons:
        season_id = season.get("seasonId", season.get("id"))
        if season_id is not None:
            season_ids.append(int(season_id))

    if not season_ids:
        raise SerializdError(
            f"No season IDs were returned for Serializd show {int(show_id)}."
        )

    payload = {
        "season_ids": season_ids,
        "show_id": int(show_id),
    }
    result = _request(
        "POST",
        f"{BASE_URL}/watched_v2",
        json=payload,
    )
    _invalidate_show(int(show_id))
    time.sleep(REQUEST_DELAY)
    return result


def unmark_episode_watched(
    show_id: int,
    season_id: int,
    episode_number: int,
) -> dict[str, Any]:
    """Remove one episode's watched state on Serializd."""

    payload = {
        "episode_numbers": [int(episode_number)],
        "season_id": int(season_id),
        "show_id": int(show_id),
    }

    result = _request(
        "POST",
        f"{BASE_URL}/episode_log/remove",
        json=payload,
    )

    _invalidate_show(int(show_id), int(season_id) if "season_id" in locals() and season_id is not None else None)
    time.sleep(REQUEST_DELAY)
    return result


# ============================================================
# RATINGS / REVIEWS
# ============================================================


def _current_backdate() -> str:
    """Return the current UTC timestamp in Serializd's browser format."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def add_episode_rating(
    show_id: int,
    season_id: int,
    episode_number: int,
    rating: int,
    *,
    review_text: str = "",
    is_rewatch: bool = False,
    backdate: str | None = None,
) -> dict[str, Any]:
    """Create a Serializd episode rating/log entry."""

    rating = int(rating)

    if not 0 <= rating <= 10:
        raise ValueError("Serializd rating must be between 0 and 10.")

    payload = {
        "show_id": int(show_id),
        "season_id": int(season_id),
        "episode_number": int(episode_number),
        "review_text": review_text,
        "rating": rating,
        "contains_spoiler": False,
        "is_log": True,
        "is_rewatch": bool(is_rewatch),
        "like": False,
        "allows_comments": True,
        "tags": [],
        "backdate": backdate if backdate is not None else _current_backdate(),
    }

    result = _request(
        "POST",
        f"{BASE_URL}/show/reviews/add",
        json=payload,
    )

    time.sleep(REQUEST_DELAY)
    return result


def log_season_review(
    show_id: int,
    season_id: int,
    *,
    stars: float | None = None,
    review_text: str = "",
    is_rewatch: bool = False,
    contains_spoiler: bool = False,
    like: bool = False,
    allows_comments: bool = True,
    tags: list[Any] | None = None,
    backdate: str | None = None,
) -> dict[str, Any]:
    """Create a Serializd season review/log using the verified web payload.

    Serializd uses the same ``/show/reviews/add`` endpoint for season reviews;
    the distinguishing field is ``episode_number: null`` together with a
    concrete ``season_id``. Native 1.0-5.0 half-star ratings map to API
    integers 2-10. A missing rating is sent as 0, matching the observed UI.
    """
    if stars is not None:
        stars = float(stars)
        doubled = stars * 2
        if not 1.0 <= stars <= 5.0 or doubled != int(doubled):
            raise ValueError("Serializd stars must be between 1.0 and 5.0 in 0.5 increments.")
        rating = int(doubled)
    else:
        rating = 0

    payload: dict[str, Any] = {
        "show_id": int(show_id),
        "season_id": int(season_id),
        "review_text": review_text,
        "rating": rating,
        "contains_spoiler": bool(contains_spoiler),
        "backdate": backdate if backdate is not None else _current_backdate(),
        "is_log": True,
        "is_rewatch": bool(is_rewatch),
        "episode_number": None,
        "tags": tags if tags is not None else [],
        "allows_comments": bool(allows_comments),
        "like": bool(like),
    }

    result = _request(
        "POST",
        f"{BASE_URL}/show/reviews/add",
        json=payload,
    )
    _invalidate_show(int(show_id), int(season_id) if "season_id" in locals() and season_id is not None else None)
    time.sleep(REQUEST_DELAY)
    return result


def log_series_review(
    show_id: int,
    *,
    stars: float | None = None,
    review_text: str = "",
    is_rewatch: bool = False,
    contains_spoiler: bool = False,
    like: bool = False,
    allows_comments: bool = True,
    tags: list[Any] | None = None,
    backdate: str | None = None,
) -> dict[str, Any]:
    """Create a Serializd series-level review/log.

    Series-level reviews use the verified ``/show/reviews/add`` endpoint with
    ``season_id`` and ``episode_number`` both explicitly set to ``None``.
    This is intentionally separate from ``log_season_review`` so that a
    series identity can never reach ``int(None)`` in the season adapter.

    WAYMARK's native 0.5-5.0 half-star scale maps to Serializd API integers
    1-10. When no rating is supplied, the browser payload uses rating=0.
    """
    if stars is not None:
        stars = float(stars)
        doubled = stars * 2
        if not 0.5 <= stars <= 5.0 or doubled != int(doubled):
            raise ValueError(
                "Serializd stars must be between 0.5 and 5.0 in 0.5 increments."
            )
        rating = int(doubled)
    else:
        rating = 0

    payload: dict[str, Any] = {
        "show_id": int(show_id),
        "season_id": None,
        "review_text": review_text,
        "rating": rating,
        "contains_spoiler": bool(contains_spoiler),
        "backdate": backdate if backdate is not None else _current_backdate(),
        "is_log": True,
        "is_rewatch": bool(is_rewatch),
        "episode_number": None,
        "tags": tags if tags is not None else [],
        "allows_comments": bool(allows_comments),
        "like": bool(like),
    }

    result = _request(
        "POST",
        f"{BASE_URL}/show/reviews/add",
        json=payload,
    )
    _invalidate_show(int(show_id))
    time.sleep(REQUEST_DELAY)
    return result



def _rating_request(payload: dict[str, Any]) -> Any:
    """Write a rating through Serializd's current API host.

    Rating writes are isolated from the legacy desktop proxy used by the
    existing Watch/History/Search flows. If the current API host is
    temporarily unavailable, fall back to the legacy host rather than
    breaking an otherwise working installation.
    """
    try:
        result = _request("POST", f"{RATING_BASE_URL}/show/reviews/add", json=payload)
    except Exception as primary_exc:
        if RATING_BASE_URL == BASE_URL:
            raise
        try:
            result = _request("POST", f"{BASE_URL}/show/reviews/add", json=payload)
        except Exception as fallback_exc:
            raise SerializdError(
                f"Serializd rating write failed on both API hosts. "
                f"Current API: {primary_exc}; legacy proxy: {fallback_exc}"
            ) from fallback_exc
    _invalidate_show(int(payload.get("show_id") or 0), int(payload.get("season_id")) if payload.get("season_id") not in (None, "", 0) else None)
    time.sleep(REQUEST_DELAY)
    return result


def rate_episode(
    show_id: int,
    season_id: int,
    episode_number: int,
    stars: float,
) -> dict[str, Any]:
    """Rate one episode without requiring review text."""
    stars = float(stars)
    doubled = stars * 2
    if not 0.5 <= stars <= 5.0 or doubled != int(doubled):
        raise ValueError("Serializd stars must be between 0.5 and 5.0 in 0.5 increments.")
    payload = {
        "show_id": int(show_id),
        "season_id": int(season_id),
        "episode_number": int(episode_number),
        "review_text": "",
        "rating": int(doubled),
        "contains_spoiler": False,
        "backdate": _current_backdate(),
        "is_log": True,
        "is_rewatch": False,
        "tags": [],
        "allows_comments": True,
        "like": False,
    }
    result = _rating_request(payload)
    return result


def rate_season(show_id: int, season_id: int, stars: float) -> dict[str, Any]:
    """Rate one season without requiring review text."""
    stars = float(stars)
    doubled = stars * 2
    if not 0.5 <= stars <= 5.0 or doubled != int(doubled):
        raise ValueError("Serializd stars must be between 0.5 and 5.0 in 0.5 increments.")
    payload = {
        "show_id": int(show_id),
        "season_id": int(season_id),
        "review_text": "",
        "rating": int(doubled),
        "contains_spoiler": False,
        "backdate": _current_backdate(),
        "is_log": True,
        "is_rewatch": False,
        "episode_number": None,
        "tags": [],
        "allows_comments": True,
        "like": False,
    }
    result = _rating_request(payload)
    return result


def rate_series(show_id: int, stars: float) -> dict[str, Any]:
    """Rate one series without requiring review text."""
    stars = float(stars)
    doubled = stars * 2
    if not 0.5 <= stars <= 5.0 or doubled != int(doubled):
        raise ValueError("Serializd stars must be between 0.5 and 5.0 in 0.5 increments.")
    payload = {
        "show_id": int(show_id),
        "season_id": None,
        "review_text": "",
        "rating": int(doubled),
        "contains_spoiler": False,
        "backdate": _current_backdate(),
        "is_log": True,
        "is_rewatch": False,
        "episode_number": None,
        "tags": [],
        "allows_comments": True,
        "like": False,
    }
    result = _rating_request(payload)
    return result


def get_watched_episode_logs(show_id: int, season_id: int) -> list[dict[str, Any]]:
    """Return live Serializd watched episode-log records for one season.

    This uses Serializd's observed season_v2_part_3 endpoint. It is a
    read-only endpoint and returns the episodeLogs associated with the
    authenticated user for the requested show/season.
    """
    # Verified from the Serializd web app Network request:
    # https://serializddesktop.onrender.com/mobile/page/show/{show_id}/season_v2_part_3/1?season_id={season_id}
    #
    # This endpoint is on the service root, NOT under /api. MOBILE_URL is
    # already the correct root for this request family.
    show_id = int(show_id)
    season_id = int(season_id)
    key = f"watched_episode:{show_id}:{season_id}"
    cached = _cache_get(key)
    if isinstance(cached, list):
        return cached

    data = _request(
        "GET",
        f"{MOBILE_URL}/show/{show_id}/season_v2_part_3/1",
        params={"season_id": int(season_id)},
    )
    if not isinstance(data, dict):
        return []
    logs = data.get("episodeLogs")
    if logs is None:
        logs = data.get("episode_logs")
    if logs is None:
        nested = data.get("data")
        if isinstance(nested, dict):
            logs = nested.get("episodeLogs", nested.get("episode_logs", []))
    return _cache_set(key, logs if isinstance(logs, list) else [], CACHE_TTL_WATCHED_EPISODES)


def get_episode_diary_entries(
    show_id: int,
    season_id: int,
    episode_number: int,
) -> list[dict[str, Any]]:
    """Return diary entries matching a specific episode."""

    matches: list[dict[str, Any]] = []

    for entry in get_full_diary():
        if int(entry.get("showId", -1)) != int(show_id):
            continue

        if int(entry.get("seasonId", -1)) != int(season_id):
            continue

        if int(entry.get("episodeNumber", -1)) != int(episode_number):
            continue

        matches.append(entry)

    return matches


def log_episode(
    show_id: int,
    season_id: int,
    episode_number: int,
    *,
    stars: float | None = None,
    review_text: str = "",
    is_rewatch: bool = False,
    contains_spoiler: bool = False,
    like: bool = False,
    allows_comments: bool = True,
    tags: list[Any] | None = None,
    backdate: str | None = None,
) -> dict[str, Any]:
    """Log a Serializd episode, optionally with a 1-5 star rating.

    WAYMARK uses Serializd's native half-star scale. The API represents
    1.0-5.0 stars as integer ratings 2-10.
    """
    if stars is not None:
        stars = float(stars)
        doubled = stars * 2
        if not 1.0 <= stars <= 5.0 or doubled != int(doubled):
            raise ValueError("Serializd stars must be between 1.0 and 5.0 in 0.5 increments.")
        rating = int(doubled)
    else:
        # The browser sends rating=0 when an episode is logged without a star rating.
        rating = 0

    payload: dict[str, Any] = {
        "show_id": int(show_id),
        "season_id": int(season_id),
        "episode_number": int(episode_number),
        "review_text": review_text,
        "rating": rating,
        "is_log": True,
        "is_rewatch": bool(is_rewatch),
        "contains_spoiler": bool(contains_spoiler),
        "like": bool(like),
        "allows_comments": bool(allows_comments),
        "tags": tags if tags is not None else [],
        "backdate": backdate if backdate is not None else _current_backdate(),
    }

    result = _request(
        "POST",
        f"{BASE_URL}/show/reviews/add",
        json=payload,
    )
    _invalidate_show(int(show_id), int(season_id) if "season_id" in locals() and season_id is not None else None)
    time.sleep(REQUEST_DELAY)
    return result



def update_review_log(
    review_id: int,
    *,
    show_id: int | None = None,
    season_id: int | None = None,
    review_text: str = "",
    stars: float | None = None,
    contains_spoiler: bool = False,
    allows_comments: bool = True,
    backdate: str | None = None,
    episode_number: int | None = None,
    is_log: bool = True,
    is_rewatch: bool = False,
    like: bool = False,
    tags: list[Any] | None = None,
    rating: int | None = None,
) -> dict[str, Any]:
    """Update an existing Serializd review/log entry.

    Serializd's observed update endpoint accepts the review_id plus the
    editable log fields. WAYMARK exposes the native 1-5 half-star scale via
    ``stars``; the underlying API uses integer ratings 2-10.

    ``rating`` is retained as an optional low-level escape hatch for existing
    code that already works with Serializd's 0-10 API scale. Do not pass both
    ``stars`` and ``rating``.
    """
    if stars is not None and rating is not None:
        raise ValueError("Pass either stars or rating, not both.")

    if stars is not None:
        stars = float(stars)
        doubled = stars * 2
        if not 1.0 <= stars <= 5.0 or doubled != int(doubled):
            raise ValueError(
                "Serializd stars must be between 1.0 and 5.0 in 0.5 increments."
            )
        rating = int(doubled)

    if rating is not None:
        rating = int(rating)
        if not 0 <= rating <= 10:
            raise ValueError("Serializd API rating must be between 0 and 10.")

    payload: dict[str, Any] = {
        "review_id": int(review_id),
        "show_id": int(show_id) if show_id is not None else None,
        "season_id": int(season_id) if season_id is not None else None,
        "review_text": review_text,
        "contains_spoiler": bool(contains_spoiler),
        "allows_comments": bool(allows_comments),
        "is_log": bool(is_log),
        "is_rewatch": bool(is_rewatch),
        "like": bool(like),
        "tags": tags if tags is not None else [],
    }

    if rating is not None:
        payload["rating"] = rating
    if backdate is not None:
        payload["backdate"] = backdate
    if episode_number is not None:
        payload["episode_number"] = int(episode_number)

    result = _request(
        "POST",
        f"{BASE_URL}/show/reviews/update",
        json=payload,
    )
    _invalidate_show(int(show_id), int(season_id) if "season_id" in locals() and season_id is not None else None)
    time.sleep(REQUEST_DELAY)
    return result


def update_rating_log(
    review_id: int,
    *,
    show_id: int,
    season_id: int | None = None,
    episode_number: int | None = None,
    rating: int,
    review_text: str = "",
    backdate: str | None = None,
) -> dict[str, Any]:
    """Update a rating through the current Serializd rating API host.

    This is deliberately separate from the Review editor's update path so
    existing Review/Watch behavior is not coupled to the Rating workflow.
    """
    rating = int(rating)
    if not 0 <= rating <= 10:
        raise ValueError("Serializd API rating must be between 0 and 10.")
    payload: dict[str, Any] = {
        "review_id": int(review_id),
        "show_id": int(show_id),
        "season_id": int(season_id) if season_id is not None else None,
        "review_text": review_text,
        "rating": rating,
        "contains_spoiler": False,
        "allows_comments": True,
        "is_log": True,
        "is_rewatch": False,
        "like": False,
        "tags": [],
    }
    if episode_number is not None:
        payload["episode_number"] = int(episode_number)
    if backdate is not None:
        payload["backdate"] = backdate
    try:
        result = _request("POST", f"{RATING_BASE_URL}/show/reviews/update", json=payload)
    except Exception as primary_exc:
        try:
            result = _request("POST", f"{BASE_URL}/show/reviews/update", json=payload)
        except Exception as fallback_exc:
            raise SerializdError(
                f"Serializd rating update failed on both API hosts. "
                f"Current API: {primary_exc}; legacy proxy: {fallback_exc}"
            ) from fallback_exc
    _invalidate_show(int(show_id), int(season_id) if "season_id" in locals() and season_id is not None else None)
    time.sleep(REQUEST_DELAY)
    return result


def delete_review_log(review_id: int) -> dict[str, Any] | None:
    """Delete an existing Serializd review/log entry."""
    result = _request(
        "POST",
        f"{BASE_URL}/show/reviews/delete",
        json={"review_id": int(review_id)},
    )
    _cache_delete_prefix("diary:")
    time.sleep(REQUEST_DELAY)
    return result


# ============================================================
# SAFE CONNECTION TEST
# ============================================================


def test_connection() -> dict[str, Any]:
    """Verify authentication without changing any account data."""

    return get_user_information()


if __name__ == "__main__":
    print("WAYMARK Serializd adapter")
    print("No write operation will be performed.")

    info = test_connection()
    print(f"Username: {info.get('username', 'Unknown')}")

    library = get_watched_library()
    print(f"Watched shows: {len(library)}")

    print("Serializd adapter connection test complete. ✅")
