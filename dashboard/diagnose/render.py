"""Diagnose Streamlit pages. Graph + log are driven by backend traces only."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from dashboard.diagnose.graph_view import render_graph_html
from dashboard.diagnose.labels import node_label, prose_alert_html
from dashboard.diagnose.trace_replay import replay_frames
from diagnosis.graph import load_graph
from diagnosis.incidents import get_incident, load_incidents
from diagnosis.runtime import get_runtime


def _recommendation_for(result) -> str | None:
    """Tolerate session objects created before DiagnosisResult.recommendation existed."""
    existing = getattr(result, "recommendation", None)
    if existing:
        return existing
    from diagnosis.fault import FaultEvidence
    from diagnosis.recommend import build_recommended_check
    from diagnosis.rules import get_workflow_rule

    overlay_id = getattr(result, "incident_id", None)
    record_id = getattr(result, "record_id", None)
    for event in reversed(getattr(result, "trace", None) or []):
        output = event.get("output") if event.get("event") == "ACTION_RESULT" else None
        fault = output.get("fault") if isinstance(output, dict) else None
        if not isinstance(fault, dict) or "node_id" not in fault:
            continue
        try:
            evidence = FaultEvidence(
                node_id=fault["node_id"],
                kind=fault["kind"],
                summary=fault["summary"],
                predicted=fault.get("predicted") or {},
                observed=fault.get("observed") or {},
            )
            current = get_workflow_rule(evidence.node_id, overlay_id)
            healthy = get_workflow_rule(evidence.node_id)
            runtime = get_runtime(record_id) if record_id else None
            return build_recommended_check(evidence, current, healthy, runtime)
        except (KeyError, TypeError, ValueError):
            return None
    return None


def _ensure_state() -> None:
    st.session_state.setdefault("diagnose_page", "Tickets")
    st.session_state.setdefault("diagnose_incident_id", "INC-1042")
    st.session_state.setdefault("diagnosis_results", {})
    st.session_state.setdefault("ticket_status", {})
    if st.session_state.diagnose_incident_id not in load_incidents():
        st.session_state.diagnose_incident_id = "INC-1042"
        st.session_state.diagnosis_results = {}
    st.session_state.setdefault("diagnose_graph", load_graph())
    st.session_state.setdefault("graph_filter", "All")
    st.session_state.setdefault("graph_search", "")
    st.session_state.setdefault("graph_selected", None)
    st.session_state.setdefault("graph_mode", "Full System")
    st.session_state.setdefault("replay_step", 1)
    from dashboard.diagnose.chat import ensure_conversation_store

    ensure_conversation_store()


def _lifecycle_status(incident_id: str) -> str:
    if st.session_state.ticket_status.get(incident_id) == "CLOSED":
        return "Closed"
    if incident_id in st.session_state.diagnosis_results:
        return "Diagnosed"
    return "New"


def render_diagnose_sidebar() -> None:
    from dashboard.diagnose.chat import ensure_conversation_store

    _ensure_state()
    st.markdown(
        "<div style='font-size: 0.75rem; font-weight: 700; color: #9ca3af; margin-top: 8px; margin-bottom: 12px; text-transform: uppercase;'>Diagnose</div>",
        unsafe_allow_html=True,
    )
    for page in ("Tickets", "Graph", "Chat"):
        if st.button(page, use_container_width=True, key=f"diag_nav_{page}"):
            if page == "Chat":
                ensure_conversation_store().start_new_chat()
            st.session_state.diagnose_page = page
            st.rerun()

    store = ensure_conversation_store()
    saved = store.list_saved_threads()
    if saved:
        st.markdown(
            "<div style='font-size: 0.75rem; font-weight: 700; color: #9ca3af; margin-top: 16px; margin-bottom: 8px; text-transform: uppercase;'>Conversations</div>",
            unsafe_allow_html=True,
        )
        for thread in saved:
            if st.button(thread.title, type="tertiary", key=f"diag_thread_{thread.id}"):
                store.switch_thread(thread.id)
                st.session_state.diagnose_page = "Chat"
                st.rerun()


def render_diagnose() -> None:
    _ensure_state()
    page = st.session_state.diagnose_page
    if page in {"Dashboard"}:
        st.session_state.diagnose_page = "Tickets"
        page = "Tickets"
    if page == "System Graph":
        st.session_state.diagnose_page = "Graph"
        page = "Graph"
    if page == "Graph":
        _render_system_graph()
    elif page == "Tickets":
        _render_tickets()
    elif page == "Ticket Detail":
        _render_ticket_detail()
    else:
        _render_chat()


def _render_tickets() -> None:
    st.markdown("### Tickets")
    st.caption("Select a ticket ID to review it, or run diagnosis from the list.")
    query = st.text_input("Search tickets", "")
    incidents = load_incidents()
    rows = [
        incident
        for incident in incidents.values()
        if not query or query.lower() in f"{incident.id} {incident.summary} {incident.text}".lower()
    ]
    header = st.columns([1.4, 0.8, 3.6, 1.1, 1.2])
    header[0].caption("Ticket")
    header[1].caption("Priority")
    header[2].caption("Summary")
    header[3].caption("Status")
    header[4].caption("")
    for incident in rows:
        cols = st.columns([1.4, 0.8, 3.6, 1.1, 1.2])
        if cols[0].button(incident.id, key=f"tix_id_{incident.id}", type="tertiary"):
            st.session_state.diagnose_incident_id = incident.id
            st.session_state.diagnose_page = "Ticket Detail"
            st.rerun()
        cols[1].write(incident.priority)
        cols[2].write(incident.summary)
        cols[3].write(_lifecycle_status(incident.id))
        if cols[4].button("Diagnose", key=f"tix_diag_{incident.id}"):
            st.session_state.diagnose_incident_id = incident.id
            _run_diagnosis(incident.id)
            st.session_state.diagnose_page = "Ticket Detail"
            st.rerun()


def _run_diagnosis(incident_id: str) -> None:
    from diagnosis.loop import diagnose
    from diagnosis.planner import ClaudePlanner
    from planning.claude_client import ClaudeClient

    st.session_state.ticket_status.pop(incident_id, None)
    client = st.session_state.get("claude_client")
    if client is None:
        client = ClaudeClient()
        st.session_state.claude_client = client
    with st.spinner("Cord is investigating the configuration graph…"):
        result = diagnose(incident_id, planner=ClaudePlanner(client=client))
    st.session_state.diagnosis_results[incident_id] = result
    st.session_state.replay_step = 1


def _render_ticket_detail() -> None:
    graph = st.session_state.diagnose_graph
    incident_id = st.session_state.diagnose_incident_id
    incident = get_incident(incident_id)
    result = st.session_state.diagnosis_results.get(incident_id)
    status = _lifecycle_status(incident_id)

    if st.button("← Tickets"):
        st.session_state.diagnose_page = "Tickets"
        st.rerun()

    head_l, head_r = st.columns([4, 1])
    head_l.markdown(f"### {incident.id}")
    head_r.markdown(f"**{status}**")

    st.info(incident.text)

    if result is None:
        if st.button("Diagnose", type="primary"):
            _run_diagnosis(incident_id)
            st.rerun()
        return

    frames = replay_frames(graph, result)
    max_step = max(len(frames), 1)
    step = st.slider("Replay investigation", 1, max_step, min(st.session_state.replay_step, max_step))
    st.session_state.replay_step = step
    frame = frames[step - 1]

    graph_col, log_col = st.columns([3, 2])
    with graph_col:
        st.markdown("**Investigation graph**")
        html = render_graph_html(
            graph,
            node_states=frame.node_states,
            incident_path=True,
            selected_id=frame.current_node,
            height=480,
        )
        components.html(html, height=500, scrolling=False)
        st.caption("Highlights come from the diagnosis trace, not a preset animation.")
    with log_col:
        st.markdown("**Investigation**")
        if frame.current_node:
            st.markdown(f"**Current**  \n{node_label(graph, frame.current_node)}")
        if frame.connected:
            st.markdown("**Connected**")
            for row in frame.connected[:8]:
                st.write(f"• {row['name']} — {row['edge']} ({row['role']})")
        if frame.decision_label:
            st.markdown(f"**Cord chose**  \n{frame.decision_label}")
        if frame.why:
            st.markdown(f"**Why**  \n{frame.why}")
        with st.expander("Full log"):
            st.text("\n\n".join(frame.log_lines))

    if result.status == "diagnosed":
        rca_label = node_label(graph, result.root_cause_node)
        rca_reason = (result.reason or "").strip()
        if rca_reason:
            st.success(f"**Root cause:** {rca_label}  \n{rca_reason}")
        else:
            st.success(f"**Root cause:** {rca_label}")
        conf = "High" if result.confidence >= 0.75 else "Medium" if result.confidence >= 0.5 else "Low"
        recommendation = _recommendation_for(result)
        if recommendation:
            st.markdown("**What to fix**")
            st.markdown(prose_alert_html(recommendation), unsafe_allow_html=True)
        ev_col, path_col = st.columns(2)
        with path_col:
            st.markdown("**Causal path**")
            for node_id in result.visited_nodes:
                marker = " ← root" if node_id == result.root_cause_node else ""
                st.write(f"{node_label(graph, node_id)}{marker}")
        with ev_col:
            st.markdown("**Evidence**")
            try:
                runtime = get_runtime(incident.deal_id)
                for field, value in runtime.values.items():
                    st.write(f"{node_label(graph, field)}: {value}")
            except KeyError:
                st.write(result.reason)
        btn_l, btn_r = st.columns(2)
        if btn_l.button("View in Graph"):
            st.session_state.graph_mode = "Incident Path"
            st.session_state.diagnose_page = "Graph"
            st.rerun()
        if status == "Diagnosed" and btn_r.button("Close ticket"):
            st.session_state.ticket_status[incident_id] = "CLOSED"
            st.rerun()
        st.caption(f"Confidence: {conf}. Cord made no changes to the CRM.")
    elif result.status == "no_anomaly":
        st.info("No validated anomaly. Cord did not start a causal walk.")
        if status == "Diagnosed" and st.button("Close ticket"):
            st.session_state.ticket_status[incident_id] = "CLOSED"
            st.rerun()
    else:
        st.warning(result.reason or "Needs a human reviewer.")
        if status == "Diagnosed" and st.button("Close ticket"):
            st.session_state.ticket_status[incident_id] = "CLOSED"
            st.rerun()


def _render_system_graph() -> None:
    graph = st.session_state.diagnose_graph
    st.markdown("### Graph")
    st.caption("Persistent configuration graph for Acme Cloud")
    tools = st.columns([2, 2, 2, 2])
    st.session_state.graph_search = tools[0].text_input("Search", st.session_state.graph_search)
    types = ["All"] + sorted({n["type"] for n in graph.nodes.values()})
    st.session_state.graph_filter = tools[1].selectbox("Type", types, index=types.index(st.session_state.graph_filter) if st.session_state.graph_filter in types else 0)
    st.session_state.graph_mode = tools[2].radio("View", ["Full System", "Incident Path"], horizontal=True)
    incident_id = st.session_state.diagnose_incident_id
    result = st.session_state.diagnosis_results.get(incident_id)

    node_states: dict[str, str] = {}
    incident_path = st.session_state.graph_mode == "Incident Path" and result is not None
    if result is not None:
        frames = replay_frames(graph, result)
        node_states = frames[-1].node_states

    search = st.session_state.graph_search.lower().strip()
    type_filter = st.session_state.graph_filter
    visible = set(graph.nodes)
    if type_filter != "All":
        visible = {nid for nid, n in graph.nodes.items() if n["type"] == type_filter}
    if search:
        visible = {
            nid
            for nid in visible
            if search in nid.lower() or search in node_label(graph, nid).lower()
        }
    if incident_path:
        visible = visible.intersection(node_states)

    subset = incident_path or type_filter != "All" or bool(search)
    html = render_graph_html(
        graph,
        node_states=node_states if not subset else {nid: node_states.get(nid, "UNVISITED") for nid in visible},
        incident_path=subset,
        height=560,
    )
    components.html(html, height=580, scrolling=False)

    counts = st.columns(4)
    counts[0].metric("Components", graph.node_count())
    counts[1].metric("Dependencies", graph.edge_count())
    counts[2].metric("Workflows", sum(1 for n in graph.nodes.values() if n["type"] == "WORKFLOW"))
    counts[3].metric("Integrations", sum(1 for n in graph.nodes.values() if n["type"] == "INTEGRATION"))


def _render_chat() -> None:
    from dashboard.diagnose.chat import render_diagnose_chat

    render_diagnose_chat()
