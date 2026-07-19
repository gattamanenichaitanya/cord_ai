"""
Central message handler for Cord AI dashboard.

Routing logic:
  - Classifies user intent via Claude
  - Dispatches to appropriate handler function
  - Manages is_processing state and pending_user_message across reruns
"""
import streamlit as st
from pathlib import Path
from datetime import datetime

from dashboard.state import add_chat_message, set_canvas_focus, store_plan, get_plan
from dashboard.chat.intent_classifier import classify_intent, Intent


# ─────────────────────────────────────────────
# Public entry point called by render.py
# ─────────────────────────────────────────────

def handle_user_message(user_message: str):
    """
    Central dispatcher. Called when a new user message arrives.

    Flow (across two reruns):
      Rerun 1 — store pending message, set is_processing=True → rerun
                 (user sees their message + spinner immediately)
      Rerun 2 — detect pending_user_message, run the long operation,
                 clear state → rerun (user sees assistant reply)
    """
    # Store message and trigger rerun so user message appears immediately
    add_chat_message("user", user_message)
    st.session_state.pending_user_message = user_message
    st.rerun()


def process_pending_message():
    """
    Called at the top of render_chat() when a pending message is detected.
    Runs the classification + dispatch, then clears state.
    """
    user_message = st.session_state.pending_user_message

    try:
        # Build context
        context = _build_context()

        # Classify intent via Claude
        classified = classify_intent(
            user_message=user_message,
            context=context,
            client=st.session_state.claude_client
        )

        # Immediately show the acknowledgment
        add_chat_message("assistant", classified.acknowledgment)

        # Dispatch to specific handler
        intent = classified.intent

        if intent == Intent.EXTRACT_REQUIREMENTS:
            handle_extract()

        elif intent == Intent.PLAN_REQUIREMENT:
            handle_plan(classified.requirement_id, classified.requirement_reference)

        elif intent == Intent.SHOW_ARTIFACT:
            handle_show(classified.artifact_target)

        elif intent == Intent.EXPLAIN:
            handle_explain(classified.question or user_message)

        elif intent == Intent.EXECUTE:
            handle_execute_request()

        else:  # UNKNOWN
            add_chat_message(
                "assistant",
                "I'm not sure what you'd like to do. You can ask me to:\n"
                "- **Extract requirements** from the loaded document\n"
                "- **Plan** a specific requirement (e.g. 'plan REQ-004')\n"
                "- **Show** the requirements list or a specific plan\n"
                "- **Explain** any concept or gap\n"
                "- **Execute** when a plan is ready and approved"
            )

    except Exception as e:
        add_chat_message("assistant", f"Something went wrong while processing your request: {e}")

    finally:
        # Always clear pending state
        st.session_state.pending_user_message = None
        st.session_state.is_processing = False
        st.rerun()


# ─────────────────────────────────────────────
# Individual intent handlers
# ─────────────────────────────────────────────

def handle_extract():
    """Run Stage 1 extraction and store requirements."""
    from planning.stages.stage_1_extraction import run_stage_1

    doc = st.session_state.get("document")
    if doc is None:
        add_chat_message("assistant", "No document is loaded yet. Please upload a document first.")
        return

    # Guard: already extracted
    if st.session_state.get("requirements") is not None:
        req_count = len(st.session_state.requirements.requirements)
        add_chat_message(
            "assistant",
            f"Requirements have already been extracted — I found {req_count} of them. "
            "They're visible in the workspace. "
            "Say **'re-extract'** if you'd like to run extraction again."
        )
        set_canvas_focus("requirements")
        return

    try:
        run_dir = Path("runs/dashboard_stage_1")
        output = run_stage_1(doc, st.session_state.claude_client, run_dir)
        st.session_state.requirements = output
        set_canvas_focus("requirements")

        req_count = len(output.requirements)
        titles = [f"- [{r.id}] {r.title}" for r in output.requirements]
        summary = "\n".join(titles)

        add_chat_message(
            "assistant",
            f"Found **{req_count} requirements**. They're now in the workspace:\n\n{summary}\n\n"
            "Ask me to plan any of them — for example: *'plan REQ-001'*"
        )
    except Exception as e:
        add_chat_message("assistant", f"Extraction failed: {e}")


def handle_plan(requirement_id: str | None, requirement_reference: str | None):
    """Run the full Stages 2-6 planning pipeline for a requirement."""
    # ── 1. Resolve requirement ──────────────────────────────────────────────
    requirements_data = st.session_state.get("requirements")
    if not requirements_data:
        add_chat_message(
            "assistant",
            "No requirements have been extracted yet. Try *'extract the requirements'* first."
        )
        return

    req = None

    # Direct ID match
    if requirement_id:
        for r in requirements_data.requirements:
            if r.id == requirement_id:
                req = r
                break
        if not req:
            add_chat_message(
                "assistant",
                f"I couldn't find a requirement with ID **{requirement_id}**. "
                "Check the requirements list and try again."
            )
            return

    # Fuzzy reference match (e.g. "the at-risk one")
    elif requirement_reference:
        ref_lower = requirement_reference.lower()
        matches = [
            r for r in requirements_data.requirements
            if any(word in r.title.lower() for word in ref_lower.split() if len(word) > 3)
        ]
        if len(matches) == 1:
            req = matches[0]
        elif len(matches) > 1:
            options = ", ".join(f"**{m.id}**: {m.title}" for m in matches[:3])
            add_chat_message(
                "assistant",
                f"I found a few possibilities — which one did you mean?\n\n{options}\n\n"
                "Reply with the exact ID, e.g. *'plan REQ-004'*."
            )
            return
        else:
            add_chat_message(
                "assistant",
                f"I couldn't match *'{requirement_reference}'* to any requirement. "
                "Try the exact ID, e.g. *'plan REQ-001'*."
            )
            return
    else:
        add_chat_message(
            "assistant",
            "Which requirement would you like me to plan? Try *'plan REQ-001'* or use the name."
        )
        return

    # ── 2. Cost guard — don't re-plan unless explicitly asked ───────────────
    existing_plan = get_plan(req.id)
    if existing_plan:
        set_canvas_focus(f"plan:{req.id}")
        add_chat_message(
            "assistant",
            f"I already have a plan for **{req.title}** — showing it now. "
            "Say *'re-plan {req.id}'* if you'd like me to run it again."
        )
        return

    # ── 3. Run Stages 2-6 with live stage-by-stage progress ─────────────────
    doc = st.session_state.get("document")
    client = st.session_state.claude_client
    run_dir = Path(f"runs/dashboard_{req.id}_{datetime.now().strftime('%Y%m%dT%H%M%S')}")
    run_dir.mkdir(parents=True, exist_ok=True)

    # Switch canvas to planning progress view
    set_canvas_focus("planning")
    st.session_state.planning_progress = {
        "req_id": req.id,
        "req_title": req.title,
        "stages": [
            {"label": "Stage 2: Mapping to capabilities", "status": "pending"},
            {"label": "Stage 3: Deciding architecture",   "status": "pending"},
            {"label": "Stage 4: Inspecting HubSpot",      "status": "pending"},
            {"label": "Stage 5: Detecting gaps",          "status": "pending"},
            {"label": "Stage 6: Finalising plan",         "status": "pending"},
        ]
    }

    def mark_stage(idx: int, status: str):
        st.session_state.planning_progress["stages"][idx]["status"] = status

    try:
        from planning.stages.stage_2_concept_mapping    import run_stage_2
        from planning.stages.stage_3_architecture_decision import run_stage_3
        from planning.stages.stage_4_state_inspection   import run_stage_4
        from planning.stages.stage_5_gap_detection      import run_stage_5
        from planning.stages.stage_6_plan_finalization  import run_stage_6

        mark_stage(0, "running")
        s2 = run_stage_2(req, client, run_dir)
        mark_stage(0, "done")

        mark_stage(1, "running")
        s3 = run_stage_3(req, s2, client, run_dir)
        mark_stage(1, "done")

        mark_stage(2, "running")
        s4 = run_stage_4(req, s3, run_dir)
        mark_stage(2, "done")
        # Store stage 4 output for the plan view
        if "stage_4_outputs" not in st.session_state:
            st.session_state.stage_4_outputs = {}
        st.session_state.stage_4_outputs[req.id] = s4

        mark_stage(3, "running")
        s5 = run_stage_5(req, s3, s4, client, run_dir)
        mark_stage(3, "done")
        if "stage_5_outputs" not in st.session_state:
            st.session_state.stage_5_outputs = {}
        st.session_state.stage_5_outputs[req.id] = s5

        mark_stage(4, "running")
        doc_path = getattr(doc, "source_path", "unknown")
        pipeline_metadata = {
            "document_title": getattr(doc, "title", "Document"),
            "loaded_at": datetime.now().isoformat()
        }
        plan = run_stage_6(req, s3, s5, client, run_dir, doc_path, pipeline_metadata)
        mark_stage(4, "done")

        # ── 4. Store and switch to plan view ─────────────────────────────────
        store_plan(req.id, plan)
        set_canvas_focus(f"plan:{req.id}")

        gap_count = len(plan.identified_gaps)
        gap_phrase = (
            f"I flagged **{gap_count} thing{'s' if gap_count != 1 else ''} worth reviewing**"
            if gap_count > 0
            else "No blockers were flagged"
        )
        add_chat_message(
            "assistant",
            f"Done. The plan for **{req.title}** is ready. "
            f"{gap_phrase} — take a look, and hit **Approve & Execute** when you're happy."
        )

    except Exception as e:
        # Mark current running stage as error
        for s in st.session_state.planning_progress["stages"]:
            if s["status"] == "running":
                s["status"] = "error"
        set_canvas_focus(f"requirements")
        add_chat_message("assistant", f"Planning failed at one of the stages: {e}")


def handle_show(artifact_target: str | None):
    """Switch canvas focus to the requested artifact."""
    if artifact_target == "requirements" or artifact_target is None:
        if st.session_state.get("requirements") is None:
            add_chat_message(
                "assistant",
                "Requirements haven't been extracted yet. Say **'extract the requirements'** first."
            )
            return
        set_canvas_focus("requirements")
        add_chat_message("assistant", "Switched to the requirements view.")

    else:
        # Treat as a specific requirement ID or plan
        plans = st.session_state.get("plans", {})
        if artifact_target in plans:
            set_canvas_focus(f"plan:{artifact_target}")
            add_chat_message("assistant", f"Showing the plan for **{artifact_target}**.")
        else:
            add_chat_message(
                "assistant",
                f"I don't have an artifact for **{artifact_target}** yet. "
                "Ask me to plan it first."
            )


def handle_explain(question: str):
    """Answer the user's question conversationally using current context."""
    # Build a context summary to inject into the Claude prompt
    context_parts = []

    doc = st.session_state.get("document")
    if doc:
        context_parts.append(f"Loaded document: '{doc.title}' ({doc.section_count} sections)")

    reqs = st.session_state.get("requirements")
    if reqs:
        req_lines = [f"  - [{r.id}] {r.title}: {r.description[:80]}" for r in reqs.requirements]
        context_parts.append("Extracted requirements:\n" + "\n".join(req_lines))

    plans = st.session_state.get("plans", {})
    if plans:
        context_parts.append(f"Plans generated for: {', '.join(plans.keys())}")

    focus = st.session_state.get("canvas_focus", "")
    if focus.startswith("plan:"):
        req_id = focus.split(":", 1)[1]
        focused_plan = plans.get(req_id)
        if focused_plan:
            context_parts.append(f"Currently viewing plan for {req_id} ({focused_plan.requirement_title}).")
            if focused_plan.identified_gaps:
                gaps_str = "\n".join([f"  - [{g.severity.value}] {g.title}: {g.description}" for g in focused_plan.identified_gaps])
                context_parts.append(f"Identified gaps in this plan:\n{gaps_str}")

    context_summary = "\n\n".join(context_parts) if context_parts else "No context loaded yet."

    prompt = (
        f"You are a helpful HubSpot implementation consultant assistant embedded in Cord AI.\n\n"
        f"Current project context:\n{context_summary}\n\n"
        f"The consultant has asked: \"{question}\"\n\n"
        f"Answer clearly and conversationally in 2-4 sentences. "
        f"If the question relates to HubSpot concepts, be specific."
    )

    try:
        answer = st.session_state.claude_client.call_text(prompt, max_tokens=512)
        add_chat_message("assistant", answer)
    except Exception as e:
        add_chat_message("assistant", f"I couldn't generate an explanation right now: {e}")


def handle_execute_request():
    """Nudge user toward the Approve & Execute button."""
    plans = st.session_state.get("plans", {})
    if not plans:
        add_chat_message(
            "assistant",
            "There's no plan ready to execute yet. First, ask me to plan a requirement "
            "(e.g. *'plan REQ-001'*), then review it in the workspace, and hit **Approve & Execute** when ready."
        )
    else:
        add_chat_message(
            "assistant",
            "When you're ready, hit the **'Approve & Execute'** button on the plan in the workspace "
            "— I'll take it from there and run the full automation."
        )


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _build_context() -> dict:
    available_requirements = []
    if st.session_state.get("requirements") is not None:
        available_requirements = [
            {"id": r.id, "title": r.title}
            for r in st.session_state.requirements.requirements
        ]
    return {
        "document_loaded": st.session_state.get("document") is not None,
        "available_requirements": available_requirements,
        "available_plans": list(st.session_state.get("plans", {}).keys()),
        "current_canvas_focus": st.session_state.get("canvas_focus", "welcome")
    }
