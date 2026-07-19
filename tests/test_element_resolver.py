import os
import asyncio
import pytest
from pathlib import Path
from playwright.async_api import async_playwright

from execution.tools.element_resolver import ElementResolver, ElementNotFoundError


@pytest.mark.anyio
async def test_element_resolver_strategies():
    async with async_playwright() as p:
        # Launch headless browser for testing
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Set mock HTML content covering all five strategies
        html_content = """
        <html>
        <body>
          <!-- Strategy 1: Role & Label -->
          <button id="btn1">Save Settings</button>

          <!-- Strategy 2: Placeholder -->
          <input id="input2" placeholder="Search contacts..." />

          <!-- Strategy 3: CSS Fallbacks -->
          <div class="card">
            <span class="title">My Card Title</span>
          </div>

          <!-- Strategy 4: HTML Data Key -->
          <div data-key="acs-risk-input">Data Key Element</div>

          <!-- Strategy 5: Icon Indicator -->
          <svg data-icon-name="trash-icon" width="24" height="24">
            <rect width="20" height="20" fill="red" />
          </svg>
        </body>
        </html>
        """
        await page.set_content(html_content)
        
        resolver = ElementResolver(page)

        # 1. Test Role & Label
        spec_role_label = {
            "primary_role": "button",
            "primary_label": "Save Settings"
        }
        loc_role = await resolver.find(spec_role_label, timeout_ms=3000)
        assert await loc_role.get_attribute("id") == "btn1"

        # 2. Test Placeholder Text
        spec_placeholder = {
            "placeholder_text": "Search contacts..."
        }
        loc_place = await resolver.find(spec_placeholder, timeout_ms=3000)
        assert await loc_place.get_attribute("id") == "input2"

        # 3. Test Fallback CSS Selectors
        spec_fallback = {
            "fallback_selectors": [".non-existent", ".card .title"]
        }
        loc_fallback = await resolver.find(spec_fallback, timeout_ms=3000)
        assert await loc_fallback.text_content() == "My Card Title"

        # 4. Test HubSpot Data Key
        spec_data_key = {
            "html_data_key": "acs-risk-input"
        }
        loc_data_key = await resolver.find(spec_data_key, timeout_ms=3000)
        assert await loc_data_key.text_content() == "Data Key Element"

        # 5. Test Icon Indicator
        spec_icon = {
            "icon_indicator": "trash-icon"
        }
        loc_icon = await resolver.find(spec_icon, timeout_ms=3000)
        assert await loc_icon.get_attribute("data-icon-name") == "trash-icon"

        # 6. Test Find Multiple
        spec_multiple = {
            "fallback_selectors": [".card .title", "#btn1"]
        }
        locs_multiple = await resolver.find_multiple(spec_multiple, timeout_ms=3000)
        assert len(locs_multiple) == 1  # the winning strategy (fallback_selectors[0]) yields 1 element
        assert await locs_multiple[0].text_content() == "My Card Title"

        # 7. Test Failure & Screenshot Capture
        spec_failing = {
            "primary_role": "link",
            "primary_label": "Sign Out",
            "placeholder_text": "Enter name",
            "fallback_selectors": [".invalid-class-name"],
            "html_data_key": "missing-key",
            "icon_indicator": "missing-icon"
        }
        
        with pytest.raises(ElementNotFoundError) as exc_info:
            await resolver.find(spec_failing, timeout_ms=1500)

        err = exc_info.value
        assert "Sign Out" in str(err)
        assert "invalid-class-name" in str(err)
        assert err.screenshot_path is not None
        assert Path(err.screenshot_path).exists()
        
        # Cleanup screenshot
        os.remove(err.screenshot_path)

        await context.close()
        await browser.close()


@pytest.mark.anyio
async def test_hubspot_find_create_workflow_button():
    # Path to the saved browser state
    auth_state_path = Path(__file__).resolve().parent.parent / ".auth" / "hubspot_state.json"
    if not auth_state_path.exists():
        pytest.skip("HubSpot session state does not exist at .auth/hubspot_state.json. Please perform login first.")

    async with async_playwright() as p:
        # Launch Chrome in headed mode to match cached profile conditions and bypass anti-automation
        browser = await p.chromium.launch(
            headless=True,  # Run headless for CI/background validation
            channel="chrome",
            ignore_default_args=["--enable-automation"],
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(storage_state=str(auth_state_path))
        page = await context.new_page()

        try:
            print("Navigating to HubSpot workflows...")
            await page.goto("https://app-na2.hubspot.com/l/workflows", timeout=60000)
            
            # Wait for the page DOM load to settle
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(5)  # Let dynamic JS load the lists
            
            resolver = ElementResolver(page)
            element_to_find = {
                "primary_role": "button",
                "primary_label": "Create workflow"
            }
            
            print("Locating 'Create workflow' button...")
            locator = await resolver.find(element_to_find, timeout_ms=15000)
            
            is_visible = await locator.is_visible()
            print(f"Locator visibility status: {is_visible}")
            assert is_visible is True
            print("Successfully located the 'Create workflow' button!")
        finally:
            await context.close()
            await browser.close()

