import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

async def dump():
    load_dotenv()
    project_root = Path(__file__).resolve().parent.parent
    session_path = project_root / ".auth" / "hubspot_state.json"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            channel="chrome",
            ignore_default_args=["--enable-automation"],
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(storage_state=str(session_path))
        page = await context.new_page()
        
        print("Navigating to HubSpot...")
        await page.goto("https://app-na2.hubspot.com/workflows/246672023/create")
        
        # Wait for page load
        await page.wait_for_selector("button:has-text('Met filter criteria')", timeout=20000)
        print("Page loaded.")
        
        await page.get_by_role("button", name="Met filter criteria").click()
        await asyncio.sleep(1)
        
        await page.locator("text='Contact'").click()
        await asyncio.sleep(1)
        
        await page.get_by_role("button", name="Add criteria").click()
        await asyncio.sleep(1)
        
        await page.get_by_role("button", name="Contact properties").click()
        await asyncio.sleep(1)
        
        input_box = page.locator('input[placeholder="Search in Contact properties"]')
        await input_box.fill("Total revenue")
        await asyncio.sleep(2)
        
        # Click the option
        option = page.locator("div:has-text('Total revenue'), span:has-text('Total revenue')").last
        await option.click()
        print("Option clicked.")
        await asyncio.sleep(3)
        
        # Now dump the HTML of the Group 1 panel
        group_1 = page.locator("div:has-text('Group 1')").first
        if await group_1.is_visible():
            print("--- Group 1 HTML ---")
            print(await group_1.inner_html())
        else:
            print("Group 1 not found. Printing body...")
            body = await page.locator("body").inner_html()
            print(body[:2000])
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(dump())
