"""Diagnose Chat page. Always on; Claude only paraphrases backend evidence."""

from __future__ import annotations

import html

import streamlit as st

from dashboard.diagnose.labels import node_label, prose_alert_html
from diagnosis.chat_reply import answer_turn
from diagnosis.conversations import ConversationStore
from diagnosis.incidents import load_incidents
from diagnosis.prose import plain_user_prose

NONE_TICKET = "None"


def ticket_select_options(incident_ids: list[str]) -> list[str]:
    return [NONE_TICKET, *incident_ids]


def ensure_conversation_store() -> ConversationStore:
    st.session_state.diagnose_conversations = ConversationStore.revive(
        st.session_state.get("diagnose_conversations")
    )
    return st.session_state.diagnose_conversations


def _status_line(incident_id: str | None) -> str:
    if not incident_id:
        return "No ticket selected. Answers are grounded in the configuration graph."
    result = st.session_state.diagnosis_results.get(incident_id)
    if result is None:
        return f"{incident_id} has not been diagnosed yet."
    graph = st.session_state.diagnose_graph
    if result.status == "diagnosed" and result.root_cause_node:
        return f"Diagnosed. Root cause: {node_label(graph, result.root_cause_node)}."
    if result.status == "no_anomaly":
        return "No validated anomaly on this ticket."
    return result.reason or "Needs a human reviewer."


def _run_and_return(incident_id: str):
    from dashboard.diagnose.render import _run_diagnosis

    _run_diagnosis(incident_id)
    return st.session_state.diagnosis_results[incident_id]


def rerun_active_thread(
    store: ConversationStore,
    *,
    client,
    run_diagnosis,
    results: dict | None = None,
    graph=None,
) -> bool:
    """Run diagnosis for the active ticket and append a grounded summary. False if no ticket."""
    thread = store.active_thread()
    if not thread.incident_id:
        return False
    store.append_message("user", "Rerun diagnosis")
    turn = answer_turn(
        "Rerun diagnosis",
        incident_id=thread.incident_id,
        result=(results or {}).get(thread.incident_id) if results is not None else None,
        prior_messages=thread.messages[:-1],
        client=client,
        run_diagnosis=run_diagnosis,
        graph=graph,
    )
    store.append_message("assistant", turn.text)
    return True


def render_diagnose_chat() -> None:
    store = ensure_conversation_store()
    thread = store.active_thread()
    incidents = load_incidents()
    options = ticket_select_options(list(incidents))
    current = thread.incident_id if thread.incident_id in incidents else None
    index = options.index(current) if current else 0

    st.markdown("### Chat")
    st.caption("Ask about the system or a ticket. Cord answers from backend evidence only.")

    chosen = st.selectbox("Context ticket", options, index=index, key=f"chat_ticket_{thread.id}")
    incident_id = None if chosen == NONE_TICKET else chosen
    if incident_id != thread.incident_id:
        store.switch_incident(incident_id)
        if incident_id:
            st.session_state.diagnose_incident_id = incident_id
        st.rerun()
    if incident_id:
        st.session_state.diagnose_incident_id = incident_id

    st.caption(_status_line(incident_id))
    result = st.session_state.diagnosis_results.get(incident_id) if incident_id else None
    if result is not None and result.status == "diagnosed":
        from dashboard.diagnose.render import _recommendation_for

        recommendation = _recommendation_for(result)
        if recommendation:
            st.markdown("**What to fix**")
            st.markdown(prose_alert_html(recommendation), unsafe_allow_html=True)

    for message in thread.messages:
        css = "chat-bubble-user" if message.role == "user" else "chat-bubble-assistant"
        body = html.escape(plain_user_prose(message.content))
        st.markdown(f"<div class='{css}'>{body}</div>", unsafe_allow_html=True)

    prompt = st.chat_input("Ask about this ticket or the system...")
    if prompt:
        store.append_message("user", prompt)
        thread = store.active_thread()
        client = st.session_state.get("claude_client")
        with st.spinner("Cord is answering from the graph and diagnosis evidence…"):
            turn = answer_turn(
                prompt,
                incident_id=thread.incident_id,
                result=st.session_state.diagnosis_results.get(thread.incident_id) if thread.incident_id else None,
                prior_messages=thread.messages[:-1],
                client=client,
                run_diagnosis=_run_and_return if thread.incident_id else None,
                graph=st.session_state.diagnose_graph,
            )
        store.append_message("assistant", turn.text)
        st.rerun()

    actions = st.columns(2)
    if incident_id and actions[0].button("Rerun diagnosis"):
        with st.spinner("Cord is re-running diagnosis…"):
            rerun_active_thread(
                store,
                client=st.session_state.get("claude_client"),
                run_diagnosis=_run_and_return,
                results=st.session_state.diagnosis_results,
                graph=st.session_state.diagnose_graph,
            )
        st.rerun()
    if incident_id and actions[1].button("Open full diagnosis"):
        st.session_state.diagnose_incident_id = incident_id
        st.session_state.diagnose_page = "Ticket Detail"
        st.rerun()
