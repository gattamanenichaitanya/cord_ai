import base64
import json
import logging
from typing import Optional
from playwright.async_api import Page

from execution.models import LocationResult

logger = logging.getLogger("VisionLocator")


class VisionLocator:
    def __init__(self, claude_client, model: str = "claude-sonnet-4-6"):
        self.client = claude_client
        self.model = model

    async def _capture_and_encode_screenshot(self, page: Page) -> str:
        """Capture screenshot and encode to base64."""
        screenshot_bytes = await page.screenshot(type="jpeg", quality=60)
        return base64.b64encode(screenshot_bytes).decode("utf-8")

    async def locate(
        self,
        page: Page,
        step_intent: str,
        element_description: dict,
        context: Optional[dict] = None
    ) -> LocationResult:
        """
        Take a screenshot of the current page, ask Claude to locate 
        the element, return coordinates or an alternative selector.
        """
        try:
            b64_image = await self._capture_and_encode_screenshot(page)
            
            prompt_text = (
                f"You are helping a browser automation agent find an element on "
                f"a HubSpot page. The agent was looking for:\n"
                f"Intent: {step_intent}\n"
                f"Expected element: {json.dumps(element_description, indent=2)}\n\n"
                f"The primary selectors failed. Look at the screenshot and:\n"
                f"1. Find the element the agent is looking for (if visible)\n"
                f"2. Report its approximate coordinates (center) and bounding box\n"
                f"3. If you can see a nearby data-test-id or aria-label attribute "
                f"that would work as a selector, suggest it\n"
                f"4. If the element isn't visible, suggest what to do (scroll, "
                f"wait, click something else first)\n\n"
                f"Be conservative — if you're not sure, set found=false rather "
                f"than guessing."
            )

            tool_schema = {
                "name": "report_location",
                "description": "Report the location of the element on the screen.",
                "input_schema": LocationResult.model_json_schema()
            }

            logger.info(f"VisionLocator: Calling Vision LLM to heal step '{step_intent}'...")
            
            # Using the Anthropic messages API structure
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                tools=[tool_schema],
                tool_choice={"type": "tool", "name": "report_location"},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": b64_image
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt_text
                            }
                        ]
                    }
                ]
            )

            # Extract tool use result
            for content in response.content:
                if content.type == "tool_use" and content.name == "report_location":
                    logger.info("VisionLocator: Received structured location result from LLM.")
                    input_data = content.input
                    if "coordinates" in input_data and isinstance(input_data["coordinates"], list):
                        input_data["coordinates"] = tuple(input_data["coordinates"])
                    return LocationResult(**input_data)
            
            logger.warning("VisionLocator: LLM did not use the report_location tool.")
            return LocationResult(
                found=False,
                reasoning="LLM did not return structured location data.",
                confidence=0.0
            )

        except Exception as e:
            logger.error(f"VisionLocator error: {e}")
            return LocationResult(
                found=False,
                reasoning=f"Vision API error: {str(e)}",
                confidence=0.0
            )
