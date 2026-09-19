import subprocess
import time

from playwright.sync_api import sync_playwright


EDGE_PATH = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
)

WAYMARK_EDGE_PROFILE = (
    r"C:\Users\SHUBHAM\Documents\WAYMARK_EDGE"
)

DEBUG_PORT = 9222

ANIME_REVIEWS_URL = (
    "https://myanimelist.net/anime/37208/"
    "Mo_Dao_Zu_Shi/reviews"
)


def main():

    print("\n========================")
    print(" WAYMARK MAL ADD REVIEW")
    print("========================")

    print(
        "\nStarting WAYMARK's Edge profile..."
    )

    edge_process = subprocess.Popen(
        [
            EDGE_PATH,
            f"--remote-debugging-port={DEBUG_PORT}",
            f"--user-data-dir={WAYMARK_EDGE_PROFILE}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
    )

    time.sleep(3)

    with sync_playwright() as p:

        print("\nConnecting to Edge...")

        try:

            browser = p.chromium.connect_over_cdp(
                f"http://127.0.0.1:{DEBUG_PORT}"
            )

        except Exception as error:

            print(
                "\nCould not connect to Edge. ❌"
            )

            print(
                f"\nError:\n{error}"
            )

            edge_process.terminate()
            return

        print(
            "Connected to Edge. ✅"
        )

        context = browser.contexts[0]

        if context.pages:
            page = context.pages[0]
        else:
            page = context.new_page()

        print(
            "\nOpening Master of Diabolism reviews..."
        )

        page.goto(
            ANIME_REVIEWS_URL,
            wait_until="domcontentloaded",
            timeout=30000,
        )

        time.sleep(3)

        print(
            "\nReviews page opened. ✅"
        )

        print(
            f"\nURL:\n{page.url}"
        )

        print(
            f"\nTitle:\n{page.title()}"
        )

        print(
            "\nLooking for 'Write a Review'..."
        )

        review_link = page.get_by_text(
            "Write a Review",
            exact=True,
        )

        if review_link.count() == 0:

            print(
                "\nCould not find 'Write a Review'. ❌"
            )

            print(
                "\nVisible review-related links:"
            )

            links = page.locator("a")

            for i in range(links.count()):

                link = links.nth(i)

                try:

                    text = link.inner_text().strip()

                    if "review" in text.lower():

                        print(
                            f"- {text}"
                        )

                except Exception:
                    pass

            input(
                "\nPress Enter to close..."
            )

            browser.close()
            edge_process.terminate()
            return

        print(
            "\n'Write a Review' found. ✅"
        )

        print(
            "\nOpening the review form..."
        )

        review_link.first.click()

        page.wait_for_load_state(
            "domcontentloaded"
        )

        time.sleep(2)

        print(
            "\nReview form opened. ✅"
        )

        print(
            f"\nURL:\n{page.url}"
        )

        print(
            f"\nTitle:\n{page.title()}"
        )

        # -------------------------------------------------
        # Textareas
        # -------------------------------------------------

        print(
            "\n========================"
        )

        print(
            "TEXTAREAS"
        )

        print(
            "========================"
        )

        textareas = page.locator(
            "textarea"
        )

        print(
            f"\nTotal textareas: "
            f"{textareas.count()}"
        )

        for i in range(textareas.count()):

            textarea = textareas.nth(i)

            try:

                print(
                    f"\nTextarea {i + 1}:"
                )

                print(
                    f"Name: "
                    f"{textarea.get_attribute('name')}"
                )

                print(
                    f"Current text:"
                )

                print(
                    textarea.input_value()
                )

            except Exception:
                pass

        # -------------------------------------------------
        # Inputs
        # -------------------------------------------------

        print(
            "\n========================"
        )

        print(
            "INPUT FIELDS"
        )

        print(
            "========================"
        )

        inputs = page.locator(
            "input"
        )

        print(
            f"\nTotal inputs: "
            f"{inputs.count()}"
        )

        for i in range(inputs.count()):

            field = inputs.nth(i)

            try:

                field_type = field.get_attribute(
                    "type"
                )

                name = field.get_attribute(
                    "name"
                )

                value = field.get_attribute(
                    "value"
                )

                checked = False

                if field_type in [
                    "radio",
                    "checkbox",
                ]:

                    checked = field.is_checked()

                print(
                    f"\nInput {i + 1}"
                )

                print(
                    f"Type: {field_type}"
                )

                print(
                    f"Name: {name}"
                )

                print(
                    f"Value: {value}"
                )

                if field_type in [
                    "radio",
                    "checkbox",
                ]:

                    print(
                        f"Checked: {checked}"
                    )

            except Exception:
                pass

        # -------------------------------------------------
        # Select fields
        # -------------------------------------------------

        print(
            "\n========================"
        )

        print(
            "SELECT FIELDS"
        )

        print(
            "========================"
        )

        selects = page.locator(
            "select"
        )

        print(
            f"\nTotal selects: "
            f"{selects.count()}"
        )

        for i in range(selects.count()):

            select = selects.nth(i)

            try:

                print(
                    f"\nSelect {i + 1}"
                )

                print(
                    f"Name: "
                    f"{select.get_attribute('name')}"
                )

                print(
                    f"Value: "
                    f"{select.input_value()}"
                )

            except Exception:
                pass

        # -------------------------------------------------
        # Buttons
        # -------------------------------------------------

        print(
            "\n========================"
        )

        print(
            "BUTTONS"
        )

        print(
            "========================"
        )

        buttons = page.locator(
            "button, input[type='submit']"
        )

        print(
            f"\nTotal buttons: "
            f"{buttons.count()}"
        )

        for i in range(buttons.count()):

            button = buttons.nth(i)

            try:

                print(
                    f"\nButton {i + 1}"
                )

                print(
                    f"Tag: "
                    f"{button.evaluate('(el) => el.tagName')}"
                )

                print(
                    f"Text: "
                    f"{button.inner_text()}"
                )

                print(
                    f"Name: "
                    f"{button.get_attribute('name')}"
                )

                print(
                    f"Value: "
                    f"{button.get_attribute('value')}"
                )

                print(
                    f"Type: "
                    f"{button.get_attribute('type')}"
                )

            except Exception:
                pass

        # -------------------------------------------------
        # Finish
        # -------------------------------------------------

        print(
            "\n========================"
        )

        print(
            "SAFE ADD REVIEW TEST COMPLETE"
        )

        print(
            "========================"
        )

        print(
            "\nNothing was entered."
        )

        print(
            "Nothing was changed."
        )

        print(
            "Nothing was published."
        )

        input(
            "\nPress Enter here to close "
            "the test..."
        )

        browser.close()

    edge_process.terminate()

    print(
        "\nReview test finished."
    )


if __name__ == "__main__":

    main()