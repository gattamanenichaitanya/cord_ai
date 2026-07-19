"""
Canvas view shown while the planning pipeline (Stages 2-6) is running.
Displays live stage-by-stage progress pulled from session_state.planning_progress.
"""
import streamlit as st


def render_planning_progress():
    """Renders the live stage progress panel during plan generation."""
    progress = st.session_state.get("planning_progress")
    if not progress:
        st.info("Planning in progress... please wait.")
        return

    req_id = progress.get("req_id", "")
    req_title = progress.get("req_title", "")
    stages = progress.get("stages", [])

    st.markdown(f"## Planning: {req_id}")
    st.markdown(f"*{req_title}*")
    st.markdown("<br/>", unsafe_allow_html=True)

    STATUS_ICONS = {
        "pending": "⏳",
        "running": "🔄",
        "done":    "✅",
        "error":   "❌",
    }
    STATUS_COLORS = {
        "pending": "#6b7280",  # grey
        "running": "#f59e0b",  # amber
        "done":    "#10b981",  # green
        "error":   "#ef4444",  # red
    }

    for stage in stages:
        label = stage["label"]
        status = stage["status"]
        icon = STATUS_ICONS.get(status, "⏳")
        color = STATUS_COLORS.get(status, "#6b7280")

        running_anim = " *(working...)*" if status == "running" else ""

        st.markdown(
            f"<div style='display:flex; align-items:center; gap:12px; padding:10px 14px; "
            f"margin-bottom:8px; border-radius:8px; background:#f9fafb; "
            f"border-left: 4px solid {color};'>"
            f"<span style='font-size:1.3rem;'>{icon}</span>"
            f"<span style='color:{color}; font-weight:500;'>{label}{running_anim}</span>"
            f"</div>",
            unsafe_allow_html=True
        )

    # If all done, show completion message
    all_done = all(s["status"] == "done" for s in stages)
    any_error = any(s["status"] == "error" for s in stages)
    if all_done:
        st.success("All stages complete! Switching to the plan view...")
    elif any_error:
        st.error("A stage encountered an error. Check the chat for details.")
    else:
        st.info("Pipeline is running — this takes around 20–30 seconds. Hang tight!")
