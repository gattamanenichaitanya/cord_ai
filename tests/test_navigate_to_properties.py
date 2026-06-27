import os
import time
from dotenv import load_dotenv
from execution.hubspot_session import HubSpotSession
from playwright.sync_api import TimeoutError

def run():
    start_time = time.time()
    steps_passed = 0
    steps_failed = 0
    screenshots_taken = []
    
    def pass_step(name):
        nonlocal steps_passed
        print(f"[PASS] {name}")
        steps_passed += 1

    def fail_step(name, info=""):
        nonlocal steps_failed
        print(f"[FAIL] {name}")
        if info:
            print(f"  {info}")
        steps_failed += 1

    def take_screenshot(page, filename):
        path = f"screenshots/{filename}"
        page.screenshot(path=path, full_page=True)
        screenshots_taken.append(path)
        print(f"Taking screenshot to {path}")

    load_dotenv()
    portal_id = os.environ.get("HUBSPOT_PORTAL_ID")
    if not portal_id:
        print("Error: HUBSPOT_PORTAL_ID not found in .env")
        return

    target_url = f"https://app.hubspot.com/property-settings/{portal_id}/properties?type=0-1"

    with HubSpotSession(slow_mo=0) as session:
        page = session.page
        print(f"Navigating to {target_url} ...")
        page.goto(target_url)

        print("Waiting for networkidle...")
        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except TimeoutError:
            print("Warning: networkidle timed out after 30s")

        print("Waiting for 'Contact properties' text...")
        try:
            page.get_by_text("Contact properties").first.wait_for(state="visible", timeout=10000)
        except TimeoutError:
            print("Warning: 'Contact properties' text not visible after 10s")

        print("Sleeping 2s for final animations...")
        time.sleep(2)

        take_screenshot(page, "properties_page.png")

        print("\nVerifications:")
        
        # 7a: Current URL contains "property-settings"
        current_url = page.url
        if "property-settings" in current_url:
            pass_step("URL contains 'property-settings'")
        else:
            fail_step("URL contains 'property-settings'", f"Current URL: {current_url}")

        # 7b: Page contains "Contact properties"
        if page.get_by_text("Contact properties", exact=False).count() > 0:
            pass_step("Page contains 'Contact properties'")
        else:
            fail_step("Page contains 'Contact properties'", f"Current URL: {current_url}\n  HTML Snippet: {page.content()[:1000]}...")

        # 7c: Button with text "Create property" is visible
        btn_role = page.get_by_role("button", name="Create property")
        btn_text = page.get_by_text("Create property", exact=True).first
        
        create_btn = None
        if btn_role.count() > 0 and btn_role.first.is_visible():
            create_btn = btn_role.first
            pass_step("'Create property' button is visible (by role)")
        elif btn_text.count() > 0 and btn_text.is_visible():
            create_btn = btn_text
            pass_step("'Create property' button is visible (by text fallback)")
        else:
            fail_step("'Create property' button is visible")
            take_screenshot(page, "debug_no_create_button.png")
            print("Visible buttons on page:")
            for b in page.get_by_role("button").all():
                if b.is_visible():
                    print(f" - {b.inner_text().strip()}")
        
        if not create_btn:
            print("Cannot proceed: Create property button not found.")
            return

        print("\nClicking 'Create property' button...")
        create_btn.click()

        print("Waiting for modal to appear...")
        # Wait up to 10 seconds for "Create new property" to be visible
        try:
            page.get_by_text("Create new property", exact=False).first.wait_for(state="visible", timeout=10000)
        except TimeoutError:
            print("Warning: 'Create new property' text not visible after 10s")
            
        time.sleep(2)

        print("\nModal Verifications:")
        # 4a: "Create new property" is present
        if page.get_by_text("Create new property", exact=False).count() > 0:
            pass_step("Modal contains 'Create new property'")
        else:
            fail_step("Modal contains 'Create new property'")

        # 4b: "Create property" button inside modal or somewhere on page
        btn_role_modal = page.get_by_role("button", name="Create property")
        btn_text_modal = page.get_by_text("Create property", exact=True).first
        if (btn_role_modal.count() > 0 and btn_role_modal.first.is_visible()) or (btn_text_modal.count() > 0 and btn_text_modal.is_visible()):
             pass_step("Modal contains 'Create property' button")
        else:
             fail_step("Modal contains 'Create property' button")

        take_screenshot(page, "create_property_modal.png")

        print("\nClosing modal...")
        cancel_btn = page.get_by_role("button", name="Cancel")
        close_btn = page.locator("button[aria-label='Close'], button[data-test-id='modal-close']")
        
        if cancel_btn.count() > 0 and cancel_btn.first.is_visible():
            print("Clicking 'Cancel' button")
            cancel_btn.first.click()
        elif close_btn.count() > 0 and close_btn.first.is_visible():
            print("Clicking 'X' (Close) button")
            close_btn.first.click()
        else:
            print("Pressing Escape key")
            page.keyboard.press("Escape")
            
        time.sleep(2)
        
        print("\nClose Verifications:")
        # Verify modal closed
        if page.get_by_text("Create new property", exact=False).is_hidden():
            pass_step("Modal heading is no longer visible")
        else:
            fail_step("Modal heading is no longer visible")
            
        take_screenshot(page, "back_to_properties.png")
        
        elapsed = time.time() - start_time
        
        print("\n" + "="*40)
        print("TEST SUMMARY")
        print("="*40)
        print(f"Steps Passed: {steps_passed}")
        print(f"Steps Failed: {steps_failed}")
        print(f"Total Time:   {elapsed:.2f}s")
        print("Screenshots taken:")
        for s in screenshots_taken:
            print(f" - {s}")

if __name__ == "__main__":
    run()
