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
