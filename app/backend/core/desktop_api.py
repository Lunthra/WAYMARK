from __future__ import annotations
from typing import Any
import os
import requests

from app.backend.core.credentials import get_service_credentials, set_credentials, delete_service_credentials
from app.backend.services.auth import get_mal_auth_status, start_mal_auth, disconnect_mal, set_mal_client_id, mal_client_id_configured
from app.backend.core import waymark_core as core
from app.backend.services.serializd import get_access_token as serializd_get_access_token, connect_with_token as serializd_connect_with_token, disconnect as serializd_disconnect, get_connection_status as serializd_connection_status
from app.backend.services.serializd import (
    search_catalog,
    get_show,
    get_season,
    get_show_watch_state,
    get_watched_episode_logs,
    log_episode,
    add_episode_rating,
    log_season_review,
    log_series_review,
    update_review_log,
    delete_review_log,
    get_full_diary,
    rate_episode,
    rate_season,
    rate_series,
)

SERIALIZD_API = "https://serializddesktop.onrender.com/api"
SERIALIZD_MOBILE = "https://serializddesktop.onrender.com/mobile/page"

SZ_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.serializd.com",
    "Referer": "https://www.serializd.com/",
    "X-Requested-With": "serializd_vercel",
}

def _sz_headers() -> dict[str, str]:
    h = dict(SZ_HEADERS)
    h["Authorization"] = f"Bearer {serializd_get_access_token()}"
    return h

def _first(d: dict[str, Any], *keys: str):
    for key in keys:
        value = d.get(key)
        if value not in (None, "", []):
            return value
    return None


def _normalize_serializd_image(value: Any) -> str | None:
    """Normalize Serializd/TMDB artwork references into browser-loadable URLs."""
    if isinstance(value, dict):
        for key in ("large", "medium", "original", "url", "src", "imageUrl", "image_url", "path", "file_path"):
            candidate = value.get(key)
            normalized = _normalize_serializd_image(candidate)
            if normalized:
                return normalized
        return None

    if not isinstance(value, str):
        return None

    url = value.strip()
    if not url:
        return None

    # Protocol-relative image URLs are common in web catalog payloads.
    if url.startswith("//"):
        return "https:" + url

    # Prefer HTTPS for remote image hosts.
    if url.startswith("http://"):
        return "https://" + url[len("http://"): ]

    # Serializd/TMDB payloads can expose a TMDB poster path instead of a full URL.
    if url.startswith("/"):
        return "https://image.tmdb.org/t/p/w500" + url

    # A bare TMDB image path may arrive without its leading slash.
    if url.startswith("image.tmdb.org/"):
        return "https://" + url

    return url if url.startswith("https://") else None

def _mal_details(anime_id: int) -> dict[str, Any]:
    # MAL returns the canonical API field names (mean, num_episodes,
    # start_date, average_episode_duration). The desktop UI uses a
    # presentation contract, so normalize them here rather than making
    # the frontend know MAL's API schema.
    token = core.mal_get_access_token()
    r = requests.get(
        f"https://api.myanimelist.net/v2/anime/{int(anime_id)}",
        headers={"Authorization": f"Bearer {token}"},
        params={"fields": (
            "id,title,main_picture,alternative_titles,start_date,end_date,synopsis,mean,"
            "rank,popularity,genres,status,num_episodes,start_season,"
            "broadcast,source,average_episode_duration,studios"
        )},
        timeout=20,
    )
    r.raise_for_status()
    raw = r.json()
    details = dict(raw)

    seconds = raw.get("average_episode_duration")
    if isinstance(seconds, (int, float)):
        minutes, secs = divmod(int(seconds), 60)
        duration = f"{minutes}m {secs}s"
    else:
        duration = None

    start = raw.get("start_date")
    picture = raw.get("main_picture")
    details.update({
        "score": raw.get("mean"),
        "year": str(start)[:4] if start else None,
        "episodes": raw.get("num_episodes"),
        "duration": duration,
        "image_url": (
            picture.get("large")
            or picture.get("medium")
            if isinstance(picture, dict)
            else None
        ),
    })
    return details

def _sz_details(show_id: int) -> dict[str, Any]:
    # This is the verified Serializd web/mobile detail surface. It exposes
    # showDetails plus the community averageRating used by the UI.
    r = requests.get(
        f"{SERIALIZD_MOBILE}/show_v2_part_1/{int(show_id)}",
        params={"optimize": "false"},
        headers=_sz_headers(),
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        return {}

    show = data.get("showDetails")
    details = dict(show) if isinstance(show, dict) else dict(data)

    for key in ("averageRating", "ratings"):
        if key in data:
            details[key] = data[key]
        if isinstance(show, dict) and key in show:
            details[key] = show[key]

    # Normalize likely naming variants for the desktop UI.
    seasons = details.get("seasons")
    if isinstance(seasons, list):
        total = 0
        for season in seasons:
            if not isinstance(season, dict):
                continue
            count = _first(
                season, "episodeCount", "numberOfEpisodes",
                "episode_count", "numEpisodes"
            )
            if isinstance(count, (int, float)):
                total += int(count)
        details.setdefault("numSeasons", len(seasons))
        details.setdefault("numEpisodes", total or None)

    return details

def search_catalogs(query: str, is_anime: bool, media_type: str) -> dict[str, Any]:
    query = str(query or "").strip()
    if not query:
        raise ValueError("Search query is required.")
    media_type = str(media_type or "").lower()
    if media_type not in {"tv", "movie"}:
        raise ValueError("media_type must be 'tv' or 'movie'.")

    use_mal = bool(is_anime)
    use_serializd = media_type == "tv"
    out = {
        "workflow_id": core.M19_WORKFLOW_ID,
        "query": query,
        "routing": {
            "anime": use_mal,
            "media_type": media_type,
            "mal": use_mal,
            "serializd": use_serializd,
        },
        "mal": {"results": [], "error": None},
        "serializd": {"results": [], "error": None},
        "read_only": True,
    }

    if use_mal:
        try:
            out["mal"]["results"] = (core.search_anime(query) or [])[:10]
        except Exception as e:
            out["mal"]["error"] = str(e)

    if use_serializd:
        try:
            serializd_results = (search_catalog(query) or [])[:10]
            normalized_results = []
            for item in serializd_results:
                if not isinstance(item, dict):
                    continue
                item = dict(item)
                if not item.get("image_url"):
                    for key in (
                        "image", "poster", "posterUrl", "imageUrl",
                        "posterPath", "poster_path", "imagePath", "image_path",
                    ):
                        normalized = _normalize_serializd_image(item.get(key))
                        if normalized:
                            item["image_url"] = normalized
                            break
                normalized_results.append(item)
            out["serializd"]["results"] = normalized_results
        except Exception as e:
            out["serializd"]["error"] = str(e)

    if use_mal:
        normalized_mal = []
        for item in out["mal"]["results"]:
            if not isinstance(item, dict):
                continue
            item = dict(item)
            node = item.get("node")
            if isinstance(node, dict):
                node = dict(node)
                picture = node.get("main_picture")
                if not node.get("image_url") and isinstance(picture, dict):
                    node["image_url"] = picture.get("large") or picture.get("medium")
                item["node"] = node
            normalized_mal.append(item)
        out["mal"]["results"] = normalized_mal

    return out

def select_result(service: str, results: list[dict[str, Any]], index: int) -> dict[str, Any]:
    i = int(index) - 1
    if not isinstance(results, list) or not 0 <= i < len(results):
        raise ValueError("Invalid search result selection.")
    selected = results[i]

    if service == "mal":
        node = selected.get("node", selected)
        ident = node.get("id") if isinstance(node, dict) else None
        if not ident:
            raise ValueError("Selected MAL result has no anime ID.")
        details = _mal_details(int(ident))
    elif service == "serializd":
        ident = selected.get("id")
        if not ident:
            raise ValueError("Selected Serializd result has no show ID.")
        details = _sz_details(int(ident))

        # Serializd's detail endpoint does not reliably repeat the artwork
        # fields that are present on the catalog-search result. Carry the
        # remote artwork URL forward from the selected catalog item so the
        # existing M20.5.6 frontend can render it without hosting or storing
        # the image locally.
        if isinstance(details, dict) and isinstance(selected, dict):
            for target, candidates in (
                ("image", (
                    "image", "poster", "posterUrl", "image_url", "imageUrl",
                    "posterPath", "poster_path", "imagePath", "image_path",
                )),
                ("backdrop", (
                    "backdrop", "backdropUrl", "backdrop_url",
                    "backdropPath", "backdrop_path", "backdropImage",
                )),
            ):
                if not details.get(target):
                    for key in candidates:
                        normalized = _normalize_serializd_image(selected.get(key))
                        if normalized:
                            details[target] = normalized
                            break

            # Normalize artwork already returned by the detail endpoint too.
            for target in ("image", "poster", "image_url", "imageUrl", "posterUrl", "backdrop", "backdrop_url", "backdropUrl"):
                if details.get(target):
                    normalized = _normalize_serializd_image(details.get(target))
                    if normalized:
                        details[target] = normalized

            if not details.get("image_url"):
                image = _normalize_serializd_image(details.get("image")) or _normalize_serializd_image(details.get("poster"))
                if image:
                    details["image_url"] = image
            if not details.get("backdrop_url"):
                backdrop = _normalize_serializd_image(details.get("backdrop"))
                if backdrop:
                    details["backdrop_url"] = backdrop
    else:
        raise ValueError("Unknown service selection.")

    return {
        "service": service,
        "selected": selected,
        "details": details,
        "read_only": True,
    }


# M20.5.8 — Review workflow bridge

def review_seasons(show_id: int) -> dict[str, Any]:
    """Return numbered Serializd seasons for Review without reading watch state."""
    show_id = int(show_id)
    if show_id <= 0:
        raise ValueError("Serializd show ID is required.")
    show = get_show(show_id) or {}
    seasons = show.get("seasons", []) if isinstance(show, dict) else []
    out = []
    for season in seasons if isinstance(seasons, list) else []:
        if not isinstance(season, dict):
            continue
        raw_number = _first(season, "seasonNumber", "season_number", "number")
        raw_id = _first(season, "seasonId", "season_id", "id")
        try:
            number = int(raw_number)
            season_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if number <= 0 or season_id <= 0:
            continue
        count = _first(season, "episodeCount", "episode_count", "numberOfEpisodes", "numEpisodes", "episodesCount")
        try:
            count = int(count) if count is not None else None
        except (TypeError, ValueError):
            count = None
        image = None
        for key in ("image", "poster", "posterUrl", "imageUrl", "image_url", "posterPath", "poster_path"):
            image = _normalize_serializd_image(season.get(key))
            if image:
                break
        out.append({
            "season_id": season_id,
            "season_number": number,
            "name": _first(season, "name", "seasonName", "title") or f"Season {number}",
            "episode_count": count,
            "image_url": image,
        })
    out.sort(key=lambda x: x["season_number"])
    return {"show_id": show_id, "seasons": out}


def review_episodes(show_id: int, season_number: int) -> dict[str, Any]:
    """Return Serializd episodes for one season for Review target selection."""
    show_id = int(show_id)
    season_number = int(season_number)
    if show_id <= 0 or season_number <= 0:
        raise ValueError("Serializd show and season are required.")
    season = get_season(show_id, season_number) or {}
    raw_episodes = season.get("episodes", []) if isinstance(season, dict) else []
    raw_season_id = _first(season, "seasonId", "season_id", "id")
    try:
        season_id = int(raw_season_id)
    except (TypeError, ValueError):
        season_id = 0
    episodes = []
    for index, ep in enumerate(raw_episodes if isinstance(raw_episodes, list) else [], 1):
        if not isinstance(ep, dict):
            continue
        raw_number = _first(ep, "episodeNumber", "episode_number", "number")
        try:
            number = int(raw_number if raw_number is not None else index)
        except (TypeError, ValueError):
            continue
        if number <= 0:
            continue
        episodes.append({
            "episode_number": number,
            "title": _first(ep, "title", "name") or f"Episode {number}",
            "image_url": _normalize_serializd_image(_first(ep, "image", "poster", "posterUrl", "imageUrl", "image_url")),
        })
    episodes.sort(key=lambda x: x["episode_number"])
    return {"show_id": show_id, "season_number": season_number, "season_id": season_id, "episodes": episodes}


def _review_payload_values(payload: dict[str, Any]) -> tuple[str, int, int, int | None, float | None, str, bool, bool, bool, bool]:
    if not isinstance(payload, dict):
        raise ValueError("Review payload must be an object.")
    target = str(payload.get("target") or "").lower()
    if target not in {"series", "season", "episode"}:
        raise ValueError("Review target must be series, season, or episode.")
    show_id = int(payload.get("show_id") or 0)
    season_id = int(payload.get("season_id") or 0)
    episode_number_raw = payload.get("episode_number")
    episode_number = int(episode_number_raw) if episode_number_raw not in (None, "", 0) else None
    if show_id <= 0:
        raise ValueError("Serializd show ID is required.")
    if target in {"season", "episode"} and season_id <= 0:
        raise ValueError("Serializd season ID is required.")
    if target == "episode" and (episode_number is None or episode_number <= 0):
        raise ValueError("Episode number is required.")
    stars_raw = payload.get("stars")
    stars = None if stars_raw in (None, "") else float(stars_raw)
    if stars is not None:
        minimum = 1.0 if target == "season" else 0.5
        if not minimum <= stars <= 5.0 or (stars * 2) != int(stars * 2):
            raise ValueError(f"Rating must be in 0.5 increments between {minimum:.1f} and 5.0.")
    text_value = str(payload.get("review_text") or "")
    return (
        target, show_id, season_id, episode_number, stars, text_value,
        bool(payload.get("is_rewatch", False)),
        bool(payload.get("contains_spoiler", False)),
        bool(payload.get("like", False)),
        bool(payload.get("allows_comments", True)),
    )


def review_execute(payload: dict[str, Any]) -> dict[str, Any]:
    """Create one Serializd series, season, or episode review/log."""
    (
        target, show_id, season_id, episode_number, stars, review_text,
        is_rewatch, contains_spoiler, like, allows_comments,
    ) = _review_payload_values(payload)
    tags = payload.get("tags") if isinstance(payload.get("tags"), list) else []
    backdate = payload.get("backdate") or None
    try:
        if target == "episode":
            # Episode reviews use the adapter's dedicated review writer so the
            # full 0.5-star range is preserved (API rating 1-10).
            result = log_episode(
                show_id, season_id, episode_number,
                stars=stars,
                review_text=review_text,
                is_rewatch=is_rewatch,
                contains_spoiler=contains_spoiler,
                like=like,
                allows_comments=allows_comments,
                tags=tags,
                backdate=backdate,
            )
        elif target == "season":
            result = log_season_review(
                show_id, season_id,
                stars=stars,
                review_text=review_text,
                is_rewatch=is_rewatch,
                contains_spoiler=contains_spoiler,
                like=like,
                allows_comments=allows_comments,
                tags=tags,
                backdate=backdate,
            )
        else:
            result = log_series_review(
                show_id,
                stars=stars,
                review_text=review_text,
                is_rewatch=is_rewatch,
                contains_spoiler=contains_spoiler,
                like=like,
                allows_comments=allows_comments,
                tags=tags,
                backdate=backdate,
            )
        return {"ok": True, "target": target, "result": result}
    except Exception as exc:
        return {"ok": False, "target": target, "error": str(exc)}


def review_existing(payload: dict[str, Any]) -> dict[str, Any]:
    """Find the user's existing diary review/log entries for a target."""
    target, show_id, season_id, episode_number, *_ = _review_payload_values({**payload, "stars": None})
    matches = []
    for entry in get_full_diary():
        if not isinstance(entry, dict):
            continue
        try:
            if int(entry.get("showId", -1)) != show_id:
                continue
        except (TypeError, ValueError):
            continue
        entry_season = entry.get("seasonId")
        entry_episode = entry.get("episodeNumber")
        if target == "series":
            if entry_season is not None or entry_episode is not None:
                continue
        elif target == "season":
            try:
                if int(entry_season) != season_id or entry_episode is not None:
                    continue
            except (TypeError, ValueError):
                continue
        else:
            try:
                if int(entry_season) != season_id or int(entry_episode) != episode_number:
                    continue
            except (TypeError, ValueError):
                continue
        review_id = entry.get("reviewId", entry.get("review_id", entry.get("id")))
        matches.append({
            **entry,
            "review_id": review_id,
            "stars": (float(entry["rating"]) / 2) if entry.get("rating") not in (None, "", 0) else None,
            "review_text": entry.get("reviewText", entry.get("review_text", "")) or "",
            "is_rewatch": bool(entry.get("isRewatch", entry.get("is_rewatch", False))),
            "contains_spoiler": bool(entry.get("containsSpoiler", entry.get("contains_spoiler", False))),
            "like": bool(entry.get("like", entry.get("liked", False))),
            "allows_comments": bool(entry.get("allowsComments", entry.get("allows_comments", True))),
            "backdate": entry.get("backdate") or entry.get("dateAdded"),
        })
    return {"ok": True, "target": target, "matches": matches}


def review_update(payload: dict[str, Any]) -> dict[str, Any]:
    review_id = int(payload.get("review_id") or 0)
    if review_id <= 0:
        raise ValueError("Review ID is required.")
    stars_raw = payload.get("stars")
    stars = None if stars_raw in (None, "") else float(stars_raw)
    if stars is not None and (not 0.5 <= stars <= 5.0 or stars * 2 != int(stars * 2)):
        raise ValueError("Updated rating must be between 0.5 and 5.0 in 0.5 increments.")
    rating = None if stars is None else int(stars * 2)
    try:
        result = update_review_log(
            review_id,
            show_id=(int(payload["show_id"]) if payload.get("show_id") not in (None, "", 0) else None),
            season_id=(int(payload["season_id"]) if payload.get("season_id") not in (None, "", 0) else None),
            review_text=str(payload.get("review_text") or ""),
            rating=rating,
            contains_spoiler=bool(payload.get("contains_spoiler", False)),
            allows_comments=bool(payload.get("allows_comments", True)),
            is_rewatch=bool(payload.get("is_rewatch", False)),
            like=bool(payload.get("like", False)),
            tags=payload.get("tags") if isinstance(payload.get("tags"), list) else [],
            episode_number=(int(payload["episode_number"]) if payload.get("episode_number") not in (None, "", 0) else None),
            backdate=payload.get("backdate") or None,
        )
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def review_delete(payload: dict[str, Any]) -> dict[str, Any]:
    review_id = int(payload.get("review_id") or 0)
    if review_id <= 0:
        raise ValueError("Review ID is required.")
    try:
        return {"ok": True, "result": delete_review_log(review_id)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def mal_status(anime_id: int) -> dict[str, Any]:
    anime_id = int(anime_id)
    if anime_id <= 0:
        raise ValueError("MAL anime ID is required.")
    data = core.get_my_status(anime_id) or {}
    if not isinstance(data, dict):
        raise ValueError("MyAnimeList returned an unexpected status response.")
    return data


def mal_update(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("MAL update payload must be an object.")
    anime_id = int(payload.get("mal_id") or 0)
    if anime_id <= 0:
        raise ValueError("MAL anime ID is required.")
    total_raw = payload.get("total_episodes")
    total = int(total_raw) if total_raw not in (None, "", 0) else None
    progress_raw = payload.get("progress")
    progress = None if progress_raw in (None, "") else int(progress_raw)
    rating_raw = payload.get("rating")
    rating = None if rating_raw in (None, "") else int(rating_raw)
    status = str(payload.get("status") or "").strip().lower() or None
    allowed = {"watching", "completed", "on_hold", "dropped", "plan_to_watch", "rewatching"}
    if status is not None and status not in allowed:
        raise ValueError("Unsupported MAL status.")
    if rating is not None and not 1 <= rating <= 10:
        raise ValueError("MAL rating must be a whole number from 1 to 10.")
    if progress is not None and progress < 0:
        raise ValueError("MAL progress cannot be negative.")
    if total is not None and progress is not None and progress > total:
        raise ValueError(f"MAL progress cannot exceed the known total of {total} episodes.")
    if status == "completed" and total is not None:
        progress = total

    operations = []
    try:
        current = core.get_my_status(anime_id) or {}
        ls = current.get("my_list_status", {}) if isinstance(current, dict) else {}
        current_progress = int(ls.get("num_episodes_watched", 0) or 0)
        current_status = ls.get("status")
        current_rating = ls.get("score")

        if progress is not None and progress != current_progress:
            operations.append({"name": f"MAL progress → E{progress}", "ok": True, "result": core.update_progress(anime_id, progress, is_rewatching=status == "rewatching")})
        elif status == "rewatching" and current_status != "rewatching":
            operations.append({"name": "MAL rewatching flag", "ok": True, "result": core.update_progress(anime_id, current_progress, is_rewatching=True)})
        if status is not None and status != "rewatching" and status != current_status:
            operations.append({"name": f"MAL status → {status}", "ok": True, "result": core.update_status(anime_id, status)})
        if rating is not None and rating != current_rating:
            operations.append({"name": f"MAL score → {rating}/10", "ok": True, "result": core.update_score(anime_id, rating)})
        if not operations:
            return {"ok": True, "operations": [], "message": "No MAL changes were requested."}
        return {"ok": all(op["ok"] for op in operations), "operations": operations}
    except Exception as exc:
        operations.append({"name": "MAL update", "ok": False, "error": str(exc)})
        return {"ok": False, "operations": operations, "error": str(exc)}


def serializd_rate(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Serializd rating payload must be an object.")
    target = str(payload.get("target") or "").lower()
    show_id = int(payload.get("show_id") or 0)
    season_id = int(payload.get("season_id") or 0) if payload.get("season_id") not in (None, "", 0) else None
    episode_number = int(payload.get("episode_number") or 0) if payload.get("episode_number") not in (None, "", 0) else None
    stars = float(payload.get("stars")) if payload.get("stars") not in (None, "") else None
    if show_id <= 0 or target not in {"series", "season", "episode"}:
        raise ValueError("A valid Serializd target and show are required.")
    if target in {"season", "episode"} and not season_id:
        raise ValueError("Serializd season ID is required.")
    if target == "episode" and not episode_number:
        raise ValueError("Serializd episode number is required.")
    if stars is None or not 0.5 <= stars <= 5.0 or stars * 2 != int(stars * 2):
        raise ValueError("Serializd rating must be 0.5 to 5.0 in half-star increments.")
    existing = payload.get("existing") if isinstance(payload.get("existing"), dict) else None
    try:
        if existing and existing.get("review_id"):
            from app.backend.services.serializd import update_rating_log
            result = update_rating_log(
                int(existing["review_id"]),
                show_id=show_id,
                season_id=season_id,
                episode_number=episode_number,
                rating=int(stars * 2),
                review_text=existing.get("review_text", ""),
                backdate=existing.get("backdate") or None,
            )
            return {"ok": True, "mode": "updated", "result": result}
        if target == "series":
            result = rate_series(show_id, stars)
        elif target == "season":
            result = rate_season(show_id, season_id, stars)
        else:
            result = rate_episode(show_id, season_id, episode_number, stars)
            # Rating an episode is a diary/log action in Serializd, but also
            # explicitly set watched state so WAYMARK's progress view agrees
            # immediately with the rating action.
            watched_result = None
            try:
                from app.backend.services.serializd import mark_episode_watched
                watched_result = mark_episode_watched(show_id, season_id, episode_number)
            except Exception as watched_exc:
                return {
                    "ok": False,
                    "mode": "partial",
                    "result": result,
                    "error": f"Episode rating was written, but watched state could not be updated: {watched_exc}",
                }
            return {"ok": True, "mode": "created", "result": result, "watched": watched_result}
        return {"ok": True, "mode": "created", "result": result}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def serializd_progress(payload: dict[str, Any]) -> dict[str, Any]:
    """Update Serializd progress for explicitly selected episodes.

    Normal watch mode skips episodes that are already logged. Rewatch mode
    deliberately sends every selected episode through the verified Watch
    rewatch path. Existing Watch/Review behavior is otherwise untouched.
    """
    if not isinstance(payload, dict):
        raise ValueError("Serializd progress payload must be an object.")

    show_id = int(payload.get("show_id") or 0)
    season_id = int(payload.get("season_id") or 0)
    season_number = int(payload.get("season_number") or 0)
    season_total = int(payload.get("season_total_episodes") or 0)
    rewatch = bool(payload.get("rewatch", False))

    if show_id <= 0 or season_id <= 0 or season_number <= 0:
        raise ValueError("Valid Serializd show and season are required.")

    selected_raw = payload.get("selected_episode_numbers")
    if not isinstance(selected_raw, list) or not selected_raw:
        raise ValueError("Select at least one Serializd episode.")

    selected: list[int] = []
    for value in selected_raw:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            selected.append(number)
    selected = sorted(set(selected))
    if not selected:
        raise ValueError("Select at least one Serializd episode.")

    if season_total and any(number > season_total for number in selected):
        raise ValueError(
            f"Serializd episode E{max(selected)} is beyond the known season total of {season_total}."
        )

    # Refresh watch state from Serializd immediately before deciding what to
    # write. The browser's earlier snapshot is retained only as a fallback if
    # the live read endpoint is temporarily unavailable.
    watched = set()
    live_read_error = None
    try:
        for record in get_watched_episode_logs(show_id, season_id):
            if not isinstance(record, dict):
                continue
            raw = record.get("episodeNumber", record.get("episode_number"))
            if raw is None and isinstance(record.get("episode"), dict):
                raw = record["episode"].get("episodeNumber", record["episode"].get("episode_number"))
            try:
                number = int(raw)
            except (TypeError, ValueError):
                continue
            if number > 0:
                watched.add(number)
    except Exception as exc:
        live_read_error = str(exc)

    if not watched and live_read_error:
        for value in (payload.get("watched_episode_numbers") or []):
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if number > 0:
                watched.add(number)

    already_selected = sorted(watched.intersection(selected))
    to_log = selected if rewatch else [number for number in selected if number not in watched]

    if not to_log:
        return {
            "ok": True,
            "operations": [],
            "message": "All selected episodes are already logged. Choose Rewatching to log them again.",
            "selected": selected,
            "skipped_existing": already_selected,
            "logged": [],
            "rewatch": rewatch,
            "live_watched": sorted(watched),
            "live_read_error": live_read_error,
            "season_completed": bool(season_total and set(selected) >= set(range(1, season_total + 1))),
        }

    operations = []
    try:
        result = watch_execute_batch({
            "mode": "serializd",
            "serializd_id": show_id,
            "serializd_season_id": season_id,
            "season_number": season_number,
            "serializd_episodes": to_log,
            "mal_episodes": [],
            "season_total_episodes": season_total or None,
            "serializd_rewatch": rewatch,
        })
        operations = list(result.get("operations", []))

        # In normal-watch mode, already-logged episodes were removed from the
        # batch, so the Watch batch cannot by itself see that the entire season
        # is now complete. Mark the season watched when the combined set of
        # existing + newly logged episodes covers every numbered episode.
        if (
            not rewatch
            and not result.get("season_completed")
            and season_total
            and set(watched).union(to_log) >= set(range(1, season_total + 1))
            and all(op.get("ok") for op in operations)
        ):
            from app.backend.services.serializd import mark_season_watched
            try:
                operations.append({
                    "name": f"Serializd season watched → S{season_number:02d}",
                    "ok": True,
                    "result": mark_season_watched(show_id, season_id),
                })
            except Exception as exc:
                operations.append({
                    "name": f"Serializd season watched → S{season_number:02d}",
                    "ok": False,
                    "error": str(exc),
                })

        failed = [op for op in operations if not op.get("ok")]
        succeeded = [op for op in operations if op.get("ok")]
        return {
            "ok": bool(operations) and not failed,
            "partial": bool(failed and succeeded),
            "selected": selected,
            "skipped_existing": already_selected if not rewatch else [],
            "logged": to_log,
            "rewatch": rewatch,
            "live_watched": sorted(watched),
            "live_read_error": live_read_error,
            "season_completed": bool(
                season_total
                and set(watched).union(to_log) >= set(range(1, season_total + 1))
            ),
            "operations": operations,
            "error": None if not failed else "One or more Serializd progress operations failed.",
        }
    except Exception as exc:
        return {
            "ok": False,
            "partial": False,
            "selected": selected,
            "skipped_existing": already_selected if not rewatch else [],
            "logged": [],
            "rewatch": rewatch,
            "operations": operations,
            "error": str(exc),
        }

def status():
    return {
        "application": "WAYMARK",
        "phase": "M20.5.8",
        "bridge": "ready",
        "core": "ready",
        "read_only": False,
        "capabilities": {
            "search": True,
            "search_selection": True,
            "library": True,
            "history": True,
            "watch": True,
            "review": True,
            "rating": True,
            "writes": True,
        },
    }

def library():
    return core.m19_library()

def history(limit=20):
    return core.m19_history(max(1, min(int(limit), 100)))


# M20.5.7 — Watch workflow bridge
def watch_seasons(show_id: int, *, include_account_state: bool = True) -> dict[str, Any]:
    """Return numbered Serializd seasons using the show response only.

    Initial Watch navigation must stay fast: do not fetch every season's
    episode list or watched logs here. Detailed episode titles and watched
    episode numbers are loaded only after the user selects a season.
    """
    show_id = int(show_id)
    if show_id <= 0:
        raise ValueError("Serializd show ID is required.")

    show = get_show(show_id) or {}
    seasons = show.get("seasons", []) if isinstance(show, dict) else []
    out = []

    def first_image(value):
        if not isinstance(value, dict):
            return None
        for key in (
            "image", "poster", "posterUrl", "imageUrl",
            "image_url", "posterPath", "poster_path",
            "imagePath", "image_path",
        ):
            image = _normalize_serializd_image(value.get(key))
            if image:
                return image
        return None

    def episode_count(value):
        if not isinstance(value, dict):
            return 0
        for key in (
            "episodeCount", "episode_count", "numberOfEpisodes",
            "numEpisodes", "episodesCount", "episodeTotal",
            "totalEpisodes", "number_of_episodes",
        ):
            raw = value.get(key)
            try:
                count = int(raw)
            except (TypeError, ValueError):
                continue
            if count > 0:
                return count
        raw_episodes = value.get("episodes")
        if isinstance(raw_episodes, list):
            numbered = []
            for ep in raw_episodes:
                if not isinstance(ep, dict):
                    continue
                try:
                    number = int(ep.get("episodeNumber"))
                except (TypeError, ValueError):
                    continue
                if number > 0:
                    numbered.append(number)
            return len(set(numbered))
        return 0

    for season in seasons or []:
        if not isinstance(season, dict):
            continue

        raw_number = season.get(
            "seasonNumber",
            season.get("season_number", season.get("number"))
        )
        try:
            number = int(raw_number)
        except (TypeError, ValueError):
            continue
        if number <= 0:
            continue

        season_id = season.get("seasonId", season.get("id"))
        if season_id is None:
            continue
        try:
            season_id = int(season_id)
        except (TypeError, ValueError):
            continue
        if season_id <= 0:
            continue

        name = (
            season.get("name")
            or season.get("title")
            or season.get("seasonName")
            or season.get("season_name")
            or season.get("displayName")
            or f"Season {number}"
        )

        count = episode_count(season)
        image = first_image(season)

        out.append({
            "season_number": number,
            "season_id": season_id,
            "name": str(name),
            "episode_count": count,
            "image_url": image,
            # Detailed progress is intentionally deferred to watch_episodes().
            "watched_episode_numbers": [],
            "watched_count": 0,
            "season_completed": False,
        })

    out.sort(key=lambda item: item["season_number"])

    # Watch keeps the account-state read because it drives the existing
    # completed-show/rewatch behavior. Rating/Progress can explicitly skip it
    # because those screens only need season metadata.
    show_state = None
    if include_account_state:
        try:
            show_state = get_show_watch_state(show_id)
        except Exception:
            show_state = None

    show_completed = False
    show_watched = bool(show_state)
    if isinstance(show_state, dict):
        status_values = []
        for key in ("status", "watchStatus", "watch_status", "listStatus", "list_status"):
            value = show_state.get(key)
            if isinstance(value, str):
                status_values.append(value.strip().lower())

        show_completed = any(
            value in {"completed", "complete", "finished"}
            for value in status_values
        )
        show_completed = show_completed or any(
            bool(show_state.get(key))
            for key in ("completed", "isCompleted", "is_completed")
        )

    return {
        "show_id": show_id,
        "seasons": out,
        "show_watched": show_watched,
        "show_completed": show_completed,
        "watched_season_count": 0,
        "total_season_count": len(out),
        "progress_deferred": True,
    }


def serializd_seasons(show_id: int) -> dict[str, Any]:
    """Return season metadata for Rating/Progress without account-wide reads."""
    return watch_seasons(show_id, include_account_state=False)

def watch_episodes(show_id: int, season_number: int) -> dict[str, Any]:
    """Return numbered Serializd episodes for one selected season."""
    show_id = int(show_id)
    season_number = int(season_number)
    if show_id <= 0 or season_number <= 0:
        raise ValueError("Valid Serializd show and season are required.")

    detail = get_season(show_id, season_number) or {}
    episodes = detail.get("episodes", []) if isinstance(detail, dict) else []
    out = []
    for ep in episodes or []:
        if not isinstance(ep, dict):
            continue
        try:
            number = int(ep.get("episodeNumber"))
        except (TypeError, ValueError):
            continue
        if number <= 0:
            continue
        out.append({
            "episode_number": number,
            "title": str(ep.get("title") or ep.get("name") or "Untitled"),
        })

    out.sort(key=lambda item: item["episode_number"])
    if not out:
        raise ValueError("No numbered episodes were found in this Serializd season.")

    watched_episode_numbers: list[int] = []
    try:
        logs = get_watched_episode_logs(show_id, int((detail.get("seasonId") or detail.get("id") or 0)))
        for log in logs:
            try:
                ep_number = int(log.get("episodeNumber"))
            except (TypeError, ValueError):
                continue
            if ep_number > 0 and ep_number not in watched_episode_numbers:
                watched_episode_numbers.append(ep_number)
        watched_episode_numbers.sort()
    except Exception:
        watched_episode_numbers = []

    return {
        "show_id": show_id,
        "season_number": season_number,
        "episodes": out,
        "final_episode": out[-1]["episode_number"],
        "watched_episode_numbers": watched_episode_numbers,
    }


def watch_execute(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute the existing verified Watch write path after validation."""
    if not isinstance(payload, dict):
        raise ValueError("Watch payload must be an object.")

    serializd_id = int(payload.get("serializd_id") or 0)
    serializd_season_id = int(payload.get("serializd_season_id") or 0)
    season_number = int(payload.get("season_number") or 0)
    episode_number = int(payload.get("episode_number") or 0)

    if serializd_id <= 0 or serializd_season_id <= 0:
        raise ValueError("A valid Serializd show and season are required.")
    if season_number <= 0 or episode_number <= 0:
        raise ValueError("A valid Serializd season and episode are required.")

    mal_id_raw = payload.get("mal_id")
    mal_id = int(mal_id_raw) if mal_id_raw not in (None, "", 0) else None

    mal_episode_raw = payload.get("mal_episode_number")
    mal_episode_number = int(mal_episode_raw) if mal_episode_raw not in (None, "", 0) else None

    mal_total_raw = payload.get("mal_total_episodes")
    mal_total = int(mal_total_raw) if mal_total_raw not in (None, "", 0) else None

    status = payload.get("status") or None
    if status == "keep":
        status = None
    serializd_rewatch = bool(payload.get("serializd_rewatch", False))

    result = core._chat_execute_anime_tv_action(
        mal_id=mal_id,
        serializd_id=serializd_id,
        serializd_season_id=serializd_season_id,
        season_number=season_number,
        episode_number=episode_number,
        mal_episode_number=mal_episode_number,
        mal_total_episodes=mal_total,
        mal_rating=None,
        serializd_stars=None,
        status=status,
        review_text="",
        season_completed=bool(payload.get("season_completed", False)),
        season_rating=None,
        season_review_text="",
        final_episode=int(payload["final_episode"]) if payload.get("final_episode") else None,
    )
    return result


# M20.5.7 UX update — batch Watch writes
def watch_execute_batch(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute selected MAL and/or Serializd episodes with explicit results."""
    if not isinstance(payload, dict):
        raise ValueError("Watch payload must be an object.")

    mode = str(payload.get("mode") or "").lower()
    if mode not in {"mal", "serializd", "both"}:
        raise ValueError("Watch service mode must be mal, serializd, or both.")

    def episode_list(value):
        if not isinstance(value, list):
            raise ValueError("Episode selection must be a list.")
        out = []
        for item in value:
            n = int(item)
            if n > 0:
                out.append(n)
        return sorted(set(out))

    mal_episodes = episode_list(payload.get("mal_episodes", []))
    serializd_episodes = episode_list(payload.get("serializd_episodes", []))

    mal_id = int(payload.get("mal_id") or 0)
    serializd_id = int(payload.get("serializd_id") or 0)
    serializd_season_id = int(payload.get("serializd_season_id") or 0)
    season_number = int(payload.get("season_number") or 0)

    if mode in {"mal", "both"} and (mal_id <= 0 or not mal_episodes):
        raise ValueError("MAL title and at least one MAL episode are required.")
    if mode in {"serializd", "both"} and (
        serializd_id <= 0 or serializd_season_id <= 0 or season_number <= 0 or not serializd_episodes
    ):
        raise ValueError("Serializd show, season, and at least one Serializd episode are required.")

    status = payload.get("status") or None
    if status == "keep":
        status = None

    # Serializd rewatch is an explicit batch flag. Keep it separate from
    # MAL status so a Serializd rewatch never changes MAL state implicitly.
    serializd_rewatch = bool(payload.get("serializd_rewatch", False))

    mal_total = payload.get("mal_total_episodes")
    try:
        mal_total = int(mal_total) if mal_total not in (None, "", 0) else None
    except (TypeError, ValueError):
        mal_total = None

    if mal_total is not None:
        invalid = [n for n in mal_episodes if n > mal_total]
        if invalid:
            raise ValueError(
                f"MAL episode E{max(invalid)} is beyond the known total of {mal_total} episodes."
            )

    season_total = payload.get("season_total_episodes")
    try:
        season_total = int(season_total) if season_total not in (None, "", 0) else None
    except (TypeError, ValueError):
        season_total = None

    operations = []

    def run_operation(name, func):
        try:
            result = func()
            operations.append({"name": name, "ok": True, "result": result})
        except Exception as exc:
            operations.append({"name": name, "ok": False, "error": str(exc)})

    # MAL is a progress/status service operation, so use the existing direct
    # MAL functions. The cross-service core action requires a Serializd payload
    # and therefore is not appropriate for the MAL-only sub-operation.
    if mode in {"mal", "both"}:
        for episode in mal_episodes:
            run_operation(
                f"MAL progress → E{episode}",
                lambda episode=episode: core.update_progress(
                    mal_id,
                    episode,
                    is_rewatching=status == "rewatching",
                ),
            )
        if status in {"watching", "completed", "on_hold", "plan_to_watch"}:
            run_operation(
                f"MAL status → {status}",
                lambda: core.update_status(mal_id, status),
            )

    # Serializd retains the already-verified core write behavior. When the
    # user selects every numbered episode in a season for a normal Watch, use
    # the season-level watched endpoint so a full season is one server write.
    # Partial selections remain episode-by-episode. Rewatch remains
    # episode-by-episode because no verified season-level rewatch endpoint is
    # available.
    if mode in {"serializd", "both"}:
        full_serializd_season = bool(
            season_total
            and set(serializd_episodes) == set(range(1, season_total + 1))
        )

        if not serializd_rewatch and full_serializd_season:
            from app.backend.services.serializd import mark_season_watched
            run_operation(
                f"Serializd season watched → S{season_number:02d}",
                lambda: mark_season_watched(serializd_id, serializd_season_id),
            )
        else:
            if serializd_rewatch:
                from app.backend.services.serializd import (
                    mark_episode_watched,
                    log_episode,
                    add_episode_rating,
                    mark_season_watched,
                )

            for index, episode in enumerate(serializd_episodes):
                completed = bool(
                    season_total
                    and set(serializd_episodes) >= set(range(1, season_total + 1))
                    and index == len(serializd_episodes) - 1
                )

                if serializd_rewatch:
                    def run_serializd_rewatch(episode=episode, completed=completed):
                        mark_episode_watched(serializd_id, serializd_season_id, episode)
                        log_episode(
                            serializd_id,
                            serializd_season_id,
                            episode,
                            stars=None,
                            review_text="",
                            is_rewatch=True,
                        )
                        if completed:
                            mark_season_watched(serializd_id, serializd_season_id)
                        return {"rewatch": True, "season_completed": completed}

                    run_operation(
                        f"Serializd rewatch → S{season_number:02d}E{episode:02d}",
                        run_serializd_rewatch,
                    )
                else:
                    run_operation(
                        f"Serializd episode → S{season_number:02d}E{episode:02d}",
                        lambda episode=episode, completed=completed: core._chat_execute_anime_tv_action(
                            mal_id=None,
                            serializd_id=serializd_id,
                            serializd_season_id=serializd_season_id,
                            season_number=season_number,
                            episode_number=episode,
                            mal_episode_number=None,
                            mal_total_episodes=None,
                            mal_rating=None,
                            serializd_stars=None,
                            status=None,
                            review_text="",
                            season_completed=completed,
                            season_rating=None,
                            season_review_text="",
                            final_episode=season_total if completed else None,
                        ),
                    )

    failed = [op for op in operations if not op["ok"]]
    succeeded = [op for op in operations if op["ok"]]
    return {
        "ok": bool(operations) and not failed,
        "partial": bool(failed and succeeded),
        "operations": operations,
        "season_completed": bool(
            season_total
            and mode in {"serializd", "both"}
            and set(serializd_episodes) >= set(range(1, season_total + 1))
        ),
    }


# ============================================================
# M22 — FIRST-RUN ACCOUNT SETUP
# ============================================================

def setup_status() -> dict[str, Any]:
    mal_creds = get_service_credentials("mal")
    mal_connected = bool(mal_creds.get("access_token"))
    sz_status = serializd_connection_status()
    return {
        "mal": {
            "connected": mal_connected,
            "username": None,
            "client_id_configured": mal_client_id_configured(),
            "auth": get_mal_auth_status(),
        },
        "serializd": sz_status,
        "complete": mal_connected and bool(sz_status.get("connected")),
    }


def mal_auth_start(client_id: str | None = None) -> dict[str, Any]:
    # Do not persist a client ID merely because an OAuth attempt started.
    # The current attempt uses the explicit value directly; auth.py persists
    # it only after MAL token exchange succeeds. This keeps failed IDs from
    # becoming sticky and allows the user to replace a bad ID on retry.
    return start_mal_auth(client_id)


def mal_auth_status() -> dict[str, Any]:
    return get_mal_auth_status()


def mal_disconnect() -> dict[str, Any]:
    return disconnect_mal()


def serializd_connect(token: str) -> dict[str, Any]:
    return serializd_connect_with_token(token)


def serializd_disconnect() -> dict[str, Any]:
    serializd_disconnect()
    return serializd_connection_status()


def setup_complete() -> dict[str, Any]:
    status = setup_status()
    return {"complete": bool(status.get("complete")), "status": status}
