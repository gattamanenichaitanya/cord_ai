import time
import json
import logging
import asyncio
from pathlib import Path
from typing import List, Tuple, Optional
from playwright.async_api import Page, Locator

logger = logging.getLogger("ElementResolver")


class ElementNotFoundError(Exception):
    """Exception raised when an element cannot be located using any strategy."""

    def __init__(
        self,
        attempted_strategies: List[Tuple[str, str]],
        element_to_find: dict,
        page_url: str,
        screenshot_path: Optional[str] = None
    ):
        self.attempted_strategies = attempted_strategies
        self.element_to_find = element_to_find
        self.page_url = page_url
        self.screenshot_path = screenshot_path

        strategies_str = "\n".join(f"  - {strat}: {res}" for strat, res in attempted_strategies)
        msg = (
            f"Could not find element on page {page_url} using any of the attempted strategies.\n"
            f"Element spec:\n{json.dumps(element_to_find, indent=2)}\n"
            f"Attempted strategies:\n{strategies_str}"
        )
        if screenshot_path:
            msg += f"\nScreenshot captured at: {screenshot_path}"
        super().__init__(msg)


class ElementResolver:
    """Finds UI elements on a Playwright page using a chain of location strategies."""

    def __init__(self, page: Page):
        self.page = page

    async def _wait_for_visible(self, locator: Locator, timeout_ms: float) -> bool:
        """Helper to wait for at least one matching element to become visible, returning True if successful."""
        import time
        start_time = time.time()
        while (time.time() - start_time) * 1000 < timeout_ms:
            try:
                count = await locator.count()
                for i in range(count):
                    if await locator.nth(i).is_visible():
                        return True
            except Exception:
                pass
            await asyncio.sleep(0.1)
        return False

    async def _get_topmost_visible(self, locator: Locator, strategy_desc: str) -> Locator:
        """Resolve locator conflicts by returning the topmost visible matching element."""
        count = await locator.count()
        if count == 1:
            logger.info(f"ElementResolver: found via {strategy_desc}")
            return locator
        else:
            logger.info(f"ElementResolver: {strategy_desc} matched {count} elements — finding the topmost visible one")
            visible_elements = []
            for i in range(count):
                nth_locator = locator.nth(i)
                if await nth_locator.is_visible():
                    visible_elements.append(nth_locator)
            
            if visible_elements:
                logger.info(f"ElementResolver: found {len(visible_elements)} visible matches, returning the last one (topmost)")
                return visible_elements[-1]
            return locator.first

    async def find(
        self,
        element_to_find: dict,
        timeout_ms: int = 10000
    ) -> Locator:
        """
        Find an element on the page using multiple strategies in order.
        
        Returns a Playwright Locator that is verified to be visible.
        Raises ElementNotFoundError if all strategies fail.
        """
        attempted_strategies = []
        page_url = self.page.url

        # Strategy 1: Role and Label
        if "primary_role" in element_to_find and "primary_label" in element_to_find:
            role = element_to_find["primary_role"]
            label = element_to_find["primary_label"]
            strategy_desc = f"get_by_role('{role}', name='{label}')"
            locator = self.page.get_by_role(role=role, name=label)
            
            logger.info(f"ElementResolver: trying {strategy_desc}")
            if await self._wait_for_visible(locator, timeout_ms / 3):
                return await self._get_topmost_visible(locator, strategy_desc)
            else:
                logger.info(f"ElementResolver: trying {strategy_desc} -> not visible")
                attempted_strategies.append((strategy_desc, "not visible or not found within timeout"))

        # Strategy 2: Placeholder Text
        if "placeholder_text" in element_to_find:
            placeholder = element_to_find["placeholder_text"]
            strategy_desc = f"get_by_placeholder('{placeholder}')"
            locator = self.page.get_by_placeholder(placeholder)
            
            logger.info(f"ElementResolver: trying {strategy_desc}")
            if await self._wait_for_visible(locator, timeout_ms / 3):
                return await self._get_topmost_visible(locator, strategy_desc)
            else:
                logger.info(f"ElementResolver: trying {strategy_desc} -> not visible")
                attempted_strategies.append((strategy_desc, "not visible or not found within timeout"))

        # Strategy 3: Fallback CSS Selectors
        if "fallback_selectors" in element_to_find:
            selectors = element_to_find["fallback_selectors"]
            if selectors:
                per_selector_timeout = timeout_ms / (3 * len(selectors))
                for selector in selectors:
                    strategy_desc = f"fallback CSS selector '{selector}'"
                    locator = self.page.locator(selector)
                    
                    logger.info(f"ElementResolver: trying {strategy_desc}")
                    if await self._wait_for_visible(locator, per_selector_timeout):
                        return await self._get_topmost_visible(locator, strategy_desc)
                    else:
                        logger.info(f"ElementResolver: trying {strategy_desc} -> not visible")
                        attempted_strategies.append((strategy_desc, "not visible or not found within timeout"))

        # Strategy 4: HubSpot data-key attribute
        if "html_data_key" in element_to_find:
            data_key = element_to_find["html_data_key"]
            strategy_desc = f"data-key locator '[data-key=\"{data_key}\"]'"
            locator = self.page.locator(f'[data-key="{data_key}"]')
            
            logger.info(f"ElementResolver: trying {strategy_desc}")
            if await self._wait_for_visible(locator, timeout_ms / 3):
                return await self._get_topmost_visible(locator, strategy_desc)
            else:
                logger.info(f"ElementResolver: trying {strategy_desc} -> not visible")
                attempted_strategies.append((strategy_desc, "not visible or not found within timeout"))

        # Strategy 5: Icon Indicator
        if "icon_indicator" in element_to_find:
            icon = element_to_find["icon_indicator"]
            strategy_desc = f"icon indicator '[data-icon-name=\"{icon}\"]'"
            locator = self.page.locator(f'svg[data-icon-name="{icon}"]')
            
            logger.info(f"ElementResolver: trying {strategy_desc}")
            if await self._wait_for_visible(locator, timeout_ms / 3):
                return await self._get_topmost_visible(locator, strategy_desc)
            else:
                logger.info(f"ElementResolver: trying {strategy_desc} -> not visible")
                attempted_strategies.append((strategy_desc, "not visible or not found within timeout"))

        # If none of the strategies succeeded, capture a screenshot for self-healing
        screenshot_dir = Path("execution_runs/screenshots")
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"resolver_error_{int(time.time())}.png"
        
        try:
            await self.page.screenshot(path=str(screenshot_path))
            screenshot_path_str = str(screenshot_path.resolve())
        except Exception as e:
            logger.error(f"ElementResolver: failed to take error screenshot: {e}")
            screenshot_path_str = None

        raise ElementNotFoundError(
            attempted_strategies=attempted_strategies,
            element_to_find=element_to_find,
            page_url=page_url,
            screenshot_path=screenshot_path_str
        )

    async def find_multiple(
        self,
        element_to_find: dict,
        timeout_ms: int = 10000
    ) -> List[Locator]:
        """
        Find multiple matching elements on the page using the strategy chain.
        Returns a list of matching locators that are visible.
        """
        # We try each strategy. The first strategy that returns any visible matching elements wins.
        # 1. Role and Label
        if "primary_role" in element_to_find and "primary_label" in element_to_find:
            role = element_to_find["primary_role"]
            label = element_to_find["primary_label"]
            locator = self.page.get_by_role(role=role, name=label)
            if await self._wait_for_visible(locator, timeout_ms / 3):
                matching = []
                for loc in await locator.all():
                    if await loc.is_visible():
                        matching.append(loc)
                if matching:
                    return matching

        # 2. Placeholder
        if "placeholder_text" in element_to_find:
            placeholder = element_to_find["placeholder_text"]
            locator = self.page.get_by_placeholder(placeholder)
            if await self._wait_for_visible(locator, timeout_ms / 3):
                matching = []
                for loc in await locator.all():
                    if await loc.is_visible():
                        matching.append(loc)
                if matching:
                    return matching

        # 3. CSS Selector fallbacks
        if "fallback_selectors" in element_to_find:
            selectors = element_to_find["fallback_selectors"]
            if selectors:
                per_selector_timeout = timeout_ms / (3 * len(selectors))
                for selector in selectors:
                    locator = self.page.locator(selector)
                    if await self._wait_for_visible(locator, per_selector_timeout):
                        matching = []
                        for loc in await locator.all():
                            if await loc.is_visible():
                                matching.append(loc)
                        if matching:
                            return matching

        # 4. HubSpot data-key
        if "html_data_key" in element_to_find:
            data_key = element_to_find["html_data_key"]
            locator = self.page.locator(f'[data-key="{data_key}"]')
            if await self._wait_for_visible(locator, timeout_ms / 3):
                matching = []
                for loc in await locator.all():
                    if await loc.is_visible():
                        matching.append(loc)
                if matching:
                    return matching

        # 5. Icon Indicator
        if "icon_indicator" in element_to_find:
            icon = element_to_find["icon_indicator"]
            locator = self.page.locator(f'svg[data-icon-name="{icon}"]')
            if await self._wait_for_visible(locator, timeout_ms / 3):
                matching = []
                for loc in await locator.all():
                    if await loc.is_visible():
                        matching.append(loc)
                if matching:
                    return matching

        return []
