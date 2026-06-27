"""
Stress test: run the HubSpot session test 5 times in a row.
Each run should restore from cache with no manual login.
"""

import sys
import time
import traceback
from execution.hubspot_session import HubSpotSession

RUNS = 5
results = []

for i in range(1, RUNS + 1):
    print(f"\n{'='*50}")
    print(f"RUN {i} of {RUNS}")
    print(f"{'='*50}")
    start = time.time()
    try:
        with HubSpotSession() as session:
            page = session.page

            page.goto("https://app.hubspot.com")
            page.wait_for_load_state("networkidle")

            screenshot_path = f"screenshots/stress_run_{i}.png"
            page.screenshot(path=screenshot_path, full_page=True)

            url   = page.url
            title = page.title()

        elapsed = time.time() - start
        results.append({"run": i, "ok": True, "url": url, "title": title,
                         "screenshot": screenshot_path, "elapsed": elapsed})
        print(f"  URL:        {url}")
        print(f"  Title:      {title}")
        print(f"  Screenshot: {screenshot_path}")
        print(f"  Time:       {elapsed:.1f}s")
        print(f"  Status:     OK")

    except Exception as e:
        elapsed = time.time() - start
        results.append({"run": i, "ok": False, "error": str(e), "elapsed": elapsed})
        print(f"  Status:     FAILED")
        print(f"  Error:      {e}")
        traceback.print_exc()

# Summary
print(f"\n{'='*50}")
print("STRESS TEST SUMMARY")
print(f"{'='*50}")
passed = sum(1 for r in results if r["ok"])
failed = sum(1 for r in results if not r["ok"])
print(f"Passed: {passed}/{RUNS}")
print(f"Failed: {failed}/{RUNS}")

if failed:
    print("\nFailed runs:")
    for r in results:
        if not r["ok"]:
            print(f"  Run {r['run']}: {r['error']}")
    sys.exit(1)
else:
    print("\nAll runs completed successfully!")
