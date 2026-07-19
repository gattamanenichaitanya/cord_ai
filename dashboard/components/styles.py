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
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
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
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
