import streamlit as st
from dashboard.state import get_plan, add_chat_message, set_canvas_focus

def render_plan(req_id: str = None):
    """Renders implementation plan details and technical actions."""
    if not req_id:
        st.error("No requirement ID provided to plan view.")
        return
        
    plan = get_plan(req_id)
    if not plan:
        st.info(f"No plan found for {req_id}. Ask me to plan this requirement in the chat.")
        return
        
    # Get extra context if available
    req_type = "Requirement"
    source_section = "Unknown"
    reqs_data = st.session_state.get("requirements")
    if reqs_data:
        for r in reqs_data.requirements:
            if r.id == req_id:
                req_type = r.requirement_type.value.replace("_", " ").title() if hasattr(r.requirement_type, "value") else str(r.requirement_type)
                source_section = r.source_section
                break

    st.markdown(f"<h2 style='margin-bottom: 4px; font-weight: 700; color: #111827;'>Plan: {plan.requirement_title}</h2>", unsafe_allow_html=True)
    st.markdown(f"<div style='color: #6b7280; font-size: 0.95rem; margin-bottom: 32px;'>{req_type} • Source: {source_section}</div>", unsafe_allow_html=True)
    
    # 3. Recommended Approach
    st.markdown("<div style='font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #6b7280; margin-bottom: 8px;'>APPROACH</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-size: 1.05rem; font-weight: 500; color: #374151; margin-bottom: 32px;'>{plan.approach_summary}</div>", unsafe_allow_html=True)
    
    # 4. Gaps / Things to review
    gaps = plan.identified_gaps
    st.markdown(f"<div style='font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #6b7280; margin-bottom: 12px;'>⚠️ BEFORE WE PROCEED — {len(gaps)} THINGS TO REVIEW</div>", unsafe_allow_html=True)
    
    if gaps:
        # Sort gaps: HIGH (0), MEDIUM (1), LOW (2)
        def severity_score(g):
            return {"high": 0, "medium": 1, "low": 2}.get(g.severity.value, 3)
            
        sorted_gaps = sorted(gaps, key=severity_score)
        
        for gap in sorted_gaps:
            color = "#ef4444" if gap.severity.value == "high" else "#f59e0b" if gap.severity.value == "medium" else "#3b82f6"
            bg_color = "#fef2f2" if gap.severity.value == "high" else "#fffbeb" if gap.severity.value == "medium" else "#eff6ff"
            badge = f"<span style='background-color:{color}; color:white; padding: 2px 8px; border-radius: 12px; font-size: 0.7rem; font-weight: 700; text-transform: uppercase;'>{gap.severity.value}</span>"
            
            gotcha_tag = f"<br/><br/><span style='background-color:rgba(0,0,0,0.05); padding: 4px 8px; border-radius: 4px; font-size: 0.75rem; color: #4b5563;'>💡 Based on known HubSpot behavior</span>" if gap.referenced_gotcha else ""
            
            details_html = ""
            if gap.description or gap.suggested_resolution or gotcha_tag:
                details_html = (
                    f"<details style='margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(0,0,0,0.05); color: #4b5563; font-size: 0.9rem;'>"
                    f"<summary style='cursor: pointer; font-weight: 500;'>View Details (Technical)</summary>"
                    f"<div style='margin-top: 8px; line-height: 1.5;'>{gap.description or ''}</div>"
                    f"<div style='margin-top: 8px;'><i>Suggested resolution:</i> {gap.suggested_resolution or ''}</div>"
                    f"{gotcha_tag}"
                    f"</details>"
                )
            
            st.markdown(
                f"<div style='background-color: {bg_color}; border-left: 4px solid {color}; padding: 16px; border-radius: 6px; margin-bottom: 16px; box-shadow: 0 1px 2px rgba(0,0,0,0.02);'>"
                f"<div style='margin-bottom: 6px; display: flex; align-items: center; gap: 10px;'>{badge} <span style='font-weight: 700; font-size: 0.95rem; color: #111827;'>{gap.title}</span></div>"
                f"<div style='color: #374151; line-height: 1.5; font-size: 0.95rem;'>{gap.summary}</div>"
                f"{details_html}"
                f"</div>",
                unsafe_allow_html=True
            )
    else:
        st.markdown("<div style='color: #10b981; font-weight: 500; margin-bottom: 32px;'>No blocking issues or major risks were detected.</div>", unsafe_allow_html=True)
        
    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
    
    # 5. Implementation Steps
    st.markdown("<div style='font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #6b7280; margin-bottom: 12px;'>STEPS</div>", unsafe_allow_html=True)
    
    for i, action in enumerate(plan.actions):
        st.markdown(
            f"<div style='margin-bottom: 12px; display: flex; gap: 12px; align-items: baseline;'>"
            f"<div style='color: #9ca3af; font-weight: 600; font-size: 0.9rem; width: 20px;'>{i+1}.</div>"
            f"<div style='color: #374151; font-weight: 500; font-size: 0.95rem;'>{action.description}</div>"
            f"</div>", 
            unsafe_allow_html=True
        )
                    
    st.markdown("<div style='height: 32px;'></div>", unsafe_allow_html=True)
    
    # 6. Execute Affordance
    # Check if there is already a pending execution or if we are currently processing
    is_executing = st.session_state.get("pending_execution") is not None or st.session_state.get("is_processing", False)
    
    if st.button("🚀 Approve & Execute", type="primary", use_container_width=True, disabled=is_executing):
        st.session_state.pending_execution = req_id
        st.session_state.is_processing = True # set immediately to prevent double click
        add_chat_message("user", f"Approve and execute the {plan.requirement_title} plan")
        add_chat_message("assistant", "Executing now — watch the browser.")
        set_canvas_focus("execution")
        st.rerun()
