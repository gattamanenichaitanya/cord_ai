import asyncio
import os
from playwright.async_api import async_playwright
from dotenv import load_dotenv

async def main():
    load_dotenv()
    auth_path = os.path.join(os.getcwd(), ".auth", "hubspot_state.json")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(storage_state=auth_path)
        page = await context.new_page()
        
        # Navigate and click through to Edit record
        await page.goto("https://app-na2.hubspot.com/workflows/246672023/create")
        print("Navigated to creation page.")
        
        # Click Met filter criteria
        await page.get_by_role("button", name="Met filter criteria").click()
        await asyncio.sleep(1)
        
        # Click Contact
        await page.locator("text='Contact'").last.click()
        await asyncio.sleep(1)
        
        # Click Add criteria
        await page.get_by_role("button", name="Add criteria").click()
        await asyncio.sleep(1)
        
        # Click Contact properties
        await page.get_by_role("button", name="Contact properties").click()
        await asyncio.sleep(1)
        
        # Search and select property
        await page.locator("input[placeholder='Search in Contact properties']").fill("Total revenue")
        await asyncio.sleep(1)
        await page.locator("button:has-text('Total revenue'), div:has-text('Total revenue')").last.click()
        await asyncio.sleep(2.5)
        
        # Click Next
        await page.get_by_role("button", name="Next").click()
        await asyncio.sleep(1)
        
        # Click Save and continue
        await page.get_by_role("button", name="Save and continue").click()
        await asyncio.sleep(1.5)
        
        # Click CRM category
        await page.locator("button:has-text('CRM'), div:has-text('CRM'), [role='button']:has-text('CRM')").last.click()
        await asyncio.sleep(1)
        
        # Click Edit record
        await page.locator("div:has-text('Edit record'), button:has-text('Edit record')").last.click()
        await asyncio.sleep(2.5)
        
        # Select property to edit (Annual Revenue)
        prop_btn = page.locator("div[class*='FormControl']:has(label:has-text('Property to edit')) button").last
        await prop_btn.click()
        await asyncio.sleep(1)
        await page.get_by_role("option", name="Annual Revenue").first.click()
        await asyncio.sleep(2.5)
        
        # Now dump the HTML of the left panel!
        panel = page.locator(".Panel__StyledPanelContainer-jZfJki, [class*='Panel'], [role='dialog']").first
        if await panel.is_visible():
            html = await panel.outer_html()
            print("FOUND PANEL HTML:")
            print(html[:5000])
            with open("scratch/panel_html.txt", "w", encoding="utf-8") as f:
                f.write(html)
            print("Saved full panel HTML to scratch/panel_html.txt")
        else:
            print("Panel not visible!")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
