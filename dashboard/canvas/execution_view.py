"""
Execution View
==============
Renders the live execution progress when the user clicks "Approve & Execute".

Architecture:
  1. On first render (pending_execution is set), pre-create st.empty() placeholders
     for every action in the plan, then call execute_plan() which blocks.
  2. The StreamlitProgressCallback writes to those placeholders IN-PLACE via
     Streamlit's WebSocket — updates appear live in the browser without a rerun.
  3. Chat narration uses a small set of pre-created st.empty() slots for sparse
     highlight messages (workflow start, healing, completion).
  4. After execute_plan() returns, st.rerun() shows the final completed state.
"""
import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import streamlit as st

from dashboard.state import add_chat_message, set_canvas_focus


# ── Status icons and colors ───────────────────────────────────────────────────

_STATUS_ICONS = {
    "pending":     "○",
    "running":     "▸",
    "success":     "✓",
    "failed":      "✗",
    "skipped":     "–",
    "healing":     "↻",
}

_STATUS_COLORS = {
    "pending":     "#9ca3af",
    "running":     "#2563eb",
    "success":     "#10b981",
    "failed":      "#ef4444",
    "skipped":     "#9ca3af",
    "healing":     "#f59e0b",
}

_METHOD_COLORS = {
    "API": ("#065f46", "#d1fae5"),   # text, bg
    "UI":  ("#1e3a8a", "#dbeafe"),
}


def _method_badge(method: str) -> str:
    fg, bg = _METHOD_COLORS.get(method, ("#374151", "#f3f4f6"))
    return (
        f"<span style='background:{bg}; color:{fg}; font-size:0.7rem; "
        f"font-weight:700; padding:2px 7px; border-radius:10px; "
        f"letter-spacing:0.05em;'>{method}</span>"
    )


def _action_html(
    icon: str,
    icon_color: str,
    description: str,
    method: str,
    detail: str = "",
    duration: str = "",
) -> str:
    badge = _method_badge(method)
    dur_html = (
        f"<span style='color:#9ca3af; font-size:0.8rem; margin-left:8px;'>{duration}</span>"
        if duration else ""
    )
    detail_html = (
        f"<div style='color:#6b7280; font-size:0.82rem; margin-top:4px; "
        f"padding-left:28px; line-height:1.4;'>{detail}</div>"
        if detail else ""
    )
    return (
        f"<div style='padding:12px 0; border-bottom:1px solid #f3f4f6;'>"
        f"  <div style='display:flex; align-items:center; gap:10px;'>"
        f"    <span style='color:{icon_color}; font-weight:700; font-size:1rem; width:18px;'>{icon}</span>"
        f"    {badge}"
        f"    <span style='color:#111827; font-weight:500; font-size:0.92rem;'>{description}</span>"
        f"    {dur_html}"
        f"  </div>"
        f"  {detail_html}"
        f"</div>"
    )


# ── Progress callback ─────────────────────────────────────────────────────────

class StreamlitProgressCallback:
    """
    Writes live execution updates to pre-created st.empty() containers.
    Also writes sparse chat narration to chat_slots.

    All methods are called synchronously from the executor thread,
    which is the same thread as Streamlit's script runner — so writing
    to st.empty() containers is safe and renders immediately.
    """

    def __init__(
        self,
        action_placeholders: Dict[str, Any],   # action_id → st.empty()
        summary_placeholder: Any,               # st.empty() for the bottom summary
        chat_slots: List[Any],                  # list of st.empty() for narration
        plan_actions: list,                     # ordered list of PlanAction objects
        action_methods: Dict[str, str],         # action_id → "API" | "UI"
    ):
        self._slots = action_placeholders
        self._summary = summary_placeholder
        self._chat_slots = chat_slots
        self._chat_idx = 0
        self._plan_actions = {a.action_id: a for a in plan_actions}
        self._methods = action_methods

        # Live tracking state
        self._action_states: Dict[str, dict] = {
            a.action_id: {"status": "pending", "detail": "", "duration": ""}
            for a in plan_actions
        }
        self._current_step_counts: Dict[str, int] = {}   # action_id → total steps seen
        self._total_steps: Dict[str, int] = {}            # populated from operation entry

        self._start_times: Dict[str, float] = {}
        self._plan_start = time.time()

    def _write_action(self, action_id: str):
        """Re-render the placeholder for one action using current state."""
        slot = self._slots.get(action_id)
        if not slot:
            return
        state = self._action_states[action_id]
        action = self._plan_actions[action_id]
        method = self._methods.get(action_id, "")

        icon = _STATUS_ICONS.get(state["status"], "○")
        color = _STATUS_COLORS.get(state["status"], "#9ca3af")

        slot.markdown(
            _action_html(
                icon=icon,
                icon_color=color,
                description=action.description[:80] + ("…" if len(action.description) > 80 else ""),
                method=method,
                detail=state["detail"],
                duration=state["duration"],
            ),
            unsafe_allow_html=True,
        )

    def _narrate(self, message: str):
        """Append a sparse narration message to the next available chat slot."""
        if self._chat_idx < len(self._chat_slots):
            self._chat_slots[self._chat_idx].markdown(
                f"<div class='chat-bubble-assistant'>{message}</div>",
                unsafe_allow_html=True,
            )
            self._chat_idx += 1
        # Also persist to chat_history so it survives rerun
        add_chat_message("assistant", message)

    # ── Callback interface ────────────────────────────────────────────────────

    def on_action_start(self, action_id: str, description: str, method: str):
        self._methods[action_id] = method
        self._start_times[action_id] = time.time()
        self._action_states[action_id]["status"] = "running"
        self._action_states[action_id]["detail"] = "Starting…"
        self._write_action(action_id)

        # Narrate only for UI (multi-step) actions — the interesting ones
        if method == "UI":
            self._narrate("Building this in the browser now — watch the window on the right. ↗")

    def on_step_start(self, action_id: str, step_id: int, intent: str):
        count = self._current_step_counts.get(action_id, 0) + 1
        self._current_step_counts[action_id] = count
        self._action_states[action_id]["status"] = "running"
        self._action_states[action_id]["detail"] = (
            f"▸ Step {count}: {intent[:60]}{'…' if len(intent) > 60 else ''}"
        )
        self._write_action(action_id)

    def on_step_complete(self, action_id: str, step_id: int, intent: str, status):
        # Keep detail showing the last completed step
        status_val = status.value if hasattr(status, "value") else str(status)
        if status_val == "success":
            self._action_states[action_id]["detail"] = (
                f"✓ {intent[:60]}{'…' if len(intent) > 60 else ''}"
            )
        elif status_val == "failed":
            self._action_states[action_id]["detail"] = (
                f"✗ {intent[:60]}{'…' if len(intent) > 60 else ''}"
            )
        self._write_action(action_id)

    def on_healing(self, action_id: str, step_id: int, message: str):
        self._action_states[action_id]["status"] = "healing"
        self._action_states[action_id]["detail"] = f"↻ {message}"
        self._write_action(action_id)
        # Narrate healing — the demo moment
        self._narrate(
            "The UI wasn't where I expected — using vision to locate it. Recovering…"
        )

    def on_action_complete(self, action_id: str, status, duration: float):
        status_val = status.value if hasattr(status, "value") else str(status)
        elapsed = f"{duration:.1f}s"
        action = self._plan_actions.get(action_id)
        short_desc = action.description[:50] + "…" if action and len(action.description) > 50 else (action.description if action else action_id)

        if status_val == "success":
            self._action_states[action_id]["status"] = "success"
            self._action_states[action_id]["detail"] = ""
            self._action_states[action_id]["duration"] = elapsed
        else:
            self._action_states[action_id]["status"] = "failed"
            self._action_states[action_id]["duration"] = elapsed

        self._write_action(action_id)

    def on_plan_complete(self, report):
        status_val = report.overall_status.value
        total = report.total_duration_seconds or 0.0
        successes = sum(1 for r in report.action_results if r.status.value == "success")
        total_actions = len(report.action_results)

        # Count properties vs workflows
        num_properties = sum(1 for r in report.action_results if r.status.value == "success" and "property" in r.operation_id.lower())
        num_workflows = sum(1 for r in report.action_results if r.status.value == "success" and "workflow" in r.operation_id.lower())

        if "executed_plans" not in st.session_state:
            st.session_state.executed_plans = set()

        if status_val == "success":
            st.session_state.executed_plans.add(report.plan_id)
            summary_color = "#10b981"
            summary_icon = "✓"
            summary_text = (
                f"Created {num_properties} properties and {num_workflows} workflows in {total:.0f}s"
            )
            self._summary.markdown(
                f"<div style='margin-top:24px; padding:16px; background:#f0fdf4; "
                f"border:1px solid #bbf7d0; border-radius:8px; color:{summary_color}; "
                f"font-weight:600; font-size:1rem;'>"
                f"{summary_icon} {summary_text}"
                f"</div>",
                unsafe_allow_html=True,
            )
            self._narrate(
                f"Done. Created {num_properties} properties and {num_workflows} workflows in {total:.0f}s. "
                f"Everything is now live in HubSpot.\n\n"
                f"Want to plan another requirement? Just ask."
            )
        else:
            failed = [
                r for r in report.action_results if r.status.value == "failed"
            ]
            fail_names = ", ".join(r.action_id for r in failed[:3])
            summary_text = (
                f"Execution stopped after {total:.0f}s. "
                f"{successes} of {total_actions} actions succeeded. "
                f"Failed: {fail_names}."
            )
            self._summary.markdown(
                f"<div style='margin-top:24px; padding:16px; background:#fef2f2; "
                f"border:1px solid #fecaca; border-radius:8px; color:#ef4444; "
                f"font-weight:600; font-size:1rem;'>"
                f"✗ {summary_text}"
                f"</div>",
                unsafe_allow_html=True,
            )
            self._narrate(
                f"Something went wrong partway through. {successes} of {total_actions} "
                f"actions completed. The failed step details are in the canvas."
            )

        # Store report and mark execution done
        st.session_state.execution_report = report
        st.session_state.pending_execution = None


# ── Main view renderer ────────────────────────────────────────────────────────

def render_execution():
    """
    Renders the live execution progress view.

    Two modes:
      A. Active execution: pending_execution is set — run the orchestrator.
      B. Completed view:   pending_execution is None, execution_report is set.
    """
    report = st.session_state.get("execution_report")
    pending_req_id = st.session_state.get("pending_execution")

    # ── Mode B: Already completed ─────────────────────────────────────────────
    if not pending_req_id and report:
        _render_completed(report)
        return

    # ── Mode A: Active execution ──────────────────────────────────────────────
    if not pending_req_id:
        st.info("No execution in progress. Approve a plan to start.")
        return

    plan = st.session_state.get("plans", {}).get(pending_req_id)
    if not plan:
        st.error(f"Plan for {pending_req_id} not found in session. Please go back and reload.")
        return

    _run_execution(plan, pending_req_id)


def _render_completed(report):
    """Show a static completed/failed summary after execution finishes."""
    import os
    status = report.overall_status.value
    successes = sum(1 for r in report.action_results if r.status.value == "success")
    total = len(report.action_results)
    duration = report.total_duration_seconds or 0.0

    plans = st.session_state.get("plans", {})
    plan = None
    for p in plans.values():
        if p.plan_id == report.plan_id:
            plan = p
            break

    # Helper to clean action descriptions
    def get_display_name(action_id, operation_id):
        desc = action_id
        if plan:
            for a in plan.actions:
                if a.action_id == action_id:
                    desc = a.description
                    break
        
        # Clean suffixes like " on [UI]", " [UI]", " [API]"
        for suffix in [" [UI]", " [API]", " on [UI]", " on [API]", " on UI", " on API"]:
            if desc.endswith(suffix):
                desc = desc[:-len(suffix)]
        
        # Format properties vs workflows
        if "property" in operation_id.lower():
            desc = desc.replace("Create ", "").replace(" number property", " property").replace(" dropdown property", " property").replace(" custom property", " property")
            if "property" not in desc.lower():
                desc += " property"
        elif "workflow" in operation_id.lower():
            desc = desc.replace("Build and publish ", "").replace("Create ", "")
            if "workflow" not in desc.lower():
                desc += " workflow"
            desc += " (ON)"
        return desc

    # Count properties vs workflows
    num_properties = sum(1 for r in report.action_results if r.status.value == "success" and "property" in r.operation_id.lower())
    num_workflows = sum(1 for r in report.action_results if r.status.value == "success" and "workflow" in r.operation_id.lower())

    if status == "success":
        st.markdown(
            f"<h2 style='color:#065f46; font-weight:700; margin-bottom:4px;'>✓ Implementation Complete</h2>",
            unsafe_allow_html=True
        )
        st.markdown(
            f"<div style='font-size:1.1rem; color:#374151; margin-bottom:20px; font-weight:500;'>"
            f"Created {num_properties} properties and {num_workflows} workflows in {duration:.0f}s."
            f"</div>",
            unsafe_allow_html=True
        )

        st.markdown("<div style='margin-bottom:12px; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:#6b7280; font-size:0.75rem;'>What was built:</div>", unsafe_allow_html=True)
        for r in report.action_results:
            if r.status.value == "success":
                display_name = get_display_name(r.action_id, r.operation_id)
                st.markdown(
                    f"<div style='display:flex; align-items:center; gap:8px; margin-bottom:8px; font-size:1rem; color:#111827; font-weight:500;'>"
                    f"<span style='color:#10b981; font-weight:bold;'>\u2713</span> {display_name}"
                    f"</div>",
                    unsafe_allow_html=True
                )

        portal_id = os.environ.get("HUBSPOT_PORTAL_ID", "")
        host_subdomain = os.environ.get("HUBSPOT_HOST", "app-na2")
        verify_url = f"https://{host_subdomain}.hubspot.com/workflows/{portal_id}"
        
        st.markdown(
            f"<a href='{verify_url}' target='_blank' style='"
            f"display:inline-block; margin-top:20px; margin-bottom:24px; padding:10px 20px; "
            f"background:#2563eb; color:white; font-weight:600; text-decoration:none; "
            f"border-radius:6px; font-size:0.9rem; box-shadow: 0 1px 2px 0 rgba(0,0,0,0.05);'>"
            f"Verify in HubSpot \u2197</a>",
            unsafe_allow_html=True
        )

    else:
        st.markdown(
            f"<h2 style='color:#ef4444; font-weight:700; margin-bottom:4px;'>✗ Implementation Stopped</h2>",
            unsafe_allow_html=True
        )
        st.markdown(
            f"<div style='font-size:1.1rem; color:#374151; margin-bottom:20px; font-weight:500;'>"
            f"{successes} of {total} actions completed before failure. Elapsed: {duration:.0f}s."
            f"</div>",
            unsafe_allow_html=True
        )

        st.markdown("<div style='margin-bottom:12px; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:#6b7280; font-size:0.75rem;'>ACTIONS</div>", unsafe_allow_html=True)
        for result in report.action_results:
            rv = result.status.value
            icon = _STATUS_ICONS.get(rv, "○")
            color = _STATUS_COLORS.get(rv, "#9ca3af")
            dur = f"{result.duration_seconds:.1f}s" if result.duration_seconds else ""
            method = result.method_used.value.upper() if result.method_used else ""
            short = result.action_id

            desc = short
            if plan:
                for a in plan.actions:
                    if a.action_id == result.action_id:
                        desc = a.description
                        break

            detail = ""
            if rv == "failed" and result.error_message:
                raw = result.error_message or ""
                detail = raw[:200] + ("…" if len(raw) > 200 else "")
            elif rv == "skipped":
                detail = "Skipped dynamically (missing operation or dependency skipped)"

            st.markdown(
                _action_html(
                    icon=icon,
                    icon_color=color,
                    description=desc,
                    method=method,
                    detail=detail,
                    duration=dur,
                ),
                unsafe_allow_html=True,
            )

    if st.button("← Back to Plan", key="exec_back"):
        st.session_state.execution_report = None
        # Find which req had the plan
        plan_id = report.plan_id
        for req_id, plan in st.session_state.get("plans", {}).items():
            if plan.plan_id == plan_id:
                set_canvas_focus(f"plan:{req_id}")
                break
        st.rerun()


def _run_execution(plan, req_id: str):
    """
    Pre-create placeholders, wire up the callback, run execute_plan(), then rerun.
    """
    from execution.orchestrator import execute_plan

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        f"<h2 style='margin-bottom:4px; font-weight:700; color:#111827;'>"
        f"Executing: {plan.requirement_title}</h2>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px; "
        "padding:10px 16px; margin-bottom:24px; color:#1e3a8a; font-size:0.9rem; "
        "font-weight:500;'>"
        "▸ &nbsp;Watch the browser window that just opened on the right of your screen."
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='font-size:0.75rem; font-weight:700; text-transform:uppercase; "
        "letter-spacing:0.05em; color:#6b7280; margin-bottom:12px;'>ACTIONS</div>",
        unsafe_allow_html=True,
    )

    # ── Pre-determine methods (sync: read operation files) ────────────────────
    import json
    from pathlib import Path
    from execution.executors.api_executor import APIExecutor

    api_executor = APIExecutor()
    action_methods: Dict[str, str] = {}

    for action in plan.actions:
        op_file = Path("graph/hubspot/operations") / f"{action.operation_id.split('.')[-1]}.json"
        method = "UI"  # default
        if op_file.exists():
            try:
                with open(op_file, "r", encoding="utf-8") as f:
                    op_data = json.load(f)
                # Check API capability synchronously (can_execute is async, use a quick heuristic)
                methods = op_data.get("execution_methods", [])
                method_names = [m.get("method") for m in methods]
                if "api" in method_names:
                    method = "API"
                elif "ui" in method_names:
                    method = "UI"
            except Exception:
                pass
        action_methods[action.action_id] = method

    # ── Pre-create one st.empty() per action ──────────────────────────────────
    action_placeholders: Dict[str, Any] = {}
    for action in plan.actions:
        ph = st.empty()
        action_placeholders[action.action_id] = ph
        method = action_methods.get(action.action_id, "")
        # Render initial pending state
        ph.markdown(
            _action_html(
                icon=_STATUS_ICONS["pending"],
                icon_color=_STATUS_COLORS["pending"],
                description=action.description[:80] + ("…" if len(action.description) > 80 else ""),
                method=method,
                detail="",
                duration="",
            ),
            unsafe_allow_html=True,
        )

    # Summary placeholder at the bottom
    summary_ph = st.empty()

    # ── Pre-create chat narration slots (3 slots: workflow start, healing, done) ──
    # These live in the canvas column since we can't write to the chat column
    # from here — but they'll also be persisted to chat_history for display after rerun.
    # We add them after a divider so they feel distinct from the checklist.
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    narration_header = st.empty()
    chat_slots = [st.empty() for _ in range(4)]  # up to 4 narration events

    # ── Build callback ────────────────────────────────────────────────────────
    callback = StreamlitProgressCallback(
        action_placeholders=action_placeholders,
        summary_placeholder=summary_ph,
        chat_slots=chat_slots,
        plan_actions=plan.actions,
        action_methods=action_methods,
    )

    # ── Run the orchestrator (blocking) ──────────────────────────────────────
    try:
        st.session_state.is_processing = True
        asyncio.run(
            execute_plan(
                plan_path_or_obj=plan,
                progress_callback=callback,
                demo_mode=True,
                dry_run=False,
            )
        )
    except Exception as e:
        # Never surface raw tracebacks to the user
        summary_ph.markdown(
            f"<div style='margin-top:24px; padding:16px; background:#fef2f2; "
            f"border:1px solid #fecaca; border-radius:8px; color:#ef4444; "
            f"font-weight:600;'>✗ Execution stopped due to a connection or configuration issue.</div>",
            unsafe_allow_html=True,
        )
        add_chat_message(
            "assistant",
            "The execution encountered an issue partway through. Let's try executing again when you're ready."
        )
        st.session_state.pending_execution = None
    finally:
        st.session_state.is_processing = False

    # ── Rerun to settle into completed state ──────────────────────────────────
    st.rerun()
