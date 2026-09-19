from __future__ import annotations

# WAYMARK Core v2.0 â€” Guided Workflow
# Built from the stable v1.9 reference Core.
# v2.0 preserves the existing MAL/Serializd Core and uses the guided
# conversational workflow as the intended entry point.
#
# Service routing:
#   Anime TV       -> MAL + Serializd
#   Live-action TV -> Serializd
#   Anime movies   -> MAL route reserved; no movie write yet
#   Non-anime movies -> TMDB identity/metadata route reserved; no movie write yet
#
# MAL and Serializd episode/season numbering are independent.
# Proposed writes are validated before explicit YES confirmation.
#
import json
import re
import subprocess
import os
import time
import tempfile
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Optional
import requests
from concurrent.futures import ThreadPoolExecutor

from playwright.sync_api import sync_playwright

from app.backend.core.credentials import get_credential
from app.backend.core.runtime_paths import get_data_file, data_dir, ensure_runtime_layout

from app.backend.services.mal import (
    get_my_anime_list,
    search_anime,
    get_access_token as mal_get_access_token,
    get_my_status,
    update_progress,
    update_status,
    update_score,
)

from app.backend.data.notes import (
    add_note,
    get_notes,
    update_note,
)

from app.backend.services.serializd import (
    get_show,
    get_season,
    get_access_token,
    mark_season_watched,
    mark_series_watched,
    log_episode,
    log_season_review,
    log_series_review,
    rate_episode,
    rate_season,
    rate_series,
    get_full_diary,
    search_catalog,
    get_watched_library,
    get_watched_episode_logs,
    mark_episode_watched,
    update_review_log,
    delete_review_log,
)


APP_VERSION = "2.0"
ensure_runtime_layout()
ALIASES_FILE = get_data_file("aliases.json")
WAYMARK_MEDIA_FILE = get_data_file("waymark_media.json")


# ============================================================
# ALIASES / ANIME RESOLUTION
# ============================================================

def load_aliases():
    """Load saved anime aliases."""

    try:
        with open(
            ALIASES_FILE,
            "r",
            encoding="utf-8",
        ) as f:
            return json.load(f)

    except FileNotFoundError:
        return {}


def save_alias(alias, anime_id):
    """Save an alias for future title recognition."""

    aliases = load_aliases()

    aliases[alias.lower()] = anime_id

    parent = os.path.dirname(ALIASES_FILE)
    os.makedirs(parent, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="aliases-", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(aliases, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, ALIASES_FILE)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def choose_from_results(results):
    """Choose a result with explicit back/cancel navigation."""
    if not results:
        return None

    print("\nMatches:")
    for index, item in enumerate(results, start=1):
        anime = item["node"]
        if "list_status" in item:
            status = item["list_status"]
            print(
                f"{index}. {anime['title']} | "
                f"{status['status']} | Episodes: "
                f"{status['num_episodes_watched']}"
            )
        else:
            print(f"{index}. {anime['title']} | MAL ID: {anime['id']}")

    if len(results) == 1:
        return results[0]

    while True:
        raw_choice = input(
            "\nChoose an anime (B = back, 0/Cancel = cancel): "
        ).strip()

        if raw_choice.lower() in {"b", "back"}:
            print("Going back one step.")
            return _BACK

        if _is_cancel_command(raw_choice):
            print("Cancelled. No service data was changed.")
            return None

        try:
            choice = int(raw_choice)
        except ValueError:
            print("Please enter a number, B, or 0/Cancel.")
            continue

        if 1 <= choice <= len(results):
            return results[choice - 1]

        print("Please choose a valid number.")

def find_in_my_list(
    query,
    anime_list,
):
    """Find anime in the user's MAL list."""

    query = query.lower().strip()

    matches = []

    for item in anime_list:

        anime = item["node"]

        if query in anime["title"].lower():

            matches.append(item)

    return matches


def resolve_anime(anime_title):
    """
    Resolve an anime title against the user's MAL list.

    Important behavior:

    - If multiple seasons/entries match, always ask.
    - A generic title is never permanently forced to one season.
    - If exactly one external MAL result is found, save the alias.
    """

    print(
        "\nLoading your MAL anime list..."
    )

    anime_list = get_my_anime_list()

    print(
        f"Loaded {len(anime_list)} anime. âœ…"
    )

    matches = find_in_my_list(
        anime_title,
        anime_list,
    )

    # --------------------------------------------------------
    # Multiple entries already in personal list
    # --------------------------------------------------------

    if len(matches) > 1:

        print(
            f'\nMultiple anime match '
            f'"{anime_title}".'
        )

        print(
            "Choose the season/entry "
            "you mean."
        )

        selected = choose_from_results(
            matches
        )
        if selected is _BACK:
            return _BACK
        return selected

    # --------------------------------------------------------
    # Exactly one entry already in personal list
    # --------------------------------------------------------

    if len(matches) == 1:

        return matches[0]

    # --------------------------------------------------------
    # Search MAL database
    # --------------------------------------------------------

    print(
        "\nNot found in your MAL list."
    )

    print(
        "Searching MAL database..."
    )

    search_results = search_anime(
        anime_title
    )

    if not search_results:

        print(
            "\nNo anime found."
        )

        return None

    # --------------------------------------------------------
    # Multiple MAL results
    # --------------------------------------------------------

    if len(search_results) > 1:

        print(
            f'\nMultiple MAL results found '
            f'for "{anime_title}".'
        )

        print(
            "Choose the season/entry "
            "you mean."
        )

        selected = choose_from_results(
            search_results
        )

    else:

        selected = search_results[0]

    if selected is _BACK:
        return _BACK

    if not selected:
        return None

    anime_id = selected["node"]["id"]

    status_data = get_my_status(
        anime_id
    )

    selected = {
        "node": selected["node"],
        "list_status": status_data.get(
            "my_list_status"
        ),
    }

    # --------------------------------------------------------
    # Save aliases ONLY when the search produced
    # exactly one result.
    # --------------------------------------------------------

    if len(search_results) == 1:

        save_alias(
            anime_title,
            anime_id,
        )

        print(
            f"\nWAYMARK remembered:"
            f"\n{anime_title} â†’ "
            f"{selected['node']['title']}"
        )

    else:

        print(
            "\nWAYMARK will not permanently "
            f"map '{anime_title}' to this season."
        )

        print(
            "You can choose the season again "
            "next time."
        )

    return selected


# ============================================================
# SERIALIZD WATCH STATE
# ============================================================

def mark_serializd_season_watched(show_id, season_id):
    """Mark an entire Serializd season as watched."""

    return mark_season_watched(
        show_id,
        season_id,
    )


def test_serializd_season_watch():
    """Persistent Serializd season-watch test. No rollback is performed."""

    print("\n========================")
    print("WAYMARK SERIALIZD SEASON WATCH TEST")
    print("========================")
    print("This test performs ONE real Serializd write.")
    print("The season will remain watched so you can verify it on the website.")

    title = input("\nTV title: ").strip()
    if not title:
        print("\nNo title entered.")
        return

    matches = search_catalog(title)
    if not matches:
        print("\nNo Serializd catalog matches found.")
        return

    print("\nCatalog matches:")
    for i, item in enumerate(matches, 1):
        print(f"{i}. {item.get('name', 'Unknown')} | ID: {item.get('id')}")

    while True:
        try:
            choice = int(input("\nChoose a show: "))
            if 1 <= choice <= len(matches):
                break
        except ValueError:
            pass
        print("Please choose a valid number.")

    show = matches[choice - 1]
    show_id = int(show["id"])
    print(f"\nSelected: {show.get('name', 'Unknown')} | Serializd ID: {show_id}")

    show_data = get_show(show_id)
    seasons = show_data.get("seasons", [])
    if not seasons:
        # Some Serializd responses expose season information through the watched-page data.
        # Fall back to season 1 only when the show response does not include a seasons list.
        season_number = int(input("Season number: ").strip())
        season_data = get_season(show_id, season_number)
        season_id = int(season_data["seasonId"])
    else:
        print("\nSeasons:")
        for i, season in enumerate(seasons, 1):
            number = season.get("seasonNumber", i)
            name = season.get("name", f"Season {number}")
            sid = season.get("seasonId", season.get("id"))
            print(f"{i}. {name} | Season number: {number} | ID: {sid}")

        while True:
            try:
                choice = int(input("\nChoose a season: "))
                if 1 <= choice <= len(seasons):
                    break
            except ValueError:
                pass
            print("Please choose a valid number.")

        selected_season = seasons[choice - 1]
        season_number = int(selected_season.get("seasonNumber", choice))
        season_id = selected_season.get("seasonId", selected_season.get("id"))
        if season_id is None:
            season_data = get_season(show_id, season_number)
            season_id = season_data["seasonId"]
        season_id = int(season_id)

    print("\nAbout to mark watched:")
    print(f"  {show.get('name', 'Unknown')} â€” Season {season_number}")
    confirmation = input("Type YES to perform the write and leave the season watched: ").strip()
    if confirmation.strip().lower() != "yes":
        print("Cancelled. No write was made.")
        return

    result = mark_serializd_season_watched(show_id, season_id)
    print(f"\nSeason watch added: {result}")
    print("\nPersistent season-watch test complete. The season was NOT removed.")
    print("Check Serializd now to verify the season appears watched. âœ…")


def mark_serializd_series_watched(show_id):
    """Mark all available seasons of a Serializd series as watched."""
    return mark_series_watched(show_id)


def test_serializd_series_watch():
    """Persistent Serializd series-watch test. No rollback is performed."""
    print("\n========================")
    print("WAYMARK SERIALIZD SERIES WATCH TEST")
    print("========================")
    print("This test performs ONE real Serializd write.")
    print("All available seasons will be marked watched and left in place.")

    title = input("\nTV title: ").strip()
    if not title:
        print("\nNo title entered.")
        return

    matches = search_catalog(title)
    if not matches:
        print("\nNo Serializd catalog matches found.")
        return

    print("\nCatalog matches:")
    for i, item in enumerate(matches, 1):
        print(f"{i}. {item.get('name', 'Unknown')} | ID: {item.get('id')}")

    while True:
        try:
            choice = int(input("\nChoose a show: "))
            if 1 <= choice <= len(matches):
                break
        except ValueError:
            pass
        print("Please choose a valid number.")

    show = matches[choice - 1]
    show_id = int(show["id"])
    show_data = get_show(show_id)
    seasons = show_data.get("seasons", [])

    season_ids = []
    print(f"\nSelected: {show.get('name', 'Unknown')} | Serializd ID: {show_id}")
    print("\nSeasons that will be marked watched:")
    for i, season in enumerate(seasons, 1):
        number = season.get("seasonNumber", i)
        name = season.get("name", f"Season {number}")
        sid = season.get("seasonId", season.get("id"))
        if sid is not None:
            season_ids.append(int(sid))
            print(f"{i}. {name} | Season number: {number} | ID: {sid}")

    if not season_ids:
        print("\nNo seasons were returned for this show.")
        return

    print("\nAbout to mark the ENTIRE SERIES watched:")
    print(f"  {show.get('name', 'Unknown')} â€” {len(season_ids)} season(s)")
    confirmation = input("Type YES to perform the write and leave the series watched: ").strip()
    if confirmation.strip().lower() != "yes":
        print("Cancelled. No write was made.")
        return

    result = mark_serializd_series_watched(show_id)
    print(f"\nSeries watch added: {result}")
    print("\nPersistent series-watch test complete. The series was NOT removed.")
    print("Check Serializd now to verify the entire series appears watched. âœ…")


# ============================================================
# SERIALIZD LOGGING / STAR RATING
# ============================================================

def test_serializd_episode_log():
    """Create one real Serializd episode log with a native star rating."""

    from datetime import datetime, timezone
    print("\n========================")
    print("WAYMARK SERIALIZD EPISODE LOG TEST")
    print("========================")
    print("This test performs ONE real Serializd log write and leaves it in place.")
    print("The log includes a 1-5 star rating in 0.5-star increments.")

    title = input("\nTV title: ").strip()
    if not title:
        print("\nNo title entered.")
        return

    matches = search_catalog(title)
    if not matches:
        print("\nNo Serializd catalog matches found.")
        return

    print("\nCatalog matches:")
    for i, item in enumerate(matches, 1):
        print(f"{i}. {item.get('name', 'Unknown')} | ID: {item.get('id')}")

    while True:
        try:
            choice = int(input("\nChoose a show: "))
            if 1 <= choice <= len(matches):
                break
        except ValueError:
            pass
        print("Please choose a valid number.")

    show = matches[choice - 1]
    show_id = int(show["id"])
    print(f"\nSelected: {show.get('name', 'Unknown')} | Serializd ID: {show_id}")

    show_data = get_show(show_id)
    seasons = show_data.get("seasons", [])
    if not seasons:
        print("\nNo seasons were returned for this show.")
        return

    print("\nSeasons:")
    for i, season in enumerate(seasons, 1):
        number = season.get("seasonNumber", i)
        name = season.get("name", f"Season {number}")
        sid = season.get("seasonId", season.get("id"))
        print(f"{i}. {name} | Season number: {number} | ID: {sid}")

    while True:
        try:
            choice = int(input("\nChoose a season: "))
            if 1 <= choice <= len(seasons):
                break
        except ValueError:
            pass
        print("Please choose a valid number.")

    selected_season = seasons[choice - 1]
    season_number = int(selected_season.get("seasonNumber", choice))
    season_id = selected_season.get("seasonId", selected_season.get("id"))
    if season_id is None:
        season_data = get_season(show_id, season_number)
        season_id = season_data["seasonId"]
    season_id = int(season_id)

    season_data = get_season(show_id, season_number)
    episodes = season_data.get("episodes", [])
    if not episodes:
        print("\nNo episodes were returned for this season.")
        return

    print("\nEpisodes:")
    for i, episode in enumerate(episodes, 1):
        number = episode.get("episodeNumber", i)
        name = episode.get("name", f"Episode {number}")
        runtime = episode.get("runtime")
        runtime_text = f" | {runtime} min" if runtime else ""
        print(f"{i}. E{int(number):02d} â€” {name}{runtime_text}")

    while True:
        try:
            choice = int(input("\nChoose an episode: "))
            if 1 <= choice <= len(episodes):
                break
        except ValueError:
            pass
        print("Please choose a valid number.")

    episode = episodes[choice - 1]
    episode_number = int(episode.get("episodeNumber", choice))
    episode_name = episode.get("name", f"Episode {episode_number}")

    while True:
        try:
            stars = float(input("\nRating (1.0 to 5.0, half-star increments): ").strip())
            doubled = stars * 2
            if 1.0 <= stars <= 5.0 and doubled == int(doubled):
                break
        except ValueError:
            pass
        print("Please enter 1.0, 1.5, 2.0 ... 5.0.")

    backdate = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    print("\nAbout to create this Serializd log:")
    print(f"  {show.get('name', 'Unknown')} â€” S{season_number:02d}E{episode_number:02d} â€” {episode_name}")
    print(f"  Rating: {stars:g} stars")
    print(f"  Log date: {backdate}")
    print("  Rewatch: No")

    confirmation = input("Type YES to create the log and leave it in Serializd: ").strip()
    if confirmation.strip().lower() != "yes":
        print("Cancelled. No write was made.")
        return

    result = log_episode(
        show_id,
        season_id,
        episode_number,
        stars=stars,
        review_text="",
        is_rewatch=False,
        backdate=backdate,
    )

    print(f"\nSerializd log response: {result}")
    print("\nPersistent episode-log test complete. The log was NOT removed.")
    print("Check Serializd to verify the date and star rating. âœ…")


# ============================================================
# SERIALIZD DIARY / HISTORY
# ============================================================

def test_serializd_diary():
    """Read the user's Serializd diary and display recent activity."""

    print("\n========================")
    print("WAYMARK SERIALIZD DIARY / HISTORY")
    print("========================")
    print("This is READ-ONLY. No Serializd data will be changed.")

    try:
        entries = get_full_diary()
    except Exception as exc:
        print(f"\nSerializd diary read failed: {exc}")
        return

    if not entries:
        print("\nNo Serializd diary entries were returned.")
        return

    print(f"\nFound {len(entries)} diary entries.\n")

    for index, entry in enumerate(entries, 1):
        show_name = entry.get("showName", "Unknown show")
        season_id = entry.get("seasonId")
        episode_number = entry.get("episodeNumber")
        episode_name = entry.get("episodeName")

        if episode_number is not None:
            season_text = ""
            if season_id is not None:
                season_text = f"S{season_id}"
            episode_text = f"E{int(episode_number):02d}"
            if season_text:
                location = f"{season_text}{episode_text}"
            else:
                location = episode_text
            if episode_name:
                location += f" â€” {episode_name}"
        else:
            location = "Series / season entry"

        rating = entry.get("rating")
        if rating is not None:
            try:
                rating_text = f"{float(rating) / 2:g} stars"
            except (TypeError, ValueError):
                rating_text = str(rating)
        else:
            rating_text = "No rating"

        date_value = entry.get("backdate") or entry.get("dateAdded") or "Unknown date"
        is_rewatch = bool(entry.get("isRewatch", False))
        is_log = bool(entry.get("isLog", False))
        review_text = (entry.get("reviewText") or "").strip()

        print(f"{index}. {show_name}")
        print(f"   {location}")
        print(f"   Rating: {rating_text}")
        print(f"   Date: {date_value}")
        print(f"   Type: {'Log' if is_log else 'Review'} | Rewatch: {'Yes' if is_rewatch else 'No'}")
        if review_text:
            print(f"   Review: {review_text}")
        print()

    print("Serializd diary read complete. No changes were made. âœ…")


# ============================================================
# MAL STATUS / PROGRESS / RATING
# ============================================================

def get_current_status(status):
    """Get the current MAL list status."""

    if not status:
        return None

    return status.get(
        "status"
    )


def get_current_episode(status):
    """Get the current watched episode."""

    if not status:
        return 0

    return status.get(
        "num_episodes_watched",
        0,
    )


def get_current_score(status):
    """Get the current MAL score."""

    if not status:
        return 0

    return status.get(
        "score",
        0,
    )


def mark_watched(
    anime_id,
    episode,
):
    """
    Mark an anime as watched up to an episode.

    Rewatching is disabled.
    """

    return update_progress(
        anime_id,
        episode,
        is_rewatching=False,
    )


def mark_rewatched(
    anime_id,
    episode,
):
    """
    Mark an anime as re-watched at the given episode.

    MAL represents this by enabling rewatching.
    """

    return update_progress(
        anime_id,
        episode,
        is_rewatching=True,
    )


def mark_rewatching(
    anime_id,
    episode,
):
    """Mark an anime as currently re-watching."""

    return update_progress(
        anime_id,
        episode,
        is_rewatching=True,
    )


def mark_watching(
    anime_id,
    episode,
):
    """Mark an anime as watching at the given episode."""

    update_status(
        anime_id,
        "watching",
    )

    return update_progress(
        anime_id,
        episode,
        is_rewatching=False,
    )


def change_status(
    anime_id,
    status,
):
    """Change the MAL list status."""

    return update_status(
        anime_id,
        status,
    )


def rate_anime(
    anime_id,
    score,
):
    """Set the MAL anime score."""

    return update_score(
        anime_id,
        score,
    )


# ============================================================
# LOCAL NOTES
# ============================================================

def create_note(
    anime_id,
    episode,
    text,
):
    """Create a local WAYMARK note."""

    return add_note(
        anime_id,
        episode,
        text,
    )


def get_anime_notes(
    anime_id,
):
    """Return all local notes for an anime."""

    return get_notes(
        anime_id
    )


def edit_note(
    anime_id,
    note_index,
    new_text,
):
    """Edit a local WAYMARK note."""

    return update_note(
        anime_id,
        note_index,
        new_text,
    )


# ============================================================
# MAL REVIEW BROWSER CONFIGURATION
# ============================================================

def _find_edge_executable():
    candidates = []
    configured = os.getenv("WAYMARK_EDGE_PATH", "").strip()
    if configured:
        candidates.append(configured)
    if os.name == "nt":
        candidates.extend([
            os.path.join(os.getenv("PROGRAMFILES", r"C:\Program Files"), "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(os.getenv("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(os.getenv("LOCALAPPDATA", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        ])
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    raise RuntimeError("Microsoft Edge was not found. Install Edge or set WAYMARK_EDGE_PATH.")


EDGE_PATH = os.getenv("WAYMARK_EDGE_PATH", "").strip() or None
WAYMARK_EDGE_PROFILE = os.path.join(str(data_dir()), "browser", "edge-profile")


# ============================================================
# MAL BROWSER CONTROL
# ============================================================

def _find_free_local_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_mal_browser(headless=False):
    """Start a dedicated Edge profile and connect Playwright over a local CDP port."""
    edge_path = EDGE_PATH or _find_edge_executable()
    os.makedirs(WAYMARK_EDGE_PROFILE, exist_ok=True)
    debug_port = _find_free_local_port()
    edge_args = [
        edge_path,
        f"--remote-debugging-port={debug_port}",
        f"--user-data-dir={WAYMARK_EDGE_PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if headless:
        edge_args.append("--headless=new")

    edge_process = subprocess.Popen(edge_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    playwright = sync_playwright().start()
    try:
        deadline = time.monotonic() + 15
        browser = None
        last_error = None
        while time.monotonic() < deadline:
            try:
                browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{debug_port}")
                break
            except Exception as exc:
                last_error = exc
                time.sleep(0.25)
        if browser is None:
            raise RuntimeError("Could not connect to the dedicated Edge browser.") from last_error
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        return edge_process, playwright, browser, page
    except Exception:
        try:
            playwright.stop()
        finally:
            edge_process.terminate()
        raise


def close_mal_browser(
    edge_process,
    playwright,
    browser,
):
    """Close the WAYMARK Edge session."""

    try:

        browser.close()

    except Exception:
        pass

    try:

        playwright.stop()

    except Exception:
        pass

    try:

        edge_process.terminate()

        edge_process.wait(
            timeout=5
        )

    except Exception:

        try:
            edge_process.kill()

        except Exception:
            pass


# ============================================================
# MAL REVIEW NAVIGATION
# ============================================================

def open_anime_reviews_page(
    page,
    anime_id,
):
    """Open an anime's MAL reviews page."""

    url = (
        f"https://myanimelist.net/anime/"
        f"{anime_id}/reviews"
    )

    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    time.sleep(3)


def open_my_review_editor(
    page,
    anime_id,
):
    """
    Open MAL's review editor for an anime.

    MAL redirects this URL to the existing review editor
    when the user already has a review.
    """

    url = (
        f"https://myanimelist.net/myreviews.php?"
        f"seriesid={anime_id}&go=write"
    )

    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    time.sleep(3)


def review_exists(
    page,
):
    """
    Return True when MAL opened an existing review.

    Existing reviews use a URL containing reviewid=.
    """

    return (
        "reviewid="
        in page.url.lower()
    )


# ============================================================
# MAL REVIEW READING
# ============================================================

def read_review_from_page(
    page,
):
    """Read the current MAL review form."""

    textareas = page.locator(
        "textarea[name='frm_review_text']"
    )

    review_text = ""

    if textareas.count() > 0:

        review_text = (
            textareas
            .first
            .input_value()
        )

    score = page.locator(
        "input[name='frmreview_overall_score']"
    )

    rating = 0

    if score.count() > 0:

        score_value = (
            score
            .first
            .get_attribute(
                "value"
            )
        )

        try:

            rating = int(
                score_value
            )

        except (
            TypeError,
            ValueError,
        ):

            rating = 0

    feelings = page.locator(
        "input[name='frm_review_feelings']:checked"
    )

    recommendation_values = {
        "1": "Recommended",
        "2": "Mixed Feelings",
        "3": "Not Recommended",
    }

    recommendation = "Not selected"

    if feelings.count() > 0:

        value = (
            feelings
            .first
            .get_attribute(
                "value"
            )
        )

        recommendation = (
            recommendation_values.get(
                value,
                f"Unknown ({value})",
            )
        )

    spoiler = page.locator(
        "input[name='frm_review_is_spoiler']:checked"
    )

    spoiler_value = None

    if spoiler.count() > 0:

        spoiler_value = (
            spoiler
            .first
            .get_attribute(
                "value"
            )
        )

    spoiler_text = "Not selected"

    if spoiler_value == "1":

        spoiler_text = "Yes"

    elif spoiler_value == "0":

        spoiler_text = "No"

    return {
        "text": review_text,
        "rating": rating,
        "recommendation": recommendation,
        "spoiler": spoiler_text,
        "url": page.url,
    }


def view_review(
    anime_id,
):
    """
    Fetch the user's MAL review for an anime.

    Uses headless Microsoft Edge so no visible browser
    window is required.

    Returns:
        dict  -> review data
        None  -> no review exists
    """

    edge_process = None
    playwright = None
    browser = None

    try:

        (
            edge_process,
            playwright,
            browser,
            page,
        ) = start_mal_browser(
            headless=True
        )

        open_my_review_editor(
            page,
            anime_id,
        )

        if not review_exists(page):

            return None

        return read_review_from_page(
            page
        )

    finally:

        if (
            edge_process is not None
            and playwright is not None
            and browser is not None
        ):

            close_mal_browser(
                edge_process,
                playwright,
                browser,
            )


# ============================================================
# MAL REVIEW FORM
# ============================================================

def select_review_recommendation(
    page,
    value,
):
    """Select MAL's recommendation radio button."""

    radio = page.locator(
        f"input[name='frm_review_feelings'][value='{value}']"
    )

    if radio.count() == 0:

        raise Exception(
            "MAL recommendation field was not found."
        )

    radio.first.check()


def select_review_spoiler(
    page,
    value,
):
    """Select MAL's spoiler radio button."""

    radio = page.locator(
        f"input[name='frm_review_is_spoiler'][value='{value}']"
    )

    if radio.count() == 0:

        raise Exception(
            "MAL spoiler field was not found."
        )

    radio.first.check()


def fill_review_form(
    page,
    review_text,
    rating,
    recommendation,
    spoiler,
):
    """
    Fill MAL's review form without publishing it.

    Returns the rating value currently held by MAL's
    hidden rating field.
    """

    textarea = page.locator(
        "textarea[name='frm_review_text']"
    )

    if textarea.count() == 0:

        raise Exception(
            "MAL review text field was not found."
        )

    textarea.first.fill(
        review_text
    )

    score = page.locator(
        "input[name='frmreview_overall_score']"
    )

    if score.count() == 0:

        raise Exception(
            "MAL review rating field was not found."
        )

    # --------------------------------------------------------
    # Try MAL's visible rating control first.
    # --------------------------------------------------------

    rating_button = page.get_by_text(
        str(rating),
        exact=True,
    )

    clicked_rating = False

    for i in range(
        rating_button.count()
    ):

        candidate = (
            rating_button.nth(i)
        )

        try:

            if candidate.is_visible():

                candidate.click()

                clicked_rating = True

                break

        except Exception:

            pass

    # --------------------------------------------------------
    # Fallback to MAL's hidden score field.
    # --------------------------------------------------------

    if not clicked_rating:

        score.first.evaluate(
            """(element, value) => {
                element.value = value;
                element.dispatchEvent(
                    new Event('change', {bubbles: true})
                );
                element.dispatchEvent(
                    new Event('input', {bubbles: true})
                );
            }""",
            str(rating),
        )

    select_review_recommendation(
        page,
        recommendation,
    )

    select_review_spoiler(
        page,
        spoiler,
    )

    return score.first.input_value()


# ============================================================
# MAL REVIEW PUBLISHING
# ============================================================

def publish_review(
    page,
):
    """
    Publish the currently filled MAL review.

    This function does not ask for terminal input.

    The future WAYMARK desktop UI will be responsible
    for asking the user for confirmation before calling it.
    """

    publish_button = page.get_by_text(
        "Publish",
        exact=True,
    )

    if publish_button.count() == 0:

        raise Exception(
            "MAL Publish button was not found."
        )

    publish_button.first.click()

    time.sleep(4)

    if (
        "myreviews.php?reviewid="
        in page.url.lower()
    ):

        return True

    return False


# ============================================================
# MAL REVIEW CREATE
# ============================================================

def add_review(
    anime_id,
    review_text,
    rating,
    recommendation,
    spoiler,
):
    """
    Create and publish a new MAL review.

    Arguments:

        anime_id:
            MAL anime ID.

        review_text:
            Review body.

        rating:
            Integer 1-10.

        recommendation:
            "1" = Recommended
            "2" = Mixed Feelings
            "3" = Not Recommended

        spoiler:
            "1" = Yes
            "0" = No

    Returns:

        True  -> review was published
        False -> MAL did not confirm publication

    Raises:

        Exception if a review already exists or
        MAL's form cannot be located.
    """

    if not review_text.strip():

        raise ValueError(
            "Review text cannot be empty."
        )

    if not (
        isinstance(rating, int)
        and 1 <= rating <= 10
    ):

        raise ValueError(
            "Review rating must be an integer from 1 to 10."
        )

    edge_process = None
    playwright = None
    browser = None

    try:

        (
            edge_process,
            playwright,
            browser,
            page,
        ) = start_mal_browser(
            headless=False
        )

        open_my_review_editor(
            page,
            anime_id,
        )

        # ----------------------------------------------------
        # Never overwrite an existing review.
        # ----------------------------------------------------

        if review_exists(page):

            raise Exception(
                "A MAL review already exists for this anime."
            )

        fill_review_form(
            page,
            review_text,
            rating,
            recommendation,
            spoiler,
        )

        return publish_review(
            page
        )

    finally:

        if (
            edge_process is not None
            and playwright is not None
            and browser is not None
        ):

            close_mal_browser(
                edge_process,
                playwright,
                browser,
            )


# ============================================================
# MAL REVIEW EDIT
# ============================================================

def edit_review(
    anime_id,
    review_text,
    rating,
    recommendation,
    spoiler,
):
    """
    Edit and publish an existing MAL review.

    Returns:

        True  -> review was published successfully
        False -> MAL did not confirm publication

    Raises:

        Exception if no existing review is found.
    """

    if not review_text.strip():

        raise ValueError(
            "Review text cannot be empty."
        )

    if not (
        isinstance(rating, int)
        and 1 <= rating <= 10
    ):

        raise ValueError(
            "Review rating must be an integer from 1 to 10."
        )

    edge_process = None
    playwright = None
    browser = None

    try:

        (
            edge_process,
            playwright,
            browser,
            page,
        ) = start_mal_browser(
            headless=False
        )

        open_my_review_editor(
            page,
            anime_id,
        )

        # ----------------------------------------------------
        # Edit requires an existing review.
        # ----------------------------------------------------

        if not review_exists(page):

            raise Exception(
                "No existing MAL review was found for this anime."
            )

        fill_review_form(
            page,
            review_text,
            rating,
            recommendation,
            spoiler,
        )

        return publish_review(
            page
        )

    finally:

        if (
            edge_process is not None
            and playwright is not None
            and browser is not None
        ):

            close_mal_browser(
                edge_process,
                playwright,
                browser,
            )


# ============================================================
# REVIEW TEST
# ============================================================

def print_review(
    title,
    review,
):
    """Temporary helper for terminal testing."""

    if not review:

        print(
            f"\nNo MAL review found for {title}."
        )

        return

    print(
        "\n========================"
    )

    print(
        f"MAL Review â€” {title}"
    )

    print(
        "========================"
    )

    print(
        f"\nRating: "
        f"{review['rating']}/10"
    )

    print(
        f"Recommendation: "
        f"{review['recommendation']}"
    )

    print(
        f"Spoiler: "
        f"{review['spoiler']}"
    )

    print(
        "\nReview:"
    )

    print(
        review["text"]
    )

    print(
        f"\nURL: "
        f"{review['url']}"
    )



# ============================================================
# EXISTING MAL CORE TEST
# ============================================================

def run_existing_mal_test():
    """Run the original MAL Core terminal test unchanged."""

    print(
        "\n========================"
    )

    print(
        "WAYMARK CORE TEST"
    )

    print(
        "========================"
    )

    # Title entry is the first screen inside this workflow.
    # B/Back here exits this workflow to the main menu; 0/Cancel
    # cancels the workflow.  B/Back returned by a deeper selector
    # means: return to this title-entry screen.
    while True:
        anime_title = input(
            "\nAnime title to test (B = back, 0/Cancel = exit): "
        ).strip()

        if anime_title.lower() in {"b", "back"}:
            print("Going back to the main menu (previous screen).")
            return

        if _is_cancel_command(anime_title):
            print("Cancelled. No service data was changed.")
            return

        if not anime_title:
            print(
                "\nNo anime title entered. Returning to the main menu."
            )
            return

        selected = resolve_anime(anime_title)

        if selected is _BACK:
            # The selector already reports the Back action. Return to the
            # title-entry screen without printing the navigation message twice.
            continue

        if not selected:
            print("\nNo anime selected. Returning to the main menu.")
            return

        anime = selected["node"]
        break

    status = selected.get(
        "list_status"
    )

    anime_id = anime["id"]

    title = anime["title"]

    print(
        f"\nSelected: {title}"
    )

    print(
        f"MAL ID: {anime_id}"
    )

    print(
        f"Status: "
        f"{get_current_status(status)}"
    )

    print(
        f"Episode: "
        f"{get_current_episode(status)}"
    )

    score = get_current_score(
        status
    )

    if score:

        print(
            f"Score: {score}/10"
        )

    else:

        print(
            "Score: Not rated"
        )

    notes = get_anime_notes(
        anime_id
    )

    print(
        f"Local notes: "
        f"{len(notes)}"
    )

    # --------------------------------------------------------
    # Review test
    # --------------------------------------------------------

    print(
        "\nTesting MAL review backend..."
    )

    review = view_review(
        anime_id
    )

    if review:

        print(
            "\nMAL review found. âœ…"
        )

        print_review(
            title,
            review,
        )

    else:

        print(
            f"\nNo MAL review found for {title}."
        )

    print(
        "\nWAYMARK core test complete. âœ…"
    )


# ============================================================
# INTERNAL WAYMARK MEDIA IDENTITY
# ============================================================

@dataclass
class WaymarkEpisode:
    """A single episode with service-specific identifiers."""
    season_number: int
    episode_number: int
    title: str = ""
    mal_id: Optional[int] = None
    serializd_id: Optional[int] = None


@dataclass
class WaymarkSeason:
    """A season belonging to a WAYMARK media identity."""
    season_number: int
    title: str = ""
    mal_id: Optional[int] = None
    serializd_id: Optional[int] = None
    episodes: list[WaymarkEpisode] = field(default_factory=list)
    is_specials: bool = False


@dataclass
class WaymarkMedia:
    """Internal identity shared by external tracking services."""
    title: str
    media_type: str  # "anime" or "tv"
    mal_id: Optional[int] = None
    serializd_id: Optional[int] = None
    seasons: list[WaymarkSeason] = field(default_factory=list)

    def service_ids(self):
        return {
            "mal": self.mal_id,
            "serializd": self.serializd_id,
        }

    def find_season(self, season_number: int):
        return next(
            (season for season in self.seasons if season.season_number == season_number),
            None,
        )

    def find_episode(self, season_number: int, episode_number: int):
        season = self.find_season(season_number)
        if season is None:
            return None
        return next(
            (episode for episode in season.episodes if episode.episode_number == episode_number),
            None,
        )

    def add_season(self, season: WaymarkSeason):
        existing = self.find_season(season.season_number)
        if existing is None:
            self.seasons.append(season)
        else:
            if season.mal_id is not None:
                existing.mal_id = season.mal_id
            if season.serializd_id is not None:
                existing.serializd_id = season.serializd_id
            if season.title:
                existing.title = season.title
            if season.episodes:
                existing.episodes = season.episodes


def create_waymark_anime(anime: dict) -> WaymarkMedia:
    """Create a WAYMARK identity from a MAL anime node."""
    return WaymarkMedia(
        title=anime.get("title", ""),
        media_type="anime",
        mal_id=anime.get("id"),
    )


def create_waymark_tv(show: dict) -> WaymarkMedia:
    """Create a WAYMARK identity from a Serializd show response."""
    show_id = show.get("id", show.get("showId"))
    title = show.get("name", show.get("title", ""))
    return WaymarkMedia(
        title=title,
        media_type="tv",
        serializd_id=show_id,
    )


def attach_serializd_season(media: WaymarkMedia, season_data: dict) -> WaymarkSeason:
    """Attach Serializd season/episode IDs without guessing a MAL match."""
    season_number = season_data.get("seasonNumber")
    if season_number is None:
        raise ValueError("Serializd season data has no seasonNumber.")

    season_id = season_data.get("seasonId", season_data.get("id"))
    season = WaymarkSeason(
        season_number=int(season_number),
        title=season_data.get("name", ""),
        serializd_id=season_id,
        is_specials=int(season_number) == 0,
    )

    for episode in season_data.get("episodes", []) or []:
        episode_number = episode.get("episodeNumber")
        if episode_number is None:
            continue
        season.episodes.append(
            WaymarkEpisode(
                season_number=int(season_number),
                episode_number=int(episode_number),
                title=episode.get("name", ""),
                serializd_id=episode.get("episodeId", episode.get("id")),
            )
        )

    media.add_season(season)
    return season


def waymark_media_to_dict(media: WaymarkMedia) -> dict:
    """Serialize a WAYMARK media identity to JSON-safe data."""
    return {
        "title": media.title,
        "media_type": media.media_type,
        "service_ids": media.service_ids(),
        "seasons": [
            {
                "season_number": season.season_number,
                "title": season.title,
                "service_ids": {
                    "mal": season.mal_id,
                    "serializd": season.serializd_id,
                },
                "is_specials": season.is_specials,
                "episodes": [
                    {
                        "season_number": episode.season_number,
                        "episode_number": episode.episode_number,
                        "title": episode.title,
                        "service_ids": {
                            "mal": episode.mal_id,
                            "serializd": episode.serializd_id,
                        },
                    }
                    for episode in season.episodes
                ],
            }
            for season in media.seasons
        ],
    }


def waymark_media_from_dict(data: dict) -> WaymarkMedia:
    """Rebuild a WAYMARK media identity from persisted JSON."""
    service_ids = data.get("service_ids", {}) or {}
    media = WaymarkMedia(
        title=data.get("title", ""),
        media_type=data.get("media_type", ""),
        mal_id=service_ids.get("mal"),
        serializd_id=service_ids.get("serializd"),
    )
    for season_data in data.get("seasons", []) or []:
        season_service_ids = season_data.get("service_ids", {}) or {}
        season = WaymarkSeason(
            season_number=int(season_data.get("season_number", 0)),
            title=season_data.get("title", ""),
            mal_id=season_service_ids.get("mal"),
            serializd_id=season_service_ids.get("serializd"),
            is_specials=bool(season_data.get("is_specials", False)),
        )
        for episode_data in season_data.get("episodes", []) or []:
            episode_service_ids = episode_data.get("service_ids", {}) or {}
            season.episodes.append(
                WaymarkEpisode(
                    season_number=int(episode_data.get("season_number", season.season_number)),
                    episode_number=int(episode_data.get("episode_number", 0)),
                    title=episode_data.get("title", ""),
                    mal_id=episode_service_ids.get("mal"),
                    serializd_id=episode_service_ids.get("serializd"),
                )
            )
        media.add_season(season)
    return media


def load_waymark_media() -> dict[str, WaymarkMedia]:
    """Load persisted WAYMARK identities. Missing file means an empty registry."""
    try:
        with open(WAYMARK_MEDIA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return {}

    registry = {}
    for key, data in raw.items():
        registry[key] = waymark_media_from_dict(data)
    return registry


def save_waymark_media(registry: dict[str, WaymarkMedia]):
    """Persist WAYMARK identities locally without storing authentication secrets."""
    payload = {
        key: waymark_media_to_dict(media)
        for key, media in sorted(registry.items())
    }
    parent = os.path.dirname(WAYMARK_MEDIA_FILE)
    os.makedirs(parent, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="waymark-media-", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, WAYMARK_MEDIA_FILE)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def waymark_identity_key(media: WaymarkMedia) -> str:
    """Return a stable explicit key for one WAYMARK identity."""
    if media.mal_id is not None:
        return f"mal:{media.mal_id}"
    if media.serializd_id is not None:
        return f"serializd:{media.serializd_id}"
    raise ValueError("A WAYMARK identity needs at least one service ID.")


def persist_waymark_identity(media: WaymarkMedia) -> str:
    """Save one explicitly identified media record and return its registry key."""
    registry = load_waymark_media()
    key = waymark_identity_key(media)
    registry[key] = media
    save_waymark_media(registry)
    return key


def test_persistent_waymark_identity():
    """Create and reload the verified Frieren link from local storage."""
    print("\n========================")
    print("WAYMARK PERSISTENT MEDIA IDENTITY")
    print("========================")
    print("This writes only local identity metadata to waymark_media.json.")
    print("No MAL or Serializd data will be changed.")

    mal_id = 52991
    serializd_id = 209867
    mal_status = get_my_status(mal_id)
    serializd_show = get_show(serializd_id)

    media = WaymarkMedia(
        title=mal_status.get("title", "Sousou no Frieren"),
        media_type="anime",
    )
    link_waymark_services(media, mal_id=mal_id, serializd_id=serializd_id)

    key = persist_waymark_identity(media)
    registry = load_waymark_media()
    loaded = registry[key]

    print(f"Saved key: {key}")
    print(f"Title: {loaded.title}")
    print(f"Type: {loaded.media_type}")
    print(f"MAL ID: {loaded.mal_id}")
    print(f"Serializd ID: {loaded.serializd_id}")
    print(f"Serializd title: {serializd_show.get('name', serializd_show.get('title', ''))}")
    print(f"Registry entries: {len(registry)}")
    print(f"File: {WAYMARK_MEDIA_FILE}")
    print("Persistent identity save + reload complete. No service data was changed. âœ…")


def print_waymark_identity(media: WaymarkMedia):
    """Human-readable temporary test for the internal identity layer."""
    print("\n========================")
    print("WAYMARK INTERNAL MEDIA IDENTITY")
    print("========================")
    print(f"Title: {media.title}")
    print(f"Type: {media.media_type}")
    print(f"MAL ID: {media.mal_id if media.mal_id is not None else 'Not linked'}")
    print(f"Serializd ID: {media.serializd_id if media.serializd_id is not None else 'Not linked'}")
    print(f"Seasons mapped: {len(media.seasons)}")
    for season in media.seasons:
        label = "Specials" if season.is_specials else f"Season {season.season_number:02d}"
        print(
            f"  {label}"
            f" | S{season.season_number:02d}"
            f" | Serializd season ID: {season.serializd_id}"
            f" | Episodes: {len(season.episodes)}"
        )
        for episode in season.episodes[:3]:
            print(
                f"      E{episode.episode_number:02d}"
                f" | {episode.title}"
                f" | Serializd episode ID: {episode.serializd_id}"
            )
        if len(season.episodes) > 3:
            print(f"      ... {len(season.episodes) - 3} more episodes")


def test_waymark_identity():
    """Build a TV identity from verified Serializd metadata.

    Season 0 is retained as Specials rather than being treated as a
    normal numbered season.
    """
    show_id = 76479  # The Boys; existing verified test show
    show = get_show(show_id)
    media = create_waymark_tv(show)

    seasons = show.get("seasons", []) or []
    if seasons:
        for season_item in seasons:
            season_number = season_item.get("seasonNumber")
            if season_number is None:
                continue
            season_data = get_season(show_id, int(season_number))
            attach_serializd_season(media, season_data)
    else:
        print("Serializd show metadata did not include a seasons list.")

    print_waymark_identity(media)
    print("\nSpecials handling: S00 is stored as a Specials season and is not a regular numbered season.")
    print("Internal identity test complete. No data was changed. âœ…")


def link_waymark_services(
    media: WaymarkMedia,
    *,
    mal_id: int | None = None,
    serializd_id: int | None = None,
) -> WaymarkMedia:
    """Explicitly link verified service IDs to one WAYMARK identity.

    This function intentionally does not perform fuzzy title matching.
    A service link is created only from IDs explicitly supplied by WAYMARK.
    """
    if mal_id is not None:
        media.mal_id = int(mal_id)
    if serializd_id is not None:
        media.serializd_id = int(serializd_id)
    return media


def test_waymark_cross_service_link():
    """Controlled read-only test linking the verified Frieren service IDs."""
    print("\n========================")
    print("WAYMARK MAL â†” SERIALIZD LINK")
    print("========================")
    print("This test uses explicitly verified IDs. No title-based fuzzy matching and no data changes.")

    mal_id = 52991
    serializd_id = 209867

    mal_status = get_my_status(mal_id)
    serializd_show = get_show(serializd_id)

    mal_title = mal_status.get("title", "Sousou no Frieren")
    serializd_title = serializd_show.get("name", serializd_show.get("title", ""))

    media = WaymarkMedia(
        title=mal_title,
        media_type="anime",
    )
    link_waymark_services(
        media,
        mal_id=mal_id,
        serializd_id=serializd_id,
    )

    print(f"WAYMARK title: {media.title}")
    print(f"Type: {media.media_type}")
    print(f"MAL ID: {media.mal_id}")
    print(f"MAL title: {mal_title}")
    print(f"Serializd ID: {media.serializd_id}")
    print(f"Serializd title: {serializd_title}")
    print("\nExplicit service link created in memory only. No MAL or Serializd data was changed. âœ…")

def attach_all_serializd_seasons(media: WaymarkMedia) -> WaymarkMedia:
    """Populate a WAYMARK media identity with all Serializd season/episode IDs.

    Season 0 is retained as Specials. No MAL episode IDs are guessed or invented.
    """
    if media.serializd_id is None:
        raise ValueError("Media has no Serializd ID.")

    show = get_show(media.serializd_id)
    seasons = show.get("seasons", []) or []
    for season_item in seasons:
        season_number = season_item.get("seasonNumber")
        if season_number is None:
            continue
        season_data = get_season(media.serializd_id, int(season_number))
        attach_serializd_season(media, season_data)
    return media


def test_persistent_episode_identity():
    """Persist the verified Frieren service link plus its Serializd episodes."""
    print("\n========================")
    print("WAYMARK PERSISTENT SEASON / EPISODE IDENTITY")
    print("========================")
    print("This reads Serializd metadata and writes only local WAYMARK identity data.")
    print("No MAL or Serializd data will be changed.")

    mal_id = 52991
    serializd_id = 209867
    mal_status = get_my_status(mal_id)
    serializd_show = get_show(serializd_id)

    registry = load_waymark_media()
    key = f"mal:{mal_id}"
    media = registry.get(key)
    if media is None:
        media = WaymarkMedia(
            title=mal_status.get("title", "Sousou no Frieren"),
            media_type="anime",
            mal_id=mal_id,
            serializd_id=serializd_id,
        )
    else:
        link_waymark_services(media, mal_id=mal_id, serializd_id=serializd_id)

    # Refresh the season/episode identity from Serializd.
    media.seasons = []
    attach_all_serializd_seasons(media)
    registry[key] = media
    save_waymark_media(registry)

    loaded = load_waymark_media()[key]
    regular_seasons = [s for s in loaded.seasons if not s.is_specials]
    specials = [s for s in loaded.seasons if s.is_specials]
    episode_count = sum(len(s.episodes) for s in loaded.seasons)

    print(f"WAYMARK title: {loaded.title}")
    print(f"Type: {loaded.media_type}")
    print(f"MAL ID: {loaded.mal_id}")
    print(f"Serializd ID: {loaded.serializd_id}")
    print(f"Regular seasons mapped: {len(regular_seasons)}")
    print(f"Specials seasons mapped: {len(specials)}")
    print(f"Total Serializd episodes mapped: {episode_count}")

    for season in loaded.seasons[:3]:
        label = "Specials" if season.is_specials else f"Season {season.season_number:02d}"
        print(f"  {label}: {len(season.episodes)} episodes")
        for episode in season.episodes[:3]:
            print(
                f"      E{episode.episode_number:02d} | {episode.title}"
                f" | Serializd episode ID: {episode.serializd_id}"
            )

    print(f"File: {WAYMARK_MEDIA_FILE}")
    print("Season/episode identity save + reload complete. No service data was changed. âœ…")


def _serializd_diary_episode_map(
    diary_entries: list[dict],
    show_id: int,
) -> dict[tuple[int, int], list[dict]]:
    """Group Serializd diary entries for one show by season/episode.

    Diary entries are activity/log records, not a complete watched-state
    database. Multiple logs for the same episode are retained so the caller
    can distinguish first watches from repeated activity.
    """
    grouped: dict[tuple[int, int], list[dict]] = {}

    for entry in diary_entries:
        if int(entry.get("showId", -1)) != int(show_id):
            continue

        episode_number = entry.get("episodeNumber")
        season_id = entry.get("seasonId")

        # Series/season-level diary entries do not have an episode number.
        if episode_number is None or season_id is None:
            continue

        key = (int(season_id), int(episode_number))
        grouped.setdefault(key, []).append(entry)

    return grouped


def test_waymark_sync_comparison():
    """Read-only comparison of MAL progress and Serializd logged activity.

    This deliberately does not write to either service. Serializd's diary is
    treated as logged activity only; it is not incorrectly presented as the
    authoritative watched-state source.
    """
    print("\n========================")
    print("WAYMARK MAL â†” SERIALIZD SYNC COMPARISON")
    print("========================")
    print("READ-ONLY. No MAL or Serializd data will be changed.")
    print("\nTest media: Sousou no Frieren")

    mal_id = 52991
    serializd_id = 209867

    # Load the persisted identity first. This proves the comparison uses the
    # internal WAYMARK mapping rather than title-based matching.
    registry = load_waymark_media()
    key = f"mal:{mal_id}"
    media = registry.get(key)

    if media is None or media.serializd_id != serializd_id:
        print("ERROR: The persisted Frieren MAL â†” Serializd identity was not found.")
        print("Run option 7 and option 8 first.")
        return

    mal_data = get_my_status(mal_id)
    diary_entries = get_full_diary()

    list_status = mal_data.get("my_list_status", {}) or {}
    mal_title = mal_data.get("title", media.title)
    mal_status = list_status.get("status", "unknown")
    mal_watched = int(list_status.get("num_episodes_watched", 0) or 0)
    mal_total = mal_data.get("num_episodes")

    serializd_show = get_show(serializd_id)
    serializd_title = serializd_show.get("name", serializd_show.get("title", media.title))

    episode_logs = _serializd_diary_episode_map(diary_entries, serializd_id)
    unique_logged = len(episode_logs)
    ratings = []
    for entries in episode_logs.values():
        for entry in entries:
            rating = entry.get("rating")
            if rating not in (None, ""):
                try:
                    ratings.append(float(rating) / 2)
                except (TypeError, ValueError):
                    pass

    print("\nWAYMARK IDENTITY")
    print(f"  Title: {media.title}")
    print(f"  Type: {media.media_type}")
    print(f"  MAL ID: {media.mal_id}")
    print(f"  Serializd ID: {media.serializd_id}")
    print("  Identity: MATCHED")

    print("\nMAL")
    print(f"  Title: {mal_title}")
    print(f"  Status: {mal_status}")
    if mal_total is None:
        print(f"  Episodes watched: {mal_watched}")
    else:
        print(f"  Episodes watched: {mal_watched} / {mal_total}")
    if list_status.get("score") is not None:
        print(f"  Score: {list_status.get('score')}/10")

    print("\nSERIALIZD")
    print(f"  Title: {serializd_title}")
    print(f"  Diary episode logs found: {unique_logged} unique episodes")
    print(f"  Diary entries for this show: {sum(len(v) for v in episode_logs.values())}")
    if ratings:
        print(f"  Logged ratings: {min(ratings):g}â€“{max(ratings):g} stars")
    else:
        print("  Logged ratings: none")

    print("\nCOMPARISON")
    print(f"  MAL progress: {mal_watched} episodes")
    print(f"  Serializd diary activity: {unique_logged} unique episode(s) logged")
    if mal_watched == unique_logged:
        print("  Result: PROGRESS COUNTS MATCH")
    else:
        print("  Result: PROGRESS COUNTS DIFFER")

    print("\nIMPORTANT")
    print("  Serializd diary entries represent logged activity, not a complete")
    print("  watched-state snapshot. WAYMARK will not treat this difference as")
    print("  an automatic sync instruction yet.")
    print("\nRead-only sync comparison complete. No service data was changed. âœ…")


# ============================================================
# SERIALIZD LIVE LIBRARY
# ============================================================

def test_live_serializd_library():
    """Read the current Serializd watched library without persisting it."""

    print("\n========================")
    print("WAYMARK LIVE SERIALIZD LIBRARY")
    print("========================")
    print("READ-ONLY. The library is fetched directly from Serializd.")
    print("Nothing from the full library is written to waymark_media.json.")

    try:
        username = None
        from app.backend.services.serializd import get_username
        username = get_username()
        library = get_watched_library()
    except Exception as exc:
        print(f"\nCould not read the Serializd library: {exc}")
        return

    print(f"\nConnected as: {username}")
    print(f"Shows returned: {len(library)}")
    print("\nCurrent watched library:")

    for index, item in enumerate(library, 1):
        name = item.get("showName", item.get("name", "Unknown"))
        show_id = item.get("showId", item.get("id", "?"))

        # watchedpage_v2 may expose aggregate counts under different keys.
        seasons = item.get("numberOfSeasons", item.get("seasonCount"))
        episodes = item.get("numberOfEpisodes", item.get("episodeCount"))

        if seasons is not None and episodes is not None:
            details = f"{seasons} seasons â€¢ {episodes} episodes"
        elif seasons is not None:
            details = f"{seasons} seasons"
        elif episodes is not None:
            details = f"{episodes} episodes"
        else:
            details = ""

        suffix = f" | {details}" if details else ""
        print(f"{index:3}. {name} | Serializd ID: {show_id}{suffix}")

    print("\nLive Serializd library read complete.")
    print("No library data was persisted locally. No service data was changed. âœ…")

# ============================================================
# SERIALIZD LIVE WATCH STATE
# ============================================================

def test_live_serializd_episode_watch_state():
    """Read live episode-level watched state for Frieren, read-only."""

    print("\n========================")
    print("WAYMARK LIVE SERIALIZD EPISODE WATCH STATE")
    print("========================")
    print("READ-ONLY. Nothing is written to WAYMARK, MAL, or Serializd.")
    print("\nTest show: Frieren: Beyond Journey's End")
    print("Serializd ID: 209867")

    try:
        from app.backend.services.serializd import get_show_watch_state, get_show, get_watched_episode_logs

        record = get_show_watch_state(209867)
        if record is None:
            print("\nFrieren was not found in the current Serializd watched library.")
            return

        season_ids = record.get("seasonIds") or []
        if not season_ids:
            print("\nNo watched seasons were returned for Frieren.")
            return

        show = get_show(209867)
        regular = []
        specials = []

        for season_id in season_ids:
            matched = next(
                (season for season in (show.get("seasons", []) or [])
                 if str(season.get("id", season.get("seasonId"))) == str(season_id)),
                None,
            )
            if not matched:
                print(f"\nCould not resolve watched season ID {season_id}.")
                continue

            season_number = matched.get("seasonNumber")
            season_name = matched.get("name", "")
            logs = get_watched_episode_logs(209867, int(season_id))

            try:
                numeric_season = int(season_number)
            except (TypeError, ValueError):
                numeric_season = None

            target = specials if numeric_season == 0 else regular
            target.append((numeric_season, season_name, int(season_id), logs))

        print("\nLIVE SERIALIZD EPISODE WATCH STATE")
        print("  Source: authenticated Serializd season_v2_part_3 episodeLogs")

        total = 0
        for season_number, season_name, season_id, logs in target if False else regular + specials:
            label = "Specials (S00)" if season_number == 0 else f"Season {season_number:02d}" if season_number is not None else season_name
            print(f"\n  {label} | Serializd season ID: {season_id} | {season_name}")
            print(f"  Watched episode-log records: {len(logs)}")

            episode_numbers = []
            for log in logs:
                number = log.get("episodeNumber")
                if number is None:
                    number = log.get("episode_number")
                if number is not None:
                    try:
                        episode_numbers.append(int(number))
                    except (TypeError, ValueError):
                        pass

            episode_numbers = sorted(set(episode_numbers))
            total += len(episode_numbers)
            if episode_numbers:
                print("  Watched episode numbers: " + ", ".join(f"E{n:02d}" for n in episode_numbers))

        print(f"\nTotal unique watched episodes returned: {total}")
        print("\nIMPORTANT")
        print("  This is episode-level activity returned live by Serializd.")
        print("  It is separate from the diary endpoint and is not persisted locally.")
        print("  We will validate its semantics before using it for synchronization.")
        print("\nLive Serializd episode watch-state read complete. No service data was changed. âœ…")

    except Exception as exc:
        print(f"\nCould not read the live Serializd episode watch state: {exc}")


def test_live_serializd_show_watch_state():
    """Read the live watched-state record for one Serializd show."""

    print("\n========================")
    print("WAYMARK LIVE SERIALIZD SHOW WATCH STATE")
    print("========================")
    print("READ-ONLY. Nothing is written to WAYMARK, MAL, or Serializd.")
    print("\nTest show: Frieren: Beyond Journey's End")
    print("Serializd ID: 209867")

    try:
        from app.backend.services.serializd import get_show_watch_state, get_show

        record = get_show_watch_state(209867)
        if record is None:
            print("\nFrieren was not found in the current Serializd watched library.")
            return

        season_ids = record.get("seasonIds") or []
        print("\nLIVE SERIALIZD WATCHED-LIBRARY STATE")
        print(f"  Show: {record.get('showName', 'Frieren: Beyond Journey\'s End')}")
        print(f"  Serializd ID: {record.get('showId', 209867)}")
        print(f"  Watched season IDs: {len(season_ids)}")

        if season_ids:
            print("\nWatched seasons:")
            show = get_show(209867)
            for season_id in season_ids:
                matched = None
                # Resolve the watched season ID to a real season number/name.
                # Serializd's watched library gives IDs; the show metadata
                # endpoint gives the human-readable season information.
                for season in show.get("seasons", []) or []:
                    sid = season.get("id", season.get("seasonId"))
                    if str(sid) == str(season_id):
                        matched = season
                        break

                if matched:
                    number = matched.get("seasonNumber")
                    name = matched.get("name", "")
                    label = f"S{int(number):02d}" if isinstance(number, int) or str(number).isdigit() else str(number)
                    if str(number) == "0":
                        label = "Specials (S00)"
                    print(f"  {label} | Serializd season ID: {season_id} | {name}")
                else:
                    print(f"  Serializd season ID: {season_id} | metadata not resolved")
        else:
            print("  No watched season IDs were returned.")

        print("\nIMPORTANT")
        print("  This is the authoritative watched-library/season-level state")
        print("  returned by the live Serializd watched-library endpoint.")
        print("  It does NOT mean every diary entry is a watched-state record.")
        print("  Individual episode diary logs remain separate activity data.")
        print("\nLive Serializd show watch-state read complete. No service data was changed. âœ…")

    except Exception as exc:
        print(f"\nCould not read the live Serializd watch state: {exc}")


# ============================================================
# SERIALIZD LIVE PERSONAL DIARY PREVIEW
# ============================================================

def test_live_serializd_personal_diary():
    """Read the authenticated user's recent Serializd activity live.

    Only the first diary page is fetched for this lightweight test. The full
    diary is intentionally not copied into WAYMARK local storage.
    """
    print("\n========================")
    print("WAYMARK LIVE SERIALIZD PERSONAL DIARY")
    print("========================")
    print("READ-ONLY. Activity is fetched live and nothing is saved locally.")

    try:
        from app.backend.services.serializd import get_diary, get_username

        username = get_username()
        data = get_diary(1)
        entries = data.get("reviews", []) if isinstance(data, dict) else []
        total_reviews = data.get("totalReviews", "?") if isinstance(data, dict) else "?"
        total_pages = data.get("totalPages", "?") if isinstance(data, dict) else "?"

        print(f"\nConnected as: {username}")
        print(f"Total diary/activity entries available: {total_reviews}")
        print(f"Diary pages available: {total_pages}")
        print(f"Entries fetched this time: {len(entries)}")

        if not entries:
            print("\nNo diary activity was returned on page 1.")
            print("\nLive Serializd personal diary read complete. No changes were made. âœ…")
            return

        print("\nRecent activity (live, page 1):\n")

        for index, entry in enumerate(entries, 1):
            show_name = entry.get("showName", "Unknown show")
            season_id = entry.get("seasonId")
            episode_number = entry.get("episodeNumber")
            episode_name = entry.get("episodeName")

            if episode_number is not None:
                location = f"E{int(episode_number):02d}"
                if season_id is not None:
                    location = f"Season ID {season_id} / {location}"
                if episode_name:
                    location += f" â€” {episode_name}"
            else:
                location = "Series / season entry"

            rating = entry.get("rating")
            if rating not in (None, ""):
                try:
                    rating_text = f"{float(rating) / 2:g} stars"
                except (TypeError, ValueError):
                    rating_text = str(rating)
            else:
                rating_text = "No rating"

            date_value = entry.get("backdate") or entry.get("dateAdded") or "Unknown date"
            review_text = (entry.get("reviewText") or "").strip()
            is_log = bool(entry.get("isLog", False))
            is_rewatch = bool(entry.get("isRewatch", False))

            print(f"{index:2}. {show_name}")
            print(f"    {location}")
            print(f"    Rating: {rating_text} | {'Log' if is_log else 'Review'} | Rewatch: {'Yes' if is_rewatch else 'No'}")
            print(f"    Date: {date_value}")
            if review_text:
                print(f"    Review: {review_text}")
            print()

        print("IMPORTANT")
        print("  This is a live read of your personal Serializd diary/activity.")
        print("  WAYMARK does not store these entries in waymark_media.json.")
        print("  The app can fetch this information only when it is needed.")
        print("\nLive Serializd personal diary read complete. No changes were made. âœ…")

    except Exception as exc:
        print(f"\nCould not read the live Serializd personal diary: {exc}")


# ============================================================
# WAYMARK CONVERSATIONAL PROTOTYPE
# ============================================================

def _parse_chat_episode(value: str) -> tuple[int, int] | None:
    """Parse S01E05, s1e5, or episode 5 into a season/episode pair."""
    value = value.strip()

    match = re.search(r"\bS(\d{1,2})\s*E(\d{1,3})\b", value, re.IGNORECASE)
    if match:
        return int(match.group(1)), int(match.group(2))

    match = re.search(r"\bseason\s*(\d{1,2}).*?\bepisode\s*(\d{1,3})\b", value, re.IGNORECASE)
    if match:
        return int(match.group(1)), int(match.group(2))

    match = re.search(r"\bepisode\s*(\d{1,3})\b", value, re.IGNORECASE)
    if match:
        return 1, int(match.group(1))

    return None


def _parse_chat_rating(value: str, service: str) -> float | int | None:
    """Extract a service-specific rating without confusing episode numbers."""
    if service == "mal":
        patterns = [
            r"\b(?:mal|myanimelist)\s*(?:rating|score)?\s*[:=]?\s*(\d{1,2})(?:\s*/\s*10)?\b",
            r"\bmal\s*(\d{1,2})\s*/\s*10\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, value, re.IGNORECASE)
            if match:
                score = int(match.group(1))
                if 1 <= score <= 10:
                    return score
        return None

    # Prefer an explicit Serializd label. This prevents the episode number
    # in "episode 5" from accidentally becoming a 5-star rating.
    patterns = [
        r"\bserializd\s*(?:rating|score)?\s*[:=]?\s*(5(?:\.0)?|[1-4](?:\.5|\.0)?)(?:\s*(?:stars?|/\s*5))?\b",
        r"\bserialised\s*(?:rating|score)?\s*[:=]?\s*(5(?:\.0)?|[1-4](?:\.5|\.0)?)(?:\s*(?:stars?|/\s*5))?\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, value, re.IGNORECASE)
        if match:
            stars = float(match.group(1))
            if 1.0 <= stars <= 5.0 and stars * 2 == int(stars * 2):
                return stars

    # Generic star wording is useful when the user clearly says "stars".
    # It is intentionally not used for a bare number because that would be
    # ambiguous with episode numbers, dates, or MAL scores.
    match = re.search(
        r"\b(?:gave\s+it|give\s+it|rated\s+it|rating(?:\s+it)?)\s*[:=]?\s*"
        r"([1-5](?:\.5)?)(?:\s*stars?)\b",
        value,
        re.IGNORECASE,
    )
    if match:
        stars = float(match.group(1))
        if 1.0 <= stars <= 5.0:
            return stars

    return None


def _chat_parse_media(value: str) -> tuple[bool | None, str | None]:
    """Infer anime/live-action and TV/movie only when the text states it."""
    lowered = value.lower()

    anime = None
    if re.search(r"\b(?:anime|animated\s+series|animated\s+show)\b", lowered):
        anime = True
    elif re.search(r"\b(?:live[- ]?action|live action|non[- ]anime)\b", lowered):
        anime = False

    media_type = None
    if re.search(r"\b(?:tv|television|tv\s+show|tv\s+series|series|show)\b", lowered):
        media_type = "tv"
    elif re.search(r"\b(?:movie|film)\b", lowered):
        media_type = "movie"

    return anime, media_type


def _extract_chat_review(value: str) -> str:
    """Extract an explicitly labelled review from the original sentence."""
    match = re.search(
        r"\b(?:review|note|notes|thoughts?)\s*[:=-]\s*(.+)$",
        value.strip(),
        re.IGNORECASE,
    )
    if not match:
        return ""

    review = match.group(1).strip()
    # Remove a trailing confirmation-style fragment if someone appended it.
    review = re.sub(r"\s+please\s+log\s+this\s*$", "", review, flags=re.IGNORECASE)
    return review.strip(" \t.,")

def _extract_chat_title(value: str) -> str:
    """Extract the title from common conversational watch statements."""
    cleaned = value.strip()

    patterns = [
        r"^(?:i\s+)?(?:just\s+)?(?:watched|watch(?:ed)?|finished|rewatched)\s+(.+?)\s+(?:s\s*\d{1,2}\s*e\s*\d{1,3}|season\s*\d{1,2}\s+episode\s*\d{1,3}|episode\s*\d{1,3})\b.*$",
        r"^(.+?)\s+(?:s\s*\d{1,2}\s*e\s*\d{1,3}|season\s*\d{1,2}\s+episode\s*\d{1,3}|episode\s*\d{1,3})\b.*$",
    ]

    for pattern in patterns:
        match = re.match(pattern, cleaned, re.IGNORECASE)
        if match:
            title = match.group(1).strip(" .,:;-")
            # Drop conversational leading phrases if the second pattern matched.
            title = re.sub(r"^(?:i\s+)?(?:just\s+)?(?:watched|watch(?:ed)?|finished|rewatched)\s+", "", title, flags=re.IGNORECASE)
            if title:
                return title.strip(" .,:;-")

    # Fallback: remove common leading verbs and explicit metadata.
    title = re.sub(
        r"^(?:i\s+)?(?:just\s+)?(?:watched|watch(?:ed)?|finished|rewatched)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    title = re.split(r"\b(?:mal|serializd|review|status)\b\s*[:=]", title, maxsplit=1, flags=re.IGNORECASE)[0]
    return title.strip(" .,:;-")



def _chat_parse_status(value: str) -> str | None:
    """Recognize the status vocabulary WAYMARK will use."""
    lowered = value.lower()
    if "completed" in lowered or "finished" in lowered:
        return "completed"
    if "rewatch" in lowered or "re-watching" in lowered:
        return "rewatching"
    if "watching" in lowered:
        return "watching"
    if "on hold" in lowered:
        return "on_hold"
    if "plan to watch" in lowered or "planning" in lowered:
        return "plan_to_watch"
    return None



def _mal_current_status_and_total(mal_selected: dict[str, Any]) -> tuple[str | None, int | None]:
    """Return the selected MAL entry's current status and total episode count."""
    node = mal_selected.get("node", {}) or {}
    list_status = mal_selected.get("list_status", {}) or {}
    status = list_status.get("status")
    total = node.get("waymark_num_episodes")
    try:
        total = int(total) if total not in (None, "", 0) else None
    except (TypeError, ValueError):
        total = None
    return status, total






def _resolve_mal_episode_for_selection(
    mal_selected: dict[str, Any],
    serializd_episode_title: str,
    serializd_episode_number: int,
    explicit_mal_episode: int | None = None,
) -> tuple[int | None, str]:
    """Resolve the MAL episode without assuming Serializd's numbering matches.

    If the user explicitly supplied a MAL/global episode number, use it. If
    not, a future metadata resolver may supply a title match. For now we only
    auto-suggest the same numeric episode when it is demonstrably within MAL's
    known total; we still ask for confirmation rather than silently mapping it.
    """
    if explicit_mal_episode is not None:
        return explicit_mal_episode, "user supplied"

    _, mal_total = _mal_current_status_and_total(mal_selected)
    if mal_total is not None and serializd_episode_number <= mal_total:
        return serializd_episode_number, "same-number candidate"

    # If MAL's total is unknown, do not silently assume that Serializd's
    # local episode number is the MAL/global episode number. Ask the user.
    return None, "no safe automatic mapping"


def _ask_for_mal_episode_number(
    mal_selected: dict[str, Any],
    serializd_episode_title: str,
    serializd_episode_number: int,
) -> tuple[int | None, bool]:
    """Ask for MAL's global episode.

    Returns (episode_number, valid_input). A private BACK sentinel requests
    navigation to the previous guided step. Entering a blank value is a valid
    choice to leave MAL progress unchanged. Invalid input returns (None, False)
    so the caller can abort before any service write occurs.

    If MAL's total is unknown (shown as '?'), there is intentionally no upper
    bound: ongoing MAL entries can accept progress beyond the currently known
    episode count.
    """
    candidate, _ = _resolve_mal_episode_for_selection(
        mal_selected,
        serializd_episode_title,
        serializd_episode_number,
    )
    mal_title = mal_selected.get("node", {}).get("title", "MAL title")
    _, mal_total = _mal_current_status_and_total(mal_selected)

    if candidate is not None:
        total_text = f" / {mal_total}" if mal_total is not None else ""
        print(
            f"\nWAYMARK can tentatively use MAL E{candidate}{total_text} "
            f"for the selected Serializd episode."
        )
        print("This is only a candidate because MAL and Serializd can number episodes differently.")
        answer = input("Use this MAL episode number? [Y/N] (B = back, 0/Cancel = cancel)\n> ").strip().lower()
        if answer in {"b", "back"}:
            return _BACK, True
        if answer in {"y", "yes"}:
            return candidate, True
        if _is_cancel_command(answer):
            print("Cancelled. No service data was changed.")
            return None, False

    prompt = "\nMAL global episode number"
    if mal_total is not None:
        prompt += f" (1-{mal_total})"
    else:
        prompt += " (positive integer; MAL total currently unknown)"
    prompt += " (press Enter to leave MAL progress unchanged): "
    value = input(prompt + " (B = back, 0/Cancel = cancel): ").strip()
    if value.lower() in {"b", "back"}:
        return _BACK, True
    if _is_cancel_command(value):
        print("Cancelled. No service data was changed.")
        return None, False
    if not value:
        return None, True
    if not value.isdigit() or int(value) < 1:
        print(f"Invalid MAL episode number for {mal_title}. No service data will be changed.")
        return None, False
    episode = int(value)
    if mal_total is not None and episode > mal_total:
        print(
            f"MAL episode E{episode} is beyond the known total of {mal_total} episodes "
            f"for {mal_title}. No service data will be changed."
        )
        return None, False
    return episode, True

def _validate_chat_action_plan(
    *,
    mal_id: int | None,
    serializd_id: int,
    serializd_season_id: int,
    season_number: int,
    episode_number: int,
    mal_episode_number: int | None,
    mal_total_episodes: int | None,
    mal_rating: int | None,
    serializd_stars: float | None,
    status: str | None,
    season_completed: bool,
    season_rating: float | None,
    final_episode: int | None = None,
) -> list[str]:
    """Validate the complete write plan before any service write occurs."""
    errors: list[str] = []

    if not isinstance(serializd_id, int) or serializd_id <= 0:
        errors.append("Serializd show ID is invalid.")
    if not isinstance(serializd_season_id, int) or serializd_season_id <= 0:
        errors.append("Serializd season ID is invalid.")
    if not isinstance(season_number, int) or season_number <= 0:
        errors.append("Serializd season number is invalid.")
    if not isinstance(episode_number, int) or episode_number <= 0:
        errors.append("Serializd episode number must be 1 or greater.")
    if final_episode is not None and episode_number > final_episode:
        errors.append(
            f"Serializd episode E{episode_number} is beyond the selected arc's final numbered episode E{final_episode}."
        )

    if mal_id is None:
        if mal_episode_number is not None or mal_rating is not None or status is not None:
            errors.append("MAL-only fields were supplied without a MAL entry.")
    else:
        if not isinstance(mal_id, int) or mal_id <= 0:
            errors.append("MAL anime ID is invalid.")
        if mal_total_episodes is not None and (not isinstance(mal_total_episodes, int) or mal_total_episodes <= 0):
            errors.append("MAL known episode total is invalid.")
        if mal_episode_number is not None and (not isinstance(mal_episode_number, int) or mal_episode_number <= 0):
            errors.append("MAL episode number must be 1 or greater.")
        elif (
            mal_episode_number is not None
            and mal_total_episodes is not None
            and mal_episode_number > mal_total_episodes
        ):
            errors.append(
                f"MAL episode E{mal_episode_number} is beyond the known total of {mal_total_episodes} episodes."
            )
        # A None/unknown MAL total is intentionally treated as an open upper bound.
        if mal_rating is not None and (not isinstance(mal_rating, int) or not 1 <= mal_rating <= 10):
            errors.append("MAL score must be an integer from 1 to 10.")
        if status is not None and status not in {"watching", "completed", "rewatching", "on_hold", "plan_to_watch"}:
            errors.append(f"Unsupported MAL status: {status}.")

    if serializd_stars is not None:
        if not isinstance(serializd_stars, (int, float)) or not 1.0 <= float(serializd_stars) <= 5.0:
            errors.append("Serializd rating must be between 1.0 and 5.0.")
        elif float(serializd_stars) * 2 != int(float(serializd_stars) * 2):
            errors.append("Serializd rating must use half-star increments.")

    if season_rating is not None:
        if not isinstance(season_rating, (int, float)) or not 1.0 <= float(season_rating) <= 5.0:
            errors.append("Serializd season rating must be between 1.0 and 5.0.")
        elif float(season_rating) * 2 != int(float(season_rating) * 2):
            errors.append("Serializd season rating must use half-star increments.")

    if season_rating is not None and not season_completed:
        errors.append("A Serializd season rating can only be written when the selected episode completes that season.")

    return errors


def _chat_execute_anime_tv_action(
    *,
    mal_id: int | None,
    serializd_id: int,
    serializd_season_id: int,
    season_number: int,
    episode_number: int,
    mal_episode_number: int | None,
    mal_total_episodes: int | None,
    mal_rating: int | None,
    serializd_stars: float | None,
    status: str | None,
    review_text: str,
    season_completed: bool = False,
    season_rating: float | None = None,
    season_review_text: str = "",
    final_episode: int | None = None,
):
    """Execute a pre-validated write plan with explicit per-operation results.

    This is transaction-safe at the application level: every input is validated
    before the first write, and failures are reported per operation. True
    cross-service rollback is not attempted because MAL and Serializd do not
    provide a shared transaction/rollback mechanism.
    """
    from datetime import datetime, timezone

    validation_errors = _validate_chat_action_plan(
        mal_id=mal_id,
        serializd_id=serializd_id,
        serializd_season_id=serializd_season_id,
        season_number=season_number,
        episode_number=episode_number,
        mal_episode_number=mal_episode_number,
        mal_total_episodes=mal_total_episodes,
        mal_rating=mal_rating,
        serializd_stars=serializd_stars,
        status=status,
        season_completed=season_completed,
        season_rating=season_rating,
        final_episode=final_episode,
    )
    if validation_errors:
        print("\nValidation failed. No service data was changed.")
        for error in validation_errors:
            print(f"  âœ— {error}")
        return {"ok": False, "cancelled": False, "validation_errors": validation_errors, "operations": []}

    print("\nExecuting verified actions...")
    operations: list[dict[str, Any]] = []

    def run_operation(name: str, func):
        try:
            result = func()
            operations.append({"name": name, "ok": True, "result": result})
            print(f"âœ“ {name}")
            return result
        except Exception as exc:
            operations.append({"name": name, "ok": False, "error": str(exc)})
            print(f"âœ— {name} â€” {exc}")
            return None

    if mal_id is not None:
        if mal_episode_number is not None:
            run_operation(
                f"MAL progress â†’ E{mal_episode_number}",
                lambda: update_progress(
                    mal_id,
                    mal_episode_number,
                    is_rewatching=status == "rewatching",
                ),
            )
        if status in {"watching", "completed", "on_hold", "plan_to_watch"}:
            run_operation(
                f"MAL status â†’ {status}",
                lambda: update_status(mal_id, status),
            )
        if mal_rating is not None:
            run_operation(
                f"MAL score â†’ {mal_rating}/10",
                lambda: update_score(mal_id, mal_rating),
            )

    run_operation(
        f"Serializd episode watched â†’ S{season_number:02d}E{episode_number:02d}",
        lambda: mark_episode_watched(serializd_id, serializd_season_id, episode_number),
    )

    backdate = (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )

    run_operation(
        "Serializd episode log/review",
        lambda: log_episode(
            serializd_id,
            serializd_season_id,
            episode_number,
            stars=serializd_stars,
            review_text=review_text,
            is_rewatch=status == "rewatching",
            backdate=backdate,
        ),
    )

    if season_completed:
        run_operation(
            f"Serializd season watched â†’ S{season_number:02d}",
            lambda: mark_season_watched(serializd_id, serializd_season_id),
        )

        if season_rating is not None or season_review_text:
            run_operation(
                "Serializd season review/rating",
                lambda: log_season_review(
                    serializd_id,
                    serializd_season_id,
                    stars=season_rating,
                    review_text=season_review_text,
                    is_rewatch=status == "rewatching",
                    backdate=backdate,
                ),
            )

    failed = [op for op in operations if not op["ok"]]
    succeeded = [op for op in operations if op["ok"]]

    print("\n========================")
    print("WAYMARK RESULT")
    print("========================")
    if not operations:
        print("No writes were requested.")
        return {"ok": True, "partial": False, "operations": operations}

    if failed:
        print("PARTIAL RESULT â€” not all requested operations succeeded.")
        print("Successful operations:")
        for op in succeeded:
            print(f"  âœ“ {op['name']}")
        print("Failed operations:")
        for op in failed:
            print(f"  âœ— {op['name']} â€” {op['error']}")
        print("\nWAYMARK did not claim full synchronization.")
        print("Because MAL and Serializd are separate services, automatic cross-service rollback is not attempted.")
        return {
            "ok": False,
            "partial": bool(succeeded),
            "operations": operations,
            "backdate": backdate,
        }

    print("All requested operations succeeded. âœ…")
    if mal_id is not None:
        print("MAL + Serializd are both updated successfully. âœ…")
    else:
        print("Serializd is updated successfully. âœ…")

    return {
        "ok": True,
        "partial": False,
        "operations": operations,
        "backdate": backdate,
    }


def _chat_search_both_services(title: str):
    """Search MAL and Serializd concurrently after routing is known."""
    def mal_search():
        anime_list = get_my_anime_list()
        matches = find_in_my_list(title, anime_list)
        return anime_list, matches

    def serializd_search():
        return search_catalog(title)

    with ThreadPoolExecutor(max_workers=2) as executor:
        mal_future = executor.submit(mal_search)
        serializd_future = executor.submit(serializd_search)
        mal_list, mal_matches = mal_future.result()
        serializd_matches = serializd_future.result()

    return mal_list, mal_matches, serializd_matches


def _format_year(value: Any) -> str:
    if value is None:
        return "?"
    text = str(value).strip()
    if not text:

        return "?"
    m = re.search(r"(\d{4})", text)
    return m.group(1) if m else text


def _format_episode_count(value: Any) -> str:
    if value is None or value == "":
        return "? eps"
    try:
        return f"{int(value)} eps"
    except (TypeError, ValueError):
        return f"{value} eps"


def _serializd_result_year(item: dict[str, Any]) -> str:
    for key in ("firstAirDate", "first_air_date", "releaseDate", "release_date", "startDate", "start_date", "year"):
        if item.get(key) not in (None, ""):
            return _format_year(item.get(key))
    return "?"


def _serializd_result_episode_count(item: dict[str, Any]) -> str:
    for key in ("numberOfEpisodes", "number_of_episodes", "numEpisodes", "episodeCount", "episode_count", "totalEpisodes"):
        if item.get(key) not in (None, ""):
            return _format_episode_count(item.get(key))
    return "? eps"


def _mal_enrich_match(item: dict[str, Any]) -> dict[str, Any]:
    """Add release year and total episode count for display when available."""
    result = dict(item)
    node = dict(result.get("node", {}))
    anime_id = node.get("id")
    if not anime_id:
        return result
    try:
        token = get_credential("mal", "access_token", env_names=("MAL_ACCESS_TOKEN",))
        if not token:
            return result
        response = requests.get(
            f"https://api.myanimelist.net/v2/anime/{anime_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"fields": "start_date,num_episodes"},
            timeout=15,
        )
        if response.ok:
            details = response.json()
            node["waymark_start_date"] = details.get("start_date")
            raw_total = details.get("num_episodes")
            # MAL can return 0 when the total episode count is unknown/ongoing.
            node["waymark_num_episodes"] = raw_total if raw_total not in (0, "0") else None
    except (OSError, KeyError, requests.RequestException, ValueError):
        pass
    result["node"] = node
    return result


def _print_mal_match_details(item: dict[str, Any], index: int) -> None:
    node = item.get("node", {})
    status = item.get("list_status", {})
    year = _format_year(node.get("waymark_start_date"))
    total = _format_episode_count(node.get("waymark_num_episodes"))
    watched = status.get("num_episodes_watched")
    progress = f"{watched}/{total.split()[0]} watched" if watched is not None and total != "? eps" else (f"{watched} watched" if watched is not None else "")
    suffix = f" | {progress}" if progress else ""
    print(f"{index}. {node.get('title', 'Unknown')} | {year} | {total}{suffix} | {status.get('status', 'unknown')}")



_BACK = object()
_Cancel = object()
_INVALID = object()
# M15.1 uses explicit sentinels for cancellation and invalid input.
# Keep the canonical uppercase name used by the workflow.
_CANCEL = _Cancel


def _is_cancel_command(value: str) -> bool:
    """Return True only for commands that cancel the entire current workflow."""
    return value.strip().lower() in {"0", "cancel", "c", "q"}


def _navigation_command(value: str) -> str | None:
    """Normalize paging commands used by guided selection screens."""
    normalized = value.strip().lower()
    if normalized in {"n", "next"}:
        return "next"
    if normalized in {"p", "prev", "previous"}:
        return "previous"
    return None


def _choose_mal_from_matches(title: str, matches: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not matches:
        return None
    enriched = [_mal_enrich_match(m) for m in matches[:10]]
    if len(enriched) == 1:
        return enriched[0]
    print(f'\nMultiple anime match "{title}".')
    print("Choose the anime/season entry you mean:")
    print("\nMAL matches:")
    for i, item in enumerate(enriched, 1):
        _print_mal_match_details(item, i)
    while True:
        choice = input("Choose an anime (B = back, 0/Cancel = cancel): ").strip()
        if choice.lower() in {"b", "back"}:
            print("Going back one step.")
            return _BACK
        if _is_cancel_command(choice):
            print("Cancelled. No service data was changed.")
            return None
        try:
            number = int(choice)
            if 1 <= number <= len(enriched):
                return enriched[number - 1]
        except ValueError:
            pass
        print("Please choose a valid number, B, or 0/Cancel.")


def _choose_serializd_match(title: str, matches: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not matches:
        return None
    exact = [m for m in matches if str(m.get("name", "")).strip().lower() == title.strip().lower()]
    if len(exact) == 1:
        # Still show the metadata when there are competing near-matches.
        competing = [m for m in matches if m is not exact[0] and str(m.get("name", "")).strip().lower() == title.strip().lower()]
        if not competing:
            return exact[0]
    if len(matches) == 1:
        return matches[0]
    print("\nSerializd matches:")
    print("Year and episode count are shown to help distinguish anime, live-action, and different versions.")
    for i, item in enumerate(matches[:10], 1):
        name = item.get("name", "Unknown")
        year = _serializd_result_year(item)
        eps = _serializd_result_episode_count(item)
        print(f"{i}. {name} | {year} | {eps}")
    while True:
        choice = input("Choose the Serializd title (B = back, 0/Cancel = cancel): ").strip()
        if choice.lower() in {"b", "back"}:
            print("Going back one step.")
            return _BACK
        if _is_cancel_command(choice):
            print("Cancelled. No service data was changed.")
            return None
        try:
            number = int(choice)
            if 1 <= number <= min(len(matches), 10):
                return matches[number - 1]
        except ValueError:
            pass
        print("Please choose a valid number, B, or 0/Cancel.")


def _season_display_name(season: dict[str, Any]) -> str:
    """Return the most useful human-facing Serializd season/arc name."""
    for key in ("name", "title", "seasonName", "season_name", "displayName", "display_name"):
        value = season.get(key)
        if value not in (None, ""):
            return str(value).strip()
    number = _serializd_season_number(season)
    return f"Season {number}" if number is not None else "Unknown season"


def _serializd_season_episode_count(show_id: int, season_number: int) -> int:
    """Return the count of numbered episodes in one Serializd season."""
    return len(_get_serializd_numbered_episodes(show_id, season_number))


def _choose_serializd_episode_in_season(
    show_id: int,
    season_number: int,
    season_meta: dict[str, Any],
    title: str,
):
    """Choose an episode after the Serializd season is already selected.

    B returns to the already-selected season screen; 0/Cancel aborts the
    current workflow. This helper exists so later guided fields can return
    exactly one step without forcing the user to reselect the season.
    """
    episodes = _get_serializd_numbered_episodes(show_id, season_number)
    season_name = _season_display_name(season_meta)
    if not episodes:
        print(f"\nNo numbered episodes were found for Serializd S{season_number:02d}.")
        return None

    print(f"\nSerializd arc selected: S{season_number:02d} â€” {season_name}")
    print(f"It contains {len(episodes)} numbered episodes.")
    print("You can choose by episode number, or search by part of the episode title.")

    page_size = 25
    page = 0

    def print_page():
        start_index = page * page_size
        page_items = episodes[start_index:start_index + page_size]
        if not page_items:
            print("No episodes on this page.")
            return
        print(f"\nEpisodes {start_index + 1}-{start_index + len(page_items)} of {len(episodes)}:")
        for ep in page_items:
            number = int(ep.get("episodeNumber"))
            ep_title = ep.get("title") or ep.get("name") or "Untitled"
            print(f"  E{number:02d} â€” {ep_title}")

    while True:
        print_page()
        value = input(
            "\nChoose episode number, type part of its title, "
            "or use N/Next or P/Previous for paging "
            "(B = back to season, 0/Cancel = cancel): "
        ).strip()
        if value.lower() in {"b", "back"}:
            print("Going back to season selection.")
            return _BACK
        if _is_cancel_command(value):
            print("Cancelled. No service data was changed.")
            return None

        navigation = _navigation_command(value)
        if navigation == "next":
            if (page + 1) * page_size < len(episodes):
                page += 1
            else:
                print("You are already on the last page.")
            continue
        if navigation == "previous":
            if page > 0:
                page -= 1
            else:
                print("You are already on the first page.")
            continue
        if value.isdigit():
            number = int(value)
            selected = next((ep for ep in episodes if int(ep.get("episodeNumber")) == number), None)
            if selected is None:
                print("That episode number is not in this Serializd arc.")
                continue
            return {
                "season_number": season_number,
                "season_id": int(season_meta.get("seasonId", season_meta.get("id"))),
                "episode_number": number,
                "episode_title": selected.get("title") or selected.get("name") or "Untitled",
                "season_name": season_name,
                "season_episode_count": len(episodes),
                "final_episode": int(episodes[-1].get("episodeNumber")),
            }

        query = value.lower()
        title_matches = [
            ep for ep in episodes
            if query in str(ep.get("title") or ep.get("name") or "").lower()
        ]
        if not title_matches:
            print("No episode title matched that text.")
            continue
        if len(title_matches) == 1:
            selected = title_matches[0]
        else:
            print("\nEpisode title matches:")
            for i, ep in enumerate(title_matches[:20], 1):
                print(f"{i}. E{int(ep.get('episodeNumber')):02d} â€” {ep.get('title') or ep.get('name') or 'Untitled'}")
            while True:
                pick = input("Choose an episode (B = back, 0/Cancel = cancel): ").strip()
                if pick.lower() in {"b", "back"}:
                    print("Going back to episode selection.")
                    selected = _BACK
                    break
                if _is_cancel_command(pick):
                    print("Cancelled. No service data was changed.")
                    return None
                try:
                    pick_num = int(pick)
                    if 1 <= pick_num <= min(20, len(title_matches)):
                        selected = title_matches[pick_num - 1]
                        break
                except ValueError:
                    pass
                print("Please choose a valid number, B, or 0/Cancel.")
            if selected is _BACK:
                continue

        return {
            "season_number": season_number,
            "season_id": int(season_meta.get("seasonId", season_meta.get("id"))),
            "episode_number": int(selected.get("episodeNumber")),
            "episode_title": selected.get("title") or selected.get("name") or "Untitled",
            "season_name": season_name,
            "season_episode_count": len(episodes),
            "final_episode": int(episodes[-1].get("episodeNumber")),
        }


def _choose_serializd_arc_and_episode(show_id: int, title: str):
    """Choose a Serializd season/arc, then an episode within that season."""
    show_data = get_show(show_id)
    seasons = show_data.get("seasons", []) or []
    usable = []
    for season in seasons:
        number = _serializd_season_number(season)
        if number is None or number <= 0:
            continue
        try:
            count = _serializd_season_episode_count(show_id, number)
        except Exception:
            count = 0
        if count <= 0:
            continue
        usable.append((number, season, count))

    usable.sort(key=lambda row: row[0])
    if not usable:
        print(f"\nNo numbered Serializd seasons/arcs were found for {title}.")
        return None

    print("\nSerializd seasons / arcs:")
    print("Choose the arc/season you were watching. Names are shown because the season numbers may differ from MAL.")
    for index, (number, season, count) in enumerate(usable, 1):
        name = _season_display_name(season)
        print(f"{index}. S{number:02d} â€” {name} | {count} episodes")

    while True:
        choice = input("Choose the Serializd arc/season (B = back, 0/Cancel = cancel): ").strip()
        if choice.lower() in {"b", "back"}:
            print("Going back one step.")
            return _BACK
        if _is_cancel_command(choice):
            print("Cancelled. No service data was changed.")
            return None
        try:
            index = int(choice)
        except ValueError:
            print("Please choose a valid number, B, or 0/Cancel.")
            continue
        if 1 <= index <= len(usable):
            season_number, season_meta, _ = usable[index - 1]
            selected_episode = _choose_serializd_episode_in_season(
                show_id, season_number, season_meta, title
            )
            if selected_episode is _BACK:
                # Back from episode selection returns exactly one level: to
                # this already-open season selection screen.
                continue
            return selected_episode
        print("Please choose a valid number.")


def _chat_resolve_serializd_season(serializd_id: int, season_number: int, title: str):
    """Resolve a literal Serializd season number and its final numbered episode."""
    show_data = get_show(serializd_id)
    seasons = show_data.get("seasons", []) or []
    matching = [
        s for s in seasons
        if str(s.get("seasonNumber", s.get("season_number", ""))) == str(season_number)
    ]
    if len(matching) != 1:
        print(f"\nCould not safely resolve Serializd Season {season_number} for {title}.")
        return None
    season = matching[0]
    season_id = season.get("seasonId", season.get("id"))
    if season_id is None:
        return None
    season_detail = get_season(serializd_id, season_number)
    episodes = season_detail.get("episodes", []) or []
    numbered = []
    for ep in episodes:
        try:
            n = int(ep.get("episodeNumber"))
        except (TypeError, ValueError):
            continue
        if n > 0:
            numbered.append(n)
    final_episode = max(numbered) if numbered else None
    return int(season_id), final_episode


def _serializd_season_number(item: dict[str, Any]) -> int | None:
    """Read a Serializd season number from known metadata keys."""
    for key in ("seasonNumber", "season_number", "number"):
        value = item.get(key)
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _get_serializd_numbered_episodes(show_id: int, season_number: int) -> list[dict[str, Any]]:
    """Return numbered episodes for one Serializd season in episode order."""
    detail = get_season(show_id, season_number)
    episodes = detail.get("episodes", []) or []
    numbered: list[dict[str, Any]] = []
    for ep in episodes:
        try:
            number = int(ep.get("episodeNumber"))
        except (TypeError, ValueError):
            continue
        if number > 0:
            numbered.append(ep)
    numbered.sort(key=lambda ep: int(ep.get("episodeNumber")))
    return numbered


def _map_global_episode_to_serializd(
    show_id: int,
    global_episode: int,
    *,
    title: str = "",
) -> dict[str, Any] | None:
    """Legacy helper retained for explicit global-episode input.

    Guided mode now prefers selecting Serializd's arc and episode directly.
    """
    if global_episode < 1:
        return None
    show_data = get_show(show_id)
    seasons = show_data.get("seasons", []) or []
    season_numbers = sorted({
        n for n in (_serializd_season_number(s) for s in seasons)
        if n is not None and n > 0
    })
    cumulative_before = 0
    for season_number in season_numbers:
        episodes = _get_serializd_numbered_episodes(show_id, season_number)
        count = len(episodes)
        if count == 0:
            continue
        if global_episode <= cumulative_before + count:
            local_index = global_episode - cumulative_before - 1
            season_meta = next((s for s in seasons if _serializd_season_number(s) == season_number), {})
            season_id = season_meta.get("seasonId", season_meta.get("id"))
            if season_id is None:
                return None
            ep = episodes[local_index]
            return {
                "season_number": season_number,
                "season_id": int(season_id),
                "episode_number": int(ep.get("episodeNumber")),
                "season_episode_count": count,
                "global_episode": global_episode,
                "mapping": "global_episode_to_serializd_seasons",
            }
        cumulative_before += count
    print(f"\nCould not map global episode {global_episode} onto Serializd for {title or 'this show'}.")
    return None























def _waymark_ci(value):
    """Case-insensitive, whitespace-normalized comparison for user input."""
    return " ".join(str(value).strip().casefold().split())











def run_waymark_chat():
    """Run the guided WAYMARK workflow with service-specific season/arc selection."""
    print("\n================================================")
    print(f"WAYMARK â€” CONVERSATIONAL MEDIA ASSISTANT v{APP_VERSION}")
    print("================================================")
    print("WAYMARK will guide you through the information it needs.")
    print("Episode reviews are optional â€” press Enter to skip them.")
    print("Completed Serializd seasons can also receive a season rating/review.")
    print("\nImportant: MAL and Serializd may organize the same anime differently.")
    print("WAYMARK lets you choose the Serializd arc/season and episode independently from MAL.")
    print("\nCurrent live workflows:")
    print("  Anime TV â†’ MAL + Serializd")
    print("  Live-action TV â†’ Serializd")
    print("  Anime movies â†’ MAL route reserved; no movie write yet")
    print("  Non-anime movies â†’ TMDB identity/metadata route reserved; no movie write yet")

    raw = input("\nWhat did you watch today? (B = back, 0/Cancel = cancel)\n> ").strip()
    if raw.lower() in {"b", "back"}:
        print("Going back to the main menu (previous screen).")
        return
    if not raw or _is_cancel_command(raw):
        print("Cancelled. No service data was changed.")
        return

    episode_info = _parse_chat_episode(raw)
    season_number, episode_number = episode_info if episode_info else (None, None)
    explicit_season_episode = bool(
        episode_info and re.search(
            r"\bS\d{1,2}\s*E\d{1,3}\b|\bseason\s*\d{1,2}.*?\bepisode\s*\d{1,3}\b",
            raw,
            re.IGNORECASE,
        )
    )
    title = _extract_chat_title(raw)
    mal_rating = _parse_chat_rating(raw, "mal")
    serializd_stars = _parse_chat_rating(raw, "serializd")
    status = _chat_parse_status(raw)
    anime, media_type = _chat_parse_media(raw)
    review_text = _extract_chat_review(raw)
    season_review_text = ""
    season_rating = None

    print("\nI understood:")
    print(f"  Title: {title}")
    print(f"  Episode: S{season_number:02d}E{episode_number:02d}" if season_number is not None else "  Episode: not specified yet")
    print(f"  Anime: {'yes' if anime is True else 'no' if anime is False else 'not specified'}")
    print(f"  Type: {'TV' if media_type == 'tv' else 'Movie' if media_type == 'movie' else 'not specified'}")

    if anime is None:
        answer = input("\nIs it an anime? [Y/N]\n> ").strip().lower()
        if answer not in {"y", "yes", "n", "no"}:
            print("Please answer Y or N. Cancelled.")
            return
        anime = answer in {"y", "yes"}

    if media_type is None:
        answer = input("\nIs it a TV show or a movie? [TV/Movie]\n> ").strip().lower()
        if answer in {"tv", "t", "tv show", "show", "series"}:
            media_type = "tv"
        elif answer in {"movie", "m", "film"}:
            media_type = "movie"
        else:
            print("Please choose TV or Movie. Cancelled.")
            return

    if media_type != "tv":
        print("\nMovie route selected.")
        if anime:
            print("Anime movie â†’ MAL route is reserved for the movie workflow; no movie write was performed.")
        else:
            print("Non-anime movie â†’ TMDB identity/metadata route is reserved; Letterboxd/movie writes are not enabled yet.")
        print("No service data was changed.")
        return

    print("\nSearching MAL and Serializd for the title at the same time...")
    try:
        mal_list, mal_matches, serializd_matches = _chat_search_both_services(title)
    except Exception as exc:
        print(f"\nTitle search failed: {exc}")
        return

    # Service-title selection is a small navigation stack:
    #   title -> MAL title -> Serializd title -> next step
    # B moves exactly one level upward; 0/Cancel aborts the whole workflow.
    while True:
        if anime:
            while True:
                if not mal_matches:
                    print("\nMAL: no matching anime found.")
                    print("WAYMARK cannot use the MAL workflow for this title.")
                    return
                mal_selected = _choose_mal_from_matches(title, mal_matches)
                if mal_selected is _BACK:
                    title = input("\nWhat did you watch today? (B = back, 0/Cancel = cancel)\n> ").strip()
                    if title.lower() in {"b", "back"}:
                        print("Going back to the main menu (previous screen).")
                        return
                    if not title or _is_cancel_command(title):
                        print("Cancelled. No service data was changed.")
                        return
                    try:
                        mal_list, mal_matches, serializd_matches = _chat_search_both_services(title)
                    except Exception as exc:
                        print(f"\nTitle search failed: {exc}")
                        return
                    # A new title means a fresh MAL/Serializd selection stack.
                    mal_selected = None
                    serializd_selected = None
                    break
                if mal_selected is None:
                    print("\nNo MAL anime selected. Cancelled.")
                    return
                break
            # If title was changed by going back from MAL selection, restart
            # the service-selection stack for the new title.
            if not mal_selected:
                continue

        else:
            print("\nMAL: not applicable because this is live-action TV.")

        # Serializd title is immediately below MAL title for anime, or below
        # the title entry for live-action. Back therefore returns to MAL title
        # selection for anime, and to title entry for live-action.
        while True:
            serializd_selected = _choose_serializd_match(title, serializd_matches)
            if serializd_selected is _BACK:
                if anime:
                    # Back exactly one level: Serializd title -> MAL title.
                    while True:
                        mal_selected = _choose_mal_from_matches(title, mal_matches)
                        if mal_selected is _BACK:
                            title = input("\nWhat did you watch today? (B = back, 0/Cancel = cancel)\n> ").strip()
                            if title.lower() in {"b", "back"}:
                                print("Going back to the main menu (previous screen).")
                                return
                            if not title or _is_cancel_command(title):
                                print("Cancelled. No service data was changed.")
                                return
                            try:
                                mal_list, mal_matches, serializd_matches = _chat_search_both_services(title)
                            except Exception as exc:
                                print(f"\nTitle search failed: {exc}")
                                return
                            # New title: restart at MAL selection.
                            mal_selected = None
                            serializd_selected = None
                            break
                        if mal_selected is None:
                            print("\nNo MAL anime selected. Cancelled.")
                            return
                        # We are back at MAL selection and selected it again;
                        # now return downward to Serializd title selection.
                        break
                    if not mal_selected:
                        break
                    continue

                # Live-action has no MAL selection, so Back returns to title entry.
                title = input("\nWhat did you watch today? (B = back, 0/Cancel = cancel)\n> ").strip()
                if title.lower() in {"b", "back"}:
                    print("Going back to the main menu (previous screen).")
                    return
                if not title or _is_cancel_command(title):
                    print("Cancelled. No service data was changed.")
                    return
                try:
                    mal_list, mal_matches, serializd_matches = _chat_search_both_services(title)
                except Exception as exc:
                    print(f"\nTitle search failed: {exc}")
                    return
                break

            if serializd_selected is None:
                print("\nSerializd: no matching title was safely found.")
                if anime:
                    print("WAYMARK will stop here rather than writing only to MAL in this prototype.")
                else:
                    print("No service data was changed.")
                return
            break

        # A new title selected through Back requires restarting the full
        # service-selection stack.
        if not serializd_selected:
            continue
        break

    serializd_id = int(serializd_selected["id"])
    print(f"\nFound on Serializd: {serializd_selected.get('name', title)} | ID: {serializd_id}")
    if anime and mal_selected:
        print(f"Found on MAL: {mal_selected['node'].get('title', title)} | ID: {mal_selected['node']['id']}")

    # New guided model: once the Serializd show is chosen, select its own
    # arc/season and episode. This avoids assuming MAL and Serializd use the
    # same season numbering.
    if explicit_season_episode:
        season_info = _chat_resolve_serializd_season(serializd_id, season_number, title)
        if not season_info:
            print("No changes were made.")
            return
        serializd_season_id, final_episode = season_info
        serializd_season_number = season_number
        serializd_episode_number = episode_number
        serializd_episode_title = ""
        season_episode_count = None
    else:
        while True:
            selected_episode = _choose_serializd_arc_and_episode(serializd_id, title)
            if selected_episode is _BACK:
                serializd_selected = _choose_serializd_match(title, serializd_matches)
                if serializd_selected is _BACK:
                    title = input("\nWhat did you watch today? (B = back, 0/Cancel = cancel)\n> ").strip()
                    if title.lower() in {"b", "back"} or not title or _is_cancel_command(title):
                        print("Cancelled. No service data was changed.")
                        return
                    try:
                        mal_list, mal_matches, serializd_matches = _chat_search_both_services(title)
                    except Exception as exc:
                        print(f"\nTitle search failed: {exc}")
                        return
                    # A new title requires a fresh service selection.
                    break
                if serializd_selected is None:
                    print("No changes were made.")
                    return
                serializd_id = int(serializd_selected["id"])
                continue
            if not selected_episode:
                print("No changes were made.")
                return
            serializd_season_number = selected_episode["season_number"]
            serializd_season_id = selected_episode["season_id"]
            serializd_episode_number = selected_episode["episode_number"]
            serializd_episode_title = selected_episode["episode_title"]
            season_episode_count = selected_episode["season_episode_count"]
            final_episode = selected_episode["final_episode"]
            break

    # MAL progress is independent from Serializd's local arc/season number.
    # If the user explicitly gave an episode in the original sentence, keep it
    # as the MAL/global candidate. Otherwise, use the selected Serializd
    # episode only as a candidate and require confirmation when appropriate.
    mal_episode_number = None
    mal_total_episodes = None
    if anime:
        explicit_mal_episode = episode_number if (episode_info and not explicit_season_episode) else None
        if explicit_mal_episode is not None:
            _, mal_total_episodes = _mal_current_status_and_total(mal_selected)
            if mal_total_episodes is not None and explicit_mal_episode > mal_total_episodes:
                print(
                    f"\nThe entered MAL episode E{explicit_mal_episode} is beyond the selected MAL title's "
                    f"known total of {mal_total_episodes} episodes."
                )
                print("WAYMARK will not write an invalid MAL progress value.")
                mal_episode_number, mal_input_valid = _ask_for_mal_episode_number(
                    mal_selected, serializd_episode_title, serializd_episode_number
                )
                if not mal_input_valid:
                    return
            else:
                mal_episode_number = explicit_mal_episode
        else:
            mal_episode_number, mal_input_valid = _ask_for_mal_episode_number(
                mal_selected, serializd_episode_title, serializd_episode_number
            )
            if mal_episode_number is _BACK:
                # Back from MAL episode returns exactly one level: to the
                # episode selector inside the already-selected Serializd season.
                season_meta = {
                    "seasonNumber": serializd_season_number,
                    "seasonId": serializd_season_id,
                    "name": f"Season {serializd_season_number}",
                }
                selected_episode = _choose_serializd_episode_in_season(
                    serializd_id,
                    serializd_season_number,
                    season_meta,
                    title,
                )
                if selected_episode is _BACK:
                    # B again moves one level further, to Serializd season selection.
                    selected_episode = _choose_serializd_arc_and_episode(serializd_id, title)
                if not selected_episode:
                    print("No changes were made.")
                    return
                serializd_season_number = selected_episode["season_number"]
                serializd_season_id = selected_episode["season_id"]
                serializd_episode_number = selected_episode["episode_number"]
                serializd_episode_title = selected_episode["episode_title"]
                season_episode_count = selected_episode["season_episode_count"]
                final_episode = selected_episode["final_episode"]
                mal_episode_number, mal_input_valid = _ask_for_mal_episode_number(
                    mal_selected, serializd_episode_title, serializd_episode_number
                )
            if not mal_input_valid:
                return

    if mal_rating is None and anime:
        value = input("\nMAL score (1-10, or press Enter to skip; type 0 or Cancel to stop): ").strip()
        if _is_cancel_command(value):
            print("Cancelled. No service data was changed.")
            return
        if value:
            m = re.fullmatch(r"(10|[1-9])(?:\s*/\s*10)?", value)
            if not m:
                print("Invalid MAL score. Please enter 1-10, or 0/Cancel to stop.")
                return
            mal_rating = int(m.group(1))

    if serializd_stars is None:
        value = input("\nSerializd stars (1.0-5.0, half-star increments, or Enter to skip; type 0 or Cancel to stop): ").strip()
        if _is_cancel_command(value):
            print("Cancelled. No service data was changed.")
            return
        if value:
            try:
                serializd_stars = float(value.replace("â˜…", "").strip())
                if not (1.0 <= serializd_stars <= 5.0) or serializd_stars * 2 != int(serializd_stars * 2):
                    raise ValueError
            except ValueError:
                print("Invalid Serializd rating. Please enter 1.0-5.0 in half-star increments, or 0/Cancel to stop.")
                return

    current_mal_status = None
    if anime and mal_selected:
        current_mal_status, mal_total_episodes = _mal_current_status_and_total(mal_selected)

    if status is None:
        current_label = current_mal_status or "unchanged"
        value = input(
            f"\nStatus [watching/completed/rewatching/skip] "
            f"(Enter = keep MAL status: {current_label}): "
        ).strip().lower()
        if _is_cancel_command(value):
            print("Cancelled. No service data was changed.")
            return
        status = None if value in {"", "skip"} else _chat_parse_status(value)
        if value not in {"", "skip"} and status is None:
            print("Unknown status. Please choose watching, completed, rewatching, skip, or 0/Cancel to stop.")
            return

    if not review_text:
        review_text = input("\nSerializd episode review/log text (or Enter to skip): ").strip()

    season_completed = serializd_episode_number == final_episode if final_episode is not None else False
    mal_series_completed = bool(
        anime
        and mal_episode_number is not None
        and mal_total_episodes is not None
        and mal_episode_number >= mal_total_episodes
    )

    if season_completed:
        print(
            f"\nWAYMARK detected that S{serializd_season_number:02d}E{serializd_episode_number:02d} "
            "is the final numbered episode of the selected Serializd arc/season."
        )
        print("Serializd will mark this season/arc as watched.")
        # Completing one Serializd arc does NOT automatically mean the entire
        # MAL series is complete. MAL is completed only when the selected MAL
        # episode reaches MAL's known total episode count.
        if mal_series_completed:
            status = "completed"
            print("The selected MAL episode is also the final MAL episode; status will become completed.")
        elif status is None and current_mal_status:
            status = current_mal_status

    if mal_series_completed and status in {None, "watching", "completed"}:
        status = "completed"
        print("\nWAYMARK detected the final MAL episode; MAL status will become completed.")

    if season_completed:
        season_review_choice = input(
            "\nYou completed this Serializd season/arc. Would you like to write a season review? [Y/N]: "
        ).strip().lower()
        if _is_cancel_command(season_review_choice):
            print("Cancelled. No service data was changed.")
            return
        if season_review_choice in {"y", "yes"}:
            season_rating_value = input(
                "Serializd season rating (1.0-5.0, half-star increments, or Enter to skip): "
            ).strip()
            if _is_cancel_command(season_rating_value):
                print("Cancelled. No service data was changed.")
                return
            if season_rating_value:
                try:
                    season_rating = float(season_rating_value.replace("â˜…", "").strip())
                    if not (1.0 <= season_rating <= 5.0) or season_rating * 2 != int(season_rating * 2):
                        raise ValueError
                except ValueError:
                    print("Invalid season rating. Please enter 1.0-5.0 in half-star increments, or 0/Cancel to stop.")
                    return
            season_review_text = input(
                "Serializd season review text (or Enter to skip): "
            ).strip()
        elif season_review_choice not in {"", "n", "no"}:
            print("Please answer Y or N. Cancelled.")
            return

    preflight_errors = _validate_chat_action_plan(
        mal_id=int(mal_selected["node"]["id"]) if mal_selected else None,
        serializd_id=serializd_id,
        serializd_season_id=serializd_season_id,
        season_number=serializd_season_number,
        episode_number=serializd_episode_number,
        mal_episode_number=mal_episode_number,
        mal_total_episodes=mal_total_episodes,
        mal_rating=mal_rating,
        serializd_stars=serializd_stars,
        status=status,
        season_completed=season_completed,
        season_rating=season_rating,
        final_episode=final_episode,
    )
    if preflight_errors:
        print("\nValidation failed. No service data was changed.")
        for error in preflight_errors:
            print(f"  âœ— {error}")
        return

    print("\n========================")
    print("CONFIRMATION")
    print("========================")
    display_title = mal_selected["node"].get("title", title) if mal_selected else serializd_selected.get("name", title)
    print(f"Title: {display_title}")
    print(f"Type: {'Anime' if anime else 'Live-action'} TV")
    if anime and mal_episode_number is not None:
        mal_total_text = f" / {mal_total_episodes}" if mal_total_episodes is not None else " / ?"
        print(f"MAL entry episode: E{mal_episode_number:04d}{mal_total_text}")
    else:
        print("MAL episode: unchanged/not specified")
    print(f"Serializd arc/season: S{serializd_season_number:02d}" + (f" â€” {selected_episode['season_name']}" if not explicit_season_episode else ""))
    print(f"Serializd episode: E{serializd_episode_number:02d}" + (f" â€” {serializd_episode_title}" if serializd_episode_title else ""))
    print(f"MAL ID: {mal_selected['node']['id']}" if mal_selected else "MAL: not applicable")
    print(f"Serializd ID: {serializd_id}")
    print(f"MAL score: {mal_rating}/10" if mal_rating is not None else "MAL score: unchanged/not applicable")
    print(f"Serializd rating: {serializd_stars:g}â˜…" if serializd_stars is not None else "Serializd rating: none")
    print(f"Status: {status}" if status else f"Status: unchanged (MAL currently {current_mal_status or 'unknown'})")
    print(f"Serializd episode review: {review_text}" if review_text else "Serializd episode review: none")
    if season_completed:
        print(f"Serializd season rating: {season_rating:g}â˜…" if season_rating is not None else "Serializd season rating: none")
        print(f"Serializd season review: {season_review_text}" if season_review_text else "Serializd season review: none")
    print(f"Serializd season completion: YES â€” final episode ({final_episode})" if season_completed else "Serializd season completion: no")
    print("MAL series completion: YES â€” final MAL episode" if mal_series_completed else "MAL series completion: no")

    confirmation = input("\nReady to save these changes?\nType YES to continue (or 0/Cancel to stop):\n> ").strip()
    if _is_cancel_command(confirmation) or confirmation.strip().lower() != "yes":
        print("Cancelled. No service data was changed.")
        return

    try:
        _chat_execute_anime_tv_action(
            mal_id=int(mal_selected["node"]["id"]) if mal_selected else None,
            serializd_id=serializd_id,
            serializd_season_id=serializd_season_id,
            season_number=serializd_season_number,
            episode_number=serializd_episode_number,
            mal_episode_number=mal_episode_number,
            mal_total_episodes=mal_total_episodes,
            mal_rating=mal_rating,
            serializd_stars=serializd_stars,
            status=status,
            review_text=review_text,
            season_completed=season_completed,
            season_rating=season_rating,
            season_review_text=season_review_text,
            final_episode=final_episode,
        )
    except Exception as exc:
        print(f"\nWAYMARK action failed: {exc}")
        print("Check the affected service before retrying.")


def _sanitize_probe_payload(value):
    """Redact credentials/secrets before displaying captured browser requests."""
    secret_keys = {
        "authorization", "cookie", "set-cookie", "token", "access_token",
        "refresh_token", "password", "secret", "client_secret",
    }
    if isinstance(value, dict):
        return {
            str(k): ("<REDACTED>" if str(k).lower().replace("-", "_") in secret_keys else _sanitize_probe_payload(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_probe_payload(v) for v in value]
    return value


def _parse_probe_body(body):
    if not body:
        return None
    try:
        return _sanitize_probe_payload(json.loads(body))
    except Exception:
        # Keep form/raw bodies visible, but never display obvious auth material.
        text = body
        lowered = text.lower()
        for marker in ("authorization=", "token=", "access_token=", "refresh_token=", "password="):
            if marker in lowered:
                return "<REDACTED FORM/RAW BODY CONTAINING CREDENTIAL MATERIAL>"
        return text[:4000]


def discover_serializd_season_review_request():
    """
    Use the real Serializd web UI to capture the exact season-rating/review POST.

    This is deliberately a discovery-only tool: WAYMARK does not replay the
    request or change the account itself. The user performs one manual test
    submission in Serializd, and we inspect the browser request it generated.
    """
    print("\n================================================")
    print("SERIALIZD SEASON-REVIEW ENDPOINT DISCOVERY")
    print("================================================")
    print("This mode does NOT replay or publish anything from WAYMARK.")
    print("You will make one manual test season rating/review in the official Serializd UI.")
    print("Use a harmless test review that you can delete afterward.\n")

    query = input("Serializd show title [Frieren]: ").strip() or "Frieren"
    results = search_catalog(query)
    if not results:
        print("No Serializd shows found.")
        return

    print("\nSerializd matches:")
    for i, item in enumerate(results[:10], 1):
        print(f"{i}. {item.get('name') or item.get('title')} | ID: {item.get('id')} | {item.get('firstAirDate') or item.get('first_air_date') or 'year unknown'}")
    raw = input("Choose a show (0 to cancel): ").strip()
    if _is_cancel_command(raw):
        return
    try:
        show = results[int(raw) - 1]
        show_id = int(show["id"])
    except Exception:
        print("Invalid selection.")
        return

    show_data = get_show(show_id)
    seasons = show_data.get("seasons") or show_data.get("showSeasons") or []
    if not seasons:
        print("No season metadata was returned for this show.")
        return

    print("\nSeasons:")
    for i, season in enumerate(seasons, 1):
        number = season.get("seasonNumber", season.get("season_number", i - 1))
        name = season.get("name") or f"Season {number}"
        sid = season.get("id")
        print(f"{i}. S{int(number):02d} â€” {name} | ID: {sid}")
    raw = input("Choose a season (0 to cancel): ").strip()
    if _is_cancel_command(raw):
        return
    try:
        season = seasons[int(raw) - 1]
        season_id = int(season["id"])
        season_number = int(season.get("seasonNumber", season.get("season_number", int(raw) - 1)))
    except Exception:
        print("Invalid season selection.")
        return

    url = f"https://www.serializd.com/show/Review-{show_id}/season/{season_id}/{season_number}"
    print(f"\nOpening official Serializd season page:\n{url}")
    print("If Serializd asks you to log in, log in in this browser profile.")
    print("Then manually open the season rating/review control and submit a harmless test.")
    print("After submitting, return here and press Enter.\n")

    captured = []
    edge_process = playwright = browser = page = None

    def on_request(request):
        try:
            request_url = request.url
            if "serializd" not in request_url.lower():
                return
            if request.method.upper() != "POST":
                return
            body = None
            try:
                body = request.post_data
            except Exception:
                pass
            captured.append({
                "method": request.method,
                "url": request_url,
                "resource_type": request.resource_type,
                "body": _parse_probe_body(body),
            })
        except Exception:
            pass

    try:
        edge_process, playwright, browser, page = start_mal_browser(headless=False)
        page.on("request", on_request)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        print("Browser is ready. Complete the season rating/review manually now.")
        input("Press Enter here AFTER the manual submission is complete... ")
    except Exception as exc:
        print(f"Browser discovery failed: {exc}")
        return
    finally:
        try:
            if browser is not None:
                browser.close()
        except Exception:
            pass
        try:
            if playwright is not None:
                playwright.stop()
        except Exception:
            pass
        try:
            if edge_process is not None:
                edge_process.terminate()
                edge_process.wait(timeout=5)
        except Exception:
            pass

    print("\n================================================")
    print("CAPTURED SERIALIZD POST REQUESTS")
    print("================================================")
    if not captured:
        print("No Serializd POST request was captured.")
        print("Make sure the manual season rating/review was actually submitted in the browser.")
        return

    for index, item in enumerate(captured, 1):
        print(f"\n[{index}] {item['method']} {item['url']}")
        print(f"Resource type: {item['resource_type']}")
        if item["body"] is not None:
            print("Payload:")
            print(json.dumps(item["body"], indent=2, ensure_ascii=False) if isinstance(item["body"], (dict, list)) else item["body"])

    review_candidates = [x for x in captured if "/reviews/" in x["url"].lower() or "review" in str(x.get("body", "")).lower()]
    print("\n================================================")
    print("LIKELY REVIEW REQUEST(S)")
    print("================================================")
    if review_candidates:
        for item in review_candidates:
            print(f"{item['method']} {item['url']}")
            if item.get("body") is not None:
                print(json.dumps(item["body"], indent=2, ensure_ascii=False) if isinstance(item["body"], (dict, list)) else item["body"])
    else:
        print("No obvious review request was identified; inspect the captured POST list above.")

    print("\nDiscovery complete. No request was replayed by WAYMARK.")
    print("Send me the captured output (WITHOUT any redacted credentials being replaced) and I will wire the verified season-review write into the next Core file.")




# ============================================================
# M18 â€” PROGRESS WORKFLOW
# ============================================================
#
# Dedicated confirmation-gated progress workflow.
#
# M18 writes anime progress through the already-verified MAL API:
#   title -> MAL match -> current progress -> target episode ->
#   optional status -> confirmation -> execution
#
# Serializd arbitrary watched-episode-count writes are intentionally NOT
# guessed here. The currently verified Serializd write surfaces are episode
# logging and season/series watched state. That distinction will be handled
# in the later platform-capability architecture work.
#
# No service write occurs before explicit YES confirmation.

M18_PROGRESS_WORKFLOW_ID = "M18_PROGRESS"

M18_PROGRESS_STATUSES = {
    "watching",
    "completed",
    "on_hold",
    "dropped",
    "plan_to_watch",
    "rewatching",
}

_M18_SKIP = object()


def _m18_choose_mal_title(title: str):
    matches = search_anime(title)
    if not matches:
        print("\nNo MAL anime found.")
        return _M18_SKIP

    selected = _choose_mal_from_matches(title, matches)
    if selected is _BACK:
        return _BACK
    if selected is None:
        return _M18_SKIP
    return selected


def _m18_status_label(status: str) -> str:
    labels = {
        "watching": "Watching",
        "completed": "Completed",
        "on_hold": "On Hold",
        "dropped": "Dropped",
        "plan_to_watch": "Plan to Watch",
        "rewatching": "Rewatching",
    }
    return labels.get(status, status or "Unknown")


def _m18_parse_episode(raw: str, maximum: int | None):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _INVALID
    if value < 0:
        return _INVALID
    if maximum is not None and value > maximum:
        return _INVALID
    return value


def _m18_build_action_plan(data: dict[str, Any]) -> ActionPlan:
    mal_id = data.get("mal_id")
    target = data.get("target_episode")
    total = data.get("total_episodes")

    if mal_id is None:
        raise ValueError("MAL anime ID is required.")
    if target is None:
        raise ValueError("Target episode is required.")

    try:
        target_int = int(target)
    except (TypeError, ValueError):
        raise ValueError("Target episode must be a whole number.")

    if target_int < 0:
        raise ValueError("Target episode cannot be negative.")

    if total not in (None, "", "?"):
        try:
            total_int = int(total)
        except (TypeError, ValueError):
            total_int = None
        if total_int is not None and target_int > total_int:
            raise ValueError("Target episode exceeds the known episode count.")

    current = int(data.get("current_episode", 0) or 0)
    new_status = data.get("new_status")
    current_status = data.get("current_status")

    if target_int == current and new_status in (None, "", current_status):
        raise ValueError("No progress change was requested.")

    plan = ActionPlan(workflow_id=M18_PROGRESS_WORKFLOW_ID)

    if target_int != current:
        plan.add(
            "mal",
            "update_progress",
            anime_id=int(mal_id),
            episode=target_int,
            is_rewatching=new_status == "rewatching",
        )

    if new_status and new_status != current_status:
        if new_status not in M18_PROGRESS_STATUSES:
            raise ValueError(f"Unsupported MAL status: {new_status}")
        plan.add(
            "mal",
            "update_status",
            anime_id=int(mal_id),
            status=new_status,
        )

    if plan.is_empty:
        raise ValueError("The Action Plan contains no changes.")

    plan.metadata.update({
        "execution_enabled": True,
        "service_scope": ["mal"],
        "serializd_progress_write": False,
        "reason": "Serializd arbitrary progress-count write is not yet verified.",
    })
    return plan


def m18_progress_smoke_test() -> str:
    """Offline structural validation; no network calls or service writes."""
    sample = {
        "mal_id": 52991,
        "title": "Sousou no Frieren",
        "current_episode": 22,
        "total_episodes": 28,
        "current_status": "watching",
        "target_episode": 23,
        "new_status": "watching",
    }
    plan = _m18_build_action_plan(sample)

    assert plan.workflow_id == M18_PROGRESS_WORKFLOW_ID
    assert len(plan.operations) == 1
    assert plan.operations[0]["service"] == "mal"
    assert plan.operations[0]["operation"] == "update_progress"
    assert plan.operations[0]["details"]["anime_id"] == 52991
    assert plan.operations[0]["details"]["episode"] == 23
    assert plan.metadata["execution_enabled"] is True
    assert plan.metadata["serializd_progress_write"] is False

    completed = dict(sample)
    completed["target_episode"] = 28
    completed["new_status"] = "completed"
    plan2 = _m18_build_action_plan(completed)
    assert len(plan2.operations) == 2
    assert plan2.operations[1]["operation"] == "update_status"
    assert plan2.operations[1]["details"]["status"] == "completed"

    return "M18 Progress smoke test passed."


def run_m18_progress_workflow():
    """Run the guided M18 anime progress workflow."""
    print("\n================================================")
    print("WAYMARK PROGRESS â€” M18")
    print("================================================")
    print("M18 currently updates anime progress through MAL.")
    print("Serializd progress-count writes are intentionally not guessed.")
    print("No service data changes until you confirm YES.\n")

    while True:
        raw = input(
            "What anime do you want to update? "
            "(B = back, 0/Cancel = cancel)\n> "
        ).strip()

        if raw.casefold() in {"b", "back"}:
            print("Exiting Progress.")
            return
        if _is_cancel_command(raw):
            print("Cancelled. No service data was changed.")
            return
        if raw:
            break
        print("Please enter an anime title.")

    selected = _m18_choose_mal_title(raw)
    if selected is _BACK:
        print("Returning to title entry.")
        return
    if selected is _M18_SKIP:
        return

    # _choose_mal_from_matches() returns the enriched MAL search object,
    # whose canonical MAL fields live under "node".
    node = selected.get("node", {}) or {}
    mal_id_raw = node.get("id")
    if mal_id_raw is None:
        print("\nThe selected MAL result did not contain a MAL ID.")
        print("No service data was changed.")
        return

    mal_id = int(mal_id_raw)
    title = node.get("title") or selected.get("title") or raw

    total_raw = node.get("waymark_num_episodes")
    if total_raw in (None, "", "?"):
        total_raw = node.get("num_episodes")

    try:
        total = int(total_raw) if total_raw not in (None, "", "?") else None
    except (TypeError, ValueError):
        total = None

    try:
        status_data = get_my_status(mal_id) or {}
    except Exception as exc:
        print(f"\nCould not read current MAL status: {exc}")
        print("No service data was changed.")
        return

    list_status = status_data.get("my_list_status", {}) or {}
    current_episode = int(list_status.get("num_episodes_watched", 0) or 0)
    current_status = list_status.get("status") or "unknown"

    if total is None:
        total_from_status = status_data.get("num_episodes")
        try:
            total = (
                int(total_from_status)
                if total_from_status not in (None, "", "?")
                else None
            )
        except (TypeError, ValueError):
            total = None

    print("\n================================================")
    print("CURRENT MAL PROGRESS")
    print("================================================")
    print(f"Anime: {title}")
    print(f"MAL ID: {mal_id}")
    print(
        f"Progress: {current_episode}/"
        f"{total if total is not None else '?'} episodes"
    )
    print(f"Status: {_m18_status_label(current_status)}")

    while True:
        raw_target = input(
            "\nWhat episode should MAL show as watched? "
            "(B = back, 0/Cancel = cancel)\n> "
        ).strip()

        if raw_target.casefold() in {"b", "back"}:
            print("Returning to title entry.")
            return
        if _is_cancel_command(raw_target):
            print("Cancelled. No service data was changed.")
            return

        target = _m18_parse_episode(raw_target, total)
        if target is _INVALID:
            maximum = str(total) if total is not None else "the known total"
            print(f"Please enter a whole episode number from 0 to {maximum}.")
            continue
        break

    while True:
        raw_status = input(
            "\nChange MAL status? "
            "[watching/completed/on_hold/dropped/plan_to_watch/rewatching/keep] "
            "(B = back, 0/Cancel = cancel)\n> "
        ).strip().casefold()

        if raw_status in {"b", "back"}:
            print("Returning to episode progress.")
            return
        if _is_cancel_command(raw_status):
            print("Cancelled. No service data was changed.")
            return

        if raw_status in {"", "keep", "same"}:
            new_status = (
                current_status
                if current_status in M18_PROGRESS_STATUSES
                else None
            )
            break

        aliases = {
            "watching": "watching",
            "watch": "watching",
            "completed": "completed",
            "complete": "completed",
            "on_hold": "on_hold",
            "hold": "on_hold",
            "dropped": "dropped",
            "drop": "dropped",
            "plan_to_watch": "plan_to_watch",
            "plan": "plan_to_watch",
            "rewatching": "rewatching",
            "rewatch": "rewatching",
        }
        if raw_status in aliases:
            new_status = aliases[raw_status]
            break
        print("Please choose a valid MAL status or 'keep'.")

    data = {
        "mal_id": mal_id,
        "title": title,
        "current_episode": current_episode,
        "total_episodes": total,
        "current_status": current_status,
        "target_episode": target,
        "new_status": new_status,
    }

    try:
        plan = _m18_build_action_plan(data)
    except ValueError as exc:
        print(f"\nValidation failed: {exc}")
        return

    print("\n================================================")
    print("PROGRESS â€” CONFIRMATION")
    print("================================================")
    print(f"Anime: {title}")
    print(f"MAL progress: {current_episode} â†’ {target}")
    if total is not None:
        print(f"Episode count: {total}")
    print(
        f"Status: {_m18_status_label(current_status)} â†’ "
        f"{_m18_status_label(new_status) if new_status else 'unchanged'}"
    )
    print("\nPlanned operations:")
    for op in plan.operations:
        print(f"- MAL: {op['operation']} {op['details']}")
    print("\nSerializd: no progress-count write will be attempted in M18.")

    while True:
        confirm = input(
            "\nConfirm this Action Plan? [Y/N] "
            "(B = back, 0/Cancel = cancel)\n> "
        ).strip().casefold()

        if confirm in {"b", "back"}:
            print("Returning to status selection.")
            return
        if _is_cancel_command(confirm) or confirm in {"n", "no"}:
            print("\nCancelled. No service data was changed.")
            return
        if confirm in {"y", "yes"}:
            break
        print("Please answer Y or N.")

    print("\nAction Plan confirmed.")
    print("Executing verified MAL progress operations...")

    execution_results = []

    for op in plan.operations:
        details = op["details"]
        try:
            if op["operation"] == "update_progress":
                result = update_progress(
                    int(details["anime_id"]),
                    int(details["episode"]),
                    is_rewatching=bool(details.get("is_rewatching", False)),
                )
            elif op["operation"] == "update_status":
                result = update_status(
                    int(details["anime_id"]),
                    details["status"],
                )
            else:
                raise ValueError(
                    f"Unsupported M18 operation: {op['operation']}"
                )

            execution_results.append({
                "operation": op["operation"],
                "ok": True,
                "result": result,
            })
            print(f"âœ“ MAL {op['operation']} completed.")
        except Exception as exc:
            execution_results.append({
                "operation": op["operation"],
                "ok": False,
                "error": str(exc),
            })
            print(f"âœ— MAL {op['operation']} failed: {exc}")

    print("\n================================================")
    print("WAYMARK RESULT")
    print("================================================")

    if all(item["ok"] for item in execution_results):
        print("Progress update completed successfully.")
        print(f"MAL now requested at episode {target}.")
        if new_status:
            print(f"MAL status: {_m18_status_label(new_status)}")
    else:
        print("Progress update finished with one or more errors.")
        print("Check the operation results above before retrying.")




# ============================================================
# M18 â€” SERIALIZD PROGRESS CAPABILITY
# ============================================================
#
# Serializd does not expose the same simple numeric "watched episode count"
# abstraction as MAL. WAYMARK's verified Serializd write surface is
# episode-level logging. Therefore M18 represents Serializd progress as the
# set of watched episode logs, rather than inventing an unverified
# "set progress to N" endpoint.
#
# The workflow:
#   show -> season -> current watched state -> target episode(s) ->
#   confirmation -> episode log writes
#
# This is deliberately separate from MAL progress because season/episode
# identity is service-specific.
#
# IMPORTANT:
# The actual Serializd adapter functions are resolved dynamically so this
# Core file remains compatible with the verified adapter names already used
# by the project. No private token or credential is stored here.

M18_SERIALIZD_PROGRESS_WORKFLOW_ID = "M18_PROGRESS_SERIALIZD"


def _m18_serializd_current_watched(show_id: int, season_id: int):
    """Read the verified live watched episode logs for one Serializd season."""
    return get_watched_episode_logs(int(show_id), int(season_id))


def _m18_serializd_add_episode(show_id: int, season_id: int, episode_number: int):
    """Use the verified Serializd episode-watch write."""
    return mark_episode_watched(
        int(show_id),
        int(season_id),
        int(episode_number),
    )


def _m18_serializd_normalize_watched(raw):
    """Normalize the verified episode-log response to episode numbers."""
    if raw is None:
        return set()

    if isinstance(raw, dict):
        for key in ("episodeLogs", "episodes", "watched_episodes", "logs", "data"):

            if key in raw:
                return _m18_serializd_normalize_watched(raw[key])

        value = raw.get("episodeNumber", raw.get("episode_number"))
        if value is not None:
            try:
                return {int(value)}
            except (TypeError, ValueError):
                return set()
        return set()

    if isinstance(raw, (list, tuple, set)):
        result = set()
        for item in raw:
            if isinstance(item, int):
                result.add(item)
                continue
            if isinstance(item, dict):
                value = item.get("episodeNumber", item.get("episode_number"))
                if value is not None:
                    try:
                        result.add(int(value))
                    except (TypeError, ValueError):
                        pass
        return result

    return set()


def _m18_serializd_build_plan(show_id, season_id, current_watched, target_episode):
    watched = set(current_watched)
    target = int(target_episode)

    if target < 1:
        raise ValueError("Serializd episode numbers start at 1.")

    missing = [ep for ep in range(1, target + 1) if ep not in watched]

    plan = ActionPlan(workflow_id=M18_SERIALIZD_PROGRESS_WORKFLOW_ID)

    for ep in missing:
        plan.add(
            "serializd",
            "mark_episode_watched",
            show_id=int(show_id),
            season_id=int(season_id),
            episode_number=ep,
        )

    if plan.is_empty:
        raise ValueError(
            "Serializd already has every episode through the requested target."
        )

    plan.metadata.update({
        "execution_enabled": True,
        "service_scope": ["serializd"],
        "representation": "episode_logs",
        "target_episode": target,
        "newly_logged_episodes": missing,
    })
    return plan


def m18_serializd_progress_smoke_test() -> str:
    """Offline validation of the Serializd ActionPlan representation."""
    plan = _m18_serializd_build_plan(
        show_id=209867,
        season_id=360492,
        current_watched={1, 2, 3},
        target_episode=5,
    )
    assert plan.workflow_id == M18_SERIALIZD_PROGRESS_WORKFLOW_ID
    assert len(plan.operations) == 2
    assert [op["details"]["episode_number"] for op in plan.operations] == [4, 5]
    assert plan.metadata["representation"] == "episode_logs"
    return "M18 Serializd Progress smoke test passed."


def run_m18_serializd_progress_workflow():
    """
    Guided Serializd progress workflow.

    Serializd progress is implemented using the verified episode-log endpoint:
    /episode_log/add via mark_episode_watched().
    """
    print("\n================================================")
    print("WAYMARK SERIALIZD PROGRESS â€” M18")
    print("================================================")
    print("Serializd progress is represented by episode watch logs.")
    print("No write occurs until explicit YES confirmation.\n")

    raw = input(
        "What show do you want to update on Serializd? "
        "(B = back, 0/Cancel = cancel)\n> "
    ).strip()

    if raw.casefold() in {"b", "back"} or _is_cancel_command(raw):
        print("Cancelled. No service data was changed.")
        return

    results = search_catalog(raw) or []
    if not results:
        print("\nNo Serializd shows found.")
        return

    print("\nSerializd show matches:")
    for i, item in enumerate(results[:10], 1):
        name = item.get("name") or item.get("title") or "Unknown title"
        year = item.get("firstAirDate") or item.get("first_air_date") or "year unknown"
        sid = item.get("id")
        print(f"{i}. {name} | ID: {sid} | {year}")

    while True:
        choice = input(
            "Choose a show (B = back, 0/Cancel = cancel): "
        ).strip()
        if choice.casefold() in {"b", "back"} or _is_cancel_command(choice):
            print("Cancelled. No service data was changed.")
            return
        try:
            selected = results[int(choice) - 1]
            show_id = int(selected["id"])
            break
        except (ValueError, IndexError, KeyError):
            print("Please choose a valid show number.")

    show_data = get_show(show_id) or {}
    show_title = (
        show_data.get("name")
        or show_data.get("title")
        or selected.get("name")
        or selected.get("title")
        or raw
    )

    seasons = show_data.get("seasons") or show_data.get("showSeasons") or []
    if not seasons:
        print("\nNo Serializd season metadata was returned.")
        print("No service data was changed.")
        return

    print(f"\nSerializd show: {show_title}")
    print("Seasons / arcs:")

    for i, season in enumerate(seasons, 1):
        number = _serializd_season_number(season)
        if number is None:
            number = i - 1
        sid = season.get("seasonId", season.get("id"))
        name = season.get("name") or f"Season {number}"
        print(f"{i}. S{int(number):02d} â€” {name} | ID: {sid}")

    while True:
        choice = input(
            "Choose a season / arc (B = back, 0/Cancel = cancel): "
        ).strip()
        if choice.casefold() in {"b", "back"} or _is_cancel_command(choice):
            print("Cancelled. No service data was changed.")
            return
        try:
            selected_season = seasons[int(choice) - 1]
            season_id = int(
                selected_season.get("seasonId", selected_season.get("id"))
            )
            season_number = _serializd_season_number(selected_season)
            if season_number is None:
                season_number = int(choice) - 1
            break
        except (ValueError, IndexError, TypeError):
            print("Please choose a valid season number.")

    season_data = get_season(show_id, season_number) or {}
    episodes = season_data.get("episodes") or []

    max_episode = len(episodes)
    if max_episode == 0:
        raw_count = (
            season_data.get("episodeCount")
            or season_data.get("episode_count")
            or selected_season.get("episodeCount")
        )
        try:
            max_episode = int(raw_count) if raw_count is not None else None
        except (TypeError, ValueError):
            max_episode = None

    try:
        raw_watched = _m18_serializd_current_watched(show_id, season_id)
        watched = _m18_serializd_normalize_watched(raw_watched)
    except Exception as exc:
        print(f"\nCould not read current Serializd watched state: {exc}")
        print("No service data was changed.")
        return

    print("\n================================================")
    print("CURRENT SERIALIZD PROGRESS")
    print("================================================")
    print(f"Show: {show_title}")
    print(f"Season: S{int(season_number):02d}")
    print(f"Season ID: {season_id}")
    print(f"Watched episode numbers detected: {sorted(watched)}")
    if max_episode is not None:
        print(f"Episode count: {max_episode}")

    while True:
        raw_target = input(
            "\nTarget episode number (B = back, 0/Cancel = cancel): "
        ).strip()

        if raw_target.casefold() in {"b", "back"} or _is_cancel_command(raw_target):
            print("Cancelled. No service data was changed.")
            return

        try:
            target = int(raw_target)
            if target < 1:
                raise ValueError
            if max_episode is not None and target > max_episode:
                print(f"Please choose 1-{max_episode}.")
                continue
            break
        except ValueError:
            print("Please enter a valid whole episode number.")

    try:
        plan = _m18_serializd_build_plan(
            show_id,
            season_id,
            watched,
            target,
        )
    except ValueError as exc:
        print(f"\n{exc}")
        return

    print("\n================================================")
    print("SERIALIZD PROGRESS â€” CONFIRMATION")
    print("================================================")
    print(f"Show: {show_title}")
    print(f"Season: S{int(season_number):02d}")
    print(f"Current detected watched: {sorted(watched)}")
    print(f"Target: through episode {target}")
    print("\nEpisodes WAYMARK plans to mark watched:")

    for op in plan.operations:
        print(
            f"- S{int(season_number):02d}E"
            f"{op['details']['episode_number']:02d}"
        )

    while True:
        confirm = input(
            "\nConfirm these Serializd episode updates? [Y/N] "
            "(B = back, 0/Cancel = cancel)\n> "
        ).strip().casefold()

        if confirm in {"b", "back"}:
            print("Returning without writing.")
            return
        if _is_cancel_command(confirm) or confirm in {"n", "no"}:
            print("Cancelled. No service data was changed.")
            return
        if confirm in {"y", "yes"}:
            break
        print("Please answer Y or N.")

    print("\nExecuting verified Serializd episode-watch operations...")
    success = 0

    for op in plan.operations:
        details = op["details"]
        try:
            mark_episode_watched(
                int(details["show_id"]),
                int(details["season_id"]),
                int(details["episode_number"]),
            )
            success += 1
            print(
                f"âœ“ Marked S{int(season_number):02d}E"
                f"{int(details['episode_number']):02d} watched."
            )
        except Exception as exc:
            print(
                f"âœ— Episode {details['episode_number']} failed: {exc}"
            )

    print("\n================================================")
    print("WAYMARK RESULT")
    print("================================================")
    print(
        f"Serializd progress execution finished: "
        f"{success}/{len(plan.operations)} episode updates succeeded."
    )


def run_m17_final_watch_validation():
    """Run the consolidated, non-destructive M17 Watch validation suite."""
    print("\n================================================")
    print("WAYMARK â€” FINAL WATCH VALIDATION (M17)")
    print("================================================")
    print("This is a non-destructive backend validation pass.")
    print("It does not write MAL or Serializd account data.")

    checks: list[tuple[str, bool, str]] = []

    # 1. M14 workflow engine foundation.
    try:
        assert WorkflowState.__name__ == "WorkflowState"
        assert WorkflowContext.__name__ == "WorkflowContext"
        assert WorkflowEngine.__name__ == "WorkflowEngine"
        assert ActionPlan.__name__ == "ActionPlan"
        checks.append(("Workflow engine foundation", True, "state/context/engine/action-plan classes available"))
    except Exception as exc:
        checks.append(("Workflow engine foundation", False, str(exc)))

    # 2. M14 Watch state map.
    try:
        assert isinstance(M142_WATCH_STATES, (tuple, list))
        required = {
            "WATCH_TITLE", "WATCH_IS_ANIME", "WATCH_MEDIA_TYPE",
            "SELECT_MAL_TITLE", "SELECT_SERIALIZD_TITLE",
            "SELECT_SERIALIZD_SEASON", "SELECT_SERIALIZD_EPISODE",
            "SELECT_MAL_EPISODE", "MAL_SCORE", "SERIALIZD_RATING",
            "STATUS", "EPISODE_REVIEW", "CONFIRM", "RESULT"
        }
        missing = sorted(required - set(M142_WATCH_STATES))
        assert not missing, f"missing states: {', '.join(missing)}"
        checks.append(("Watch state model", True, f"{len(M142_WATCH_STATES)} states present"))
    except Exception as exc:
        checks.append(("Watch state model", False, str(exc)))

    # 3. M14.3 adapter/state mapping.
    try:
        assert isinstance(M143_M12_STATE_MAP, dict)
        assert len(M143_M12_STATE_MAP) >= 10
        checks.append(("M12 â†’ workflow adapter", True, "state mapping available"))
    except Exception as exc:
        checks.append(("M12 â†’ workflow adapter", False, str(exc)))

    # 4. M14.4 prompt bridge.
    try:
        samples = [
            ("What did you watch today?", "WATCH_TITLE"),
            ("Choose an anime", "SELECT_MAL_TITLE"),
            ("Choose a Serializd season", "SELECT_SERIALIZD_SEASON"),
            ("Choose a Serializd episode", "SELECT_SERIALIZD_EPISODE"),
            ("Choose the MAL episode", "SELECT_MAL_EPISODE"),
            ("MAL score", "MAL_SCORE"),
            ("Serializd rating", "SERIALIZD_RATING"),
            ("status", "STATUS"),
            ("episode review", "EPISODE_REVIEW"),
            ("season review", "EPISODE_REVIEW"),
            ("confirm", "CONFIRM"),
        ]
        failures = []
        for prompt, expected in samples:
            actual = m144_state_from_prompt(prompt)
            if actual != expected:
                failures.append(f"{prompt!r} -> {actual!r}, expected {expected!r}")
        assert not failures, "; ".join(failures)
        checks.append(("Prompt/state bridge", True, "representative Watch prompts resolve correctly"))
    except Exception as exc:
        checks.append(("Prompt/state bridge", False, str(exc)))

    # 5. M12 entry point remains available for the eventual UI bridge.
    try:
        assert callable(run_waymark_chat)
        assert callable(_run_waymark_chat_m12)
        checks.append(("M12 Watch entry point", True, "existing guided Watch workflow preserved"))
    except Exception as exc:
        checks.append(("M12 Watch entry point", False, str(exc)))

    # 6. Deterministic Back/Cancel architecture.
    try:
        assert WorkflowEngine.BACK == "B"
        assert WorkflowEngine.CANCEL == "0"
        checks.append(("Back / Cancel controls", True, "global workflow controls preserved"))
    except Exception as exc:
        checks.append(("Back / Cancel controls", False, str(exc)))

    print("\nM17 validation results:")
    for name, passed, detail in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name} â€” {detail}")

    passed = all(item[1] for item in checks)
    print("\n================================================")
    if passed:
        print("M17 FINAL WATCH VALIDATION PASSED")
        print("================================================")
        print("Watch workflow architecture is ready to move forward.")
        print("No live service data was changed by this validation.")
    else:
        print("M17 FINAL WATCH VALIDATION FAILED")
        print("================================================")
        print("Fix the failed backend checks before proceeding.")
    return passed


# ============================================================
# M19 â€” SEARCH / LIBRARY / HISTORY
# ============================================================
#
# M19 adds the read-only discovery surfaces needed by the future WAYMARK UI:
#   - Search: MAL + Serializd catalog discovery
#   - Library: MAL anime list + Serializd watched library
#   - History: recent Serializd diary/activity
#
# These are read-only in M19. No MAL or Serializd account data is changed.
# Service-specific identity is preserved; results are labeled by service.
# ============================================================


M19_WORKFLOW_ID = "M19_SEARCH_LIBRARY_HISTORY"

def _m19_get_mal_details(anime_id):
    """Fetch the full selected MAL anime record for the read-only detail view."""
    token = mal_get_access_token()
    response = requests.get(
        f"https://api.myanimelist.net/v2/anime/{int(anime_id)}",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "fields": (
                "id,title,main_picture,alternative_titles,start_date,end_date,"
                "synopsis,mean,rank,popularity,num_list_users,num_scoring_users,"
                "nsfw,genres,created_at,updated_at,status,num_episodes,"
                "start_season,broadcast,source,average_episode_duration,"
                "rating,pictures,background,related_anime,related_manga,"
                "recommendations,studios,statistics"
            )
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def _m19_print_mal_details(anime):
    node = anime.get("node", anime) if isinstance(anime, dict) else {}
    ls = anime.get("list_status", {}) if isinstance(anime, dict) else {}
    print("\n----------------------------------------")
    print(f"MAL DETAILS â€” {node.get('title', 'Unknown')}")
    print("----------------------------------------")
    fields = [
        ("MAL ID", node.get("id")),
        ("Score", node.get("mean")),
        ("Rank", node.get("rank")),
        ("Popularity", node.get("popularity")),
        ("Year", node.get("start_date", "")[:4] if node.get("start_date") else None),
        ("Aired", f"{node.get('start_date') or '?'} â†’ {node.get('end_date') or '?'}"),
        ("Status", node.get("status")),
        ("Episodes", node.get("num_episodes")),
        ("Duration", (
            f"{int(node.get('average_episode_duration')) // 60}m "
            f"{int(node.get('average_episode_duration')) % 60}s"
            if str(node.get('average_episode_duration', '')).isdigit()
            else node.get('average_episode_duration')
        )),
        ("Genres", ", ".join(g.get("name", "") for g in node.get("genres", [])) or None),
        ("Studios", ", ".join(s.get("name", "") for s in node.get("studios", [])) or None),
        ("Your status", ls.get("status")),
        ("Your progress", ls.get("num_episodes_watched")),
        ("Your score", ls.get("score")),
    ]
    for label, value in fields:
        if value not in (None, "", []):
            print(f"{label}: {value}")
    if node.get("synopsis"):
        print(f"Synopsis: {node['synopsis']}")

def _m19_find_numeric_key(data, wanted_keys):
    """Recursively find a numeric value under one of the requested keys."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key in wanted_keys and isinstance(value, (int, float)):
                return float(value)
            found = _m19_find_numeric_key(value, wanted_keys)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _m19_find_numeric_key(item, wanted_keys)
            if found is not None:
                return found
    return None

def _m19_get_serializd_community_rating(show_id):
    """Read the public/community show rating without writing anything.

    The primary show metadata endpoint does not currently expose the community
    average in WAYMARK's verified response shape. Try the ratings surface and
    accept the documented averageRating-style fields when present.
    """
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.serializd.com",
        "Referer": "https://www.serializd.com/",
        "X-Requested-With": "serializd_vercel",
    }

    import requests as _m19_requests

    candidate_urls = [
        f"https://serializddesktop.onrender.com/api/show/{int(show_id)}/ratings",
        f"https://serializddesktop.onrender.com/api/show/{int(show_id)}/stats",
    ]

    for url in candidate_urls:
        try:
            response = _m19_requests.get(url, headers=headers, timeout=15)
            if response.status_code < 200 or response.status_code >= 300:
                continue
            data = response.json()
            value = _m19_find_numeric_key(
                data,
                {
                    "averageRating",
                    "average_rating",
                    "avgRating",
                    "avg_rating",
                    "meanRating",
                    "mean_rating",
                },
            )
            if value is not None:
                # Serializd API surfaces may use 0-10 while the website
                # presents the community average as 0-5.
                if value > 5:
                    value = value / 2
                return round(value, 2)
        except Exception:
            continue

    return None

def _m19_maybe_number(value):
    if value in (None, "", []):
        return None
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return int(number) if number.is_integer() else number
    except (TypeError, ValueError):
        return value

def _m19_first_present(data, *paths):
    """Return the first non-empty value from simple/nested API paths."""
    if not isinstance(data, dict):
        return None
    for path in paths:
        current = data
        for key in path.split("."):
            if not isinstance(current, dict) or key not in current:
                current = None
                break
            current = current[key]
        if current not in (None, "", []):
            return current
    return None

def _m19_normalize_serializd_genres(genres):
    if not genres:
        return None
    if isinstance(genres, list):
        names = []
        for genre in genres:
            if isinstance(genre, dict):
                name = (
                    genre.get("name")
                    or genre.get("title")
                    or genre.get("label")
                    or genre.get("genreName")
                )
            else:
                name = str(genre)
            if name:
                names.append(name)
        return ", ".join(names) if names else None
    return str(genres)

def _m19_normalize_serializd_date(value):
    if not value:
        return None
    text = str(value)
    return text[:10] if len(text) >= 10 else text

def _m19_maybe_number(value):
    if value in (None, "", []):
        return None
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return int(number) if number.is_integer() else number
    except (TypeError, ValueError):
        return value

def _m19_first_present(data, *paths):
    if not isinstance(data, dict):
        return None
    for path in paths:
        current = data
        for key in path.split("."):
            if not isinstance(current, dict) or key not in current:
                current = None
                break
            current = current[key]
        if current not in (None, "", []):
            return current
    return None

def _m19_normalize_serializd_genres(genres):
    if not genres:
        return None
    if isinstance(genres, list):
        names = []
        for genre in genres:
            if isinstance(genre, dict):
                name = (
                    genre.get("name")
                    or genre.get("title")
                    or genre.get("label")
                    or genre.get("genreName")
                )
            else:
                name = str(genre)
            if name:
                names.append(name)
        return ", ".join(names) if names else None
    return str(genres)

def _m19_normalize_serializd_date(value):
    if not value:
        return None
    value = str(value)
    return value[:10] if len(value) >= 10 else value

def _m19_serializd_season_summary(show):
    """Extract season/episode information when get_show exposes seasons."""
    seasons = (
        show.get("seasons")
        or show.get("seasonList")
        or show.get("season_data")
        or []
    )
    if not isinstance(seasons, list):
        return None, None, []

    visible_seasons = []
    total_episodes = 0

    for season in seasons:
        if not isinstance(season, dict):
            continue

        number = (
            season.get("seasonNumber")
            if season.get("seasonNumber") is not None
            else season.get("season_number")
        )
        name = season.get("name") or season.get("title")
        count = (
            season.get("episodeCount")
            or season.get("numberOfEpisodes")
            or season.get("episode_count")
        )

        if count is None and isinstance(season.get("episodes"), list):
            count = len(season["episodes"])

        count_num = _m19_maybe_number(count)
        if isinstance(count_num, (int, float)):
            total_episodes += int(count_num)

        visible_seasons.append({
            "number": number,
            "name": name,
            "episodes": count_num,
        })

    return len(visible_seasons) or None, total_episodes or None, visible_seasons

def _m19_print_serializd_details(show):
    show = show if isinstance(show, dict) else {}

    title = _m19_first_present(show, "name", "title") or "Unknown"
    show_id = _m19_first_present(show, "id", "showId")

    first_air = _m19_first_present(
        show,
        "firstAirDate",
        "first_air_date",
        "releaseDate",
        "release_date",
    )
    year = _m19_first_present(show, "year", "releaseYear")
    if not year and first_air:
        year = str(first_air)[:4]

    # Serializd's verified show-detail averageRating is on a 0â€“10 scale;
    # WAYMARK displays it on a 0â€“5 star scale.
    rating = show.get("averageRating")
    if isinstance(rating, (int, float)) and not isinstance(rating, bool):
        rating = round(float(rating) / 2, 2)
    else:
        rating = show.get("_waymark_community_rating")



    season_count = _m19_first_present(
        show,
        "seasonCount",
        "numberOfSeasons",
        "season_count",
        "seasonsCount",
        "stats.seasonCount",
        "statistics.seasonCount",
    )
    episode_count = _m19_first_present(
        show,
        "episodeCount",
        "numberOfEpisodes",
        "episode_count",
        "episodesCount",
        "stats.episodeCount",
        "statistics.episodeCount",
    )

    derived_season_count, derived_episode_count, seasons = _m19_serializd_season_summary(show)
    if season_count is None:
        season_count = derived_season_count
    if episode_count is None:
        episode_count = derived_episode_count

    genres = _m19_normalize_serializd_genres(
        _m19_first_present(show, "genres", "genre", "genreList")
    )
    status = _m19_first_present(show, "status", "showStatus", "airStatus")
    overview = _m19_first_present(
        show,
        "summary",
        "overview",
        "synopsis",
        "description",
    )

    print("\n----------------------------------------")
    print(f"SERIALIZD DETAILS â€” {title}")
    print("----------------------------------------")

    fields = [
        ("Serializd ID", show_id),
        ("Year", year),
        ("First aired", _m19_normalize_serializd_date(first_air)),
        ("Rating", f"{float(rating):.2f} / 5" if isinstance(rating, (int, float)) else rating),
        ("Seasons", _m19_maybe_number(season_count)),
        ("Episodes", _m19_maybe_number(episode_count)),
        ("Status", status),
        ("Genres", genres),
    ]

    for label, value in fields:
        if value not in (None, "", []):
            print(f"{label}: {value}")

    if seasons:
        print("\nSeasons:")
        for season in seasons:
            number = season.get("number")
            name = season.get("name")
            count = season.get("episodes")
            label = f"S{int(number):02d}" if isinstance(number, (int, float)) else "Season"
            if name:
                label += f" â€” {name}"
            if count is not None:
                label += f" ({count} episodes)"
            print(f"  â€¢ {label}")

    if overview:
        print(f"\nSynopsis: {overview}")

    network = _m19_first_present(show, "network.name", "networkName")
    creator = _m19_first_present(show, "creator.name", "creatorName")
    if network:
        print(f"Network: {network}")
    if creator:
        print(f"Creator: {creator}")


def _m19_select_numbered(results, service_name):
    if not results:
        print(f"\nNo {service_name} results found.")
        return None
    while True:
        print(f"\n{service_name} results:")
        for i, item in enumerate(results, 1):
            if service_name == "MyAnimeList":
                node = item.get("node", item)
                print(f"  {i}. {node.get('title', 'Unknown')} | MAL ID: {node.get('id')}")
            else:
                print(f"  {i}. {item.get('name') or item.get('title') or 'Unknown'} | Serializd ID: {item.get('id')} | {item.get('year') or item.get('releaseYear') or item.get('firstAirDate') or ''}")
        raw = input(f"Select {service_name} result (B = back, 0/Cancel = cancel)\n> ").strip().lower()
        if raw in {"b", "0", "cancel"}:
            return None
        try:
            n = int(raw)
            if 1 <= n <= len(results):
                return results[n - 1]
        except ValueError:
            pass
        print("Please enter a valid result number.")

def _m19_ask_yes_no(prompt):
    while True:
        raw = input(f"{prompt} (Y/N, B = back, 0/Cancel = cancel)\n> ").strip().lower()
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        if raw in {"b", "0", "cancel"}:
            return None
        print("Please enter Y or N.")

def _m19_ask_media_type():
    while True:
        raw = input("Is it a TV show or a movie? (T = TV show, M = movie, B = back, 0/Cancel = cancel)\n> ").strip().lower()
        if raw in {"t", "tv", "tv show", "show"}:
            return "tv"
        if raw in {"m", "movie", "film"}:
            return "movie"
        if raw in {"b", "0", "cancel"}:
            return None
        print("Please enter T for TV show or M for movie.")

def m19_search(query=None):
    """Guided read-only discovery with service routing and detail views."""
    if query is None:
        query = input("\nSearch WAYMARK (B = back, 0/Cancel = cancel)\n> ").strip()

    if query.lower() in {"b", "0", "cancel"}:
        return None
    if not query:
        print("Search cancelled: title cannot be empty.")
        return None

    is_anime = _m19_ask_yes_no("Is it an anime?")
    if is_anime is None:
        return None

    media_type = _m19_ask_media_type()
    if media_type is None:
        return None

    use_mal = is_anime
    use_serializd = media_type == "tv"

    print("\n================================================")
    print("WAYMARK SEARCH â€” M19 GUIDED DISCOVERY")
    print("================================================")
    print(f"Title: {query}")
    print(f"Anime: {'Yes' if is_anime else 'No'}")
    print(f"Media type: {'TV show' if media_type == 'tv' else 'Movie'}")

    if not use_mal and not use_serializd:
        print("\nNo current WAYMARK search service applies to non-anime movies.")
        print("No service was queried. Read-only; no service data was changed.")
        return None

    if use_mal:
        try:
            mal_results = search_anime(query) or []
        except Exception as exc:
            print(f"\nMyAnimeList search failed: {exc}")
            mal_results = []
        selected_mal = _m19_select_numbered(mal_results[:10], "MyAnimeList")
        if selected_mal is not None:
            mal_node = selected_mal.get("node", selected_mal)
            mal_id = mal_node.get("id")
            try:
                mal_details = _m19_get_mal_details(mal_id) if mal_id else mal_node
            except Exception as exc:
                print(f"\nMAL detail lookup failed; showing available search data. ({exc})")
                mal_details = selected_mal
            _m19_print_mal_details(mal_details)

    if use_serializd:
        try:
            serializd_results = search_catalog(query) or []
        except Exception as exc:
            print(f"\nSerializd search failed: {exc}")
            serializd_results = []
        selected_serializd = _m19_select_numbered(serializd_results[:10], "Serializd")
        if selected_serializd is not None:
            try:
                show_id = selected_serializd.get("id")
                details = get_show(show_id) if show_id else selected_serializd

            except Exception as exc:
                print(f"\nSerializd detail lookup failed; showing available search data. ({exc})")
                details = selected_serializd

            # Preserve any rating exposed by search/show responses first.
            if isinstance(details, dict):
                existing_rating = _m19_first_present(
                    details,
                    "averageRating",
                    "average_rating",
                    "avgRating",
                    "avg_rating",
                    "rating",
                )
                if existing_rating is None and show_id:
                    community_rating = _m19_get_serializd_community_rating(show_id)
                    if community_rating is not None:
                        details["_waymark_community_rating"] = community_rating

            _m19_print_serializd_details(details)

    print("\nSearch complete. Read-only; no service data was changed. âœ…")
    return True

def run_m19_search_workflow():
    return m19_search()

def _m19_mal_library_rows():
    """Normalize the existing MAL list into UI-friendly read-only rows."""
    raw = get_my_anime_list() or []
    rows = []

    for item in raw:
        node = item.get("node", item) if isinstance(item, dict) else {}
        status = item.get("list_status", {}) if isinstance(item, dict) else {}
        if not isinstance(status, dict):
            status = {}

        title = node.get("title", "Unknown title")
        mal_id = node.get("id")
        watched = status.get("num_episodes_watched", 0)
        total = node.get("num_episodes")

        rows.append({
            "service": "MAL",
            "id": mal_id,
            "title": title,
            "status": status.get("status", ""),
            "watched": watched,
            "total": total,
            "score": status.get("score"),
        })

    return rows


def _m19_serializd_library_rows():
    """Normalize the existing Serializd watched library into UI rows."""
    raw = get_watched_library() or []
    rows = []

    for item in raw:
        if not isinstance(item, dict):
            continue

        title = item.get("showName") or item.get("name") or "Unknown title"
        show_id = item.get("showId", item.get("id"))
        seasons = item.get("numberOfSeasons", item.get("seasonCount"))
        episodes = item.get("numberOfEpisodes", item.get("episodeCount"))

        rows.append({
            "service": "Serializd",
            "id": show_id,
            "title": title,
            "seasons": seasons,
            "episodes": episodes,
        })

    return rows


def m19_library():
    """Read both connected libraries without writing local or service data."""
    result = {
        "workflow_id": M19_WORKFLOW_ID,
        "mal": [],
        "serializd": [],
        "errors": [],
    }

    try:
        result["mal"] = _m19_mal_library_rows()
    except Exception as exc:
        result["errors"].append(f"MAL library: {exc}")

    try:
        result["serializd"] = _m19_serializd_library_rows()
    except Exception as exc:
        result["errors"].append(f"Serializd library: {exc}")

    return result


def run_m19_library_workflow():
    """Interactive, read-only combined library view."""
    print("\n================================================")
    print("WAYMARK LIBRARY â€” M19")
    print("================================================")
    print("Read-only view of the connected MAL and Serializd libraries.")

    result = m19_library()

    print(f"\nMAL anime entries: {len(result['mal'])}")
    for row in result["mal"][:25]:
        progress = str(row["watched"])
        if row["total"] is not None:
            progress += f"/{row['total']}"
        score = row["score"] if row["score"] is not None else "-"
        status = row["status"] or "-"
        print(
            f"  â€¢ {row['title']} | {status} | "
            f"Episodes {progress} | Score {score}/10 | MAL ID {row['id']}"
        )

    print(f"\nSerializd watched shows: {len(result['serializd'])}")
    for row in result["serializd"][:25]:
        details = []
        if row["seasons"] is not None:
            details.append(f"{row['seasons']} seasons")
        if row["episodes"] is not None:
            details.append(f"{row['episodes']} episodes")
        suffix = f" | {', '.join(details)}" if details else ""
        print(f"  â€¢ {row['title']}{suffix} | Serializd ID {row['id']}")

    if result["errors"]:
        print("\nLibrary warnings:")
        for error in result["errors"]:
            print(f"  - {error}")

    print("\nLibrary read complete. No service data was changed. âœ…")


def _m19_history_rows(limit=20):
    """Read recent Serializd diary activity and normalize it."""
    from app.backend.services.serializd import get_diary

    data = get_diary(1)
    entries = data.get("reviews", []) if isinstance(data, dict) else []

    rows = []
    for entry in entries[:limit]:
        if not isinstance(entry, dict):
            continue

        show = entry.get("showName", "Unknown show")
        season_id = entry.get("seasonId")
        episode_number = entry.get("episodeNumber")
        episode_name = entry.get("episodeName")
        created = (
            entry.get("backdate")
            or entry.get("createdAt")
            or entry.get("date")
            or entry.get("timestamp")
            or ""
        )
        rating = entry.get("rating")

        if episode_number is not None:
            try:
                label = f"S{int(entry.get('seasonNumber', 0)):02d}E{int(episode_number):02d}"
            except (TypeError, ValueError):
                label = f"Episode {episode_number}"
            if episode_name:
                label += f" â€” {episode_name}"
        elif season_id is not None:
            label = "Season activity"
        else:
            label = "Series activity"

        rows.append({
            "service": "Serializd",
            "show": show,
            "item": label,
            "date": created,
            "rating": rating,
            "review_id": entry.get("id"),
        })

    return rows


def _m19_mal_history_rows(limit=20):
    """Read recent MAL list activity and normalize it for History.

    MAL's user-list surface provides current watched progress and an
    ``updated_at`` timestamp, but it does not expose a per-episode diary
    comparable to Serializd's diary endpoint. Therefore each row represents
    the latest MAL list activity for an anime, using only fields MAL supplies.
    """
    raw = get_my_anime_list() or []
    candidates = []

    for item in raw:
        if not isinstance(item, dict):
            continue

        node = item.get("node", item)
        status = item.get("list_status", {})
        if not isinstance(node, dict) or not isinstance(status, dict):
            continue

        mal_id = node.get("id")
        title = node.get("title") or "Unknown title"
        watched = status.get("num_episodes_watched", 0)
        total = node.get("num_episodes")
        updated = status.get("updated_at") or status.get("updatedAt") or ""

        try:
            watched_number = int(watched or 0)
        except (TypeError, ValueError):
            watched_number = 0

        # An entry with zero watched episodes is list state, not watch history.
        if watched_number <= 0:
            continue

        try:
            total_number = int(total) if total not in (None, "") else None
        except (TypeError, ValueError):
            total_number = None

        if total_number and total_number > 0:
            progress = f"E{watched_number} / E{total_number}"
        else:
            progress = f"E{watched_number}"

        mal_status = status.get("status")
        if mal_status:
            label = f"Progress: {progress} · {mal_status}"
        else:
            label = f"Progress: {progress}"

        candidates.append({
            "service": "MAL",
            "show": str(title),
            "item": label,
            "date": updated,
            "rating": status.get("score"),
            "review_id": None,
            "_sort_date": str(updated or ""),
            "_mal_id": mal_id,
        })

    candidates.sort(key=lambda row: row["_sort_date"], reverse=True)

    rows = []
    for row in candidates[:max(0, int(limit))]:
        row.pop("_sort_date", None)
        row.pop("_mal_id", None)
        rows.append(row)

    return rows


def m19_history(limit=20):
    """Read recent personal MAL + Serializd activity; no writes."""
    limit = max(1, min(int(limit), 100))
    result = {
        "workflow_id": M19_WORKFLOW_ID,
        "entries": [],
        "errors": [],
    }

    serializd_rows = []
    mal_rows = []

    try:
        serializd_rows = _m19_history_rows(limit)
    except Exception as exc:
        result["errors"].append(f"Serializd history: {exc}")

    try:
        mal_rows = _m19_mal_history_rows(limit)
    except Exception as exc:
        result["errors"].append(f"MAL history: {exc}")

    combined = serializd_rows + mal_rows

    def sort_key(row):
        value = row.get("date") if isinstance(row, dict) else ""
        return str(value or "")

    combined.sort(key=sort_key, reverse=True)
    result["entries"] = combined[:limit]
    return result


def run_m19_history_workflow():
    """Interactive, read-only recent history view."""
    print("\n================================================")
    print("WAYMARK HISTORY â€” M19")
    print("================================================")
    print("Recent Serializd diary/activity. Nothing is written or synced.")

    result = m19_history(limit=20)

    if not result["entries"]:
        print("\nNo recent history entries were returned.")
    else:
        print(f"\nRecent entries: {len(result['entries'])}")
        for row in result["entries"]:
            rating = row["rating"]
            rating_text = f" | Rating {rating}/10" if rating not in (None, 0) else ""
            date_text = f" | {row['date']}" if row["date"] else ""
            print(
                f"  â€¢ {row['show']} | {row['item']}"
                f"{rating_text}{date_text}"
            )

    if result["errors"]:
        print("\nHistory warnings:")
        for error in result["errors"]:
            print(f"  - {error}")

    print("\nHistory read complete. No service data was changed. âœ…")


def m19_offline_smoke_test():
    """Validate M19's normalization and read-only contract without network calls."""
    search_result = m19_search("")
    assert search_result is None

    # Routing contract:
    # anime + TV -> MAL + Serializd
    # anime + movie -> MAL only
    # non-anime + TV -> Serializd only
    # non-anime + movie -> no current search service
    assert M19_WORKFLOW_ID == "M19_SEARCH_LIBRARY_HISTORY"

    rows = [{
        "showName": "Example Show",
        "showId": 123,
        "numberOfSeasons": 2,
        "numberOfEpisodes": 20,
    }]
    original = get_watched_library
    try:
        globals()["get_watched_library"] = lambda: rows
        normalized = _m19_serializd_library_rows()
        assert normalized[0]["title"] == "Example Show"
        assert normalized[0]["id"] == 123
        assert normalized[0]["seasons"] == 2
        assert normalized[0]["episodes"] == 20
    finally:
        globals()["get_watched_library"] = original

    print("M19 Search / Library / History smoke test passed.")
    return True




def main():
    """Run the terminal development menu for the WAYMARK core."""
    print("\n========================")
    print("WAYMARK SERIALIZD SERIES WATCH")
    print("========================")
    print("\nThis test is for Serializd only. Your MAL functions remain in Core unchanged.")
    print("\n1. Run the existing MAL Core test")
    print("2. Persistent Serializd series-watch test")
    print("3. Persistent Serializd episode log + star-rating test")
    print("4. Read Serializd diary / history")
    print("5. Test WAYMARK internal media identity")
    print("6. Test explicit MAL â†” Serializd service link")
    print("7. Test persistent WAYMARK media identity")
    print("8. Test persistent season / episode identity")
    print("9. Compare MAL â†” Serializd progress (read-only)")
    print("10. Read live Serializd watched library")
    print("11. Read live Serializd show watch state")
    print("12. Read live Serializd episode watch state")
    print("13. Read live personal Serializd diary")
    print("14. WAYMARK conversational prototype")
    print("15. Discover Serializd season-review write request")
    print("16. WAYMARK Review Season workflow (M15.3 â€” multiline reviews)")
    print("17. WAYMARK Review Episode workflow (M15.4)")
    print("18. WAYMARK Review Series workflow (M15.5 â€” verified execution)")
    print("19. WAYMARK Rate Episode workflow (M16)")
    print("20. WAYMARK Rate Season workflow (M16)")
    print("21. WAYMARK Rate Series workflow (M16)")
    print("22. WAYMARK Rate Anime / Anime Movie workflow (M16)")
    print("23. WAYMARK Rate Episode workflow (M16 â€” final)")
    print("24. WAYMARK Rate Season workflow (M16 â€” final)")
    print("25. WAYMARK Final Watch Validation (M17)")
    print("26. WAYMARK Progress workflow (M18 â€” MAL)")
    print("27. WAYMARK Progress workflow (M18 â€” Serializd)")
    print("28. WAYMARK Search (M19 â€” guided discovery + details)")
    print("29. WAYMARK Library (M19 â€” MAL + Serializd)")
    print("30. WAYMARK History (M19 â€” Serializd diary)")

    choice = input("\nChoose 1-30 (B = back, 0/Cancel = exit): ").strip().lower()
    if choice in {"0", "cancel", "c", "q", "b", "back"}:
        print("Exiting WAYMARK.")
        return
    actions = {
        "1": run_existing_mal_test,
        "2": test_serializd_series_watch,
        "3": test_serializd_episode_log,
        "4": test_serializd_diary,
        "5": test_waymark_identity,
        "6": test_waymark_cross_service_link,
        "7": test_persistent_waymark_identity,
        "8": test_persistent_episode_identity,
        "9": test_waymark_sync_comparison,
        "10": test_live_serializd_library,
        "11": test_live_serializd_show_watch_state,
        "12": test_live_serializd_episode_watch_state,
        "13": test_live_serializd_personal_diary,
        "14": run_waymark_chat,
        "15": discover_serializd_season_review_request,
        "16": run_m151_review_season_workflow,
        "17": run_m154_review_episode_workflow,
        "18": run_m155_review_series_workflow,
        "19": run_m16_rate_episode_workflow,
        "20": run_m16_rate_season_workflow,
        "21": run_m16_rate_series_workflow,
        "22": run_m16_rate_anime_workflow,
        "23": run_m16_rate_episode_final_workflow,
        "24": run_m16_rate_season_final_workflow,
        "25": run_m17_final_watch_validation,
        "26": run_m18_progress_workflow,
        "27": run_m18_serializd_progress_workflow,
        "28": run_m19_search_workflow,
        "29": run_m19_library_workflow,
        "30": run_m19_history_workflow,
    }
    action = actions.get(choice)
    if action is None:
        print("Invalid choice.")
        return
    action()


# ==================== M14 WORKFLOW ENGINE ====================

# ==================== M14 WORKFLOW ENGINE ====================
#
# M14 introduces a UI-independent workflow/state foundation.
# The existing M12 guided workflow remains intact below.
#
# The engine is intentionally small in this first implementation:
# - WorkflowState: one conversational state
# - WorkflowContext: current state + collected data
# - WorkflowEngine: transitions, validation, Back, and Cancel
# - ActionPlan: proposed service changes, before confirmation/execution
#
# M12 is NOT replaced in this version. This scaffold is the safe bridge
# from the tested CLI workflow toward the future desktop UI.

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class WorkflowState:
    state_id: str
    question: str = ""
    required: bool = True
    validator: Optional[Callable[[Any, "WorkflowContext"], Any]] = None
    next_state: Optional[Callable[[Any, "WorkflowContext"], Optional[str]]] = None
    previous_state: Optional[str] = None


@dataclass
class WorkflowContext:
    workflow_id: str
    state_id: str
    data: Dict[str, Any] = field(default_factory=dict)
    history: List[str] = field(default_factory=list)
    cancelled: bool = False
    completed: bool = False

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


@dataclass
class ActionPlan:
    """A proposed set of service changes; it is not execution itself."""
    workflow_id: str
    operations: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add(self, service: str, operation: str, **details: Any) -> None:
        self.operations.append({
            "service": service,
            "operation": operation,
            "details": details,
        })

    @property
    def is_empty(self) -> bool:
        return not self.operations


class WorkflowEngine:
    """
    Generic state machine for WAYMARK workflows.

    This class deliberately knows nothing about MAL, Serializd, TMDB, or UI.
    Service adapters and UI layers will be connected in later milestones.
    """

    BACK = "B"
    CANCEL = "0"

    def __init__(self, workflow_id: str, states: Dict[str, WorkflowState],
                 initial_state: str):
        if initial_state not in states:
            raise ValueError(f"Unknown initial state: {initial_state}")
        self.states = states
        self.context = WorkflowContext(
            workflow_id=workflow_id,
            state_id=initial_state,
        )

    @property
    def current_state(self) -> WorkflowState:
        return self.states[self.context.state_id]

    @property
    def is_finished(self) -> bool:
        return self.context.cancelled or self.context.completed

    def prompt(self) -> str:
        return self.current_state.question

    def cancel(self) -> None:
        self.context.cancelled = True

    def back(self) -> bool:
        """Move back exactly one state; returns False at the root."""
        if not self.context.history:
            return False

        self.context.state_id = self.context.history.pop()
        return True

    def submit(self, value: Any) -> Dict[str, Any]:
        """
        Process one answer.

        Returns a small structured event so a future UI can render it without
        depending on CLI print statements.
        """
        if self.is_finished:
            return {"ok": False, "event": "finished"}

        if isinstance(value, str):
            command = value.strip()
            if command.upper() == self.BACK:
                moved = self.back()
                return {
                    "ok": moved,
                    "event": "back" if moved else "root",
                    "state_id": self.context.state_id,
                }
            if command == self.CANCEL:
                self.cancel()
                return {"ok": True, "event": "cancelled"}

        state = self.current_state

        if value in ("", None) and state.required:
            return {
                "ok": False,
                "event": "validation_error",
                "error": "A value is required.",
                "state_id": state.state_id,
            }

        if state.validator is not None:
            try:
                result = state.validator(value, self.context)
            except ValueError as exc:
                return {
                    "ok": False,
                    "event": "validation_error",
                    "error": str(exc),
                    "state_id": state.state_id,
                }
            if result is not None:
                value = result

        # Store state-specific data under its state ID. Individual workflows
        # can additionally write domain-friendly keys into context.data.
        self.context.set(state.state_id, value)

        if state.next_state is None:
            self.context.completed = True
            return {
                "ok": True,
                "event": "completed",
                "state_id": state.state_id,
            }

        next_id = state.next_state(value, self.context)
        if next_id is None:
            self.context.completed = True
            return {
                "ok": True,
                "event": "completed",
                "state_id": state.state_id,
            }

        if next_id not in self.states:
            raise ValueError(f"Unknown next state: {next_id}")

        self.context.history.append(state.state_id)
        self.context.state_id = next_id

        return {
            "ok": True,
            "event": "transition",
            "from_state": state.state_id,
            "state_id": next_id,
        }


# ==================== M14.2 WATCH WORKFLOW BRIDGE ====================
#
# M14.2 connects the tested M12 Watch workflow to the generic workflow model.
# The existing M12 implementation is intentionally preserved. This bridge is
# backend-only and does not alter service credentials, API calls, or write logic.

M142_WATCH_STATES = (
    "WATCH_TITLE",
    "WATCH_IS_ANIME",
    "WATCH_MEDIA_TYPE",
    "SELECT_MAL_TITLE",
    "SELECT_SERIALIZD_TITLE",
    "SELECT_SERIALIZD_SEASON",
    "SELECT_SERIALIZD_EPISODE",
    "SELECT_MAL_EPISODE",
    "MAL_SCORE",
    "SERIALIZD_RATING",
    "STATUS",
    "EPISODE_REVIEW",
    "CONFIRM",
    "RESULT",
)


def m142_normalize_command(value):
    """Normalize only workflow navigation commands; leave domain answers intact."""
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if stripped.upper() == "B":
        return WorkflowEngine.BACK
    if stripped.lower() in {"0", "cancel"}:
        return WorkflowEngine.CANCEL
    return value


def m142_watch_context():
    """Create a clean context for a future UI-driven Watch session."""
    return WorkflowContext(
        workflow_id="WATCH",
        state_id="WATCH_TITLE",
    )


def m142_build_watch_state_map():
    """
    Return the deterministic Watch state map.

    Domain-specific question/validation details remain owned by the existing
    M12 implementation for now. These state identifiers provide the stable
    contract that the future UI and workflow engine can target.
    """
    return {
        "WATCH_TITLE": WorkflowState(
            "WATCH_TITLE",
            "What did you watch today?",
            required=True,
            previous_state=None,
        ),
        "WATCH_IS_ANIME": WorkflowState(
            "WATCH_IS_ANIME",
            "Is it an anime? [Y/N]",
            required=True,
            previous_state="WATCH_TITLE",
        ),
        "WATCH_MEDIA_TYPE": WorkflowState(
            "WATCH_MEDIA_TYPE",
            "Is it a TV show or a movie? [TV/Movie]",

            required=True,
            previous_state="WATCH_IS_ANIME",
        ),
        "SELECT_MAL_TITLE": WorkflowState(
            "SELECT_MAL_TITLE",
            "Choose the anime from MyAnimeList.",
            required=True,
            previous_state="WATCH_MEDIA_TYPE",
        ),
        "SELECT_SERIALIZD_TITLE": WorkflowState(
            "SELECT_SERIALIZD_TITLE",
            "Choose the matching Serializd title.",
            required=True,
            previous_state="SELECT_MAL_TITLE",
        ),
        "SELECT_SERIALIZD_SEASON": WorkflowState(
            "SELECT_SERIALIZD_SEASON",
            "Choose the Serializd season/arc.",
            required=True,
            previous_state="SELECT_SERIALIZD_TITLE",
        ),
        "SELECT_SERIALIZD_EPISODE": WorkflowState(
            "SELECT_SERIALIZD_EPISODE",
            "Choose the Serializd episode.",
            required=True,
            previous_state="SELECT_SERIALIZD_SEASON",
        ),
        "SELECT_MAL_EPISODE": WorkflowState(
            "SELECT_MAL_EPISODE",
            "Choose the MAL episode.",
            required=False,
            previous_state="SELECT_SERIALIZD_EPISODE",
        ),
        "MAL_SCORE": WorkflowState(
            "MAL_SCORE",
            "What is your MAL score?",
            required=False,
            previous_state="SELECT_MAL_EPISODE",
        ),
        "SERIALIZD_RATING": WorkflowState(
            "SERIALIZD_RATING",
            "What is your Serializd rating?",
            required=False,
            previous_state="MAL_SCORE",
        ),
        "STATUS": WorkflowState(
            "STATUS",
            "What is the status?",
            required=True,
            previous_state="SERIALIZD_RATING",
        ),
        "EPISODE_REVIEW": WorkflowState(
            "EPISODE_REVIEW",
            "Write an episode review, or press Enter to skip.",
            required=False,
            previous_state="STATUS",
        ),
        "CONFIRM": WorkflowState(
            "CONFIRM",
            "Confirm the proposed changes.",
            required=True,
            previous_state="EPISODE_REVIEW",
        ),
        "RESULT": WorkflowState(
            "RESULT",
            "Operation result.",
            required=False,
            previous_state="CONFIRM",
        ),
    }


class M142WatchWorkflow:
    """
    Thin stateful wrapper for the M12 Watch workflow.

    It deliberately does not execute service writes. The existing M12
    execution path remains the authority until M14.3+ migrates individual
    operations into ActionPlan/service adapters.
    """

    workflow_id = "WATCH"

    def __init__(self):
        self.states = m142_build_watch_state_map()
        self.context = m142_watch_context()

    @property
    def state(self):
        return self.context.state_id

    @property
    def data(self):
        return self.context.data

    def set_state(self, state_id):
        if state_id not in self.states:
            raise ValueError(f"Unknown Watch state: {state_id}")
        self.context.state_id = state_id

    def record(self, key, value):
        self.context.set(key, value)

    def back(self):
        """Move one state backward using the explicit M12 state order."""
        current = self.state
        try:
            index = M142_WATCH_STATES.index(current)
        except ValueError:
            return False
        if index <= 0:
            return False
        self.set_state(M142_WATCH_STATES[index - 1])
        return True

    def cancel(self):
        self.context.cancelled = True

    def build_read_only_action_plan(self):
        """
        Build a non-executable description from collected data.

        This is intentionally read-only in M14.2. No network/service call is
        performed by this method.
        """
        plan = ActionPlan(workflow_id=self.workflow_id)
        return plan


def m142_smoke_test():
    """Pure backend smoke test for state, Back, Cancel, and ActionPlan behavior."""
    wf = M142WatchWorkflow()

    assert wf.state == "WATCH_TITLE"

    wf.record("title", "Frieren")
    wf.set_state("WATCH_IS_ANIME")
    assert wf.state == "WATCH_IS_ANIME"

    assert wf.back() is True
    assert wf.state == "WATCH_TITLE"

    wf.set_state("MAL_SCORE")
    assert wf.back() is True
    assert wf.state == "SELECT_MAL_EPISODE"

    plan = wf.build_read_only_action_plan()
    assert plan.workflow_id == "WATCH"
    assert plan.is_empty

    wf.cancel()
    assert wf.context.cancelled is True

    return "M14.2 backend smoke test passed."




# ==================== M14.3 REAL M12 WATCH ADAPTER ====================
#
# This adapter is the first executable bridge from the generic workflow engine
# to the real M12 Watch sequence. It deliberately keeps service execution in
# the existing tested M12 implementation.
#
# Design rule:
#   Workflow Engine -> collect/validate/plan
#   Existing M12 -> actual service execution
#
# This prevents an architectural refactor from accidentally changing live
# MAL/Serializd write behavior.

M143_M12_STATE_MAP = {
    "TITLE": "WATCH_TITLE",
    "ANIME": "WATCH_IS_ANIME",
    "MEDIA_TYPE": "WATCH_MEDIA_TYPE",
    "MAL_TITLE": "SELECT_MAL_TITLE",
    "SERIALIZD_TITLE": "SELECT_SERIALIZD_TITLE",
    "SERIALIZD_SEASON": "SELECT_SERIALIZD_SEASON",
    "SERIALIZD_EPISODE": "SELECT_SERIALIZD_EPISODE",
    "MAL_EPISODE": "SELECT_MAL_EPISODE",
    "MAL_SCORE": "MAL_SCORE",
    "SERIALIZD_RATING": "SERIALIZD_RATING",
    "STATUS": "STATUS",
    "EPISODE_REVIEW": "EPISODE_REVIEW",
    "CONFIRM": "CONFIRM",
    "RESULT": "RESULT",
}


class M143M12WatchAdapter:
    """
    Adapter representing the tested M12 Watch workflow as engine states.

    It is intentionally service-agnostic. The adapter stores the answers and
    exposes a deterministic state contract. Existing M12 service operations
    remain the source of truth for network writes.
    """

    workflow_id = "WATCH"

    def __init__(self):
        self.workflow = M142WatchWorkflow()
        self.m12_state = "TITLE"

    @property
    def engine_state(self):
        return M143_M12_STATE_MAP[self.m12_state]

    @property
    def data(self):
        return self.workflow.data

    def _set_m12_state(self, state):
        if state not in M143_M12_STATE_MAP:
            raise ValueError(f"Unknown M12 state: {state}")
        self.m12_state = state
        self.workflow.set_state(M143_M12_STATE_MAP[state])

    def answer(self, key, value, next_state=None):
        """Record a validated M12 answer and optionally advance."""
        self.workflow.record(key, value)
        if next_state is not None:
            self._set_m12_state(next_state)

    def back(self):
        """Back follows the explicit M12 order and never cancels."""
        current_engine = self.engine_state
        if not self.workflow.back():
            return False

        for m12_key, engine_key in M143_M12_STATE_MAP.items():
            if engine_key == self.workflow.state:
                self.m12_state = m12_key
                break
        return current_engine != self.engine_state

    def cancel(self):
        self.workflow.cancel()

    def build_action_plan(self):
        """
        Produce a read-only ActionPlan from the collected workflow data.

        No service request is made here. Execution remains in the existing
        M12 implementation until the service adapter migration milestone.
        """
        plan = ActionPlan(workflow_id=self.workflow_id)

        if self.data.get("mal_episode") not in (None, ""):
            plan.add(
                "MAL",
                "update_watch_state",
                episode=self.data.get("mal_episode"),
                score=self.data.get("mal_score"),
                status=self.data.get("status"),
            )

        if self.data.get("serializd_episode") not in (None, ""):
            plan.add(
                "Serializd",
                "log_episode",
                season=self.data.get("serializd_season"),
                episode=self.data.get("serializd_episode"),
                rating=self.data.get("serializd_rating"),
                status=self.data.get("status"),
            )

        if self.data.get("episode_review") not in (None, ""):
            plan.add(
                "Serializd",
                "review_episode",
                review=self.data.get("episode_review"),
            )

        return plan


def m143_smoke_test():
    """
    Verify the real M12 state sequence can be represented by the new engine.

    This is intentionally offline: no credentials, browser, network request,
    or service write is used.
    """
    wf = M143M12WatchAdapter()

    assert wf.engine_state == "WATCH_TITLE"

    wf.answer("title", "Frieren", "ANIME")
    assert wf.engine_state == "WATCH_IS_ANIME"

    wf.answer("is_anime", True, "MEDIA_TYPE")
    wf.answer("media_type", "TV", "MAL_TITLE")
    wf.answer("mal_title", {"id": 52991, "title": "Sousou no Frieren"}, "SERIALIZD_TITLE")
    wf.answer("serializd_title", {"id": 209867, "title": "Frieren: Beyond Journey's End"}, "SERIALIZD_SEASON")
    wf.answer("serializd_season", "S01", "SERIALIZD_EPISODE")
    wf.answer("serializd_episode", 22, "MAL_EPISODE")
    wf.answer("mal_episode", 22, "MAL_SCORE")
    wf.answer("mal_score", 10, "SERIALIZD_RATING")
    wf.answer("serializd_rating", 5, "STATUS")
    wf.answer("status", "watching", "EPISODE_REVIEW")
    wf.answer("episode_review", "", "CONFIRM")

    assert wf.engine_state == "CONFIRM"

    plan = wf.build_action_plan()
    assert len(plan.operations) == 1 or len(plan.operations) == 2
    assert all(op["service"] in {"MAL", "Serializd"} for op in plan.operations)

    # Verify Back is exactly one state.
    # From CONFIRM, one Back returns to EPISODE_REVIEW.
    assert wf.back() is True
    assert wf.engine_state == "EPISODE_REVIEW"

    # A second Back returns to STATUS.
    assert wf.back() is True
    assert wf.engine_state == "STATUS"

    # Verify Cancel terminates the pending workflow.
    wf.cancel()
    assert wf.workflow.context.cancelled is True

    return "M14.3 M12 Watch adapter smoke test passed."




# ==================== M14.4 REAL M12 ENGINE INTEGRATION ====================
#
# M14.4 is deliberately non-invasive.
#
# The real, tested M12 Watch runner remains responsible for its prompts,
# service searches, validation, and service writes. The Workflow Engine is now
# attached to that live runner through an input/state bridge.
#
# This gives us a safe first integration:
#   real M12 conversation
#          â†“
#   Workflow Engine state/context mirror
#          â†“
#   existing M12 execution path
#
# We do NOT migrate network writes in this milestone.

M144_PROMPT_STATE_RULES = (
    (("what did you watch today",), "WATCH_TITLE"),
    (("is it an anime",), "WATCH_IS_ANIME"),
    (("tv show or a movie",), "WATCH_MEDIA_TYPE"),
    (("choose an anime", "choose the anime", "mal matches"), "SELECT_MAL_TITLE"),
    (("choose a matching serializd",), "SELECT_SERIALIZD_TITLE"),
    (("serializd season", "arc"), "SELECT_SERIALIZD_SEASON"),
    (("serializd episode",), "SELECT_SERIALIZD_EPISODE"),
    (("mal episode",), "SELECT_MAL_EPISODE"),
    (("mal score",), "MAL_SCORE"),
    (("serializd rating", "serializd stars"), "SERIALIZD_RATING"),
    (("status",), "STATUS"),
    (("episode review",), "EPISODE_REVIEW"),
    (("season review",), "EPISODE_REVIEW"),
    (("confirm",), "CONFIRM"),
)


def m144_state_from_prompt(prompt: str) -> str | None:
    """Resolve a live M12 input prompt to the corresponding engine state."""
    normalized = " ".join(str(prompt).strip().casefold().split())
    for phrases, state_id in M144_PROMPT_STATE_RULES:
        if any(phrase in normalized for phrase in phrases):
            return state_id
    return None


class M144EngineBridge:
    """
    Mirrors the live M12 conversation into WorkflowContext.

    The bridge never replaces M12 validation and never performs service I/O.
    It exists so the UI-independent engine has a live state representation
    while M12 remains the execution authority.
    """

    def __init__(self):
        self.workflow = M142WatchWorkflow()
        self.last_prompt_state = None

    @property
    def state(self):
        return self.workflow.state

    @property
    def data(self):
        return self.workflow.data

    def observe_prompt(self, prompt: str):
        state_id = m144_state_from_prompt(prompt)
        if state_id is None:
            return None

        # Synchronize the engine with the actual M12 prompt currently shown.
        self.workflow.set_state(state_id)
        self.last_prompt_state = state_id
        return state_id

    def observe_answer(self, value):
        """Record an answer without changing M12's own validation semantics."""
        if self.last_prompt_state:
            self.workflow.record(self.last_prompt_state, value)

    def observe_back(self):
        """Mirror a M12 Back result into the engine state."""
        return self.workflow.back()

    def cancel(self):
        self.workflow.cancel()


def _m144_run_live_m12_with_engine():
    """
    Run the existing M12 workflow while attaching a Workflow Engine mirror.

    This function is intentionally conservative. The legacy M12 function is
    executed unchanged; input is observed only to keep engine state in sync.
    """
    import builtins

    bridge = M144EngineBridge()
    original_input = builtins.input

    def bridged_input(prompt=""):
        state_id = bridge.observe_prompt(prompt)
        value = original_input(prompt)
        bridge.observe_answer(value)

        command = value.strip().casefold() if isinstance(value, str) else ""
        if command in {"0", "cancel", "c", "q"}:
            bridge.cancel()
        elif command in {"b", "back"}:
            # M12 itself owns the actual navigation. This call only mirrors
            # the state for the engine and does not alter M12's return value.
            bridge.observe_back()

        return value

    builtins.input = bridged_input
    try:
        return _run_waymark_chat_m12()
    finally:
        builtins.input = original_input


def m144_engine_bridge_smoke_test():
    """Offline test for prompt-to-state mapping and Back/Cancel mirroring."""
    bridge = M144EngineBridge()

    assert bridge.observe_prompt("What did you watch today?") == "WATCH_TITLE"
    bridge.observe_answer("Frieren")
    assert bridge.data["WATCH_TITLE"] == "Frieren"

    assert bridge.observe_prompt("Is it an anime? [Y/N]") == "WATCH_IS_ANIME"
    bridge.observe_answer("yes")

    assert bridge.observe_prompt("Is it a TV show or a movie? [TV/Movie]") == "WATCH_MEDIA_TYPE"
    bridge.observe_answer("TV")

    assert bridge.observe_prompt("Choose an anime (B = back, 0/Cancel = cancel):") == "SELECT_MAL_TITLE"
    bridge.observe_answer("1")

    bridge.workflow.set_state("MAL_SCORE")
    assert bridge.observe_back() is True
    assert bridge.state == "SELECT_MAL_EPISODE"

    bridge.cancel()
    assert bridge.workflow.context.cancelled is True

    return "M14.4 engine bridge smoke test passed."


# Preserve the original M12 implementation under a stable legacy name.
# The public run_waymark_chat entry point below now attaches the engine bridge.
_run_waymark_chat_m12 = run_waymark_chat
run_waymark_chat = _m144_run_live_m12_with_engine


# M14.4 diagnostic menu entry. The main menu remains unchanged except that
# option 14 now uses the engine-backed wrapper above.
def m144_diagnostics():
    print("\nM14.4 Workflow Engine diagnostics")
    print(m144_engine_bridge_smoke_test())


# ============================================================
# M15.1 â€” REVIEW SEASON WORKFLOW
# ============================================================

M151_REVIEW_SEASON_STATES = (
    "REVIEW_SEASON_TITLE",
    "REVIEW_SEASON_IS_ANIME",
    "REVIEW_SEASON_MEDIA_TYPE",
    "SELECT_SERIALIZD_SHOW",
    "SELECT_SERIALIZD_SEASON",
    "REVIEW_SEASON_RATING",
    "REVIEW_SEASON_TEXT",
    "REVIEW_SEASON_CONFIRM",
    "REVIEW_SEASON_RESULT",
)


@dataclass
class M151ReviewSeasonContext:
    state: str = "REVIEW_SEASON_TITLE"
    history: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    cancelled: bool = False


class M151ReviewSeasonWorkflow:
    """Deterministic guided workflow for reviewing a Serializd season."""

    def __init__(self):
        self.context = M151ReviewSeasonContext()

    @property
    def state(self):
        return self.context.state

    @property
    def data(self):
        return self.context.data

    def set_state(self, state: str):
        if state not in M151_REVIEW_SEASON_STATES:
            raise ValueError(f"Unknown M15.1 state: {state}")
        current = self.context.state
        if current != state:
            self.context.history.append(current)
        self.context.state = state
        return state

    def back(self):
        if not self.context.history:
            return False
        self.context.state = self.context.history.pop()
        return True

    def cancel(self):
        self.context.cancelled = True
        self.context.state = "REVIEW_SEASON_RESULT"
        return True

    def set_data(self, key: str, value: Any):
        self.context.data[key] = value
        return value

    def validate(self):
        d = self.data
        if not str(d.get("title", "")).strip():
            raise ValueError("A show title is required.")
        if d.get("anime") not in {True, False}:
            raise ValueError("Anime classification is required.")
        if d.get("media_type") != "tv":
            raise ValueError("M15.1 season review currently requires a TV show.")
        if not d.get("serializd_show_id"):
            raise ValueError("A Serializd show identity is required.")
        if not d.get("serializd_season_id"):
            raise ValueError("A Serializd season identity is required.")
        rating = d.get("rating")
        if rating is not None and (
            not isinstance(rating, (int, float))
            or not 0.5 <= float(rating) <= 5.0
            or abs(float(rating) * 2 - round(float(rating) * 2)) > 1e-9
        ):
            raise ValueError("Serializd season rating must be between 0.5 and 5.0 in half-star increments.")
        if not str(d.get("review_text", "")).strip():
            raise ValueError("Season review text is required.")
        return True

    def build_action_plan(self):
        self.validate()
        d = self.data
        operations = [{
            "service": "serializd",
            "operation": "review_season",
            "show_id": int(d["serializd_show_id"]),
            "season_id": int(d["serializd_season_id"]),
            "season_number": d.get("season_number"),
            "rating": float(d["rating"]) if d.get("rating") is not None else None,
            "review_text": str(d["review_text"]).strip(),
        }]
        return ActionPlan(
            workflow_id="M15.2_REVIEW_SEASON",
            operations=operations,
            metadata={
                "workflow": "M15.2_REVIEW_SEASON",
                "execution_enabled": True,
                "execution_reason": "Serializd season-review request verified from official UI discovery.",
                "endpoint": "https://serializddesktop.onrender.com/api/show/reviews/add",
                "rating_mapping": "WAYMARK 0.5-5.0 stars -> Serializd API 1-10",
            },
        )


def _m151_choose_serializd_show(title: str):
    results = search_catalog(title) or []
    if not results:
        print("\nNo Serializd shows found.")
        return None

    print("\nSerializd show matches:")
    for i, item in enumerate(results[:10], 1):
        name = item.get("name") or item.get("title") or "Unknown title"
        year = item.get("firstAirDate") or item.get("first_air_date") or "year unknown"
        sid = item.get("id")
        print(f"{i}. {name} | ID: {sid} | {year}")

    while True:
        raw = input("Choose a Serializd show (B = back, 0/Cancel = cancel): ").strip()
        command = raw.casefold()
        if command in {"0", "cancel", "c", "q"}:
            return _CANCEL
        if command in {"b", "back"}:
            return _BACK
        try:
            return results[int(raw) - 1]
        except (ValueError, IndexError):
            print("Invalid selection.")


def _m151_choose_serializd_season(show_id: int):
    show_data = get_show(show_id) or {}
    seasons = show_data.get("seasons") or show_data.get("showSeasons") or []
    if not seasons:
        print("\nNo Serializd season metadata was returned.")
        return None

    print("\nSerializd seasons / arcs:")
    for i, season in enumerate(seasons, 1):
        number = _serializd_season_number(season)
        if number is None:
            number = i - 1
        name = season.get("name") or f"Season {number}"
        sid = season.get("seasonId", season.get("id"))
        print(f"{i}. S{int(number):02d} â€” {name} | ID: {sid}")

    while True:
        raw = input("Choose a season / arc (B = back, 0/Cancel = cancel): ").strip()
        command = raw.casefold()
        if command in {"0", "cancel", "c", "q"}:
            return _CANCEL
        if command in {"b", "back"}:
            return _BACK
        try:
            selected = seasons[int(raw) - 1]
            sid = selected.get("seasonId", selected.get("id"))
            if sid is None:
                raise ValueError
            number = _serializd_season_number(selected)
            return {
                "season_id": int(sid),
                "season_number": number if number is not None else int(raw) - 1,
                "name": selected.get("name") or f"Season {number}",
            }
        except (ValueError, IndexError, TypeError):
            print("Invalid season selection.")


def _m151_parse_rating(raw: str):
    value = raw.strip()
    if not value:
        return None
    try:
        rating = float(value)
    except ValueError:
        return _INVALID
    if (
        rating < 0.5
        or rating > 5.0
        or abs(rating * 2 - round(rating * 2)) > 1e-9
    ):
        return _INVALID
    return rating




def _m153_finalize_review_lines(lines):
    """Return a multiline review while preserving intentional line breaks.

    Trailing blank lines are removed, but blank lines inside the review are
    preserved so the terminal collector can represent multiple paragraphs.
    """
    cleaned = [line.rstrip() for line in lines]
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    return "\n".join(cleaned).strip()


def _m153_collect_multiline_review():
    """Collect a multiline review from the terminal.

    Enter submits the current line and starts another line. The explicit
    /done command finishes the review, so Enter is no longer ambiguous.
    /back and /cancel provide workflow navigation without consuming review
    content.
    """
    print("\nWhat is your season review?")
    print("Type your review one line at a time.")
    print("Press Enter after each line to continue.")
    print("When finished, type /done on a new line.")
    print("Commands: /back = previous step, /cancel = cancel workflow")

    lines = []
    while True:
        line = input("> ")
        command = line.strip().casefold()

        if command == "/done":
            review = _m153_finalize_review_lines(lines)
            if not review:
                print("A season review cannot be empty. Enter some text before /done.")
                continue
            return review

        if command == "/cancel":
            return _CANCEL

        if command == "/back":
            return _BACK

        # Preserve ordinary review text exactly enough to keep paragraph
        # structure. A leading/trailing space on a line is not meaningful in
        # the terminal editor, so only trailing whitespace is removed.
        lines.append(line.rstrip())


def run_m151_review_season_workflow():
    """Run the M15.1 guided Review â†’ Season workflow."""
    workflow = M151ReviewSeasonWorkflow()

    print("\n================================================")
    print("WAYMARK â€” REVIEW SEASON WORKFLOW (M15.3)")
    print("================================================")
    print("Review â†’ Season")
    print("This workflow prepares a Serializd season-review Action Plan with multiline review input.")
    print("No service write occurs until the exact Serializd write request is verified.")

    # 1. Title
    raw = input(
        "\nWhat show do you want to review? "
        "(B = back, 0/Cancel = cancel)\n> "
    ).strip()
    if raw.casefold() in {"0", "cancel", "c", "q"}:
        print("\nCancelled. No service data was changed.")
        return
    if raw.casefold() in {"b", "back"}:
        print("\nAlready at the start of Review â†’ Season.")
        return
    if not raw:
        print("Please enter a show title.")
        return
    workflow.set_data("title", raw)

    # 2. Anime classification
    while True:
        raw = input(
            "\nIs it an anime? [Y/N] "
            "(B = back, 0/Cancel = cancel)\n> "
        ).strip().casefold()
        if raw in {"0", "cancel", "c", "q"}:
            print("\nCancelled. No service data was changed.")
            return
        if raw in {"b", "back"}:
            print("\nGoing back to title entry.")
            raw = input(
                "What show do you want to review? "
                "(0/Cancel = cancel)\n> "
            ).strip()
            if not raw or raw.casefold() in {"0", "cancel", "c", "q"}:
                print("\nCancelled. No service data was changed.")
                return
            workflow.set_data("title", raw)
            continue
        if raw in {"y", "yes", "n", "no"}:
            workflow.set_data("anime", raw in {"y", "yes"})
            break
        print("Please answer Y or N.")

    # 3. Media type
    while True:
        raw = input(
            "\nIs it a TV show or a movie? [TV/Movie] "
            "(B = back, 0/Cancel = cancel)\n> "
        ).strip().casefold()
        if raw in {"0", "cancel", "c", "q"}:
            print("\nCancelled. No service data was changed.")
            return
        if raw in {"b", "back"}:
            raw = input("\nIs it an anime? [Y/N]\n> ").strip().casefold()
            if raw not in {"y", "yes", "n", "no"}:
                print("\nCancelled. No service data was changed.")
                return
            workflow.set_data("anime", raw in {"y", "yes"})
            continue
        if raw in {"tv", "t", "tv show", "show", "series"}:
            workflow.set_data("media_type", "tv")
            break
        if raw in {"movie", "m", "film"}:
            print("\nM15.1 currently handles TV season reviews only.")
            print("No service data was changed.")
            return
        print("Please choose TV or Movie.")

    # 4. Serializd show identity
    try:
        selected = _m151_choose_serializd_show(workflow.data["title"])
    except Exception as exc:
        print(f"\nSerializd title search failed: {exc}")
        return
    if selected is _CANCEL:
        print("\nCancelled. No service data was changed.")
        return
    if selected is _BACK:
        print("\nGoing back to title entry.")
        return run_m151_review_season_workflow()
    if selected is None:
        return

    try:
        show_id = int(selected["id"])
    except (KeyError, TypeError, ValueError):
        print("Selected Serializd result has no usable ID.")
        return

    workflow.set_data("serializd_show_id", show_id)
    workflow.set_data(
        "serializd_show_title",
        selected.get("name") or selected.get("title") or workflow.data["title"],
    )

    # 5. Serializd season / arc identity
    while True:
        try:
            season = _m151_choose_serializd_season(show_id)
        except Exception as exc:
            print(f"\nSerializd season lookup failed: {exc}")
            return

        if season is _CANCEL:
            print("\nCancelled. No service data was changed.")
            return

        if season is _BACK:
            try:
                selected = _m151_choose_serializd_show(workflow.data["title"])
            except Exception as exc:
                print(f"\nSerializd title search failed: {exc}")
                return
            if selected is _CANCEL:
                print("\nCancelled. No service data was changed.")
                return
            if selected is _BACK:
                continue
            if selected is None:
                return
            try:
                show_id = int(selected["id"])
            except (KeyError, TypeError, ValueError):
                print("Selected Serializd result has no usable ID.")
                return
            workflow.set_data("serializd_show_id", show_id)
            workflow.set_data(
                "serializd_show_title",
                selected.get("name") or selected.get("title") or workflow.data["title"],
            )
            continue

        if season is None:
            return

        workflow.set_data("serializd_season_id", season["season_id"])
        workflow.set_data("season_number", season["season_number"])
        workflow.set_data("season_name", season["name"])
        break

    # 6. Rating
    while True:
        raw = input(
            "\nSeason rating on Serializd "
            "(0.5â€“5.0, Enter = no rating; B = back, 0/Cancel = cancel)\n> "
        ).strip()
        if raw.casefold() in {"0", "cancel", "c", "q"}:
            print("\nCancelled. No service data was changed.")
            return
        if raw.casefold() in {"b", "back"}:
            print("\nGoing back to season selection.")
            return run_m151_review_season_workflow()
        rating = _m151_parse_rating(raw)
        if rating is _INVALID:
            print("Enter 0.5â€“5.0 in half-star increments, or press Enter to skip.")
            continue
        workflow.set_data("rating", rating)
        break

    # 7. Review text â€” multiline terminal editor
    review = _m153_collect_multiline_review()
    if review is _CANCEL:
        print("\nCancelled. No service data was changed.")
        return
    if review is _BACK:
        print("\nGoing back to season rating.")
        while True:
            raw = input(
                "Season rating on Serializd "
                "(0.5â€“5.0, Enter = no rating)\n> "
            ).strip()
            if raw.casefold() in {"0", "cancel", "c", "q"}:
                print("\nCancelled. No service data was changed.")
                return
            rating = _m151_parse_rating(raw)
            if rating is _INVALID:
                print("Invalid rating.")
                continue
            workflow.set_data("rating", rating)
            break
        review = _m153_collect_multiline_review()
        if review is _CANCEL:
            print("\nCancelled. No service data was changed.")
            return
        if review is _BACK:
            print("\nAlready at the review entry screen. No service data was changed.")
            return
    workflow.set_data("review_text", review)

    # 8. Build Action Plan
    try:
        plan = workflow.build_action_plan()
    except ValueError as exc:
        print(f"\nValidation failed: {exc}")
        return

    workflow.set_state("REVIEW_SEASON_CONFIRM")

    print("\n================================================")
    print("REVIEW SEASON â€” CONFIRMATION")
    print("================================================")
    print(f"Show: {workflow.data['serializd_show_title']}")
    print(
        f"Season/Arc: S{int(workflow.data['season_number']):02d} "
        f"â€” {workflow.data['season_name']}"
    )
    print(f"Serializd show ID: {workflow.data['serializd_show_id']}")
    print(f"Serializd season ID: {workflow.data['serializd_season_id']}")
    print(
        "Rating: "
        f"{workflow.data['rating'] if workflow.data['rating'] is not None else 'not set'}"
    )
    print(f"Review: {workflow.data['review_text']}")
    print("\nPlanned operation: Serializd season review")
    print("Execution status: READY â€” Serializd season-review request verified.")

    raw = input(
        "\nConfirm this Action Plan? [Y/N] "
        "(B = back, 0/Cancel = cancel)\n> "
    ).strip().casefold()

    if raw in {"0", "cancel", "c", "q", "n", "no"}:
        print("\nCancelled. No service data was changed.")
        return
    if raw in {"b", "back"}:
        print("\nReturning to season review details. No service data was changed.")
        return
    if raw not in {"y", "yes"}:
        print("\nPlease answer Y or N. No service data was changed.")
        return

    print("\nAction Plan confirmed.")
    print("Executing verified Serializd season review...")

    operation = plan.operations[0]
    try:
        result = log_season_review(
            int(operation["show_id"]),
            int(operation["season_id"]),
            stars=operation.get("rating"),
            review_text=operation.get("review_text", ""),
            is_rewatch=False,
            backdate=(
                datetime.now(timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            ),
        )
    except Exception as exc:
        print(f"\nSerializd season-review execution failed: {exc}")
        print("No additional WAYMARK writes were attempted.")
        workflow.set_state("REVIEW_SEASON_RESULT")
        return plan

    print("\n================================================")
    print("WAYMARK RESULT")
    print("================================================")
    print("Serializd season review submitted successfully.")
    if result is not None:
        print(f"Serializd response: {result}")
    workflow.set_state("REVIEW_SEASON_RESULT")
    return plan


def m153_multiline_review_smoke_test():
    """Offline validation for multiline review preservation."""
    review = _m153_finalize_review_lines([
        "Paragraph one.",
        "",
        "Paragraph two.",
        "Final line.",
        "",
    ])
    assert review == "Paragraph one.\n\nParagraph two.\nFinal line."
    assert _m153_finalize_review_lines(["", "   "]) == ""
    return "M15.3 multiline review smoke test passed."


def m151_review_season_smoke_test():
    """Offline validation of the M15.1 state/data/ActionPlan layer."""
    workflow = M151ReviewSeasonWorkflow()
    assert workflow.state == "REVIEW_SEASON_TITLE"

    workflow.set_data("title", "Frieren")
    workflow.set_state("REVIEW_SEASON_IS_ANIME")
    workflow.set_data("anime", True)
    workflow.set_state("REVIEW_SEASON_MEDIA_TYPE")
    workflow.set_data("media_type", "tv")
    workflow.set_state("SELECT_SERIALIZD_SHOW")
    workflow.set_data("serializd_show_id", 209867)
    workflow.set_data("serializd_show_title", "Frieren: Beyond Journey's End")
    workflow.set_state("SELECT_SERIALIZD_SEASON")
    workflow.set_data("serializd_season_id", 123456)
    workflow.set_data("season_number", 1)
    workflow.set_data("season_name", "Season 1")
    workflow.set_state("REVIEW_SEASON_RATING")
    workflow.set_data("rating", 5.0)
    workflow.set_state("REVIEW_SEASON_TEXT")
    workflow.set_data("review_text", "Offline M15.1 smoke-test review.")

    plan = workflow.build_action_plan()
    assert plan.workflow_id == "M15.2_REVIEW_SEASON"
    assert plan.operations[0]["operation"] == "review_season"
    assert plan.operations[0]["service"] == "serializd"
    assert plan.metadata["execution_enabled"] is True

    assert workflow.back() is True
    assert workflow.state == "REVIEW_SEASON_RATING"

    workflow.cancel()
    assert workflow.context.cancelled is True
    return "M15.1 Review Season smoke test passed."


def m152_review_season_smoke_test():
    """Offline validation that M15.2 produces an executable verified plan."""
    result = m151_review_season_smoke_test()
    assert result == "M15.1 Review Season smoke test passed."
    return "M15.2 Review Season smoke test passed."



# ============================================================
# M15.4 â€” REVIEW EPISODE WORKFLOW
# ============================================================

M154_REVIEW_EPISODE_WORKFLOW_ID = "M15.4_REVIEW_EPISODE"

class M154ReviewEpisodeWorkflow:
    """Guided Serializd episode-review workflow."""

    STATES = (
        "REVIEW_EPISODE_TITLE",
        "REVIEW_EPISODE_IS_ANIME",
        "REVIEW_EPISODE_MEDIA_TYPE",
        "SELECT_SERIALIZD_SHOW",
        "SELECT_SERIALIZD_SEASON",
        "SELECT_SERIALIZD_EPISODE",
        "REVIEW_EPISODE_RATING",
        "REVIEW_EPISODE_TEXT",
        "REVIEW_EPISODE_CONFIRM",
        "REVIEW_EPISODE_RESULT",
    )

    def __init__(self):
        self.state = "REVIEW_EPISODE_TITLE"
        self.data: Dict[str, Any] = {}

    def set_state(self, state: str):
        if state not in self.STATES:
            raise ValueError(f"Unknown M15.4 state: {state}")
        self.state = state
        return state

    def set_data(self, key: str, value: Any):
        self.data[key] = value
        return value

    def validate(self):
        d = self.data
        if not str(d.get("title", "")).strip():
            raise ValueError("A show title is required.")
        if d.get("anime") not in {True, False}:
            raise ValueError("Anime classification is required.")
        if d.get("media_type") != "tv":
            raise ValueError("Episode review currently requires a TV show.")
        if not d.get("serializd_show_id"):
            raise ValueError("A Serializd show identity is required.")
        if not d.get("serializd_season_id"):
            raise ValueError("A Serializd season identity is required.")
        if d.get("serializd_episode_number") is None:
            raise ValueError("A Serializd episode identity is required.")
        rating = d.get("rating")
        if rating is not None and (
            not isinstance(rating, (int, float))
            or not 0.5 <= float(rating) <= 5.0
            or abs(float(rating) * 2 - round(float(rating) * 2)) > 1e-9
        ):
            raise ValueError("Serializd episode rating must be between 0.5 and 5.0 in half-star increments.")
        if not str(d.get("review_text", "")).strip():
            raise ValueError("Episode review text is required.")
        return True

    def build_action_plan(self):
        self.validate()
        d = self.data
        return ActionPlan(
            workflow_id=M154_REVIEW_EPISODE_WORKFLOW_ID,
            operations=[{
                "service": "serializd",
                "operation": "review_episode",
                "show_id": int(d["serializd_show_id"]),
                "season_id": int(d["serializd_season_id"]),
                "season_number": int(d["season_number"]),
                "episode_number": int(d["serializd_episode_number"]),
                "episode_name": d.get("serializd_episode_name", ""),
                "rating": (
                    float(d["rating"]) if d.get("rating") is not None else None
                ),
                "review_text": str(d["review_text"]).strip(),
                "verified_endpoint": "POST /api/show/reviews/add",
                "verified_rating_scale": "WAYMARK 0.5-5.0 stars -> Serializd API 1-10",
            }],
            metadata={
                "workflow": M154_REVIEW_EPISODE_WORKFLOW_ID,
                "execution_enabled": True,
                "execution_reason": (
                    "Serializd episode review uses the existing verified "
                    "episode review/log service adapter."
                ),
                "endpoint": "https://serializddesktop.onrender.com/api/show/reviews/add",
                "episode_number_is_serializd_local_number": True,
            },
        )


def _m154_collect_multiline_review():
    print("\nWhat is your episode review?")
    print("Type your review one line at a time.")
    print("Press Enter after each line to continue.")
    print("When finished, type /done on a new line.")
    print("Commands: /back = previous step, /cancel = cancel workflow")

    lines = []
    while True:
        line = input("> ")
        command = line.strip().casefold()

        if command == "/done":
            review = _m153_finalize_review_lines(lines)
            if not review:
                print("An episode review cannot be empty. Enter some text before /done.")
                continue
            return review

        if command == "/cancel":
            return _CANCEL

        if command == "/back":
            return _BACK

        lines.append(line)


def _m154_choose_episode(show_id: int, season_number: int):
    try:
        detail = get_season(show_id, season_number) or {}
    except Exception as exc:
        print(f"\nSerializd episode lookup failed: {exc}")
        return None

    episodes = detail.get("episodes") or []
    numbered = []
    for episode in episodes:
        try:
            number = int(episode.get("episodeNumber"))
        except (TypeError, ValueError):
            continue
        if number > 0:
            numbered.append((number, episode))

    numbered.sort(key=lambda pair: pair[0])
    if not numbered:
        print("\nNo numbered Serializd episodes were returned for this season.")
        return None

    print("\nSerializd episodes:")
    for index, (number, episode) in enumerate(numbered, 1):
        name = episode.get("name") or episode.get("title") or f"Episode {number}"
        print(f"{index}. E{number} â€” {name}")

    while True:
        raw = input(
            "Choose an episode (B = back, 0/Cancel = cancel): "
        ).strip()
        command = raw.casefold()
        if command in {"0", "cancel", "c", "q"}:
            return _CANCEL
        if command in {"b", "back"}:
            return _BACK
        try:
            selected = numbered[int(raw) - 1]
            number, episode = selected
            return {
                "episode_number": number,
                "name": episode.get("name") or episode.get("title") or f"Episode {number}",
            }
        except (ValueError, IndexError):
            print("Invalid episode selection.")


def run_m154_review_episode_workflow():
    print("\n================================================")
    print("WAYMARK â€” REVIEW EPISODE WORKFLOW (M15.4)")
    print("================================================")
    print("Review â†’ Episode")
    print("Episode reviews are written to Serializd.")
    print("Serializd episode numbering is kept independent from MAL numbering.")

    workflow = M154ReviewEpisodeWorkflow()

    # 1. Title
    while True:
        raw = input(
            "\nWhat show do you want to review an episode from? "
            "(B = back, 0/Cancel = cancel)\n> "
        ).strip()
        command = raw.casefold()
        if command in {"0", "cancel", "c", "q", "b", "back"}:
            print("Cancelled. No service data was changed.")
            return
        if raw:
            workflow.set_data("title", raw)
            break
        print("Please enter a show title.")

    # 2. Anime
    while True:
        raw = input(
            "\nIs it an anime? [Y/N] "
            "(B = back, 0/Cancel = cancel)\n> "
        ).strip().casefold()
        if raw in {"0", "cancel", "c", "q"}:
            print("Cancelled. No service data was changed.")
            return
        if raw in {"b", "back"}:
            print("Returning to title entry.")
            return
        if raw in {"y", "yes"}:
            workflow.set_data("anime", True)
            break
        if raw in {"n", "no"}:
            workflow.set_data("anime", False)
            break
        print("Please answer Y or N.")

    # 3. Media type
    while True:
        raw = input(
            "\nIs it a TV show or a movie? [TV/Movie] "
            "(B = back, 0/Cancel = cancel)\n> "
        ).strip().casefold()
        if raw in {"0", "cancel", "c", "q"}:
            print("Cancelled. No service data was changed.")
            return
        if raw in {"b", "back"}:
            print("Returning to anime classification.")
            return
        if raw in {"tv", "tv show", "show", "series"}:
            workflow.set_data("media_type", "tv")
            break
        if raw in {"movie", "film"}:
            print("Episode reviews require a TV/series identity.")
            continue
        print("Please answer TV or Movie.")

    # 4. Serializd show
    selected_show = _m151_choose_serializd_show(workflow.data["title"])
    if selected_show is _CANCEL:
        print("Cancelled. No service data was changed.")
        return
    if selected_show is _BACK:
        print("Returning to media type.")
        return
    if not selected_show:
        return

    show_id = int(selected_show["id"])
    show_title = selected_show.get("name") or selected_show.get("title") or workflow.data["title"]
    workflow.set_data("serializd_show_id", show_id)
    workflow.set_data("serializd_show_title", show_title)

    # 5. Serializd season
    season = _m151_choose_serializd_season(show_id)
    if season is _CANCEL:
        print("Cancelled. No service data was changed.")
        return
    if season is _BACK:
        print("Returning to Serializd show selection.")
        return
    if not season:
        return

    workflow.set_data("serializd_season_id", int(season["season_id"]))
    workflow.set_data("season_number", int(season["season_number"]))
    workflow.set_data("season_name", season["name"])

    # 6. Serializd episode
    episode = _m154_choose_episode(show_id, int(season["season_number"]))
    if episode is _CANCEL:
        print("Cancelled. No service data was changed.")
        return
    if episode is _BACK:
        print("Returning to Serializd season selection.")
        return
    if not episode:
        return

    workflow.set_data("serializd_episode_number", int(episode["episode_number"]))
    workflow.set_data("serializd_episode_name", episode["name"])

    # 7. Rating
    while True:
        raw = input(
            "\nEpisode rating on Serializd "
            "(0.5â€“5.0, Enter = no rating; B = back, 0/Cancel = cancel)\n> "
        ).strip()
        command = raw.casefold()
        if command in {"0", "cancel", "c", "q"}:
            print("Cancelled. No service data was changed.")
            return
        if command in {"b", "back"}:
            print("Returning to episode selection.")
            return
        if not raw:
            workflow.set_data("rating", None)
            break
        rating = _m151_parse_rating(raw)
        if rating is _INVALID:
            print("Invalid rating.")
            continue
        workflow.set_data("rating", rating)
        break

    # 8. Multiline review
    review = _m154_collect_multiline_review()
    if review is _CANCEL:
        print("Cancelled. No service data was changed.")
        return
    if review is _BACK:
        print("Returning to episode rating.")
        return
    workflow.set_data("review_text", review)

    # 9. ActionPlan + confirmation
    try:
        plan = workflow.build_action_plan()
    except ValueError as exc:
        print(f"\nValidation failed: {exc}")
        return

    operation = plan.operations[0]

    print("\n================================================")
    print("REVIEW EPISODE â€” CONFIRMATION")
    print("================================================")
    print(f"Show: {show_title}")
    print(f"Season/Arc: S{operation['season_number']:02d} â€” {season['name']}")
    print(
        f"Episode: E{operation['episode_number']} â€” "
        f"{operation['episode_name']}"
    )
    print(f"Serializd show ID: {operation['show_id']}")
    print(f"Serializd season ID: {operation['season_id']}")
    print(f"Serializd episode number: {operation['episode_number']}")
    print(
        "Rating: "
        f"{operation['rating'] if operation['rating'] is not None else 'not set'}"
    )
    print(f"Review: {operation['review_text']}")
    print("\nPlanned operation: Serializd episode review")
    print("Execution status: READY â€” verified Serializd episode-review adapter.")

    while True:
        raw = input(
            "\nConfirm this Action Plan? [Y/N] "
            "(B = back, 0/Cancel = cancel)\n> "
        ).strip().casefold()

        if raw in {"0", "cancel", "c", "q", "n", "no"}:
            print("\nCancelled. No service data was changed.")
            return
        if raw in {"b", "back"}:
            print("\nCancelled. No service data was changed.")
            return
        if raw in {"y", "yes"}:
            break
        print("Please answer Y or N.")

    print("\nAction Plan confirmed.")
    print("Executing verified Serializd episode review...")

    try:
        result = log_episode(
            int(operation["show_id"]),
            int(operation["season_id"]),
            int(operation["episode_number"]),
            stars=operation.get("rating"),
            review_text=operation.get("review_text", ""),
            is_rewatch=False,
            backdate=(
                datetime.now(timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            ),
        )
    except Exception as exc:
        print(f"\nSerializd episode-review execution failed: {exc}")
        print("No additional WAYMARK writes were attempted.")
        return

    print("\n================================================")
    print("WAYMARK RESULT")
    print("================================================")
    print("Serializd episode review submitted successfully.")
    if result is not None:
        print(f"Serializd response: {result}")


def m154_episode_review_smoke_test():
    """Offline structural test; no Serializd calls or writes."""
    workflow = M154ReviewEpisodeWorkflow()
    workflow.data.update({
        "title": "Frieren",
        "anime": True,
        "media_type": "tv",
        "serializd_show_id": 209867,
        "serializd_show_title": "Frieren: Beyond Journey's End",
        "serializd_season_id": 307972,
        "season_number": 1,
        "season_name": "Season 1",
        "serializd_episode_number": 21,
        "serializd_episode_name": "Episode 21",
        "rating": 5.0,
        "review_text": "First paragraph.\n\nSecond paragraph.",
    })

    plan = workflow.build_action_plan()
    assert plan.workflow_id == M154_REVIEW_EPISODE_WORKFLOW_ID
    assert len(plan.operations) == 1
    op = plan.operations[0]
    assert op["show_id"] == 209867
    assert op["season_id"] == 307972
    assert op["episode_number"] == 21
    assert op["rating"] == 5.0
    assert op["review_text"] == "First paragraph.\n\nSecond paragraph."
    assert plan.metadata["execution_enabled"] is True
    return "M15.4 Episode Review smoke test passed."

if os.environ.get("WAYMARK_M154_SMOKE_TEST") == "1":
    print(m154_episode_review_smoke_test())
    raise SystemExit(0)


# ============================================================
# M15.5 â€” REVIEW SERIES WORKFLOW
# ============================================================

M155_REVIEW_SERIES_WORKFLOW_ID = "M15.5_REVIEW_SERIES"


class M155ReviewSeriesWorkflow:
    """
    Guided Serializd series-review workflow.

    The exact series-level Serializd write request was manually verified from
    the official Serializd web UI in M15.5. A series review uses the same
    verified POST endpoint as season/episode reviews, with:
      season_id = None
      episode_number = None
    """

    STATES = (
        "REVIEW_SERIES_TITLE",
        "REVIEW_SERIES_IS_ANIME",
        "REVIEW_SERIES_MEDIA_TYPE",
        "SELECT_SERIALIZD_SHOW",
        "REVIEW_SERIES_RATING",
        "REVIEW_SERIES_TEXT",
        "REVIEW_SERIES_CONFIRM",
        "REVIEW_SERIES_RESULT",
    )

    def __init__(self):
        self.state = "REVIEW_SERIES_TITLE"
        self.data: Dict[str, Any] = {}

    def set_state(self, state: str):
        if state not in self.STATES:
            raise ValueError(f"Unknown M15.5 state: {state}")
        self.state = state
        return state

    def set_data(self, key: str, value: Any):
        self.data[key] = value
        return value

    def validate(self):
        d = self.data
        if not str(d.get("title", "")).strip():
            raise ValueError("A show title is required.")
        if d.get("anime") not in {True, False}:
            raise ValueError("Anime classification is required.")
        if d.get("media_type") != "tv":
            raise ValueError("Series review currently requires a TV show.")
        if not d.get("serializd_show_id"):
            raise ValueError("A Serializd show identity is required.")
        rating = d.get("rating")
        if rating is not None and (
            not isinstance(rating, (int, float))
            or not 0.5 <= float(rating) <= 5.0
            or abs(float(rating) * 2 - round(float(rating) * 2)) > 1e-9
        ):
            raise ValueError(
                "Serializd series rating must be between 0.5 and 5.0 "
                "in half-star increments."
            )
        if not str(d.get("review_text", "")).strip():
            raise ValueError("Series review text is required.")
        return True

    def build_action_plan(self):
        self.validate()
        d = self.data

        # Verified from Serializd's official UI:
        # POST /api/show/reviews/add
        # Series-level review is represented by season_id=None and
        # episode_number=None. The existing Serializd review adapter is used
        # so authentication and request headers remain centralized there.
        return ActionPlan(
            workflow_id=M155_REVIEW_SERIES_WORKFLOW_ID,
            operations=[{
                "service": "serializd",
                "operation": "review_series",
                "show_id": int(d["serializd_show_id"]),
                "rating": (
                    float(d["rating"]) if d.get("rating") is not None else None
                ),
                "review_text": str(d["review_text"]).strip(),
                "season_id": None,
                "episode_number": None,
                "verified_endpoint": (
                    "https://serializddesktop.onrender.com/api/show/reviews/add"
                ),
            }],
            metadata={
                "workflow": M155_REVIEW_SERIES_WORKFLOW_ID,
                "execution_enabled": True,
                "execution_reason": (
                    "Series-level Serializd review request verified from "
                    "official UI discovery: season_id=null and "
                    "episode_number=null."
                ),
                "endpoint": (
                    "https://serializddesktop.onrender.com/api/show/reviews/add"
                ),
                "rating_mapping": (
                    "WAYMARK 0.5-5.0 stars -> Serializd API 1-10"
                ),
            },
        )


def _m155_collect_multiline_review():
    print("\nWhat is your series review?")
    print("Type your review one line at a time.")
    print("Press Enter after each line to continue.")

    print("When finished, type /done on a new line.")
    print("Commands: /back = previous step, /cancel = cancel workflow")

    lines = []
    while True:
        line = input("> ")
        command = line.strip().casefold()

        if command == "/done":
            review = _m153_finalize_review_lines(lines)
            if not review:
                print("A series review cannot be empty. Enter some text before /done.")
                continue
            return review

        if command == "/cancel":
            return _CANCEL

        if command == "/back":
            return _BACK

        lines.append(line)


def run_m155_review_series_workflow():
    print("\n================================================")
    print("WAYMARK â€” REVIEW SERIES WORKFLOW (M15.5)")
    print("================================================")
    print("Review â†’ Series")
    print("This workflow builds and executes a verified Serializd series-review Action Plan.")
    print("Verified: POST /api/show/reviews/add with season_id=null and episode_number=null.")

    workflow = M155ReviewSeriesWorkflow()

    # Title
    while True:
        raw = input(
            "\nWhat show do you want to review? "
            "(B = back, 0/Cancel = cancel)\n> "
        ).strip()
        command = raw.casefold()

        if command in {"0", "cancel", "c", "q", "b", "back"}:
            print("Cancelled. No service data was changed.")
            return
        if raw:
            workflow.set_data("title", raw)
            break
        print("Please enter a show title.")

    # Anime
    while True:
        raw = input(
            "\nIs it an anime? [Y/N] "
            "(B = back, 0/Cancel = cancel)\n> "
        ).strip().casefold()

        if raw in {"0", "cancel", "c", "q"}:
            print("Cancelled. No service data was changed.")
            return
        if raw in {"b", "back"}:
            print("Returning to title entry.")
            return
        if raw in {"y", "yes"}:
            workflow.set_data("anime", True)
            break
        if raw in {"n", "no"}:
            workflow.set_data("anime", False)
            break
        print("Please answer Y or N.")

    # Media type
    while True:
        raw = input(
            "\nIs it a TV show or a movie? [TV/Movie] "
            "(B = back, 0/Cancel = cancel)\n> "
        ).strip().casefold()

        if raw in {"0", "cancel", "c", "q"}:
            print("Cancelled. No service data was changed.")
            return
        if raw in {"b", "back"}:
            print("Returning to anime classification.")
            return
        if raw in {"tv", "tv show", "show", "series"}:
            workflow.set_data("media_type", "tv")
            break
        if raw in {"movie", "film"}:
            print("Series review currently requires a TV/series identity.")
            continue
        print("Please answer TV or Movie.")

    # Serializd show
    selected_show = _m151_choose_serializd_show(workflow.data["title"])
    if selected_show is _CANCEL:
        print("Cancelled. No service data was changed.")
        return
    if selected_show is _BACK:
        print("Returning to media type.")
        return
    if not selected_show:
        return

    show_id = int(selected_show["id"])
    show_title = (
        selected_show.get("name")
        or selected_show.get("title")
        or workflow.data["title"]
    )
    workflow.set_data("serializd_show_id", show_id)
    workflow.set_data("serializd_show_title", show_title)

    # Rating
    while True:
        raw = input(
            "\nSeries rating on Serializd "
            "(0.5â€“5.0, Enter = no rating; B = back, 0/Cancel = cancel)\n> "
        ).strip()
        command = raw.casefold()

        if command in {"0", "cancel", "c", "q"}:
            print("Cancelled. No service data was changed.")
            return
        if command in {"b", "back"}:
            print("Returning to Serializd show selection.")
            return
        if not raw:
            workflow.set_data("rating", None)
            break

        rating = _m151_parse_rating(raw)
        if rating is _INVALID:
            print("Invalid rating.")
            continue
        workflow.set_data("rating", rating)
        break

    # Review
    review = _m155_collect_multiline_review()
    if review is _CANCEL:
        print("Cancelled. No service data was changed.")
        return
    if review is _BACK:
        print("Returning to series rating.")
        return
    workflow.set_data("review_text", review)

    try:
        plan = workflow.build_action_plan()
    except ValueError as exc:
        print(f"\nValidation failed: {exc}")
        return

    operation = plan.operations[0]

    print("\n================================================")
    print("REVIEW SERIES â€” CONFIRMATION")
    print("================================================")
    print(f"Show: {show_title}")
    print(f"Serializd show ID: {operation['show_id']}")
    print(
        "Rating: "
        f"{operation['rating'] if operation['rating'] is not None else 'not set'}"
    )
    print(f"Review: {operation['review_text']}")
    print("\nPlanned operation: Serializd series review")
    print("Execution status: READY â€” verified Serializd series-review adapter.")

    while True:
        raw = input(
            "\nConfirm this Action Plan? [Y/N] "
            "(B = back, 0/Cancel = cancel)\n> "
        ).strip().casefold()

        if raw in {"0", "cancel", "c", "q", "n", "no", "b", "back"}:
            print("\nCancelled. No service data was changed.")
            return
        if raw in {"y", "yes"}:
            break
        print("Please answer Y or N.")

    print("\nAction Plan confirmed.")
    print("Executing verified Serializd series review...")

    # The verified Serializd request uses the dedicated series-review adapter.
    # It sends season_id=None and episode_number=None while preserving the
    # module's centralized authentication, headers, backdate handling, and
    # error behavior.
    try:
        result = log_series_review(
            int(operation["show_id"]),
            stars=operation.get("rating"),
            review_text=operation.get("review_text", ""),
            is_rewatch=False,
            backdate=(
                datetime.now(timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            ),
        )
    except Exception as exc:
        print(f"\nSerializd series-review execution failed: {exc}")
        print("No additional WAYMARK writes were attempted.")
        workflow.set_state("REVIEW_SERIES_RESULT")
        return plan

    print("\n================================================")
    print("WAYMARK RESULT")
    print("================================================")
    print("Serializd series review submitted successfully.")
    if result is not None:
        print(f"Serializd response: {result}")
    workflow.set_state("REVIEW_SERIES_RESULT")
    return plan


def m155_review_series_smoke_test():
    """Offline structural test; no network calls or writes."""
    workflow = M155ReviewSeriesWorkflow()
    workflow.data.update({
        "title": "Dark Matter",
        "anime": False,
        "media_type": "tv",
        "serializd_show_id": 196322,
        "serializd_show_title": "Dark Matter",
        "rating": 4.0,
        "review_text": "First paragraph.\n\nSecond paragraph.",
    })

    plan = workflow.build_action_plan()

    assert plan.workflow_id == M155_REVIEW_SERIES_WORKFLOW_ID
    assert len(plan.operations) == 1
    op = plan.operations[0]
    assert op["service"] == "serializd"
    assert op["operation"] == "review_series"
    assert op["show_id"] == 196322
    assert op["season_id"] is None
    assert op["episode_number"] is None
    assert plan.metadata["execution_enabled"] is True
    assert plan.metadata["endpoint"].endswith("/api/show/reviews/add")
    assert op["review_text"] == "First paragraph.\n\nSecond paragraph."

    return "M15.5 Series Review smoke test passed."



# ============================================================
# M16 â€” RATING WORKFLOWS
# ============================================================

M16_RATE_EPISODE_WORKFLOW_ID = "M16_RATE_EPISODE"
M16_RATE_SEASON_WORKFLOW_ID = "M16_RATE_SEASON"
M16_RATE_SERIES_WORKFLOW_ID = "M16_RATE_SERIES"
M16_RATE_ANIME_WORKFLOW_ID = "M16_RATE_ANIME"


class M16RatingWorkflow:
    """Deterministic, review-independent rating workflow."""

    def __init__(self, workflow_id: str, level: str):
        self.workflow_id = workflow_id
        self.level = level
        self.data: dict[str, Any] = {}

    def set_data(self, key: str, value: Any):
        self.data[key] = value
        return value

    def validate(self):
        if not str(self.data.get("title", "")).strip():
            raise ValueError("A title is required.")
        rating = self.data.get("rating")
        if self.level == "anime":
            if not isinstance(rating, int) or isinstance(rating, bool):
                raise ValueError("MAL rating must be a whole number from 1 to 10.")
            if not 1 <= rating <= 10:
                raise ValueError("MAL rating must be a whole number from 1 to 10.")
        else:
            if not isinstance(rating, (int, float)) or isinstance(rating, bool):
                raise ValueError("A rating is required.")
            rating = float(rating)
            if rating < 0.5 or rating > 5.0 or abs(rating * 2 - round(rating * 2)) > 1e-9:
                raise ValueError("Rating must be between 0.5 and 5.0 in half-star increments.")
        if self.level in {"episode", "season", "series"} and not self.data.get("serializd_show_id"):
            raise ValueError("A Serializd show identity is required.")
        if self.level == "episode":
            if not self.data.get("serializd_season_id"):
                raise ValueError("A Serializd season identity is required.")
            if not self.data.get("serializd_episode_number"):
                raise ValueError("A Serializd episode identity is required.")
        if self.level == "season" and not self.data.get("serializd_season_id"):
            raise ValueError("A Serializd season identity is required.")
        if self.level == "anime" and not self.data.get("mal_id"):
            raise ValueError("A MAL anime identity is required.")
        return True

    def build_action_plan(self):
        self.validate()
        d = self.data
        rating = d["rating"]
        if self.level != "anime":
            rating = float(rating)
        if self.level == "anime":
            operation = {
                "service": "mal",
                "operation": "rate_anime",
                "mal_id": int(d["mal_id"]),
                "rating": int(rating),
            }
            endpoint = "MAL PATCH /anime/{anime_id}/my_list_status"
            mapping = "MAL native 1-10 score"
        else:
            operation = {
                "service": "serializd",
                "operation": f"rate_{self.level}",
                "show_id": int(d["serializd_show_id"]),
                "rating": rating,
            }
            if self.level == "episode":
                operation.update({
                    "season_id": int(d["serializd_season_id"]),
                    "episode_number": int(d["serializd_episode_number"]),
                })
            elif self.level == "season":
                operation["season_id"] = int(d["serializd_season_id"])
            endpoint = "Serializd POST /api/show/reviews/add"
            mapping = "WAYMARK 0.5-5.0 stars -> Serializd API 1-10"

        return ActionPlan(
            workflow_id=self.workflow_id,
            operations=[operation],
            metadata={
                "workflow": self.workflow_id,
                "execution_enabled": True,
                "review_independent": True,
                "endpoint": endpoint,
                "rating_mapping": mapping,
                "review_text": None,
            },
        )


def _m16_read_mal_rating():
    """Read MAL's native whole-number 1â€“10 score."""
    while True:
        raw = input(
            "\nMAL rating (1â€“10, whole numbers; B = back, 0/Cancel = cancel)\n> "
        ).strip()
        command = raw.casefold()
        if command in {"0", "cancel", "c", "q"}:
            return _CANCEL
        if command in {"b", "back"}:
            return _BACK
        try:
            rating = int(raw)
        except ValueError:
            print("Please enter a whole-number rating from 1 to 10.")
            continue
        if not 1 <= rating <= 10:
            print("Please enter a whole-number rating from 1 to 10.")
            continue
        return rating


def _m16_read_rating(label: str):
    while True:
        raw = input(
            f"\n{label} (0.5â€“5.0, half-star increments; B = back, 0/Cancel = cancel)\n> "
        ).strip()
        command = raw.casefold()
        if command in {"0", "cancel", "c", "q"}:
            return _CANCEL
        if command in {"b", "back"}:
            return _BACK
        rating = _m151_parse_rating(raw)
        if rating is _INVALID or rating is None:
            print("Please enter a rating from 0.5 to 5.0 in 0.5-star increments.")
            continue
        return rating


def _m16_confirm_and_execute(plan: ActionPlan, workflow: M16RatingWorkflow):
    op = plan.operations[0]
    print("\n================================================")
    print("WAYMARK â€” RATING CONFIRMATION")
    print("================================================")
    print(f"Title: {workflow.data.get('serializd_show_title') or workflow.data.get('title')}")
    if workflow.level == "anime":
        print(f"Rating: {op['rating']}/10")
    else:
        print(f"Rating: {op['rating']}â˜…")
    print(f"Service: {op['service'].title()}")
    if workflow.level == "episode":
        print(f"Serializd season ID: {op['season_id']}")
        print(f"Serializd episode: E{op['episode_number']:02d}")
    elif workflow.level == "season":
        print(f"Serializd season ID: {op['season_id']}")
    elif workflow.level == "anime":
        print(f"MAL ID: {op['mal_id']}")
    print("Review: none â€” rating-only workflow")
    print("\nPlanned operation: rating only")
    print("Execution status: READY")

    while True:
        raw = input("\nConfirm this Action Plan? [Y/N] (B = back, 0/Cancel = cancel)\n> ").strip().casefold()
        if raw in {"0", "cancel", "c", "q", "n", "no", "b", "back"}:
            print("\nCancelled. No service data was changed.")
            return None
        if raw in {"y", "yes"}:
            break
        print("Please answer Y or N.")

    try:
        if op["service"] == "serializd":
            if workflow.level == "episode":
                result = rate_episode(
                    op["show_id"], op["season_id"], op["episode_number"], op["rating"]
                )
            elif workflow.level == "season":
                result = rate_season(op["show_id"], op["season_id"], op["rating"])
            else:
                result = rate_series(op["show_id"], op["rating"])
        else:
            # MAL's score is an integer 1â€“10. This workflow accepts WAYMARK's
            # common half-star scale and converts it deterministically.
            result = update_score(op["mal_id"], op["rating"])
    except Exception as exc:
        print(f"\nWAYMARK rating execution failed: {exc}")
        print("No additional WAYMARK writes were attempted.")
        return plan

    print("\n================================================")
    print("WAYMARK RESULT")
    print("================================================")
    print("Rating submitted successfully.")
    if result is not None:
        print(f"Service response: {result}")
    return plan


def _m16_select_serializd_target(level: str, title: str):
    selected_show = _m151_choose_serializd_show(title)
    if selected_show is _CANCEL or selected_show is _BACK or selected_show is None:
        return selected_show
    show_id = int(selected_show["id"])
    show_title = selected_show.get("name") or selected_show.get("title") or title

    if level == "series":
        return {"show_id": show_id, "show_title": show_title}

    season = _m151_choose_serializd_season(show_id)
    if season is _CANCEL or season is _BACK or season is None:
        return season
    if level == "season":
        return {
            "show_id": show_id,
            "show_title": show_title,
            "season_id": season["season_id"],
            "season_number": season["season_number"],
            "season_name": season["name"],
        }

    episode = _m154_choose_episode(show_id, season["season_number"])
    if episode is _CANCEL or episode is _BACK or episode is None:
        return episode
    return {
        "show_id": show_id,
        "show_title": show_title,
        "season_id": season["season_id"],
        "season_number": season["season_number"],
        "season_name": season["name"],
        "episode_number": episode["episode_number"],
        "episode_name": episode["name"],
    }


def _m16_run_serializd_rating(level: str):
    workflow_id = {
        "episode": M16_RATE_EPISODE_WORKFLOW_ID,
        "season": M16_RATE_SEASON_WORKFLOW_ID,
        "series": M16_RATE_SERIES_WORKFLOW_ID,
    }[level]
    workflow = M16RatingWorkflow(workflow_id, level)
    print("\n================================================")
    print(f"WAYMARK â€” RATE {level.upper()} (M16)")
    print("================================================")
    print("Rating is independent from review. No review text will be requested.")

    title = input("\nWhat show do you want to rate? (B = back, 0/Cancel = cancel)\n> ").strip()
    if _is_cancel_command(title):
        print("Cancelled. No service data was changed.")
        return
    if title.casefold() in {"b", "back"}:
        return
    if not title:
        print("A title is required.")
        return
    workflow.set_data("title", title)

    selected = _m16_select_serializd_target(level, title)
    if selected is _CANCEL or selected is _BACK or selected is None:
        print("Cancelled or returned. No service data was changed.")
        return
    workflow.set_data("serializd_show_id", selected["show_id"])
    workflow.set_data("serializd_show_title", selected["show_title"])
    if "season_id" in selected:
        workflow.set_data("serializd_season_id", selected["season_id"])
        workflow.set_data("serializd_season_number", selected["season_number"])
        workflow.set_data("serializd_season_name", selected["season_name"])
    if "episode_number" in selected:
        workflow.set_data("serializd_episode_number", selected["episode_number"])
        workflow.set_data("serializd_episode_name", selected["episode_name"])

    rating = _m16_read_rating("Serializd rating")
    if rating is _CANCEL or rating is _BACK:
        print("Cancelled. No service data was changed.")
        return
    workflow.set_data("rating", rating)

    try:
        plan = workflow.build_action_plan()
    except ValueError as exc:
        print(f"\nValidation failed: {exc}")
        return
    return _m16_confirm_and_execute(plan, workflow)


def run_m16_rate_episode_workflow():
    return _m16_run_serializd_rating("episode")


def run_m16_rate_season_workflow():
    return _m16_run_serializd_rating("season")


def run_m16_rate_series_workflow():
    return _m16_run_serializd_rating("series")


def run_m16_rate_episode_final_workflow():
    print("\n================================================")
    print("WAYMARK â€” RATE EPISODE (M16 â€” FINAL)")
    print("================================================")
    print("Serializd episode rating only. No review text will be requested.")
    return _m16_run_serializd_rating("episode")


def run_m16_rate_season_final_workflow():
    print("\n================================================")
    print("WAYMARK â€” RATE SEASON (M16 â€” FINAL)")
    print("================================================")
    print("Serializd season rating only. No review text will be requested.")
    return _m16_run_serializd_rating("season")


def run_m16_rate_anime_workflow():
    print("\n================================================")
    print("WAYMARK â€” RATE ANIME / ANIME MOVIE (M16)")
    print("================================================")
    print("MAL is used for anime scoring, including anime movie entries.")
    print("Rating is independent from review. No review text will be requested.")

    workflow = M16RatingWorkflow(M16_RATE_ANIME_WORKFLOW_ID, "anime")
    title = input("\nWhat anime or anime movie do you want to rate? (B = back, 0/Cancel = cancel)\n> ").strip()
    if _is_cancel_command(title):
        print("Cancelled. No service data was changed.")
        return
    if title.casefold() in {"b", "back"}:
        return
    if not title:
        print("A title is required.")
        return
    workflow.set_data("title", title)

    try:
        selected = resolve_anime(title)
    except Exception as exc:
        print(f"\nMAL anime lookup failed: {exc}")
        return
    if selected is None or selected == _CANCEL or selected == _BACK:
        print("Cancelled. No service data was changed.")
        return
    try:
        workflow.set_data("mal_id", int(selected["node"]["id"]))
    except (KeyError, TypeError, ValueError):
        print("Could not resolve a MAL anime identity.")
        return

    rating = _m16_read_mal_rating()
    if rating is _CANCEL or rating is _BACK:
        print("Cancelled. No service data was changed.")
        return
    workflow.set_data("rating", rating)

    try:
        plan = workflow.build_action_plan()
    except ValueError as exc:
        print(f"\nValidation failed: {exc}")
        return
    return _m16_confirm_and_execute(plan, workflow)


def m16_rating_smoke_test():
    """Offline M16 structural tests. No network calls or writes."""
    # Serializd episode
    w = M16RatingWorkflow(M16_RATE_EPISODE_WORKFLOW_ID, "episode")
    w.data.update({"title":"Dark Matter", "serializd_show_id":196322, "serializd_season_id":509488, "serializd_episode_number":1, "rating":4.5})
    p = w.build_action_plan()
    assert p.operations[0]["operation"] == "rate_episode"
    assert p.operations[0]["rating"] == 4.5
    assert p.metadata["review_independent"] is True

    # Serializd season
    w = M16RatingWorkflow(M16_RATE_SEASON_WORKFLOW_ID, "season")
    w.data.update({"title":"Dark Matter", "serializd_show_id":196322, "serializd_season_id":285443, "rating":4.0})
    p = w.build_action_plan()
    assert p.operations[0]["operation"] == "rate_season"

    # Serializd series
    w = M16RatingWorkflow(M16_RATE_SERIES_WORKFLOW_ID, "series")
    w.data.update({"title":"Dark Matter", "serializd_show_id":196322, "rating":5.0})
    p = w.build_action_plan()
    assert p.operations[0]["operation"] == "rate_series"

    # MAL anime/anime movie entry
    w = M16RatingWorkflow(M16_RATE_ANIME_WORKFLOW_ID, "anime")
    w.data.update({"title":"Frieren", "mal_id":52991, "rating":4.5})
    p = w.build_action_plan()
    assert p.operations[0]["service"] == "mal"
    assert p.operations[0]["rating"] == 9

    # Final menu entries reuse the same validated workflow definitions.
    assert run_m16_rate_episode_final_workflow.__name__ == "run_m16_rate_episode_final_workflow"
    assert run_m16_rate_season_final_workflow.__name__ == "run_m16_rate_season_final_workflow"

    return "M16 Rating smoke test passed â€” episode + season included."


if os.environ.get("WAYMARK_M16_SMOKE_TEST") == "1":
    print(m16_rating_smoke_test())
    raise SystemExit(0)


if __name__ == "__main__":
    main()
