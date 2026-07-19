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
        
        # Step 1
        await page.get_by_role("textbox", name="Unnamed workflow").fill("At-Risk Customer Alert")
        await asyncio.sleep(1)
        
        # Step 2
        await page.get_by_role("button", name="Met filter criteria").click()
        await asyncio.sleep(1)
        
        # Step 3
        await page.locator("text='Contact'").click()
        await asyncio.sleep(1)
        
        # Step 4
        await page.get_by_role("button", name="Add criteria").click()
        await asyncio.sleep(1)
        
        # Step 5
        await page.get_by_role("button", name="Contact properties").click()
        await asyncio.sleep(1)
        
        # Step 6
        input_box = page.locator('input[placeholder="Search in Contact properties"]')
        await input_box.fill("Total revenue")
        await asyncio.sleep(2)
        
        # Click Option
        results = page.locator("[class*='results'], [class*='list'], .private-selectable-list").first
        option = page.locator("div:has-text('Total revenue'), span:has-text('Total revenue')").last
        await option.click()
        print("Selected property.")
        await asyncio.sleep(3)
        
        # Dump page HTML to file
        html_content = await page.locator("body").inner_html()
        out_file = project_root / "scratch" / "body_html.txt"
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"Dumped HTML to {out_file}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(dump())
