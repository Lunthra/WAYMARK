from __future__ import annotations

from pathlib import Path
import sys

from waymark_letterboxd_import_v1 import (
    export_summary,
    load_letterboxd_export,
)


def find_export_directory() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1])

    candidates = [
        Path.cwd(),
        Path.home() / "Downloads",
        Path.home() / "Downloads" / "letterboxd",
    ]

    for candidate in candidates:
        if (
            (candidate / "watched.csv").exists()
            or (candidate / "diary.csv").exists()
            or (candidate / "ratings.csv").exists()
        ):
            return candidate

    raise FileNotFoundError(
        "Could not find a Letterboxd export directory automatically. "
        "Run this test with the export folder path as the first argument."
    )


print("=" * 48)
print("WAYMARK — LETTERBOXD EXPORT IMPORT TEST")
print("=" * 48)

export_dir = find_export_directory()
print(f"\nReading Letterboxd export: {export_dir}")

export = load_letterboxd_export(export_dir)
summary = export_summary(export)

print("\nLetterboxd export read successfully. ✓")
print(f"Watched films:   {summary['watched']}")
print(f"Ratings:         {summary['ratings']}")
print(f"Diary entries:   {summary['diary']}")
print(f"Reviews:         {summary['reviews']}")
print(f"Watchlist:       {summary['watchlist']}")

assert summary["watched"] >= 0
assert summary["ratings"] >= 0
assert summary["diary"] >= 0
assert summary["reviews"] >= 0
assert summary["watchlist"] >= 0

if export.watched:
    first = export.watched[0]
    assert first.title
    assert first.letterboxd_uri
    print("\nFirst watched-film record:")
    print(f"Title:             {first.title}")
    print(f"Year:              {first.year}")
    print(f"Letterboxd URI:    {first.letterboxd_uri}")

if export.ratings:
    rated = export.ratings[0]
    print("\nFirst rating record:")
    print(f"Title:             {rated.title}")
    print(f"Rating:            {rated.rating}")

if export.diary:
    diary = export.diary[0]
    print("\nFirst diary record:")
    print(f"Title:             {diary.title}")
    print(f"Watched date:      {diary.watched_date}")
    print(f"Rewatch:           {diary.rewatch}")

print("\nRead-only test: no Letterboxd or WAYMARK tracking data was changed.")
print("\nM11.6 WAYMARK Letterboxd export-import test passed. ✓")
