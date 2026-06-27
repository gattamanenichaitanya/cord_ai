"""
Test: HubSpot Session Manager
==============================
Opens a HubSpot session (first run will prompt for manual login),
navigates to the app, takes a screenshot, and prints page info.

Run with:
    python -m tests.test_session
"""

from execution.hubspot_session import HubSpotSession


def run():
    # Open a managed HubSpot session
    with HubSpotSession() as session:
        page = session.page

        # Navigate to HubSpot main app
        print("Navigating to HubSpot...")
        page.goto("https://app.hubspot.com")

        # Wait a moment for the page to fully load
        page.wait_for_load_state("networkidle")

        # Take a full-page screenshot
        screenshot_path = "screenshots/session_test.png"
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"Screenshot saved to {screenshot_path}")

        # Print current page info
        print(f"Current URL: {page.url}")
        print(f"Page Title: {page.title()}")

    print("Session closed successfully.")


if __name__ == "__main__":
    run()
