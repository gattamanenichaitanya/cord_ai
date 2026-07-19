"""
UIExecutor
==========
Handles operations that require browser-based UI interaction via Playwright.
Falls back from API when an operation's preferred method is UI, or when API
execution is unavailable.

Currently implements the create_custom_property UI flow (steps 1-4).
Workflow creation and other complex UI flows will be added in Day 2+.
"""

import os
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright, Page, Locator, BrowserContext

from planning.models import PlanAction
from execution.models import (
    ActionResult,
    ExecutionStep,
    ExecutionStatus,
    ExecutionMethodUsed,
    ScreenshotRecord,
)
from execution.executors.base import ExecutorBase
from execution.tools.element_resolver import ElementResolver, ElementNotFoundError
from execution.tools.vision_locator import VisionLocator
from execution.hubspot_session import (
    DEMO_BROWSER_POSITION,
    DEMO_BROWSER_SIZE,
    DEMO_SLOW_MO,
    DEFAULT_SLOW_MO,
)

logger = logging.getLogger("UIExecutor")

# HubSpot object type IDs for URL parameter substitution
OBJECT_TYPE_IDS = {
    "contacts": "0-1",
    "companies": "0-2",
    "deals": "0-3",
    "tickets": "0-5",
    "quotes": "0-14",
    "products": "0-7",
    "line_items": "0-8",
}

# Path to the saved browser state (cookies + localStorage)
AUTH_STATE_PATH = Path(__file__).resolve().parent.parent.parent / ".auth" / "hubspot_state.json"


class UIExecutor(ExecutorBase):
    """Executes plan actions via browser UI interaction using Playwright."""

    def __init__(
        self,
        page: Page = None,
        vision_locator: Optional[VisionLocator] = None,
        demo_mode: bool = False,
        progress_callback: Optional[Any] = None,
    ):
        """
        Initialize the UI executor.

        Args:
            page: An active Playwright Page instance (from an already-opened
                  HubSpotSession or test harness). If None, execute() will
                  launch its own async session using the saved auth state.
            vision_locator: Optional VisionLocator instance for self-healing broken selectors.
            demo_mode: If True, launches headed browser positioned on the right half.
            progress_callback: Callback dispatcher for execution steps.
        """
        self.page = page
        self.resolver: Optional[ElementResolver] = None
        self.vision_locator = vision_locator
        self.demo_mode = demo_mode
        self.progress_callback = progress_callback

        # Portal ID for URL substitution
        self.portal_id = os.environ.get("HUBSPOT_PORTAL_ID", "")

        # Managed browser resources (only used when self.page is None)
        self._playwright = None
        self._browser = None
        self._context: Optional[BrowserContext] = None

    # ── Lifecycle helpers ──────────────────────────────────────────

    async def _ensure_page(self):
        """If no page was injected, launch a Chrome session from saved state."""
        if self.page is not None:
            return

        if not AUTH_STATE_PATH.exists():
            raise RuntimeError(
                f"No active page provided and no saved session at {AUTH_STATE_PATH}. "
                "Run tests/test_session.py to log in first."
            )

        self._playwright = await async_playwright().start()

        # Set up demo parameters if demo_mode is enabled
        slow_mo = DEMO_SLOW_MO if self.demo_mode else DEFAULT_SLOW_MO
        headless = False if self.demo_mode else True
        args = ["--disable-blink-features=AutomationControlled"]
        if self.demo_mode:
            args.extend([
                f"--window-position={DEMO_BROWSER_POSITION}",
                f"--window-size={DEMO_BROWSER_SIZE}"
            ])

        self._browser = await self._playwright.chromium.launch(
            headless=headless,
            slow_mo=slow_mo,
            channel="chrome",
            ignore_default_args=["--enable-automation"],
            args=args,
        )
        
        context_args = {"storage_state": str(AUTH_STATE_PATH)}
        if self.demo_mode:
            context_args["no_viewport"] = True

        self._context = await self._browser.new_context(**context_args)
        self.page = await self._context.new_page()
        logger.info("UIExecutor: launched browser session from saved auth state.")

    async def _cleanup(self):
        """Close browser resources that we opened ourselves."""
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        # Only clear self.page if we created it
        if self._playwright is None:
            self.page = None

    # ── ExecutorBase interface ─────────────────────────────────────

    async def can_execute(self, operation_entry: dict) -> bool:
        """Returns True if operation_entry has a UI execution method."""
        methods = operation_entry.get("execution_methods", [])
        for m in methods:
            if m.get("method") == "ui":
                return True
        return False

    async def execute(
        self,
        action: PlanAction,
        operation_entry: dict,
        run_dir: Path,
    ) -> ActionResult:
        """
        Execute one action via the browser UI.

        1. Find the UI method entry
        2. Navigate to the target URL
        3. Execute each step in order
        4. Run verification
        5. Return ActionResult with full audit trail
        """
        started_at = datetime.now()
        steps: List[ExecutionStep] = []
        error_message: Optional[str] = None
        verification_result: Optional[dict] = None
        overall_status = ExecutionStatus.IN_PROGRESS

        # 1. Find the UI method entry
        ui_method = None
        for m in operation_entry.get("execution_methods", []):
            if m.get("method") == "ui":
                ui_method = m
                break

        if not ui_method:
            return ActionResult(
                action_id=action.action_id,
                operation_id=action.operation_id,
                method_used=ExecutionMethodUsed.UI,
                status=ExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(),
                duration_seconds=0.0,
                error_message="No UI method configuration found in operation schema.",
            )

        try:
            self.operation_entry = operation_entry
            # 2. Ensure we have an active page
            await self._ensure_page()
            self.resolver = ElementResolver(self.page)

            # 3. Navigate to the target URL
            nav_step = await self._navigate(ui_method, action.parameters, run_dir, action.action_id)
            steps.append(nav_step)

            if nav_step.status == ExecutionStatus.FAILED:
                overall_status = ExecutionStatus.FAILED
                error_message = nav_step.error_message
            else:
                # 4. Execute each UI step in order
                ui_steps = ui_method.get("steps", [])
                for step_def in ui_steps:
                    exec_step = await self._execute_step_with_healing(
                        step_def, action.parameters, run_dir, action.action_id
                    )
                    steps.append(exec_step)

                    if exec_step.status == ExecutionStatus.FAILED:
                        overall_status = ExecutionStatus.FAILED
                        error_message = exec_step.error_message
                        break

                # 5. Verification (if all steps passed)
                if overall_status != ExecutionStatus.FAILED:
                    verification_result = await self._run_verification(
                        ui_method, action.parameters, run_dir, action.action_id
                    )
                    if verification_result and not verification_result.get("success", False):
                        overall_status = ExecutionStatus.FAILED
                        error_message = f"UI verification failed: {verification_result.get('reason', 'unknown')}"
                    else:
                        overall_status = ExecutionStatus.SUCCESS

        except Exception as e:
            overall_status = ExecutionStatus.FAILED
            error_message = f"UIExecutor unexpected error: {str(e)}"
            logger.error(error_message, exc_info=True)
        finally:
            await self._cleanup()

        completed_at = datetime.now()
        duration = (completed_at - started_at).total_seconds()

        action_result = ActionResult(
            action_id=action.action_id,
            operation_id=action.operation_id,
            method_used=ExecutionMethodUsed.UI,
            status=overall_status,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            steps=steps,
            output_data={},
            error_message=error_message,
            verification_result=verification_result,
        )

        # Persist the action result
        actions_dir = run_dir / "actions"
        actions_dir.mkdir(parents=True, exist_ok=True)
        result_file = actions_dir / f"{action.action_id}.json"
        result_file.write_text(action_result.model_dump_json(indent=2), encoding="utf-8")

        return action_result

    # ── Navigation ─────────────────────────────────────────────────

    async def _navigate(
        self,
        ui_method: dict,
        action_params: dict,
        run_dir: Path,
        action_id: str,
    ) -> ExecutionStep:
        """Navigate to the target URL specified in the operation entry."""
        step_id = 0
        intent = "Navigate to target URL"
        if self.progress_callback and hasattr(self.progress_callback, "on_step_start"):
            self.progress_callback.on_step_start(action_id, step_id, intent)

        step_start = datetime.now()
        screenshots: List[ScreenshotRecord] = []

        nav_info = ui_method.get("navigation", {})
        url_pattern = nav_info.get("url_pattern", "")

        # Substitute URL parameters
        object_type = action_params.get("object_type", "contacts")
        object_type_id = OBJECT_TYPE_IDS.get(object_type, "0-1")

        url = (
            url_pattern
            .replace("{portal_id}", self.portal_id)
            .replace("{object_type_id}", object_type_id)
            .replace("{object_type}", object_type)
        )

        logger.info(f"UIExecutor: navigating to {url}")

        try:
            await self.page.goto(url, timeout=60000)
            await self.page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(3)  # Let dynamic JS render

            # Take a screenshot after navigation
            ss_record = await self._take_screenshot(
                run_dir, action_id, 0, "after_navigation", "Page after navigation"
            )
            screenshots.append(ss_record)

            res = ExecutionStep(
                step_id=0,
                intent="Navigate to target URL",
                status=ExecutionStatus.SUCCESS,
                started_at=step_start,
                completed_at=datetime.now(),
                reasoning=f"Navigated to {url}",
                screenshots=screenshots,
            )
        except Exception as e:
            ss_record = await self._take_screenshot(
                run_dir, action_id, 0, "nav_error", "Navigation error"
            )
            screenshots.append(ss_record)

            res = ExecutionStep(
                step_id=0,
                intent="Navigate to target URL",
                status=ExecutionStatus.FAILED,
                started_at=step_start,
                completed_at=datetime.now(),
                error_message=f"Navigation failed: {str(e)}",
                screenshots=screenshots,
            )

        if self.progress_callback and hasattr(self.progress_callback, "on_step_complete"):
            self.progress_callback.on_step_complete(action_id, step_id, intent, res.status)

        return res

    # ── Step Execution ─────────────────────────────────────────────

    async def _execute_step_with_healing(
        self,
        step: dict,
        action_params: dict,
        run_dir: Path,
        action_id: str,
        max_healing_attempts: int = 2,
        current_item: Optional[dict] = None
    ) -> ExecutionStep:
        """Wrapper around _execute_step that self-heals when elements aren't found."""
        step_id = step.get("step_id", 0)
        intent = step.get("intent", "Unknown step")

        if self.progress_callback and hasattr(self.progress_callback, "on_step_start"):
            self.progress_callback.on_step_start(action_id, step_id, intent)

        final_result = None
        try:
            for attempt in range(max_healing_attempts + 1):
                result = await self._execute_step(step, action_params, run_dir, action_id, current_item=current_item)
                
                if result.status == ExecutionStatus.SUCCESS:
                    if attempt > 0:
                        result.healing_attempts = attempt
                        result.reasoning = f"{result.reasoning} (Succeeded on healing attempt {attempt})"
                    final_result = result
                    break
                    
                error_msg = str(result.error_message) if result.error_message else ""
                should_heal = (
                    result.status == ExecutionStatus.FAILED 
                    and (
                        "Element not found" in error_msg 
                        or "Timeout" in error_msg 
                        or "intercepts pointer events" in error_msg
                    )
                )
                
                if should_heal:
                    if attempt == max_healing_attempts or not self.vision_locator:
                        logger.error(f"UIExecutor: Element not found, no healing possible. {result.error_message}")
                        final_result = result
                        break
                    
                    logger.warning(f"UIExecutor: Element not found — attempting vision-based healing (attempt {attempt+1})")
                    if self.progress_callback and hasattr(self.progress_callback, "on_healing"):
                        self.progress_callback.on_healing(action_id, step_id, f"Attempting vision-based healing (attempt {attempt+1})")
                    
                    location = await self.vision_locator.locate(
                        page=self.page,
                        step_intent=step["intent"],
                        element_description=step.get("element_to_find", {})
                    )
                    
                    if location.found:
                        if location.alternative_selector:
                            element_spec = step.setdefault("element_to_find", {})
                            element_spec["fallback_selectors"] = (
                                element_spec.get("fallback_selectors", []) 
                                + [location.alternative_selector]
                            )
                            msg = f"Vision suggested alternative selector '{location.alternative_selector}'."
                            logger.info(f"UIExecutor: {msg}")
                            if self.progress_callback and hasattr(self.progress_callback, "on_healing"):
                                self.progress_callback.on_healing(action_id, step_id, msg)
                            continue
                            
                        elif location.coordinates:
                            msg = f"Vision suggested clicking coordinates {location.coordinates}."
                            logger.info(f"UIExecutor: {msg}")
                            if self.progress_callback and hasattr(self.progress_callback, "on_healing"):
                                self.progress_callback.on_healing(action_id, step_id, msg)
                            await self.page.mouse.click(*location.coordinates)
                            
                            if step.get("action") == "click":
                                final_result = ExecutionStep(
                                    step_id=step["step_id"],
                                    intent=step["intent"],
                                    status=ExecutionStatus.SUCCESS,
                                    started_at=datetime.now(),
                                    completed_at=datetime.now(),
                                    healing_attempts=attempt + 1,
                                    reasoning=f"Healed via vision — clicked at coords {location.coordinates}. {location.reasoning}"
                                )
                                break
                            else:
                                logger.error("UIExecutor: Can't click-heal a non-click action.")
                    else:
                        msg = f"Vision healing failed: {location.followup_suggestion or 'Element not found'}"
                        logger.info(f"UIExecutor: {msg}")
                        if self.progress_callback and hasattr(self.progress_callback, "on_healing"):
                            self.progress_callback.on_healing(action_id, step_id, msg)
                else:
                    final_result = result
                    break
        except Exception as e:
            final_result = ExecutionStep(
                step_id=step_id,
                intent=intent,
                status=ExecutionStatus.FAILED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                error_message=f"Healing helper error: {e}"
            )
            
        if final_result is None:
            final_result = ExecutionStep(
                step_id=step_id,
                intent=intent,
                status=ExecutionStatus.FAILED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                error_message="Healing helper exited loop without a result"
            )

        if self.progress_callback and hasattr(self.progress_callback, "on_step_complete"):
            self.progress_callback.on_step_complete(action_id, step_id, intent, final_result.status)

        return final_result

    async def _execute_step(
        self,
        step_def: dict,
        action_params: dict,
        run_dir: Path,
        action_id: str,
        current_item: Optional[dict] = None
    ) -> ExecutionStep:
        """
        Execute a single UI step from the operation entry.
        """
        step_id = step_def.get("step_id", 0)
        intent = step_def.get("intent", "Unknown step")
        action_type = step_def.get("action", "")
        step_start = datetime.now()
        screenshots: List[ScreenshotRecord] = []

        logger.info(f"UIExecutor: step {step_id} — {intent} (action: {action_type})")

        try:
            # Take "before" screenshot
            ss_before = await self._take_screenshot(
                run_dir, action_id, step_id, "before", f"Before: {intent}"
            )
            screenshots.append(ss_before)

            # ── Handle execute_loop ──
            if action_type == "execute_loop":
                loop_over = step_def.get("loop_over", "")
                items = self._resolve_list(loop_over, action_params)
                sub_steps = step_def.get("loop_sub_steps", [])
                
                for idx, item in enumerate(items):
                    logger.info(f"UIExecutor: Loop step — executing iteration {idx} for item {item}")
                    for sub_step in sub_steps:
                        # 1. Check skip_when
                        skip_when = sub_step.get("skip_when", "")
                        if skip_when and self._evaluate_skip_when(skip_when, idx):
                            continue
                            
                        # 2. Check applies_to_action_type
                        applies_to = sub_step.get("applies_to_action_type")
                        if applies_to and item.get("type") != applies_to:
                            continue
                            
                        # 3. Check conditional_on
                        cond = sub_step.get("conditional_on")
                        if cond and "change_type == 'Replace'" in cond and item.get("change_type") != "Replace":
                            continue
                            
                        # 4. Run the sub-step
                        res = await self._execute_step_with_healing(
                            sub_step, action_params, run_dir, action_id, current_item=item
                        )
                        if res.status == ExecutionStatus.FAILED:
                            return ExecutionStep(
                                step_id=step_id,
                                intent=intent,
                                status=ExecutionStatus.FAILED,
                                started_at=step_start,
                                completed_at=datetime.now(),
                                error_message=f"Loop execution failed at iteration {idx}, sub-step '{sub_step.get('intent')}': {res.error_message}",
                                screenshots=screenshots
                            )
                
                return ExecutionStep(
                    step_id=step_id,
                    intent=intent,
                    status=ExecutionStatus.SUCCESS,
                    started_at=step_start,
                    completed_at=datetime.now(),
                    reasoning=f"Successfully executed loop over {len(items)} items.",
                    screenshots=screenshots
                )

            # ── Handle evaluate_branches ──
            if action_type == "evaluate_branches":
                conditional_on = step_def.get("conditional_on", "")
                branches = step_def.get("branches", {})
                
                if conditional_on == "current_action.type":
                    branch_key = current_item.get("type", "") if current_item else ""
                elif conditional_on == "plan.trigger.has_additional_conditions":
                    conditions = action_params.get("trigger", {}).get("conditions", [])
                    branch_key = "additional_AND_condition" if len(conditions) > 1 else "no_additional"
                else:
                    branch_key = self._resolve_value(step_def, action_params, current_item) or ""
                    
                branch_spec = branches.get(branch_key)
                if not branch_spec:
                    logger.info(f"UIExecutor: evaluate_branches — no branch spec found or 'no_additional' matched for '{branch_key}', skipping")
                    return ExecutionStep(
                        step_id=step_id,
                        intent=intent,
                        status=ExecutionStatus.SKIPPED,
                        started_at=step_start,
                        completed_at=datetime.now(),
                        reasoning=f"No branch action needed for '{branch_key}'.",
                        screenshots=screenshots
                    )
                
                # Check if this is the step 9 loop handler trigger
                if branch_key == "additional_AND_condition":
                    conditions = action_params.get("trigger", {}).get("conditions", [])
                    # We repeat steps 5-8 for additional conditions
                    for idx, cond in enumerate(conditions[1:], start=1):
                        logger.info(f"UIExecutor: Step 9 — configuring additional condition {idx}: {cond}")
                        # Click "Add criteria" inside Group 1
                        add_criteria_locator = self.page.locator("button:has-text('Add criteria')").last
                        await self._resilient_click(add_criteria_locator)
                        await asyncio.sleep(1)
                        # Run sub-steps 5, 6, 7, 8
                        sub_res = await self._run_sub_steps([5, 6, 7, 8], action_params, run_dir, action_id, current_item=cond)
                        if any(r.status == ExecutionStatus.FAILED for r in sub_res):
                            return ExecutionStep(
                                step_id=step_id,
                                intent=intent,
                                status=ExecutionStatus.FAILED,
                                started_at=step_start,
                                completed_at=datetime.now(),
                                error_message="Failed to configure additional trigger condition.",
                                screenshots=screenshots
                            )
                
                # Check if this is step 13 action picker selection
                elif isinstance(branch_spec, dict) and "action_label_in_picker" in branch_spec:
                    category = branch_spec.get("category_to_open")
                    action_label = branch_spec.get("action_label_in_picker")
                    # Click category
                    category_btn = self.page.locator(f"button:has-text('{category}'), div:has-text('{category}'), [role='button']:has-text('{category}')").last
                    if await category_btn.is_visible():
                        await self._resilient_click(category_btn)
                        await asyncio.sleep(1)
                    # Click action card
                    action_btn = self.page.locator(f"div:has-text('{action_label}'), button:has-text('{action_label}'), [class*='card']:has-text('{action_label}')").last
                    await self._resilient_click(action_btn)
                    await asyncio.sleep(2)

                return ExecutionStep(
                    step_id=step_id,
                    intent=intent,
                    status=ExecutionStatus.SUCCESS,
                    started_at=step_start,
                    completed_at=datetime.now(),
                    reasoning=f"Evaluated branch '{branch_key}' successfully.",
                    screenshots=screenshots
                )

            # ── Handle conditional steps ──
            if action_type == "configure_options":
                exec_step = await self._handle_conditional_step(
                    step_def, action_params, run_dir, action_id, step_id, intent, step_start, screenshots
                )
                return exec_step

            # ── Check if step should be skipped ──
            element_spec = step_def.get("element_to_find")
            if element_spec:
                # Copy element_spec to avoid mutating the original definition
                element_spec = dict(element_spec)
                for key in ["primary_label", "placeholder_text"]:
                    val = element_spec.get(key)
                    if val and any(token in str(val) for token in ["plan.", "current_item.", "current_action.", "current_condition."]):
                        import re
                        val_src = re.sub(r'value of\s+', '', str(val)).strip()
                        resolved_val = self._resolve_value({"value_source": val_src}, action_params, current_item)
                        if resolved_val:
                            # Apply value mapping from internal name if defined
                            mapping = element_spec.get("value_mapping_from_internal_name", {})
                            element_spec[key] = mapping.get(resolved_val, resolved_val)
                            
                # Resolve fallback_selectors dynamic references
                fallbacks = element_spec.get("fallback_selectors", [])
                if fallbacks:
                    resolved_fallbacks = []
                    for fb in fallbacks:
                        if any(token in str(fb) for token in ["plan.", "current_item.", "current_action.", "current_condition."]):
                            import re
                            match = re.search(r'(value of\s+)?(plan\.\w+(\.\w+)?|current_item\.\w+|current_action\.\w+)', fb)
                            if match:
                                val_src = match.group(2)
                                resolved_val = self._resolve_value({"value_source": val_src}, action_params, current_item)
                                if resolved_val:
                                    mapping = element_spec.get("value_mapping_from_internal_name", {})
                                    mapped_val = mapping.get(resolved_val, resolved_val)
                                    resolved_fb = fb.replace(match.group(0), mapped_val)
                                    resolved_fallbacks.append(resolved_fb)
                            else:
                                resolved_fallbacks.append(fb)
                        else:
                            resolved_fallbacks.append(fb)
                    element_spec["fallback_selectors"] = resolved_fallbacks

            # 1. Check skippable_when condition
            skippable_when = step_def.get("skippable_when", "")
            if skippable_when and self._should_skip(skippable_when, action_params):
                return ExecutionStep(
                    step_id=step_id,
                    intent=intent,
                    status=ExecutionStatus.SKIPPED,
                    started_at=step_start,
                    completed_at=datetime.now(),
                    reasoning=f"Skipped: {skippable_when}",
                    screenshots=screenshots,
                )

            # 2. For select_option, skip if value matches the default
            if action_type == "select_option" and element_spec:
                value = self._resolve_value(step_def, action_params, current_item)
                default_value = element_spec.get("default_value", "")
                if default_value and value and value.lower() == default_value.lower():
                    logger.info(
                        f"UIExecutor: step {step_id} — value '{value}' matches "
                        f"default '{default_value}', skipping select_option"
                    )
                    return ExecutionStep(
                        step_id=step_id,
                        intent=intent,
                        status=ExecutionStatus.SKIPPED,
                        started_at=step_start,
                        completed_at=datetime.now(),
                        reasoning=f"Value '{value}' matches default '{default_value}' — no change needed.",
                        screenshots=screenshots,
                    )

            # ── Special wait_until_visible pattern matching ──
            if action_type == "wait_until_visible" and element_spec and element_spec.get("primary_label_pattern"):
                pattern = element_spec.get("primary_label_pattern").replace("{N}", r"\d+")
                try:
                    await self.page.wait_for_selector("text=/contacts meet the enrollment criteria/i", timeout=15000)
                    logger.info("UIExecutor: enrollment count finished loading")
                    return ExecutionStep(
                        step_id=step_id,
                        intent=intent,
                        status=ExecutionStatus.SUCCESS,
                        started_at=step_start,
                        completed_at=datetime.now(),
                        reasoning="Enrollment criteria count finished loading.",
                        screenshots=screenshots
                    )
                except Exception as e:
                    logger.error(f"UIExecutor: timed out waiting for enrollment count: {e}")
                    raise ElementNotFoundError("Enrollment criteria count did not load in time.")

            # ── Resolve the target element ──
            if not element_spec:
                return ExecutionStep(
                    step_id=step_id,
                    intent=intent,
                    status=ExecutionStatus.SKIPPED,
                    started_at=step_start,
                    completed_at=datetime.now(),
                    reasoning="No element_to_find defined — skipping step.",
                    screenshots=screenshots,
                )

            locator = await self.resolver.find(element_spec, timeout_ms=10000)

            # ── Resolve the value (if needed) ──
            value = self._resolve_value(step_def, action_params, current_item)

            # ── Perform the action ──
            if action_type == "fill":
                await locator.fill(value or "")
                logger.info(f"UIExecutor: filled element with '{value}'")

            elif action_type == "click":
                await self._resilient_click(locator)
                logger.info(f"UIExecutor: clicked element")
                await asyncio.sleep(2)

            elif action_type == "select_option":
                await self._handle_select_option(locator, element_spec, value)

            elif action_type == "verify_or_select":
                current_val = ""
                try:
                    current_val = await locator.input_value()
                except Exception:
                    try:
                        current_val = await locator.text_content()
                    except Exception:
                        pass
                
                # Check for operator label mappings
                op_mapping = {
                    "equals": "is equal to any of",
                    "is_any_of": "is any of",
                    "greater_than": "is greater than",
                    "less_than": "is less than",
                    "is_within_next_n_days": "is within the next [N] days"
                }
                mapped_value = op_mapping.get(value.lower() if value else "", value)
                
                norm_mapped = mapped_value.lower().replace(" any of", "").strip()
                norm_current = current_val.lower().replace(" any of", "").strip()
                
                if norm_current and norm_mapped in norm_current:
                    logger.info(f"UIExecutor: value already matches '{mapped_value}' (normalized match: '{norm_mapped}' in '{norm_current}')")
                else:
                    await self._handle_select_option(locator, element_spec, mapped_value)

            elif action_type == "set_toggle":
                await self._handle_set_toggle(locator, value)

            elif action_type == "wait_until_visible":
                # Element was already found by resolver — nothing more to do
                logger.info(f"UIExecutor: element is visible")

            elif action_type == "fill_or_select":
                class_name = await locator.get_attribute("class") or ""
                if "CodeMirror" in class_name:
                    logger.info("UIExecutor: Element is CodeMirror, clicking and typing...")
                    await locator.click()
                    await self.page.keyboard.type(value or "")
                    await asyncio.sleep(0.5)
                else:
                    try:
                        await locator.fill(value or "")
                        logger.info(f"UIExecutor: filled element with '{value}'")
                    except Exception:
                        await self._handle_select_option(locator, element_spec, value)

            elif action_type == "fill_then_select":
                await locator.focus()
                await self.page.keyboard.type(value or "", delay=50)
                await asyncio.sleep(2.0)
                # Try to locate inside search results containers first
                results_container = self.page.locator("[class*='results'], [class*='list'], [role='listbox'], .private-selectable-list").first
                if await results_container.is_visible() and await results_container.locator(f"text='{value}'").count() > 0:
                    option = results_container.locator(f"button:has-text('{value}'), div:has-text('{value}'), span:has-text('{value}'), [role='option']:has-text('{value}')").last
                else:
                    option = self.page.locator(f"button:has-text('{value}'), div:has-text('{value}'), span:has-text('{value}'), [role='option']:has-text('{value}')").last
                await self._resilient_click(option)
                await asyncio.sleep(2.5)

            elif action_type == "select_radio":
                mapping = step_def.get("value_mapping", {})
                target_label = mapping.get(str(value).lower(), value)
                radio_option = self.page.locator(f"label:has-text('{target_label}'), input[type='radio'] ~ span:has-text('{target_label}')").first
                await self._resilient_click(radio_option)
                await asyncio.sleep(0.5)

            else:
                logger.warning(f"UIExecutor: unknown action type '{action_type}' — skipping")
                return ExecutionStep(
                    step_id=step_id,
                    intent=intent,
                    status=ExecutionStatus.SKIPPED,
                    started_at=step_start,
                    completed_at=datetime.now(),
                    reasoning=f"Unknown action type '{action_type}'.",
                    screenshots=screenshots,
                )

            # Take "after" screenshot
            ss_after = await self._take_screenshot(
                run_dir, action_id, step_id, "after", f"After: {intent}"
            )
            screenshots.append(ss_after)

            # Verify expected_outcome if defined
            expected = step_def.get("expected_outcome")
            if expected:
                await self._verify_expected_outcome(expected)

            return ExecutionStep(
                step_id=step_id,
                intent=intent,
                status=ExecutionStatus.SUCCESS,
                started_at=step_start,
                completed_at=datetime.now(),
                reasoning=f"Completed '{action_type}' action successfully.",
                screenshots=screenshots,
            )

        except ElementNotFoundError as enf:
            try:
                # Target the actual configuration sidebar/panel
                sidebar_loc = self.page.locator("[role='dialog'], .UIAbstractPanel, .private-panel, [class*='Panel'], [class*='sidebar']")
                visible_sidebar = None
                for i in range(await sidebar_loc.count()):
                    loc = sidebar_loc.nth(i)
                    if await loc.is_visible():
                        visible_sidebar = loc
                        break
                if visible_sidebar:
                    html = await visible_sidebar.inner_html()
                    logger.warning(f"UIExecutor: Visible sidebar/panel HTML snippet:\n{html[:4000]}")
                    try:
                        os.makedirs("scratch", exist_ok=True)
                        with open("scratch/sidebar_dump.html", "w", encoding="utf-8") as f:
                            f.write(html)
                        logger.info("UIExecutor: Wrote full sidebar HTML to scratch/sidebar_dump.html")
                    except Exception as f_err:
                        logger.warning(f"UIExecutor: Failed to save full HTML: {f_err}")
                else:
                    logger.warning("UIExecutor: No visible sidebar/panel container found.")
            except Exception as dump_err:
                logger.warning(f"UIExecutor: Failed to dump sidebar HTML: {dump_err}")

            # Capture error screenshot
            ss_error = await self._take_screenshot(
                run_dir, action_id, step_id, "error", f"Error: {intent}"
            )
            screenshots.append(ss_error)

            return ExecutionStep(
                step_id=step_id,
                intent=intent,
                status=ExecutionStatus.FAILED,
                started_at=step_start,
                completed_at=datetime.now(),
                error_message=f"Element not found: {str(enf)[:500]}",
                screenshots=screenshots,
            )

        except Exception as e:
            ss_error = await self._take_screenshot(
                run_dir, action_id, step_id, "error", f"Error: {intent}"
            )
            screenshots.append(ss_error)

            return ExecutionStep(
                step_id=step_id,
                intent=intent,
                status=ExecutionStatus.FAILED,
                started_at=step_start,
                completed_at=datetime.now(),
                error_message=f"Step execution error: {str(e)}",
                screenshots=screenshots,
            )

    # ── Conditional / Branch handling ──────────────────────────────

    async def _handle_conditional_step(
        self,
        step_def: dict,
        action_params: dict,
        run_dir: Path,
        action_id: str,
        step_id: int,
        intent: str,
        step_start: datetime,
        screenshots: List[ScreenshotRecord],
    ) -> ExecutionStep:
        """
        Handle a conditional step that branches based on a value
        from the action parameters.
        """
        conditional_on = step_def.get("conditional_on", "")
        branches = step_def.get("branches", {})

        # Resolve the branch key from action params
        branch_value = action_params.get(conditional_on, "default")

        # Map plan field_type values to branch keys
        field_type_to_branch = {
            "text": "default",
            "textarea": "default",
            "number": "number",
            "dropdown": "select",
            "date": "default",
            "datetime": "default",
            "booleancheckbox": "default",
        }
        branch_key = field_type_to_branch.get(branch_value, branch_value)

        if branch_key not in branches:
            branch_key = "default"

        branch_description = branches.get(branch_key, "No action needed")
        logger.info(
            f"UIExecutor: conditional step — field_type='{branch_value}' "
            f"→ branch='{branch_key}': {branch_description}"
        )

        # For "default" branches, no additional UI action is needed
        if branch_key == "default":
            return ExecutionStep(
                step_id=step_id,
                intent=intent,
                status=ExecutionStatus.SUCCESS,
                started_at=step_start,
                completed_at=datetime.now(),
                reasoning=f"Conditional branch '{branch_key}': {branch_description}. No UI action needed.",
                screenshots=screenshots,
            )

        # For "select" branch (dropdown options), this would require
        # additional UI interaction to configure options — stubbed for Day 2
        if branch_key == "select":
            logger.warning(
                "UIExecutor: dropdown option configuration via UI is not yet implemented. "
                "Skipping options configuration step."
            )
            return ExecutionStep(
                step_id=step_id,
                intent=intent,
                status=ExecutionStatus.SKIPPED,
                started_at=step_start,
                completed_at=datetime.now(),
                reasoning="Dropdown options configuration via UI is not yet implemented (Day 2).",
                screenshots=screenshots,
            )

        # For "number" branch, optional number format — skip for now
        return ExecutionStep(
            step_id=step_id,
            intent=intent,
            status=ExecutionStatus.SUCCESS,
            started_at=step_start,
            completed_at=datetime.now(),
            reasoning=f"Conditional branch '{branch_key}': {branch_description}.",
            screenshots=screenshots,
        )

    # ── Value Resolution ───────────────────────────────────────────

    def _resolve_value(
        self,
        step_def: dict,
        action_params: dict,
        current_item: Optional[dict] = None,
    ) -> Optional[str]:
        """
        Resolve a value_source reference into a concrete value.
        """
        value_source = step_def.get("value_source")
        if not value_source:
            return None

        # Handle current loop item (current_item, current_action, current_condition)
        if value_source.startswith(("current_item.", "current_action.", "current_condition.")):
            field_name = value_source.split(".", 1)[1]
            if current_item:
                return str(current_item.get(field_name, ""))
            return ""

        # Map plan.trigger.X to trigger.conditions[0].X for the first condition
        if value_source.startswith("plan.trigger."):
            field = value_source.split("plan.trigger.", 1)[1]
            conditions = action_params.get("trigger", {}).get("conditions", [])
            if conditions:
                return str(conditions[0].get(field, ""))
            return ""

        if value_source.startswith("plan."):
            field_name = value_source.split(".", 1)[1]
            # Use nested resolution
            import re
            parts = re.split(r'\.(?![^\[]*\])', field_name)
            curr = action_params
            for part in parts:
                if not isinstance(curr, dict):
                    return ""
                curr = curr.get(part, "")
            return str(curr)

        # Treat as literal
        return value_source

    def _resolve_list(self, loop_over: str, action_params: dict) -> list:
        """Resolve a dotted path to a list in action_params."""
        if loop_over.startswith("plan."):
            field = loop_over.split("plan.", 1)[1]
            import re
            parts = re.split(r'\.(?![^\[]*\])', field)
            curr = action_params
            for part in parts:
                if not isinstance(curr, dict):
                    return []
                curr = curr.get(part, [])
            if isinstance(curr, list):
                return curr
        return []

    def _evaluate_skip_when(self, skip_when: str, index: int) -> bool:
        """Evaluate loop step skip conditions."""
        if skip_when == "current_action_index == 0":
            return index == 0
        return False

    async def _run_sub_steps(
        self,
        step_ids: List[int],
        action_params: dict,
        run_dir: Path,
        action_id: str,
        current_item: dict
    ) -> List[ExecutionStep]:
        """Execute a list of steps sequentially with loop context."""
        results = []
        steps_list = self.operation_entry.get("steps", [])
        for step_id in step_ids:
            step_def = next((s for s in steps_list if s.get("step_id") == step_id), None)
            if step_def:
                result = await self._execute_step_with_healing(
                    step_def, action_params, run_dir, action_id, current_item=current_item
                )
                results.append(result)
                if result.status == ExecutionStatus.FAILED:
                    break
        return results

    # ── Skip Condition Evaluation ────────────────────────────────

    def _should_skip(self, skippable_when: str, action_params: dict) -> bool:
        """
        Evaluate a skippable_when condition string.

        Supported format:
            "plan.field_name is 'value'"
            "plan.field_name is 'value' (explanation text)"
            e.g., "plan.field_type is 'text' (single-line text is the default)"

        Returns True if the condition is met (step should be skipped).
        """
        import re

        # Parse "plan.field_name is 'value'" pattern — extract the first quoted value
        match = re.match(
            r"""([\w.]+)\s+is\s+['"]([^'"]+)['"]""",
            skippable_when.strip(),
        )
        if match:
            source = match.group(1)  # e.g., "plan.field_type"
            expected = match.group(2)  # e.g., "text"

            # Handle "plan.X" references
            if source.startswith("plan."):
                field = source.split(".", 1)[1]
                actual = str(action_params.get(field, ""))
                if actual.lower() == expected.lower():
                    logger.info(
                        f"UIExecutor: skippable_when matched — {source}='{actual}' is '{expected}'"
                    )
                    return True

        return False

    # ── Action Helpers ─────────────────────────────────────────────

    async def _resilient_click(self, locator: Locator, timeout_ms: int = 5000):
        """
        Click an element with fallback strategies for HubSpot modal overlays.

        HubSpot modals have layered scroll containers where the submit button
        can be obscured by modal content. This method:
          1. Scrolls the element into view via JS within its scroll container
          2. Tries a normal Playwright click (short timeout)
          3. Falls back to force=True click if intercepted
          4. Last resort: dispatches a JS click event directly
        """
        # Step 1: Scroll element into view via JavaScript
        try:
            element = locator.first
            await element.evaluate("el => el.scrollIntoView({ block: 'center', behavior: 'instant' })")
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.debug(f"UIExecutor: JS scrollIntoView failed (non-fatal): {e}")

        # Step 2: Try normal click with short timeout
        try:
            await locator.click(timeout=timeout_ms)
            return
        except Exception as e:
            error_msg = str(e)
            if "intercepts pointer events" not in error_msg and "Timeout" not in error_msg:
                raise  # Re-raise if it's not an interception/timeout issue

            logger.info(f"UIExecutor: normal click intercepted — trying force click")

        # Step 3: Force click (bypasses actionability checks)
        try:
            await locator.click(force=True, timeout=timeout_ms)
            return
        except Exception as e:
            logger.info(f"UIExecutor: force click failed — trying JS click: {e}")

        # Step 4: Last resort — JavaScript click
        await locator.first.evaluate("el => el.click()")
        logger.info("UIExecutor: used JavaScript click as last resort")

    async def _handle_select_option(
        self, locator: Locator, element_spec: dict, value: Optional[str]
    ):
        """
        Handle selecting an option from a combobox or dropdown.
        HubSpot uses custom dropdowns, so we click to open, then
        find and click the matching option.
        """
        if not value:
            logger.info("UIExecutor: no value provided for select — skipping")
            return

        # Check if this is a skippable step (value matches default)
        default_value = element_spec.get("default_value", "")
        if default_value and value.lower() == default_value.lower():
            logger.info(
                f"UIExecutor: value '{value}' matches default '{default_value}' — skipping select"
            )
            return

        # Map common internal names (e.g., group_name) to user-friendly UI text
        normalized = value.lower().replace("_", "").replace(" ", "")
        group_mapping = {
            "contactinformation": "Contact information",
            "companyinformation": "Company information",
            "dealinformation": "Deal information",
            "ticketinformation": "Ticket information",
            "text": "Single-line text",
            "dropdown": "Dropdown select",
            "isequaltoanyof": "is equal to",
            "isnotequaltoanyof": "is not equal to",
        }
        search_value = group_mapping.get(normalized, value)

        # Click the combobox to open the dropdown list
        await locator.click()
        await asyncio.sleep(1)

        # Try to find the option by its text content
        option_locator = self.page.get_by_role("option", name=search_value)
        try:
            await option_locator.first.wait_for(state="visible", timeout=5000)
            await option_locator.first.click()
            logger.info(f"UIExecutor: selected option '{search_value}' via role lookup")
            await asyncio.sleep(2.5)
        except Exception:
            # Fallback: try locating by text within a listbox
            try:
                listbox = self.page.get_by_role("listbox")
                option = listbox.get_by_text(search_value, exact=False)
                await option.first.click()
                logger.info(f"UIExecutor: selected option '{search_value}' via listbox text")
                await asyncio.sleep(2.5)
            except Exception as e:
                logger.error(f"UIExecutor: failed to select option '{search_value}': {e}")
                raise

    async def _handle_set_toggle(self, locator: Locator, value: Optional[str]):
        """Handle toggling a checkbox or switch element."""
        if value is None:
            return

        target_state = value.lower() in ("true", "1", "yes", "on", "enabled")

        # Check current state
        is_checked = await locator.is_checked() if hasattr(locator, "is_checked") else False

        if is_checked != target_state:
            await self._resilient_click(locator)
            logger.info(
                f"UIExecutor: toggled from {is_checked} to {target_state}"
            )
        else:
            logger.info(f"UIExecutor: toggle already in desired state ({target_state})")

    # ── Verification ───────────────────────────────────────────────

    async def _run_verification(
        self,
        ui_method: dict,
        action_params: dict,
        run_dir: Path,
        action_id: str,
    ) -> Optional[dict]:
        """
        Run post-execution verification as defined in the operation entry.
        """
        verification = ui_method.get("verification")
        if not verification:
            return {"success": True, "reason": "No verification defined."}

        method = verification.get("method", "")

        if method == "list_check":
            return await self._verify_list_check(verification, action_params, run_dir, action_id)

        if method == "in_place_state_check":
            # Wait for activation transition to complete
            await asyncio.sleep(4)
            content = await self.page.content()
            
            # Take screenshot to verify visually
            await self._take_screenshot(
                run_dir, action_id, 99, "verification", "Verification: check active status"
            )
            
            has_turn_off = "Turn off" in content
            if has_turn_off:
                logger.info("UIExecutor: in_place_state_check passed — found 'Turn off' in page.")
                return {"success": True, "reason": "Workflow status changed to ON (found 'Turn off' button)."}
            else:
                logger.warning("UIExecutor: in_place_state_check failed — 'Turn off' not found.")
                return {"success": False, "reason": "Workflow activation could not be verified ('Turn off' button missing)."}

        logger.warning(f"UIExecutor: unknown verification method '{method}'")
        return {"success": True, "reason": f"Verification method '{method}' not implemented — skipping."}

    async def _verify_list_check(
        self,
        verification: dict,
        action_params: dict,
        run_dir: Path,
        action_id: str,
    ) -> dict:
        """
        Navigate to a listing page and check if a specific item
        appears in the list (e.g., a property label in the properties list).
        """
        navigate_to = verification.get("navigate_to", "")
        search_for_source = verification.get("search_for", "")

        # Resolve the search term
        if search_for_source.startswith("plan."):
            field_name = search_for_source.split(".", 1)[1]
            search_term = str(action_params.get(field_name, ""))
        else:
            search_term = search_for_source

        if not search_term:
            return {"success": False, "reason": "No search term resolved for verification."}

        # Substitute URL parameters
        object_type = action_params.get("object_type", "contacts")
        object_type_id = OBJECT_TYPE_IDS.get(object_type, "0-1")

        url = (
            navigate_to
            .replace("{portal_id}", self.portal_id)
            .replace("{object_type_id}", object_type_id)
        )

        try:
            await self.page.goto(url, timeout=60000)
            await self.page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(2)

            # Poll for the search term (HubSpot's search index can take a moment to sync)
            found = False
            for attempt in range(3):
                content = await self.page.content()
                if search_term.lower() in content.lower():
                    found = True
                    break
                logger.info(f"UIExecutor: verification attempt {attempt + 1} — '{search_term}' not found yet, waiting...")
                await asyncio.sleep(3)

            # Take verification screenshot
            await self._take_screenshot(
                run_dir, action_id, 99, "verification", f"Verification: looking for '{search_term}'"
            )

            if found:
                logger.info(f"UIExecutor: verification passed — found '{search_term}' in page.")
                return {"success": True, "reason": f"Found '{search_term}' in page content."}
            else:
                logger.warning(f"UIExecutor: verification failed — '{search_term}' not found in page.")
                return {"success": False, "reason": f"'{search_term}' not found in page content after retries."}

        except Exception as e:
            return {"success": False, "reason": f"Verification navigation error: {str(e)}"}

    # ── Expected Outcome Check ─────────────────────────────────────

    async def _verify_expected_outcome(self, expected: dict):
        """
        Lightweight check after a step — wait for UI signals like
        modals closing or toasts appearing.
        """
        if expected.get("modal_closes"):
            # Wait a moment for modal transition
            await asyncio.sleep(1.5)
            logger.info("UIExecutor: waited for modal close transition")

        if expected.get("toast_appears"):
            # Try to detect a toast/notification
            try:
                toast = self.page.locator("[data-test-id='toast'], .private-alert, [role='alert']")
                await toast.first.wait_for(state="visible", timeout=5000)
                logger.info("UIExecutor: toast notification detected")
            except Exception:
                logger.warning("UIExecutor: expected toast notification but none detected")

    # ── Screenshot Management ──────────────────────────────────────

    async def _take_screenshot(
        self,
        run_dir: Path,
        action_id: str,
        step_id: int,
        phase: str,
        caption: str,
    ) -> ScreenshotRecord:
        """
        Capture a screenshot and return a ScreenshotRecord.
        Saves to: run_dir/screenshots/{action_id}/step_{N}_{phase}.png
        """
        screenshots_dir = run_dir / "screenshots" / action_id
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        filename = f"step_{step_id}_{phase}.png"
        filepath = screenshots_dir / filename

        try:
            await self.page.screenshot(path=str(filepath), full_page=True)
        except Exception as e:
            logger.error(f"UIExecutor: failed to take screenshot: {e}")

        return ScreenshotRecord(
            step_id=step_id,
            filename=f"screenshots/{action_id}/{filename}",
            caption=caption,
            timestamp=datetime.now(),
        )
