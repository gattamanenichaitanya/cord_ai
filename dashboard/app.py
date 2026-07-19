import logging
# Suppress Streamlit local_sources_watcher errors when scanning transformers
logging.getLogger("streamlit.watcher.local_sources_watcher").setLevel(logging.ERROR)

import streamlit as st
from dashboard.state import init_state
from dashboard.components.styles import inject_custom_css
from dashboard.chat.render import render_chat
from dashboard.canvas.render import render_canvas

# 1. Page Configuration
st.set_page_config(
    page_title="CordAI",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. State Initialization
init_state()

# 3. Inject CSS Stylesheet
inject_custom_css()

# 4. Render Sidebar
with st.sidebar:
    st.markdown("<div style='display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 1.2rem; color: #111827; margin-bottom: 24px;'><span style='background: #2563eb; color: white; border-radius: 6px; padding: 2px 6px;'>✨</span> CordAI</div>", unsafe_allow_html=True)
    if st.button("➕ New chat", use_container_width=True):
        st.session_state.document = None
        st.session_state.chat_history = []
        st.session_state.requirements = None
        st.session_state.plans = {}
        st.session_state.canvas_focus = "welcome"
        st.rerun()
        
    st.markdown("<div style='font-size: 0.75rem; font-weight: 700; color: #9ca3af; margin-top: 24px; margin-bottom: 12px; text-transform: uppercase;'>RECENT</div>", unsafe_allow_html=True)
    st.markdown("<div style='color: #4b5563; font-size: 0.9rem; margin-bottom: 12px; padding: 8px; background: #f3f4f6; border-radius: 6px; font-weight: 500;'>Acme Corp implement...</div>", unsafe_allow_html=True)
    st.markdown("<div style='color: #6b7280; font-size: 0.9rem; margin-bottom: 12px; padding: 8px;'>Globex renewal setup</div>", unsafe_allow_html=True)
    st.markdown("<div style='color: #6b7280; font-size: 0.9rem; margin-bottom: 12px; padding: 8px;'>Initech data model</div>", unsafe_allow_html=True)

    st.markdown("<hr style='margin: 20px 0 16px 0; border: 0; border-top: 1px solid #e5e7eb;'/>", unsafe_allow_html=True)
    
    # Connection check (cached to prevent pinging HubSpot on every rerun)
    if "hubspot_connected" not in st.session_state:
        from dashboard.demo_safety import check_hubspot_connection
        st.session_state.hubspot_connected = check_hubspot_connection()
        
    with st.expander("🛠️ Demo Safety & Economics", expanded=False):
        # 1. HubSpot connection indicator
        if st.session_state.hubspot_connected:
            st.markdown("<div style='font-size:0.85rem; color:#10b981; font-weight:600; margin-bottom:12px;'>● HubSpot Connected</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='font-size:0.85rem; color:#ef4444; font-weight:600; margin-bottom:12px;'>○ HubSpot Disconnected</div>", unsafe_allow_html=True)
            
        # 2. Session API cost
        from dashboard.demo_safety import get_session_cost
        cost = get_session_cost()
        st.markdown(
            f"<div style='font-size:0.82rem; color:#4b5563; margin-bottom:16px;'>"
            f"<b>Session cost:</b> ${cost:.2f}<br/>"
            f"<span style='font-size:0.75rem; color:#9ca3af;'>Est. LLM + Vision tokens</span>"
            f"</div>",
            unsafe_allow_html=True
        )
        
        # 3. Reset HubSpot state
        if st.button("Reset HubSpot state", type="secondary", use_container_width=True):
            from dashboard.demo_safety import reset_demo_state
            with st.spinner("Resetting..."):
                res = reset_demo_state()
            deleted_p = len(res["deleted_properties"])
            deleted_w = len(res["deleted_workflows"])
            if deleted_p or deleted_w:
                st.success(f"Cleaned {deleted_p} properties and {deleted_w} workflows!")
            else:
                st.info("Nothing to clean. HubSpot is already reset.")
            # Clear executed state
            st.session_state.executed_plans = set()
            st.session_state.execution_report = None
            st.rerun()

# 5. Main Content Area
if st.session_state.get("document") is None:
    # EMPTY STATE
    st.markdown("<div style='height: 15vh;'></div>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            """
            <div style='text-align: center; margin-bottom: 40px;'>
                <div style='background: #2563eb; color: white; font-size: 2rem; width: 64px; height: 64px; border-radius: 16px; display: inline-flex; align-items: center; justify-content: center; margin-bottom: 16px;'>✨</div>
                <h1 style='font-size: 2rem; font-weight: 600; color: #111827; margin-bottom: 8px;'>CordAI</h1>
                <p style='font-size: 1.1rem; color: #6b7280;'>Your AI implementation partner</p>
                <p style='color: #6b7280; margin-top: 24px; font-size: 0.95rem;'>Attach a design document and I'll read it, plan the implementation, and configure it for you.</p>
            </div>
            """, 
            unsafe_allow_html=True
        )
        
        # Render the chat composer for empty state
        render_chat(is_empty_state=True)
else:
    # ACTIVE CONVERSATION
    st.markdown(
        """
        <div style='margin-bottom: 16px; border-bottom: 1px solid #e5e7eb; padding-bottom: 12px;'>
            <span style='font-weight: 600; color: #111827;'>CordAI</span>
            <span style='color: #9ca3af; margin: 0 8px;'>•</span>
            <span style='color: #6b7280;'>Your AI implementation partner</span>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    chat_col, canvas_col = st.columns([38, 62])

    with chat_col:
        render_chat(is_empty_state=False)

    with canvas_col:
        render_canvas()
