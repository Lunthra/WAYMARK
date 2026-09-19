"""WAYMARK TMDB movie metadata client.

Uses the TMDB API Read Access Token as the primary authentication method,
with TMDB_API_KEY available as a fallback for v3 API requests.

This module is intentionally independent from waymark_core.py, mal.py, and
serializd.py so TMDB can be validated before being integrated into WAYMARK.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from app.backend.core.credentials import get_credential


TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p"
TMDB_LANGUAGE = "en-US"


class TMDBError(RuntimeError):
    """Raised when a TMDB request cannot be completed successfully."""


@dataclass(frozen=True)
class MovieSearchResult:
    """Small, stable representation of a TMDB movie search result."""

    tmdb_id: int
    title: str
    original_title: str
    release_date: str | None
    year: int | None
    overview: str
    poster_path: str | None
    backdrop_path: str | None
    vote_average: float | None
    vote_count: int | None

    @property
    def poster_url(self) -> str | None:
        return build_image_url(self.poster_path, "w500")

    @property
    def backdrop_url(self) -> str | None:
        return build_image_url(self.backdrop_path, "w1280")


class TMDBClient:
    """Minimal TMDB v3 client for WAYMARK movie discovery and metadata."""

    def __init__(self, *, language: str = TMDB_LANGUAGE, timeout: int = 20) -> None:
        if load_dotenv is not None and os.getenv("WAYMARK_DISABLE_DOTENV", "0").strip().lower() not in {"1", "true", "yes", "on"}:
            load_dotenv()

        self.language = language
        self.timeout = timeout
        self.access_token = get_credential("tmdb", "read_access_token", env_names=("TMDB_API_READ_ACCESS_TOKEN",)) or ""
        self.api_key = get_credential("tmdb", "api_key", env_names=("TMDB_API_KEY",)) or ""

        if not self.access_token and not self.api_key:
            raise TMDBError(
                "TMDB credentials are missing. Add TMDB_API_READ_ACCESS_TOKEN "
                "or TMDB_API_KEY to the WAYMARK .env file."
            )

    def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = dict(params or {})
        query.setdefault("language", self.language)

        headers = {
            "accept": "application/json",
            "User-Agent": "WAYMARK/0.1 (personal media tracker)",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        elif self.api_key:
            query["api_key"] = self.api_key

        url = f"{TMDB_BASE_URL}{path}?{urlencode(query)}"
        last_error: Exception | None = None

        for attempt in range(3):
            request = Request(url, headers=headers, method="GET")
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    payload = response.read().decode("utf-8")
                break
            except HTTPError as exc:
                try:
                    body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    body = ""
                if exc.code == 401:
                    raise TMDBError("TMDB authentication failed. Check the credentials in .env.") from exc
                if exc.code == 429:
                    if attempt < 2:
                        time.sleep(1.0 * (attempt + 1))
                        last_error = exc
                        continue
                    raise TMDBError("TMDB rate limit reached. Please wait and try again.") from exc
                raise TMDBError(
                    f"TMDB request failed with HTTP {exc.code}: {body[:300]}"
                ) from exc
            except (URLError, ConnectionResetError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                reason = getattr(exc, "reason", exc)
                raise TMDBError(f"Could not reach TMDB: {reason}") from exc
        else:
            raise TMDBError(f"Could not reach TMDB: {last_error}")

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise TMDBError("TMDB returned an invalid JSON response.") from exc

        if not isinstance(data, dict):
            raise TMDBError("TMDB returned an unexpected response format.")

        return data

    def test_connection(self) -> dict[str, Any]:
        """Verify that the configured credentials can make an authenticated call."""
        return self._request("/configuration")

    def search_movies(
        self,
        query: str,
        *,
        year: int | None = None,
        page: int = 1,
        include_adult: bool = False,
        region: str | None = None,
    ) -> list[MovieSearchResult]:
        """Search TMDB movies and return normalized results."""
        cleaned = query.strip()
        if not cleaned:
            raise ValueError("Movie search query cannot be empty.")
        if page < 1:
            raise ValueError("TMDB page must be at least 1.")

        params: dict[str, Any] = {
            "query": cleaned,
            "page": page,
            "include_adult": str(include_adult).lower(),
        }
        if year is not None:
            params["year"] = year
        if region:
            params["region"] = region.upper()

        data = self._request("/search/movie", params)
        results = data.get("results", [])
        if not isinstance(results, list):
            raise TMDBError("TMDB returned an unexpected search result format.")

        normalized: list[MovieSearchResult] = []
        for item in results:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            normalized.append(_to_search_result(item))
        return normalized

    def get_movie(self, tmdb_id: int) -> dict[str, Any]:
        """Get full TMDB movie details for a movie ID."""
        if not isinstance(tmdb_id, int) or isinstance(tmdb_id, bool) or tmdb_id <= 0:
            raise ValueError("TMDB movie ID must be a positive integer.")
        return self._request(f"/movie/{tmdb_id}")


def _to_search_result(item: dict[str, Any]) -> MovieSearchResult:
    release_date = item.get("release_date") or None
    year = None
    if release_date and len(release_date) >= 4 and release_date[:4].isdigit():
        year = int(release_date[:4])

    vote_average = item.get("vote_average")
    if vote_average is not None:
        try:
            vote_average = float(vote_average)
        except (TypeError, ValueError):
            vote_average = None

    vote_count = item.get("vote_count")
    if vote_count is not None:
        try:
            vote_count = int(vote_count)
        except (TypeError, ValueError):
            vote_count = None

    return MovieSearchResult(
        tmdb_id=int(item["id"]),
        title=str(item.get("title") or ""),
        original_title=str(item.get("original_title") or ""),
        release_date=release_date,
        year=year,
        overview=str(item.get("overview") or ""),
        poster_path=item.get("poster_path"),
        backdrop_path=item.get("backdrop_path"),
        vote_average=vote_average,
        vote_count=vote_count,
    )


def build_image_url(path: str | None, size: str = "w500") -> str | None:
    """Build a TMDB image URL from an image path returned by the API."""
    if not path:
        return None
    return f"{TMDB_IMAGE_BASE_URL}/{size}{path}"
