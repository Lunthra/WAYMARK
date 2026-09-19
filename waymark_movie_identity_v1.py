"""WAYMARK movie identity layer.

M11.5: Represents a movie using independent service identifiers without
pretending that one service's IDs are equivalent to another service's IDs.

This module is intentionally separate from waymark_core.py and does not
persist data or perform any writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


class MovieIdentityError(ValueError):
    """Raised when movie identity data is invalid or inconsistent."""


@dataclass(frozen=True)
class WaymarkMovieIdentity:
    """Stable identity record for one movie across supported services."""

    title: str
    year: int | None
    tmdb_id: int
    imdb_id: str | None = None
    letterboxd_uri: str | None = None

    @property
    def identity_key(self) -> str:
        """Primary WAYMARK identity key for the movie."""
        return f"tmdb:{self.tmdb_id}"

    @property
    def letterboxd_slug(self) -> str | None:
        """Return the Letterboxd film slug when the URI is a normal film URL."""
        if not self.letterboxd_uri:
            return None
        path = urlparse(self.letterboxd_uri).path.strip("/")
        parts = path.split("/")
        if len(parts) == 2 and parts[0] == "film" and parts[1]:
            return parts[1]
        return None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "title": self.title,
            "year": self.year,
            "tmdb_id": self.tmdb_id,
            "imdb_id": self.imdb_id,
            "letterboxd_uri": self.letterboxd_uri,
        }


def identity_from_tmdb_details(
    details: dict[str, Any],
    *,
    letterboxd_uri: str | None = None,
) -> WaymarkMovieIdentity:
    """Create a WAYMARK movie identity from TMDB movie details.

    Letterboxd is optional because a TMDB movie may not yet have a verified
    Letterboxd mapping. No mapping is guessed from title/year alone.
    """
    if not isinstance(details, dict):
        raise MovieIdentityError("TMDB movie details must be a dictionary.")

    raw_tmdb_id = details.get("id")
    if isinstance(raw_tmdb_id, bool):
        raise MovieIdentityError("TMDB movie ID is invalid.")
    try:
        tmdb_id = int(raw_tmdb_id)
    except (TypeError, ValueError) as exc:
        raise MovieIdentityError("TMDB movie ID is missing or invalid.") from exc
    if tmdb_id <= 0:
        raise MovieIdentityError("TMDB movie ID must be positive.")

    title = str(details.get("title") or "").strip()
    if not title:
        raise MovieIdentityError("TMDB movie title is missing.")

    release_date = str(details.get("release_date") or "").strip()
    year: int | None = None
    if len(release_date) >= 4 and release_date[:4].isdigit():
        year = int(release_date[:4])

    imdb_id = details.get("imdb_id")
    if imdb_id is not None:
        imdb_id = str(imdb_id).strip() or None

    if letterboxd_uri is not None:
        letterboxd_uri = letterboxd_uri.strip()
        if not letterboxd_uri:
            letterboxd_uri = None
        elif not _is_letterboxd_film_uri(letterboxd_uri):
            raise MovieIdentityError(
                "Letterboxd URI must be a Letterboxd film URL such as "
                "https://letterboxd.com/film/interstellar/."
            )

    return WaymarkMovieIdentity(
        title=title,
        year=year,
        tmdb_id=tmdb_id,
        imdb_id=imdb_id,
        letterboxd_uri=letterboxd_uri,
    )


def _is_letterboxd_film_uri(uri: str) -> bool:
    parsed = urlparse(uri)
    if parsed.scheme != "https":
        return False
    if parsed.netloc.lower() not in {"letterboxd.com", "www.letterboxd.com"}:
        return False
    path_parts = parsed.path.strip("/").split("/")
    return len(path_parts) == 2 and path_parts[0] == "film" and bool(path_parts[1])
