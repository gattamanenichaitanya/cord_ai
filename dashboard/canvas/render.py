import streamlit as st
from .welcome import render_welcome
from .requirements_view import render_requirements
from .plan_view import render_plan
from .execution_view import render_execution
from .planning_progress_view import render_planning_progress

def render_artifact_selector():
    """Renders the non-linear selector bar (pill buttons) above the canvas views."""
    requirements = st.session_state.get("requirements")
    if not requirements:
        return
        
    focus = st.session_state.get("canvas_focus", "welcome")
    plans = st.session_state.get("plans", {})
    
    # Tab list starting with "Requirements", followed by planned reqs
    tabs_data = ["Requirements"] + [f"{req_id} \u25b8" for req_id in plans.keys()]
    
    # Left-align tabs by creating narrow columns followed by a large remainder column
    col_widths = [1.5] * len(tabs_data) + [6.0]
    cols = st.columns(col_widths)
    
    for idx, tab_label in enumerate(tabs_data):
        with cols[idx]:
            # Determine active status and routing target
            if tab_label == "Requirements":
                is_active = (focus == "requirements")
                target_focus = "requirements"
            else:
                req_id = tab_label.split()[0]
                is_active = (focus == f"plan:{req_id}")
                target_focus = f"plan:{req_id}"
                
            btn_type = "primary" if is_active else "secondary"
            if st.button(tab_label, key=f"tab_btn_{tab_label}", type=btn_type):
                st.session_state.canvas_focus = target_focus
                st.rerun()
                
    st.markdown("<hr style='margin: 10px 0 18px 0; border: 0; border-top: 2px solid #e5e7eb;'/>", unsafe_allow_html=True)

def render_canvas():
    """
    Renders the appropriate screen within the Canvas side of the column layout.
    """
    # Show a spinner overlay when the agent is processing
    is_processing = st.session_state.get("is_processing", False)
    pending = st.session_state.get("pending_user_message")
    if is_processing or pending:
        with st.spinner("CordAI is working on it..."):
            st.empty()
        return
    
    # Determine which screen to render based on session state focus
    focus = st.session_state.get("canvas_focus", "welcome")
    
    # 1. Render selector tabs if we are not on the welcome or transient views
    if focus not in ("welcome", "planning"):
        render_artifact_selector()
    
    # 2. Dispatch views
    if focus == "welcome":
        render_welcome()
    elif focus == "planning":
        render_planning_progress()
    elif focus == "requirements":
        render_requirements()
    elif focus.startswith("plan:"):
        req_id = focus.split(":", 1)[1]
        render_plan(req_id)
    elif focus == "execution":
        render_execution()
    else:
        st.error(f"Canvas focus state '{focus}' is not recognized.")
