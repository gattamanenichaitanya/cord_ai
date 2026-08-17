"""Test 17: UI highlights come from traces, not ticket maps."""

from __future__ import annotations

from pathlib import Path

from dashboard.diagnose.labels import role_label
from dashboard.diagnose.trace_replay import highlight_sequence, replay_frames
from diagnosis.graph import load_graph
from diagnosis.loop import DiagnosisResult


def _result(trace, *, status="diagnosed", rca="derive_pricing_segment") -> DiagnosisResult:
    return DiagnosisResult(
        status=status,
        root_cause_node=rca,
        confidence=0.9,
        reason="from trace",
        record_id="DEAL-X",
        incident_id=None,
        discrepancy={"summary": "demo"},
        visited_nodes=[],
        trace=trace,
    )


TRACE_A = [
    {"event": "EXPECTATION_VALIDATION", "results": [{"status": "VIOLATED", "summary": "Contract Sent before approval."}]},
    {
        "event": "PLANNER_DECISION",
        "current_node": "deal_stage",
        "selected_target": "deal_stage_automation",
        "reason": "Producer of the anomalous Deal Stage value.",
        "edge_type": "WRITES",
        "semantic_role": "UPSTREAM_PRODUCER",
    },
    {"event": "ACTION_RESULT", "action_type": "INSPECT_CONNECTED_NODE", "output": {"moved_to": "deal_stage_automation"}},
    {"event": "STOP", "status": "diagnosed", "root_cause_node": "derive_pricing_segment", "reason": "missing write"},
]

TRACE_D = [
    {"event": "EXPECTATION_VALIDATION", "results": [{"status": "VIOLATED", "summary": "Fulfillment never started."}]},
    {
        "event": "PLANNER_DECISION",
        "current_node": "deal_stage",
        "selected_target": "fulfillment_workflow",
        "reason": "Consumer of Deal Stage; fulfillment is missing.",
        "edge_type": "READS",
        "semantic_role": "DOWNSTREAM_CONSUMER",
    },
    {"event": "ACTION_RESULT", "action_type": "INSPECT_CONNECTED_NODE", "output": {"moved_to": "fulfillment_workflow"}},
    {"event": "STOP", "status": "diagnosed", "root_cause_node": "fulfillment_workflow", "reason": "disabled"},
]


def test_17_highlight_sequences_differ_from_traces():
    seq_a = highlight_sequence(TRACE_A)
    seq_d = highlight_sequence(TRACE_D)
    assert seq_a != seq_d
    assert seq_a[0] == ("deal_stage", "deal_stage_automation")
    assert seq_d[0] == ("deal_stage", "fulfillment_workflow")


def test_17_replay_uses_trace_targets_not_ticket_id():
    graph = load_graph()
    frames_a = replay_frames(graph, _result(TRACE_A, rca="derive_pricing_segment"))
    frames_d = replay_frames(graph, _result(TRACE_D, rca="fulfillment_workflow"))
    assert any(frame.selected_target == "deal_stage_automation" for frame in frames_a)
    assert any(frame.selected_target == "fulfillment_workflow" for frame in frames_d)
    assert frames_a[0].decision_label != frames_d[0].decision_label
    assert "Producer" in {row["role"] for row in frames_a[0].connected}
    assert "Consumer" in {row["role"] for row in frames_d[0].connected}


def test_17_ui_hides_internal_planner_jargon():
    assert role_label("UPSTREAM_PRODUCER") == "Producer"
    assert role_label("DOWNSTREAM_CONSUMER") == "Consumer"
    source = (Path("dashboard") / "diagnose" / "render.py").read_text(encoding="utf-8")
    assert "semantic_role" not in source
    assert "selected_action_id" not in source
    assert "What to fix" in source
    assert "_render_dashboard" not in source
    assert 'for page in ("Tickets", "Graph", "Chat")' in source
    assert "Inspect component" not in source
    assert "Search component" not in source
    assert "navigationButtons: false" in (Path("dashboard") / "diagnose" / "graph_view.py").read_text(encoding="utf-8")
    assert 'button("Open",' not in source
    assert 'button("Diagnose"' in source
    assert "?ticket=" not in source
    assert "tix_id_" in source
    assert "Affected system" not in source
    assert "Run Diagnosis" not in source
    assert '"Closed"' in source
    tickets_fn = source.split("def _render_tickets")[1].split("def _run_diagnosis")[0]
    assert "incident.source" not in tickets_fn
    assert "READY" not in tickets_fn


def test_17_display_edges_do_not_change_diagnosis_graph():
    from dashboard.diagnose.graph_view import DISPLAY_ONLY_EDGES, assert_display_edges_are_decoys
    from diagnosis.graph import load_graph

    assert_display_edges_are_decoys()
    graph = load_graph()
    real = {(edge["from"], edge["type"], edge["to"]) for edge in graph.edges}
    for edge in DISPLAY_ONLY_EDGES:
        assert (edge["from"], edge["type"], edge["to"]) not in real
        assert edge["from"] in graph.nodes
        assert edge["to"] in graph.nodes
    from types import SimpleNamespace

    from dashboard.diagnose.render import _recommendation_for

    old = SimpleNamespace(
        status="diagnosed",
        incident_id="INC-1188",
        record_id="DEAL-4920",
        trace=[],
    )
    assert _recommendation_for(old) is None


def test_what_to_fix_strips_markdown_and_keeps_amounts_as_text():
    from dashboard.diagnose.labels import plain_user_prose, prose_alert_html

    raw = (
        "On this deal, discount governance set approval required to `no` even though "
        "the deal amount is `$250,000` and pricing segment is `Enterprise`."
    )
    plain = plain_user_prose(raw)
    assert "`" not in plain
    assert "$250,000" in plain
    assert "Enterprise" in plain
    html = prose_alert_html(raw)
    assert "<code>" not in html
    assert "$250,000" in html


def test_17_no_frontend_ticket_maps():
    diagnose_dir = Path("dashboard") / "diagnose"
    for path in diagnose_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert '"INC-1042": "derive_pricing_segment"' not in text
        assert 'if incident_id == "INC-1042"' not in text
        assert 'INC-3310": "fulfillment_workflow"' not in text
