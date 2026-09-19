"""Read-only M11.5 test for WAYMARK movie identity."""

from tmdb import TMDBClient
from waymark_movie_identity_v1 import identity_from_tmdb_details


TMDB_ID = 157336
LETTERBOXD_URI = "https://letterboxd.com/film/interstellar/"


def main() -> None:
    print("================================================")
    print("WAYMARK — MOVIE IDENTITY TEST")
    print("================================================")
    print()
    print(f"Fetching TMDB movie details: {TMDB_ID}")

    client = TMDBClient()
    details = client.get_movie(TMDB_ID)
    identity = identity_from_tmdb_details(
        details,
        letterboxd_uri=LETTERBOXD_URI,
    )

    print()
    print("WAYMARK movie identity created successfully. ✓")
    print()
    print(f"Title:             {identity.title}")
    print(f"Year:              {identity.year}")
    print(f"TMDB ID:           {identity.tmdb_id}")
    print(f"IMDb ID:           {identity.imdb_id}")
    print(f"Letterboxd URI:    {identity.letterboxd_uri}")
    print(f"Letterboxd slug:   {identity.letterboxd_slug}")
    print(f"WAYMARK key:       {identity.identity_key}")
    print()

    assert identity.title == "Interstellar"
    assert identity.year == 2014
    assert identity.tmdb_id == 157336
    assert identity.imdb_id == "tt0816692"
    assert identity.letterboxd_slug == "interstellar"
    assert identity.identity_key == "tmdb:157336"

    print("Identity assertions passed. ✓")
    print("Read-only test: no tracking data was changed.")
    print()
    print("M11.5 WAYMARK movie-identity test passed. ✓")


if __name__ == "__main__":
    main()
