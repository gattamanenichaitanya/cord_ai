import streamlit as st

def init_state():
    """Initialize the session state with default variables if they don't exist."""
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    
    if "document" not in st.session_state:
        st.session_state.document = None
        
    if "requirements" not in st.session_state:
        st.session_state.requirements = None
        
    if "plans" not in st.session_state:
        st.session_state.plans = {}
        
    if "canvas_focus" not in st.session_state:
        st.session_state.canvas_focus = "welcome"
        
    if "execution_report" not in st.session_state:
        st.session_state.execution_report = None
        
    if "is_processing" not in st.session_state:
        st.session_state.is_processing = False
        
    if "pending_execution" not in st.session_state:
        st.session_state.pending_execution = None

    if "pending_user_message" not in st.session_state:
        st.session_state.pending_user_message = None

    if "planning_progress" not in st.session_state:
        st.session_state.planning_progress = None

    if "stage_4_outputs" not in st.session_state:
        st.session_state.stage_4_outputs = {}

    if "stage_5_outputs" not in st.session_state:
        st.session_state.stage_5_outputs = {}

    if "claude_client" not in st.session_state:
        from planning.claude_client import ClaudeClient
        st.session_state.claude_client = ClaudeClient()
        
    if "recent_chats" not in st.session_state:
        st.session_state.recent_chats = [
            "Ticket routing workflow",
            "Globex renewal setup",
            "Initech data model"
        ]
        
    if "current_chat_title" not in st.session_state:
        st.session_state.current_chat_title = None

def add_chat_message(role: str, content: str):
    """Add a message to the chat history."""
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    st.session_state.chat_history.append({"role": role, "content": content})

def set_canvas_focus(focus_str: str):
    """Set the focus of the canvas panel."""
    st.session_state.canvas_focus = focus_str

def store_plan(req_id: str, plan):
    """Store an implementation plan for a requirement ID."""
    if "plans" not in st.session_state:
        st.session_state.plans = {}
    st.session_state.plans[req_id] = plan

def get_plan(req_id: str):
    """Retrieve the implementation plan for a requirement ID."""
    if "plans" not in st.session_state:
        st.session_state.plans = {}
    return st.session_state.plans.get(req_id)

def has_requirements() -> bool:
    """Return True if requirements have been loaded or generated."""
    return st.session_state.get("requirements") is not None
