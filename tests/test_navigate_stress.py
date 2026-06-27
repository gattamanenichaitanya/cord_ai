import os
import time
import statistics
import traceback
from dotenv import load_dotenv
from execution.hubspot_session import HubSpotSession
from playwright.sync_api import TimeoutError

def run_single(run_index):
    start_time = time.time()
    steps_passed = 0
    steps_failed = 0
    error_msg = ""
    
    def pass_step(name):
        nonlocal steps_passed
        steps_passed += 1

    def fail_step(name, info=""):
        nonlocal steps_failed, error_msg
        steps_failed += 1
        error_msg += f"{name}: {info}\n"

    target_url = f"https://app.hubspot.com/property-settings/{os.environ.get('HUBSPOT_PORTAL_ID')}/properties?type=0-1"

    try:
        with HubSpotSession(slow_mo=0) as session:
            page = session.page
            page.goto(target_url)

            try:
                page.wait_for_load_state("networkidle", timeout=30000)
            except TimeoutError:
                pass

            try:
                page.get_by_text("Contact properties").first.wait_for(state="visible", timeout=10000)
            except TimeoutError:
                pass

            time.sleep(2)

            current_url = page.url
            if "property-settings" in current_url:
                pass_step("URL contains 'property-settings'")
            else:
                fail_step("URL contains 'property-settings'", f"Current URL: {current_url}")

            if page.get_by_text("Contact properties", exact=False).count() > 0:
                pass_step("Page contains 'Contact properties'")
            else:
                fail_step("Page contains 'Contact properties'")

            btn_role = page.get_by_role("button", name="Create property")
            btn_text = page.get_by_text("Create property", exact=True).first
            
            create_btn = None
            if btn_role.count() > 0 and btn_role.first.is_visible():
                create_btn = btn_role.first
                pass_step("'Create property' button is visible")
            elif btn_text.count() > 0 and btn_text.is_visible():
                create_btn = btn_text
                pass_step("'Create property' button is visible")
            else:
                fail_step("'Create property' button is visible")
            
            if not create_btn:
                return False, time.time() - start_time, error_msg

            create_btn.click()

            try:
                page.get_by_text("Create new property", exact=False).first.wait_for(state="visible", timeout=10000)
            except TimeoutError:
                pass
                
            time.sleep(2)

            if page.get_by_text("Create new property", exact=False).count() > 0:
                pass_step("Modal contains 'Create new property'")
            else:
                fail_step("Modal contains 'Create new property'")

            btn_role_modal = page.get_by_role("button", name="Create property")
            btn_text_modal = page.get_by_text("Create property", exact=True).first
            if (btn_role_modal.count() > 0 and btn_role_modal.first.is_visible()) or (btn_text_modal.count() > 0 and btn_text_modal.is_visible()):
                 pass_step("Modal contains 'Create property' button")
            else:
                 fail_step("Modal contains 'Create property' button")

            cancel_btn = page.get_by_role("button", name="Cancel")
            close_btn = page.locator("button[aria-label='Close'], button[data-test-id='modal-close']")
            
            if cancel_btn.count() > 0 and cancel_btn.first.is_visible():
                cancel_btn.first.click()
            elif close_btn.count() > 0 and close_btn.first.is_visible():
                close_btn.first.click()
            else:
                page.keyboard.press("Escape")
                
            time.sleep(2)
            
            if page.get_by_text("Create new property", exact=False).is_hidden():
                pass_step("Modal heading is no longer visible")
            else:
                fail_step("Modal heading is no longer visible")
                
            elapsed = time.time() - start_time
            if steps_failed == 0:
                return True, elapsed, ""
            else:
                return False, elapsed, error_msg

    except Exception as e:
        return False, time.time() - start_time, str(e) + "\n" + traceback.format_exc()

def run_stress_test():
    load_dotenv()
    if not os.environ.get("HUBSPOT_PORTAL_ID"):
        print("Error: HUBSPOT_PORTAL_ID not found in .env")
        return

    runs = 10
    success_count = 0
    failure_count = 0
    times = []
    errors = []

    print(f"Starting stress test for {runs} runs...")

    for i in range(1, runs + 1):
        print(f"Run {i}/{runs}... ", end="", flush=True)
        success, elapsed, error = run_single(i)
        times.append(elapsed)
        if success:
            success_count += 1
            print(f"PASS ({elapsed:.2f}s)")
        else:
            failure_count += 1
            errors.append((i, error))
            print(f"FAIL ({elapsed:.2f}s)")

    print("\n" + "="*40)
    print("STRESS TEST RESULTS")
    print("="*40)
    print(f"Total Runs: {runs}")
    print(f"Success:    {success_count}")
    print(f"Failure:    {failure_count}")
    
    if times:
        mean_time = statistics.mean(times)
        min_time = min(times)
        max_time = max(times)
        print("\nTiming Distribution:")
        print(f"  Mean: {mean_time:.2f}s")
        print(f"  Min:  {min_time:.2f}s")
        print(f"  Max:  {max_time:.2f}s")

    if failure_count > 0:
        print("\nFailure Details:")
        for run_id, err in errors:
            print(f"\n--- Run {run_id} ---")
            print(err)

if __name__ == "__main__":
    run_stress_test()
