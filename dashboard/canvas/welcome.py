import streamlit as st

def render_welcome():
    """Renders the default welcome screen on the canvas."""
    st.markdown("## 🚀 Welcome to CordAI")
    st.markdown(
        "CordAI is an agentic implementation partner to analyze business requirements "
        "and automatically construct, test, and activate any SaaS platform."
    )
    
    st.markdown("---")
    
    st.markdown("### 📋 How to Begin")
    st.write("1. **Upload a Requirements Document:** Submit a text or DOCX file containing your business specifications.")
    st.write("2. **Refine Requirements:** The agent will parse your document into discrete automation rules.")
    st.write("3. **Generate Action Plans:** Review and approve technical execution plans before they are deployed.")
    st.write("4. **Watch Live Execution:** Follow step-by-step browser automation with automatic vision self-healing.")
    
    st.info("💡 **Ready to start?** Upload your requirements document or drop a message in the chat box to the left!")
