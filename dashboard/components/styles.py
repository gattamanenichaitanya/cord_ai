import streamlit as st

def inject_custom_css():
    """Inject custom shared CSS to style the Cord AI dashboard."""
    css = """
    <style>
    /* Styling for primary accent buttons (teal/professional blue) */
    div.stButton > button:first-child {
        background-color: #0f766e !important;
        color: white !important;
        border-radius: 6px !important;
        border: 1px solid #0f766e !important;
        font-weight: 500 !important;
        transition: all 0.2s ease-in-out !important;
    }
    div.stButton > button:first-child:hover {
        background-color: #0d9488 !important;
        border-color: #0d9488 !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1) !important;
    }

    /* Overall workspace layout tweaks */
    /* Keep stHeader itself visible (not display:none) since it also houses the
       sidebar re-expand control when the sidebar is collapsed; only hide the
       Deploy/menu chrome we don't want. */
    header[data-testid="stHeader"] {
        background: transparent !important;
        box-shadow: none !important;
    }
    [data-testid="stToolbarActions"],
    [data-testid="stAppDeployButton"],
    [data-testid="stMainMenu"] {
        display: none !important;
    }

    .stApp {
        overflow: hidden !important;
    }
    .block-container {
        padding-top: 0rem !important;
        padding-bottom: 0 !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-height: 100vh !important;
        overflow: hidden !important;
    }

    /* Distinct Sidebar/Chat column section header styling */
    .chat-header {
        font-size: 1.1rem;
        font-weight: 600;
        color: #1f2937;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid #e5e7eb;
    }

    /* Canvas workspace styling to make it feel like an IDE panel */
    .canvas-container {
        background-color: #fcfcfd !important;
        border: 1px solid #e5e7eb !important;
        border-radius: 12px !important;
        padding: 24px !important;
        min-height: 80vh !important;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05) !important;
    }

    /* User chat bubble styling */
    .chat-bubble-user {
        background-color: #0f766e !important;
        color: white !important;
        border-radius: 16px 16px 0px 16px !important;
        padding: 10px 16px !important;
        margin-bottom: 24px !important;
        margin-left: auto !important;
        max-width: 85% !important;
        font-size: 0.95rem !important;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05) !important;
        width: fit-content;
    }

    /* Assistant chat text styling (no bubble, plain text) */
    .chat-bubble-assistant {
        color: #374151 !important;
        margin-bottom: 24px !important;
        margin-right: 15% !important;
        font-size: 0.95rem !important;
        line-height: 1.5 !important;
    }

    /* Force chat input to span 100% of column width to fix off-center alignment */
    [data-testid="stChatInput"] {
        width: 100% !important;
        max-width: 100% !important;
    }

    /* Chain flex sizing from the sidebar's scroll container down to its vertical
       block so the content fills the available height exactly (no overflow/scrollbar)
       instead of being forced to a fixed viewport-based height. */
    [data-testid="stSidebarContent"] {
        display: flex !important;
        flex-direction: column !important;
        height: 100% !important;
        overflow: hidden !important;
    }
    [data-testid="stSidebarUserContent"] {
        display: flex !important;
        flex-direction: column !important;
        flex: 1 !important;
        min-height: 0 !important;
    }
    /* Streamlit wraps stVerticalBlock in an unlabeled div — include it in the flex chain too */
    [data-testid="stSidebarUserContent"] > div {
        display: flex !important;
        flex-direction: column !important;
        flex: 1 !important;
        min-height: 0 !important;
    }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        display: flex !important;
        flex-direction: column !important;
        flex: 1 !important;
        min-height: 0 !important;
    }

    /* Push the wrapper div containing the user profile down to the bottom of the sidebar */
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div:has(.sidebar-user-profile) {
        margin-top: auto !important;
    }

    /* When the sidebar is collapsed, its floating re-expand chevron sits fixed at the
       top-left of the header and overlaps the chat topbar's leading "CordAI" text.
       Shift the whole main content area right (not just the topbar) so the topbar,
       chat column, and canvas column all stay aligned with each other. */
    [data-testid="stSidebar"][aria-expanded="false"] ~ div .block-container {
        padding-left: calc(2rem + 40px) !important;
    }

    /* User profile stays at its natural size */
    .sidebar-user-profile {
        width: 100% !important;
        box-sizing: border-box !important;
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
