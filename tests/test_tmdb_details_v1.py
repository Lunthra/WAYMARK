"""WAYMARK M11.4 — TMDB movie-details test.

Reads the TMDB credential from .env and fetches full details for
Interstellar (TMDB ID 157336). Read-only; no WAYMARK, MAL, Serializd,
or Letterboxd data is changed.
"""
from tmdb import TMDBClient, TMDBError

TMDB_ID = 157336

def main():
    print("=" * 48)
    print("WAYMARK — TMDB MOVIE DETAILS TEST")
    print("=" * 48)
    print()
    print(f"Fetching TMDB movie ID: {TMDB_ID}")
    print()

    try:
        client = TMDBClient()
        details = client.get_movie(TMDB_ID)
    except TMDBError as exc:
        print(f"TMDB test failed: {exc}")
        raise SystemExit(1)

    print("TMDB connection + movie details request succeeded. ✓")
    print()
    print(f"TMDB ID:        {details.get('id')}")
    print(f"Title:          {details.get('title')}")
    print(f"Original title: {details.get('original_title')}")
    print(f"Release date:   {details.get('release_date') or 'unknown'}")
    print(f"Runtime:        {details.get('runtime') or 'unknown'} minutes")
    genres = ", ".join(g.get("name", "") for g in details.get("genres", []) if g.get("name"))
    print(f"Genres:         {genres or 'none'}")
    print(f"Status:         {details.get('status') or 'unknown'}")
    print(f"IMDb ID:        {details.get('imdb_id') or 'none'}")
    print(f"Poster path:    {details.get('poster_path') or 'none'}")
    print(f"Backdrop path:  {details.get('backdrop_path') or 'none'}")
    print()
    print("M11.4 TMDB movie-details test passed. ✓")
    print("Read-only test: no tracking data was changed.")

if __name__ == "__main__":
    main()
