import json
import subprocess
import time

from playwright.sync_api import sync_playwright

from mal import (
    get_my_anime_list,
    search_anime,
    get_my_status,
    update_progress,
    update_status,
    update_score,
)

from notes import (
    add_note,
    get_notes,
    update_note,
)


ALIASES_FILE = "aliases.json"


def load_aliases():
    """Load saved anime aliases."""

    with open(
        ALIASES_FILE,
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def save_alias(alias, anime_id):
    """Save an alias for future title recognition."""

    aliases = load_aliases()

    aliases[alias.lower()] = anime_id

    with open(
        ALIASES_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            aliases,
            f,
            indent=2,
            ensure_ascii=False,
        )


def choose_action():
    """Ask the user what they did."""

    print("\nWhat did you do?\n")

    print("1. Watched")
    print("2. Re-watched")
    print("3. Re-watching")
    print("4. Watching")
    print("5. Rate")
    print("6. Change Status")
    print("7. Note")
    print("8. Review")

    while True:

        choice = input(
            "\nChoose an option: "
        ).strip()

        if choice == "1":
            return "watched"

        if choice == "2":
            return "re-watched"

        if choice == "3":
            return "re-watching"

        if choice == "4":
            return "watching"

        if choice == "5":
            return "rate"

        if choice == "6":
            return "change_status"

        if choice == "7":
            return "note"

        if choice == "8":
            return "review"

        print(
            "Please choose 1, 2, 3, 4, 5, 6, 7, or 8."
        )


def choose_note_action():
    """Ask what the user wants to do with notes."""

    print("\nWhat do you want to do?\n")

    print("1. View Note")
    print("2. Edit Note")

    while True:

        choice = input(
            "\nChoose an option: "
        ).strip()

        if choice == "1":
            return "view"

        if choice == "2":
            return "edit"

        print(
            "Please choose 1 or 2."
        )


def choose_status():
    """Ask the user for a new MAL status."""

    print("\nChoose new status:\n")

    print("1. Watching")
    print("2. Completed")
    print("3. On Hold")
    print("4. Dropped")
    print("5. Plan to Watch")

    while True:

        choice = input(
            "\nChoose a status: "
        ).strip()

        if choice == "1":
            return "watching"

        if choice == "2":
            return "completed"

        if choice == "3":
            return "on_hold"

        if choice == "4":
            return "dropped"

        if choice == "5":
            return "plan_to_watch"

        print(
            "Please choose 1, 2, 3, 4, or 5."
        )


def display_status_name(status):
    """Convert MAL status names into readable names."""

    names = {
        "watching": "Watching",
        "completed": "Completed",
        "on_hold": "On Hold",
        "dropped": "Dropped",
        "plan_to_watch": "Plan to Watch",
    }

    return names.get(
        status,
        status,
    )


def choose_from_results(results):
    """Let the user choose an anime."""

    if not results:
        return None

    print("\nMatches:")

    for index, item in enumerate(
        results,
        start=1,
    ):

        anime = item["node"]

        if "list_status" in item:

            status = item["list_status"]

            print(
                f"{index}. "
                f"{anime['title']} | "
                f"{status['status']} | "
                f"Episodes: "
                f"{status['num_episodes_watched']}"
            )

        else:

            print(
                f"{index}. "
                f"{anime['title']} | "
                f"MAL ID: "
                f"{anime['id']}"
            )

    if len(results) == 1:
        return results[0]

    while True:

        try:

            choice = int(
                input(
                    "\nChoose an anime: "
                )
            )

            if 1 <= choice <= len(results):

                return results[
                    choice - 1
                ]

            print(
                "Please choose a valid number."
            )

        except ValueError:

            print(
                "Please enter a number."
            )


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
    Resolve the user's anime title.

    If multiple entries match, always ask the user.
    A previous alias can never force a particular season.
    """

    print(
        "\nLoading your MAL anime list..."
    )

    anime_list = get_my_anime_list()

    print(
        f"Loaded {len(anime_list)} anime. ✅"
    )

    matches = find_in_my_list(
        anime_title,
        anime_list,
    )

    # Multiple matching seasons/entries.
    # Always ask the user.
    if len(matches) > 1:

        print(
            f'\nMultiple anime match '
            f'"{anime_title}".'
        )

        print(
            "Choose the season/entry "
            "you mean."
        )

        return choose_from_results(
            matches
        )

    # Exactly one match.
    if len(matches) == 1:

        return matches[0]

    # Nothing in personal MAL list.
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

    # Multiple MAL results.
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

    # Only save an alias when there was
    # exactly one search result.
    if len(search_results) == 1:

        save_alias(
            anime_title,
            anime_id,
        )

        print(
            f"\nWAYMARK remembered:"
            f"\n{anime_title} → "
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


def get_current_score(status):
    """Get the current MAL score."""

    if not status:
        return 0

    return status.get(
        "score",
        0,
    )


def display_notes(
    title,
    notes,
):
    """Display all notes for an anime."""

    if not notes:

        print(
            f"\nNo notes found for {title}."
        )

        return

    print(
        f"\n========================"
    )

    print(
        f"Notes for {title}"
    )

    print(
        f"========================"
    )

    for index, note in enumerate(
        notes,
        start=1,
    ):

        episode = note.get(
            "episode"
        )

        text = note.get(
            "text",
            "",
        )

        created_at = note.get(
            "created_at",
            "Unknown",
        )

        if episode is None:

            location = "Anime"

        else:

            location = f"Episode {episode}"

        print(
            f"\n{index}. {location}"
        )

        print(
            f"   {text}"
        )

        print(
            f"   Created: {created_at}"
        )

        if "updated_at" in note:

            print(
                f"   Updated: "
                f"{note['updated_at']}"
            )


def handle_notes(
    anime_id,
    title,
):
    """Handle viewing and editing notes."""

    note_action = choose_note_action()

    notes = get_notes(
        anime_id
    )

    # =============================================
    # VIEW NOTE
    # =============================================

    if note_action == "view":

        display_notes(
            title,
            notes,
        )

        return

    # =============================================
    # EDIT NOTE
    # =============================================

    if note_action == "edit":

        if not notes:

            print(
                f"\nNo notes found for {title}."
            )

            return

        display_notes(
            title,
            notes,
        )

        while True:

            choice = input(
                "\nChoose the note to edit "
                "(or type 'cancel'): "
            ).strip().lower()

            if choice == "cancel":

                print(
                    "Edit cancelled."
                )

                return

            try:

                note_number = int(
                    choice
                )

                if (
                    1
                    <= note_number
                    <= len(notes)
                ):

                    break

                print(
                    "Please choose a valid "
                    "note number."
                )

            except ValueError:

                print(
                    "Please enter a note number."
                )

        note_index = note_number - 1

        old_text = notes[
            note_index
        ]["text"]

        print(
            f"\nCurrent note:"
        )

        print(
            old_text
        )

        new_text = input(
            "\nNew note: "
        ).strip()

        if not new_text:

            print(
                "\nNote cannot be empty."
            )

            return

        print(
            f"\nWAYMARK will change:"
            f"\nOld: {old_text}"
            f"\nNew: {new_text}"
        )

        confirmation = input(
            "\nSave changes? (yes/no): "
        ).strip().lower()

        if confirmation != "yes":

            print(
                "Edit cancelled."
            )

            return

        success = update_note(
            anime_id,
            note_index,
            new_text,
        )

        if success:

            print(
                "\nNote updated successfully. ✅"
            )

        else:

            print(
                "\nCould not update the note."
            )

        return



# =============================================
# MAL WEBSITE REVIEW AUTOMATION
# =============================================

EDGE_PATH = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
)

WAYMARK_EDGE_PROFILE = (
    r"C:\Users\SHUBHAM\Documents\WAYMARK_EDGE"
)

DEBUG_PORT = 9222


def start_mal_browser(headless=False):
    """Start WAYMARK's dedicated Edge profile and connect Playwright."""

    edge_args = [
        EDGE_PATH,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={WAYMARK_EDGE_PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    if headless:
        edge_args.append("--headless=new")

    edge_process = subprocess.Popen(
        edge_args
    )

    time.sleep(3)

    playwright = sync_playwright().start()

    try:
        browser = playwright.chromium.connect_over_cdp(
            f"http://127.0.0.1:{DEBUG_PORT}"
        )
    except Exception:
        playwright.stop()
        edge_process.terminate()
        raise

    context = browser.contexts[0]

    if context.pages:
        page = context.pages[0]
    else:
        page = context.new_page()

    return (
        edge_process,
        playwright,
        browser,
        page,
    )


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
        edge_process.wait(timeout=5)
    except Exception:
        try:
            edge_process.kill()
        except Exception:
            pass


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
    Open MAL's review editor for the anime.

    MAL accepts a direct review-write URL. For an anime
    without an existing review, it opens the new-review
    form. If a review already exists, MAL redirects to
    the existing review editor.

    Using the direct URL is more reliable than searching
    the Reviews page for the visible "Write a Review"
    link, which can vary with page state or rendering.
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
    """Return True when MAL opened an existing review editor."""

    return "reviewid=" in page.url.lower()


def read_review_from_page(
    page,
):
    """Read the current MAL review form."""

    textareas = page.locator(
        "textarea[name='frm_review_text']"
    )

    review_text = ""

    if textareas.count() > 0:
        review_text = textareas.first.input_value()

    score = page.locator(
        "input[name='frmreview_overall_score']"
    )

    rating = 0

    if score.count() > 0:
        score_value = score.first.get_attribute(
            "value"
        )

        try:
            rating = int(score_value)
        except (TypeError, ValueError):
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
        value = feelings.first.get_attribute(
            "value"
        )

        recommendation = recommendation_values.get(
            value,
            f"Unknown ({value})",
        )

    spoiler = page.locator(
        "input[name='frm_review_is_spoiler']:checked"
    )

    spoiler_value = None

    if spoiler.count() > 0:
        spoiler_value = spoiler.first.get_attribute(
            "value"
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


def display_review(
    title,
    review,
):
    """Display a review retrieved from MAL."""

    print(
        "\n========================"
    )

    print(
        f"MAL Review — {title}"
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


def choose_review_rating(
    current_rating=None,
):
    """Ask for a MAL review rating."""

    if current_rating:
        print(
            f"\nCurrent review rating: "
            f"{current_rating}/10"
        )

    while True:

        value = input(
            "\nReview rating (1-10): "
        ).strip()

        try:

            rating = int(value)

            if 1 <= rating <= 10:
                return rating

        except ValueError:
            pass

        print(
            "Please enter a number between 1 and 10."
        )


def choose_review_recommendation(
    current=None,
):
    """Ask for the MAL review recommendation."""

    print(
        "\nWould you recommend this?"
    )

    print("1. Recommended")
    print("2. Mixed Feelings")
    print("3. Not Recommended")

    if current:
        print(
            f"\nCurrent: {current}"
        )

    while True:

        choice = input(
            "\nChoose an option: "
        ).strip()

        if choice == "1":
            return "1"

        if choice == "2":
            return "2"

        if choice == "3":
            return "3"

        print(
            "Please choose 1, 2, or 3."
        )


def read_multiline_review(prompt):
    """Read a multi-line review from the terminal."""

    print(
        f"\n{prompt}"
    )

    print(
        "Type your review below."
    )

    print(
        "When finished, type END on a new line."
    )

    lines = []

    while True:

        line = input()

        if line.strip().upper() == "END":
            break

        lines.append(line)

    return "\n".join(lines).strip()


def choose_review_spoiler(
    current=None,
):
    """Ask whether the MAL review contains spoilers."""

    print(
        "\nDoes the review contain spoilers?"
    )

    print("1. Yes")
    print("2. No")

    if current:
        print(
            f"\nCurrent: {current}"
        )

    while True:

        choice = input(
            "\nChoose an option: "
        ).strip()

        if choice == "1":
            return "1"

        if choice == "2":
            return "0"

        print(
            "Please choose 1 or 2."
        )


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
    """Fill MAL's review form without submitting it."""

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

    # MAL uses a hidden score field that is updated by
    # the visible rating controls. Click the visible
    # rating button when possible, then verify the
    # hidden field. Fall back to setting the hidden
    # field only if MAL's visible control is not found.
    rating_button = page.get_by_text(
        str(rating),
        exact=True,
    )

    clicked_rating = False

    for i in range(rating_button.count()):

        candidate = rating_button.nth(i)

        try:

            if candidate.is_visible():

                candidate.click()
                clicked_rating = True
                break

        except Exception:
            pass

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


def publish_review(
    page,
):
    """
    Ask for confirmation, then submit the MAL review.

    If MAL stops the submission for CAPTCHA or another
    validation step, the user can complete it in Edge.
    """

    print(
        "\n========================"
    )

    print(
        "READY TO PUBLISH TO MAL"
    )

    print(
        "========================"
    )

    print(
        "\nThe review has been filled into MAL."
    )

    print(
        "Nothing has been published yet."
    )

    print(
        "\nIf MAL shows a CAPTCHA or validation "
        "prompt, complete it in the Edge window."
    )

    confirmation = input(
        "\nPublish this review to MAL? (yes/no): "
    ).strip().lower()

    if confirmation != "yes":

        print(
            "\nPublish cancelled."
        )

        return False

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

    if "myreviews.php?reviewid=" in page.url.lower():

        print(
            "\nMAL review saved successfully. ✅"
        )

        return True

    print(
        "\nMAL did not navigate to the "
        "saved review page yet."
    )

    print(
        "Check the WAYMARK Edge window."
    )

    print(
        "If MAL is asking for CAPTCHA or "
        "another validation step, complete it there."
    )

    input(
        "\nAfter completing any required "
        "validation, press Enter..."
    )

    if "myreviews.php?reviewid=" in page.url.lower():

        print(
            "\nMAL review saved successfully. ✅"
        )

        return True

    print(
        "\nThe review could not be confirmed "
        "as saved."
    )

    print(
        "No local review copy was created."
    )

    return False


def handle_review(
    anime_id,
    title,
):
    """Handle MAL website review operations."""

    print(
        "\n========================"
    )

    print(
        f"MAL Review — {title}"
    )

    print(
        "========================"
    )

    print("\n1. View Review")
    print("2. Add Review")
    print("3. Edit Review")

    while True:

        choice = input(
            "\nChoose an option: "
        ).strip()

        if choice in [
            "1",
            "2",
            "3",
        ]:
            break

        print(
            "Please choose 1, 2, or 3."
        )

    edge_process = None
    playwright = None
    browser = None

    try:

        headless_review = choice == "1"

        if headless_review:
            print(
                "\nStarting background MAL review fetch..."
            )
        else:
            print(
                "\nStarting MAL browser automation..."
            )

        (
            edge_process,
            playwright,
            browser,
            page,
        ) = start_mal_browser(
            headless=headless_review
        )

        print(
            "Connected to MAL. ✅"
        )

        # =========================================
        # VIEW / EDIT EXISTING REVIEW
        # =========================================

        if choice in [
            "1",
            "3",
        ]:

            print(
                "\nOpening your MAL review..."
            )

            open_my_review_editor(
                page,
                anime_id,
            )

            if not review_exists(page):

                print(
                    f"\nYou do not have a MAL review "
                    f"for {title}."
                )

                if choice == "1":

                    return

                print(
                    "\nOpening the Add Review form..."
                )

            else:

                review = read_review_from_page(
                    page
                )

                if choice == "1":

                    display_review(
                        title,
                        review,
                    )

                    input(
                        "\nPress Enter to close..."
                    )

                    return

                # =================================
                # EDIT REVIEW
                # =================================

                print(
                    "\nCurrent review loaded from MAL. ✅"
                )

                display_review(
                    title,
                    review,
                )

                print(
                    "\n========================"
                )

                print(
                    "EDIT REVIEW"
                )

                print(
                    "========================"
                )

                print(
                    "\nCurrent review text is shown above."
                )

                print(
                    "To keep it unchanged, type KEEP."
                )

                edit_choice = input(
                    "\nEdit the review? (yes/keep): "
                ).strip().lower()

                if edit_choice == "yes":

                    new_text = read_multiline_review(
                        "New review text:"
                    )

                    if not new_text:

                        print(
                            "\nReview text cannot be empty."
                        )

                        return

                else:

                    new_text = review["text"]

                rating = choose_review_rating(
                    review["rating"]
                )

                recommendation = (
                    choose_review_recommendation(
                        review["recommendation"]
                    )
                )

                spoiler = choose_review_spoiler(
                    review["spoiler"]
                )

                print(
                    "\nFilling your changes into MAL..."
                )

                actual_rating = fill_review_form(
                    page,
                    new_text,
                    rating,
                    recommendation,
                    spoiler,
                )

                print(
                    "\nReview form updated. ✅"
                )

                print(
                    f"MAL rating field: "
                    f"{actual_rating}/10"
                )

                publish_review(
                    page
                )

                return

        # =========================================
        # ADD REVIEW
        # =========================================

        print(
            "\nOpening the MAL Add Review form..."
        )

        open_my_review_editor(
            page,
            anime_id,
        )

        if review_exists(page):

            print(
                f"\nYou already have a MAL review "
                f"for {title}."
            )

            print(
                "WAYMARK will not overwrite it."
            )

            print(
                "Use Review → Edit Review "
                "to modify the existing review."
            )

            input(
                "\nPress Enter to close..."
            )

            return

        print(
            "\nAdd Review form opened. ✅"
        )

        review_text = read_multiline_review(
            "Review text:"
        )

        if not review_text:

            print(
                "\nReview text cannot be empty."
            )

            return

        rating = choose_review_rating()

        recommendation = (
            choose_review_recommendation()
        )

        spoiler = choose_review_spoiler()

        print(
            "\nFilling the review into MAL..."
        )

        actual_rating = fill_review_form(
            page,
            review_text,
            rating,
            recommendation,
            spoiler,
        )

        print(
            "\nReview form filled. ✅"
        )

        print(
            f"MAL rating field: "
            f"{actual_rating}/10"
        )

        publish_review(
            page
        )

    except Exception as error:

        print(
            "\nMAL review operation failed. ❌"
        )

        print(
            f"\nError:\n{error}"
        )

        print(
            "\nNo review was stored locally."
        )

        input(
            "\nPress Enter to close..."
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


def main():

    print("\n========================")
    print("        WAYMARK")
    print("========================")

    # ---------------------------------------------
    # Choose action
    # ---------------------------------------------

    action = choose_action()

    print(
        f"\nAction: {action}"
    )

    # ---------------------------------------------
    # Anime title
    # ---------------------------------------------

    anime_title = input(
        "\nAnime title: "
    ).strip()

    if not anime_title:

        print(
            "\nAnime title cannot be empty."
        )

        return

    # ---------------------------------------------
    # Resolve anime
    # ---------------------------------------------

    selected = resolve_anime(
        anime_title
    )

    if not selected:
        return

    anime = selected["node"]

    status = selected.get(
        "list_status"
    )

    anime_id = anime["id"]

    title = anime["title"]

    print(
        f"\nSelected: {title}"
    )

    # =============================================
    # NOTE
    # =============================================

    if action == "note":

        handle_notes(
            anime_id,
            title,
        )

        return

    # =============================================
    # REVIEW
    # =============================================

    if action == "review":

        handle_review(
            anime_id,
            title,
        )

        return

    # =============================================
    # CHANGE STATUS
    # =============================================

    if action == "change_status":

        if status:

            current_status = status[
                "status"
            ]

            old_status_name = (
                display_status_name(
                    current_status
                )
            )

            print(
                f"Current status: "
                f"{old_status_name}"
            )

        else:

            current_status = None

            old_status_name = "Not on list"

            print(
                "Current status: "
                "Not on your MAL list."
            )

        new_status = choose_status()

        new_status_name = (
            display_status_name(
                new_status
            )
        )

        print(
            f"\nWAYMARK will change:"
            f"\n{old_status_name} → "
            f"{new_status_name}"
        )

        confirmation = input(
            "\nContinue? (yes/no): "
        ).strip().lower()

        if confirmation != "yes":

            print(
                "Update cancelled."
            )

            return

        update_status(
            anime_id,
            new_status,
        )

        print(
            f"\n{title} marked as "
            f"{new_status_name}. ✅"
        )

        return

    # =============================================
    # RATING
    # =============================================

    if action == "rate":

        current_score = get_current_score(
            status
        )

        if current_score == 0:

            print(
                "Current rating: Not rated"
            )

        else:

            print(
                f"Current rating: "
                f"{current_score}/10"
            )

        while True:

            rating_input = input(
                "\nRating (1-10): "
            ).strip()

            try:

                rating = int(
                    rating_input
                )

                if 1 <= rating <= 10:

                    break

                print(
                    "Please enter a rating "
                    "between 1 and 10."
                )

            except ValueError:

                print(
                    "Please enter a number "
                    "between 1 and 10."
                )

        print(
            f"\nWAYMARK will set:"
            f"\nRating: {rating}/10"
        )

        confirmation = input(
            "\nContinue? (yes/no): "
        ).strip().lower()

        if confirmation != "yes":

            print(
                "Update cancelled."
            )

            return

        update_score(
            anime_id,
            rating,
        )

        print(
            f"\n{title} rated "
            f"{rating}/10. ⭐"
        )

        return

    # =============================================
    # CURRENT PROGRESS
    # =============================================

    if status:

        current_episode = status[
            "num_episodes_watched"
        ]

        current_status = status[
            "status"
        ]

        currently_rewatching = status.get(
            "is_rewatching",
            False,
        )

        print(
            f"Current status: "
            f"{current_status}"
        )

        print(
            f"Current progress: "
            f"{current_episode}"
        )

        print(
            f"Currently re-watching: "
            f"{currently_rewatching}"
        )

    else:

        current_episode = 0

        print(
            "Not currently on your MAL list."
        )

        print(
            "Current progress: 0"
        )

    # =============================================
    # EPISODE
    # =============================================

    episode_input = input(
        "\nEpisode number: "
    ).strip()

    try:

        episode = int(
            episode_input
        )

        if episode < 1:
            raise ValueError

    except ValueError:

        print(
            "\nPlease enter a valid "
            "episode number."
        )

        return

    # =============================================
    # WATCHED
    # =============================================

    if action == "watched":

        if episode <= current_episode:

            print(
                f"\nMAL already has you "
                f"at episode "
                f"{current_episode}."
            )

            print(
                "No update needed."
            )

            return

        print(
            f"\nWAYMARK will update:"
            f"\n{current_episode} → "
            f"{episode}"
        )

        confirmation = input(
            "\nContinue? (yes/no): "
        ).strip().lower()

        if confirmation != "yes":

            print(
                "Update cancelled."
            )

            return

        update_progress(
            anime_id,
            episode,
            is_rewatching=False,
        )

        print(
            f"\n{title} watched up to "
            f"episode {episode}. ✅"
        )

        return

    # =============================================
    # RE-WATCHED
    # =============================================

    if action == "re-watched":

        print(
            f"\nRe-watched episode "
            f"{episode} of {title}."
        )

        confirmation = input(
            "\nContinue? (yes/no): "
        ).strip().lower()

        if confirmation != "yes":

            print(
                "Update cancelled."
            )

            return

        update_progress(
            anime_id,
            episode,
            is_rewatching=True,
        )

        print(
            f"\n{title} marked as "
            f"re-watching at episode "
            f"{episode}. 🔄"
        )

        return

    # =============================================
    # RE-WATCHING
    # =============================================

    if action == "re-watching":

        print(
            f"\nWAYMARK will mark "
            f"{title} as re-watching."
        )

        print(
            f"Starting episode: "
            f"{episode}"
        )

        confirmation = input(
            "\nContinue? (yes/no): "
        ).strip().lower()

        if confirmation != "yes":

            print(
                "Update cancelled."
            )

            return

        update_progress(
            anime_id,
            episode,
            is_rewatching=True,
        )

        print(
            f"\n{title} is now marked "
            f"as re-watching. 🔄"
        )

        return

    # =============================================
    # WATCHING
    # =============================================

    if action == "watching":

        print(
            f"\nWAYMARK will mark "
            f"{title} as watching."
        )

        print(
            f"Episode: {episode}"
        )

        confirmation = input(
            "\nContinue? (yes/no): "
        ).strip().lower()

        if confirmation != "yes":

            print(
                "Update cancelled."
            )

            return

        update_status(
            anime_id,
            "watching",
        )

        update_progress(
            anime_id,
            episode,
            is_rewatching=False,
        )

        print(
            f"\n{title} is now "
            f"watching at episode "
            f"{episode}. ▶️"
        )

        return


if __name__ == "__main__":
    main()