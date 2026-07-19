from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional
from planning.claude_client import ClaudeClient

class Intent(str, Enum):
    EXTRACT_REQUIREMENTS = "extract_requirements"
    PLAN_REQUIREMENT = "plan_requirement"
    SHOW_ARTIFACT = "show_artifact"       # switch canvas focus
    EXPLAIN = "explain"                    # answer a question conversationally
    EXECUTE = "execute"                    # user asks to execute (we'll nudge to button)
    INSPECT_HUBSPOT = "inspect_hubspot"    # live query against the HubSpot portal
    UNKNOWN = "unknown"

class ClassifiedIntent(BaseModel):
    intent: Intent
    requirement_id: Optional[str] = Field(default=None, description="The resolved requirement ID (e.g., REQ-001) for PLAN_REQUIREMENT or SHOW_ARTIFACT.")
    requirement_reference: Optional[str] = Field(default=None, description="Raw reference to the requirement if the ID is unclear (e.g., 'the at-risk one').")
    artifact_target: Optional[str] = Field(default=None, description="The target artifact to show ('requirements' or a specific requirement ID like 'REQ-001') for SHOW_ARTIFACT.")
    question: Optional[str] = Field(default=None, description="The raw conversational question/clarification text for EXPLAIN or INSPECT_HUBSPOT.")
    inspect_object: Optional[str] = Field(default=None, description="For INSPECT_HUBSPOT: the HubSpot object type to query (e.g. 'contacts', 'companies', 'deals'). Infer from the user's question. Default to 'contacts' if unclear.")
    acknowledgment: str = Field(..., description="A short, natural-language response showing you understood the request (e.g., 'Tackling the At-Risk Customer Alert plan next.').")
    confidence: float = Field(..., description="Classification confidence score between 0.0 and 1.0.")

def classify_intent(
    user_message: str,
    context: dict,
    client: ClaudeClient
) -> ClassifiedIntent:
    """
    Classifies a user's raw message into a structured intent using a Claude call.
    """
    system_prompt = """You are the command interpreter for Cord AI, a tool that helps consultants implement HubSpot SaaS configurations from design documents.
Your task is to map the user's message to a structured intent and resolve references where possible.

INTENTS:
- extract_requirements: Triggered when the user wants to extract or load requirements from the document (e.g., "extract the requirements", "what needs to be done", "read the doc").
- plan_requirement: Triggered when the user wants to generate a plan for a specific requirement (e.g., "plan REQ-004", "plan the at-risk workflow", "let's do number 4", "tackle the risk one"). You MUST try to resolve the requirement_id from the available requirements list in the context. Match by ID or by title similarity. If you resolve it, set `requirement_id`. If ambiguous or not found, set `requirement_reference` to the raw phrase and leave `requirement_id` null.
- show_artifact: Triggered when the user wants to switch the canvas view to see a specific artifact or requirement (e.g., "show me the requirements", "go back to the list", "show REQ-002"). Set `artifact_target` to "requirements" or the specific requirement ID (e.g., "REQ-002").
- explain: Triggered when the user asks a conversational question about the loaded document, the current plan, HubSpot concepts, or gaps that were flagged. Examples: "why did you flag that", "what's re-enrollment", "explain the second gap". Put the query inside the `question` field.
- inspect_hubspot: Triggered when the user asks a question that requires checking the LIVE state of the HubSpot portal — whether a field/property exists, what properties are on an object, what workflows exist, etc. Examples: "Is there a field called Annexure Revenue on the contact object?", "Does acs_risk_score exist?", "What custom properties does the company object have?", "List all contact properties in the acme group". Set `question` to the user's full question and `inspect_object` to the HubSpot object type (contacts, companies, deals, tickets). Default inspect_object to 'contacts' if the object is not specified.
- execute: Triggered when the user wants to run or deploy the active action plan (e.g., "execute", "run it", "go ahead and build it").
- unknown: Default fallback if the intent is not clear.

CRITICAL ROUTING RULE: Any question about whether a property/field EXISTS in HubSpot, or what properties/workflows currently exist in the portal, MUST be routed to inspect_hubspot — NOT explain. The explain intent is only for questions about document content, plans, or HubSpot concepts.

RESOLUTION RULES:
1. Use the provided context (available requirements and plans) to resolve ambiguous terms like "the risk one" or "number 3".
2. Create a friendly, natural-language acknowledgment sentence showing immediate action.
"""

    context_str = f"""Available Context:
- Document Loaded: {context.get('document_loaded', False)}
- Available Requirements (extracted): {context.get('available_requirements', [])}
- Available Plans (req_ids with generated plans): {context.get('available_plans', [])}
- Current Canvas Focus: '{context.get('current_canvas_focus', 'welcome')}'

User Message: "{user_message}"
"""

    try:
        parsed_intent, metadata = client.call_with_structured_output(
            prompt=context_str,
            output_model=ClassifiedIntent,
            system_prompt=system_prompt
        )
        
        # Log this call in st.session_state for browser network tracing if running in Streamlit
        import streamlit as st
        from datetime import datetime
        if st.runtime.exists():
            if "api_logs" not in st.session_state:
                st.session_state.api_logs = []
            st.session_state.api_logs.append({
                "Timestamp": datetime.now().strftime("%H:%M:%S"),
                "API Endpoint": "api.anthropic.com/v1/messages",
                "Model": metadata.get("model", "unknown"),
                "Input Tokens": metadata.get("input_tokens", 0),
                "Output Tokens": metadata.get("output_tokens", 0),
                "Latency": f"{metadata.get('latency', 0.0):.2f}s"
            })
        
        return parsed_intent
    except Exception as e:
        # Fallback in case of call/validation failures
        print(f"Error during intent classification: {e}")
        return ClassifiedIntent(
            intent=Intent.UNKNOWN,
            acknowledgment="I encountered an issue processing that. Could you please rephrase?",
            confidence=0.0
        )
