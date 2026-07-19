"""
HubSpot Session Manager
=======================
Manages persistent browser sessions for HubSpot.
Logs in manually once, saves cookies/localStorage to disk,
and reuses the session on subsequent runs.

SECURITY NOTE: .auth/hubspot_state.json contains live session
cookies. Anyone with this file can impersonate you on HubSpot.
It is excluded from git via .gitignore.
"""

import time
from pathlib import Path
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page


# Path to the saved browser state (cookies + localStorage)
AUTH_STATE_PATH = Path(__file__).resolve().parent.parent / ".auth" / "hubspot_state.json"

# HubSpot URLs used for navigation and validation
HUBSPOT_LOGIN_URL = "https://app.hubspot.com/login"
HUBSPOT_APP_URL = "https://app.hubspot.com"

# Demo Mode window properties
DEMO_BROWSER_POSITION = "770,0"
DEMO_BROWSER_SIZE = "1150,1080"
DEMO_SLOW_MO = 350
DEFAULT_SLOW_MO = 50


class HubSpotSession:
    """
    Context manager that provides a logged-in HubSpot browser session.

    Usage:
        with HubSpotSession() as session:
            page = session.page
            page.goto("https://app.hubspot.com/contacts/...")
    """

    def __init__(self, slow_mo: int = None, demo_mode: bool = False):
        """
        Initialize the session manager.

        Args:
            slow_mo: Milliseconds to wait between each Playwright action.
                     Useful for visual debugging. Set to 0 for production speed.
            demo_mode: If True, uses DEMO_SLOW_MO and positions browser on the right.
        """
        self.demo_mode = demo_mode
        if slow_mo is not None:
            self.slow_mo = slow_mo
        else:
            self.slow_mo = DEMO_SLOW_MO if demo_mode else DEFAULT_SLOW_MO

        # These are populated when entering the context manager
        self._playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None

    def __enter__(self):
        """Start the browser and establish a logged-in session."""
        # Start Playwright engine
        self._playwright = sync_playwright().start()

        # Check if we have a saved session
        if AUTH_STATE_PATH.exists():
            self._restore_session()
        else:
            self._first_time_login()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanly close the browser context and browser on exit."""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self._playwright:
            self._playwright.stop()

        # Don't suppress exceptions
        return False

    def _launch_browser(self) -> Browser:
        """
        Launch Chrome in headed mode with slow_mo for visual debugging.

        Uses channel="chrome" to launch the system-installed Chrome browser
        instead of Playwright's bundled Chromium. This is required because
        Google blocks OAuth sign-in on automation browsers (Chromium) with
        'This browser or app may not be secure'. The real Chrome is trusted.

        Additionally strips automation-detection flags:
        - Removes --enable-automation (hides the "controlled by automation" bar)
        - Adds --disable-blink-features=AutomationControlled (prevents
          navigator.webdriver from being set to true, which Google checks)
        """
        args = ["--disable-blink-features=AutomationControlled"]
        if self.demo_mode:
            args.append(f"--window-position={DEMO_BROWSER_POSITION}")
            args.append(f"--window-size={DEMO_BROWSER_SIZE}")

        return self._playwright.chromium.launch(
            headless=False,
            slow_mo=self.slow_mo,
            channel="chrome",
            # Strip the --enable-automation flag that Playwright adds by default.
            # This flag causes Google to reject the browser as an automation tool.
            ignore_default_args=["--enable-automation"],
            # Disable the AutomationControlled blink feature so that
            # navigator.webdriver is not set to true in the browser.
            args=args,
        )

    def _first_time_login(self):
        """
        First-run flow: open the login page, wait for the user to
        log in manually (including 2FA), then save the session state.
        """
        # Launch browser with no saved state
        self.browser = self._launch_browser()
        context_args = {}
        if self.demo_mode:
            context_args["no_viewport"] = True
        self.context = self.browser.new_context(**context_args)
        self.page = self.context.new_page()

        # Navigate to HubSpot login
        self.page.goto(HUBSPOT_LOGIN_URL)

        # Prompt the user to log in manually
        print("=" * 50)
        print("FIRST TIME SETUP: Please log into HubSpot manually.")
        print("Complete login (including any 2FA), then return")
        print("here and press Enter to save the session.")
        print("=" * 50)

        # Block until the user presses Enter in the terminal
        input("\nPress Enter after you have logged in successfully...")

        # Verify login succeeded by checking the URL
        current_url = self.page.url
        if "/login" in current_url or "app.hubspot.com" not in current_url:
            print(f"WARNING: Login may not have completed. Current URL: {current_url}")
            print("Continuing anyway — the session may not work on next run.")

        # Save the browser state (cookies + localStorage) to disk
        # Ensure the .auth directory exists
        AUTH_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.context.storage_state(path=str(AUTH_STATE_PATH))
        print(f"Session saved to {AUTH_STATE_PATH}")

    def _restore_session(self):
        """
        Subsequent-run flow: load the saved session state and verify
        we're still logged in. If the session has expired, delete the
        state file and fall back to the first-time login flow.
        """
        # Launch browser and load saved state into a new context
        self.browser = self._launch_browser()
        context_args = {"storage_state": str(AUTH_STATE_PATH)}
        if self.demo_mode:
            context_args["no_viewport"] = True
        self.context = self.browser.new_context(**context_args)
        self.page = self.context.new_page()

        # Navigate to HubSpot and check if we're still authenticated
        self.page.goto(HUBSPOT_APP_URL)

        # Wait for navigation to settle (redirects may occur)
        time.sleep(3)

        current_url = self.page.url

        # If we got redirected back to the login page, session has expired
        if "/login" in current_url:
            print("Session expired. Restarting login flow.")

            # Clean up the current browser
            self.context.close()
            self.context = None
            self.browser.close()
            self.browser = None

            # Delete the stale state file
            AUTH_STATE_PATH.unlink()

            # Fall back to the first-time login flow
            self._first_time_login()
        else:
            print("Session restored from cache.")


if __name__ == "__main__":
    # Allow running the script directly to initialize/refresh the login state
    print("Initializing HubSpot Session to capture auth state...")
    with HubSpotSession() as session:
        print("Success! Auth state has been captured/restored.")
