import time
from playwright.sync_api import sync_playwright

def run():
    # Initialize Playwright using the sync API context manager
    with sync_playwright() as p:
        # Print status update
        print("Launching Chromium browser in headed mode...")
        
        # Launch Chromium with headed mode (headless=False) and 500ms slow motion delay
        browser = p.chromium.launch(headless=False, slow_mo=500)
        
        # Create a new browser context (session)
        context = browser.new_context()
        
        # Open a new tab/page in the context
        page = context.new_page()
        
        # Navigate to HubSpot login page
        print("Navigating to https://app.hubspot.com...")
        page.goto("https://app.hubspot.com")
        
        # Wait for 5 seconds to observe the page visually
        print("Waiting 5 seconds to observe the page...")
        time.sleep(5)
        
        # Capture a full-page screenshot and save it to screenshots/hello.png
        screenshot_path = "screenshots/hello.png"
        print(f"Saving full-page screenshot to {screenshot_path}...")
        page.screenshot(path=screenshot_path, full_page=True)
        
        # Retrieve and print the current page URL and title
        print(f"Current URL: {page.url}")
        print(f"Page Title: {page.title()}")
        
        # Cleanly close the browser context and browser
        context.close()
        browser.close()
        print("Browser closed successfully.")

if __name__ == "__main__":
    run()
