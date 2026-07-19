import streamlit as st
from dashboard.state import set_canvas_focus
from dashboard.chat.handlers import handle_user_message

def render_requirements():
    """Renders the requirements list parsed from uploaded documents (Stage 1)."""
    requirements_data = st.session_state.get("requirements")
    doc = st.session_state.get("document")
    
    if not requirements_data:
        st.warning("No requirements extracted yet. Please upload a document and ask to extract requirements.")
        return
        
    doc_title = doc.title if doc else "Document"
    st.markdown(f"<h3 style='margin-bottom: 8px; color: #111827;'>Requirements — {doc_title}</h3>", unsafe_allow_html=True)
    
    if requirements_data.document_summary:
        st.markdown(f"<div style='font-size: 0.9rem; color: #4b5563; font-style: italic; margin-bottom: 12px;'>{requirements_data.document_summary}</div>", unsafe_allow_html=True)
    
    plans = st.session_state.get("plans", {})
    
    # Display each requirement as a clean card
    for req in requirements_data.requirements:
        req_type = req.requirement_type.value if hasattr(req.requirement_type, "value") else str(req.requirement_type)
        
        # Color codes: workflow=blue, property=green, pipeline=orange, dashboard=purple
        color_map = {
            "workflow": "#dbeafe",  # light blue
            "property_configuration": "#dcfce7",  # light green
            "pipeline": "#ffedd5",  # light orange
            "dashboard": "#f3e8ff",  # light purple
            "object_configuration": "#fee2e2"  # light red
        }
        text_color_map = {
            "workflow": "#1e40af",
            "property_configuration": "#166534",
            "pipeline": "#9a3412",
            "dashboard": "#6b21a8",
            "object_configuration": "#991b1b"
        }
        
        bg_color = color_map.get(req_type, "#f3f4f6")
        text_color = text_color_map.get(req_type, "#374151")
        
        has_plan = req.id in plans
        planned_indicator = " <span style='color: #10b981; font-weight: 600; font-size: 0.9rem;'>✓ planned</span>" if has_plan else ""
        
        # Row container for card
        with st.container():
            col1, col2 = st.columns([4, 1])
            with col1:
                # Title & Planned Checkmark
                st.markdown(
                    f"<div style='margin-bottom: 2px; font-weight: 600; color: #111827; font-size: 0.95rem;'>{req.id}: {req.title}{planned_indicator}</div>", 
                    unsafe_allow_html=True
                )
                # Type pill & Section indicator
                st.markdown(
                    f"<span style='background-color: {bg_color}; color: {text_color}; padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: 500;'>{req_type}</span>"
                    f" <span style='color: #6b7280; font-size: 0.75rem; margin-left: 8px;'>Section: {req.source_section}</span>",
                    unsafe_allow_html=True
                )
            with col2:
                # Plan this or View Plan action button
                btn_label = "View Plan" if has_plan else "Plan"
                # Offset alignment spacing
                st.markdown("<div style='margin-top: 0px;'></div>", unsafe_allow_html=True)
                if st.button(btn_label, key=f"plan_btn_{req.id}"):
                    if has_plan:
                        set_canvas_focus(f"plan:{req.id}")
                        st.rerun()
                    else:
                        handle_user_message(f"Plan {req.id}")
            
            # Details Expander
            with st.expander("Details & Excerpt", expanded=False):
                st.markdown(f"**Description:**  \n{req.description}")
                st.markdown(f"**Source Excerpt:**  \n```text\n{req.source_excerpt}\n```")
                if req.dependencies:
                    st.markdown(f"**Dependencies:** {', '.join(req.dependencies)}")
            
            st.markdown("<hr style='margin: 4px 0 8px 0; border: 0; border-top: 1px solid #f3f4f6;'/>", unsafe_allow_html=True)
