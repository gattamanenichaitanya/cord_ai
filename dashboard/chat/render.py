import streamlit as st
from pathlib import Path
from dashboard.state import add_chat_message
from dashboard.chat.handlers import handle_user_message, process_pending_message
from planning.document_loader import load_document


def render_chat(is_empty_state=False):
    """Renders the chat interface. Handles empty state vs active conversation layout."""

    # ── Step 0: Process any pending message ─────────────────────────────────
    if st.session_state.get("pending_user_message") and not st.session_state.get("is_processing", False):
        pass  # handled below

    # ── Step 1: Render Chat History (Only if not empty state) ───────────────
    if not is_empty_state:
        # Document loaded badge in chat flow (based on user reference)
        doc = st.session_state.get("document")
        if doc:
            st.markdown(f"<div style='color: #6b7280; font-size: 0.85rem; margin-bottom: 24px; display: flex; align-items: center; justify-content: center;'><span style='border: 1px solid #e5e7eb; border-radius: 12px; padding: 4px 12px; background: white;'>📄 {doc.title} • {doc.section_count} sections</span></div>", unsafe_allow_html=True)

        chat_container = st.container(height=690, border=False)
        with chat_container:
            for message in st.session_state.chat_history:
                role = message["role"]
                content = message["content"]
                if role == "user":
                    st.markdown(f"<div class='chat-bubble-user'>\n\n{content}\n\n</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='chat-bubble-assistant'>\n\n{content}\n\n</div>", unsafe_allow_html=True)

    # ── Step 2: Processing state / chat input ────────────────────────────────
    is_processing = st.session_state.get("is_processing", False)
    pending = st.session_state.get("pending_user_message")

    if pending:
        st.caption("⏳ CordAI is working...")
        st.chat_input("Message CordAI...", disabled=True, key="disabled_input")
        process_pending_message()

    elif is_processing:
        st.caption("⏳ CordAI is working...")
        st.chat_input("Message CordAI...", disabled=True, key="disabled_input")

    else:
        # File upload logic using st.chat_input(accept_file=True)
        placeholder = "How can I help?" if is_empty_state else "Ask CordAI..."
        prompt = st.chat_input(
            placeholder,
            accept_file=True,
            file_type=["docx", "md", "txt"],
            key="active_input"
        )
        
        if prompt:
            prompt_files = None
            prompt_text = None
            
            if isinstance(prompt, str):
                prompt_text = prompt
            else:
                try:
                    prompt_files = prompt.files
                except AttributeError:
                    prompt_files = prompt.get("files") if hasattr(prompt, "get") else None
                    
                try:
                    prompt_text = prompt.text
                except AttributeError:
                    prompt_text = prompt.get("text") if hasattr(prompt, "get") else None

            # 1. Process file uploads if any
            if prompt_files:
                uploaded_file = prompt_files[0]
                temp_dir = Path("scratch/temp_uploads")
                temp_dir.mkdir(parents=True, exist_ok=True)
                
                # Use the original filename instead of a hardcoded string
                original_filename = uploaded_file.name
                temp_file_path = temp_dir / original_filename
                
                with open(temp_file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                try:
                    doc = load_document(str(temp_file_path))
                    st.session_state.document = doc
                    st.session_state.chat_history = []
                    st.session_state.current_chat_title = doc.title
                    
                    if "recent_chats" not in st.session_state:
                        st.session_state.recent_chats = []
                    # Insert at the beginning, ensuring no duplicates (if desired, or just let it append)
                    if doc.title in st.session_state.recent_chats:
                        st.session_state.recent_chats.remove(doc.title)
                    st.session_state.recent_chats.insert(0, doc.title)
                    
                    add_chat_message("assistant", f"Loaded **'{doc.title}'** — {doc.section_count} sections.")
                    st.session_state.canvas_focus = "welcome"
                except Exception as e:
                    st.error(f"Error loading document: {e}")
            
            # 2. Process text if any (or rerun if just a file)
            if prompt_text:
                if is_empty_state and not prompt_files:
                    st.error("Please attach a design document first before sending messages.")
                else:
                    # handle_user_message calls st.rerun() internally
                    handle_user_message(prompt_text)
            elif prompt_files:
                st.rerun()


