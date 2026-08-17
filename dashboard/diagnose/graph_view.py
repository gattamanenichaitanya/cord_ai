"""vis-network HTML for the Diagnose system / investigation graph."""

from __future__ import annotations

import json
from typing import Any

from diagnosis.graph import SystemGraph

from dashboard.diagnose.labels import node_label

# Display-only decoy links. Never loaded by diagnosis.loop / SystemGraph.
_DIAGNOSIS_NODE_IDS = frozenset(
    {
        "deal_amount",
        "discount_pct",
        "customer_tier",
        "pricing_segment",
        "approval_required",
        "deal_stage",
        "fulfillment_started",
        "sales_process_complete",
        "derive_pricing_segment",
        "discount_governance",
        "deal_stage_automation",
        "legacy_discount_override",
        "fulfillment_workflow",
        "reporting_workflow",
        "derive_enterprise_branch",
        "derive_smb_branch",
        "segment_mapper",
        "CHANGE-1007",
    }
)

DISPLAY_ONLY_EDGES: tuple[dict[str, str], ...] = (
    {"from": "company", "type": "CONTAINS", "to": "industry"},
    {"from": "company", "type": "CONTAINS", "to": "region"},
    {"from": "company", "type": "CONTAINS", "to": "partner_tier"},
    {"from": "company", "type": "CONTAINS", "to": "nps_score"},
    {"from": "company", "type": "CONTAINS", "to": "customer_health_score"},
    {"from": "contact", "type": "CONTAINS", "to": "lead_source"},
    {"from": "contact", "type": "CONTAINS", "to": "marketing_source"},
    {"from": "contact", "type": "CONTAINS", "to": "billing_contact_email"},
    {"from": "deal", "type": "CONTAINS", "to": "sales_owner"},
    {"from": "deal", "type": "CONTAINS", "to": "close_date"},
    {"from": "deal", "type": "CONTAINS", "to": "forecast_category"},
    {"from": "deal", "type": "CONTAINS", "to": "next_step"},
    {"from": "deal", "type": "CONTAINS", "to": "renewal_date"},
    {"from": "deal", "type": "CONTAINS", "to": "mrr"},
    {"from": "company", "type": "CONTAINS", "to": "territory_assignment"},
    {"from": "lead_assignment_workflow", "type": "READS", "to": "lead_source"},
    {"from": "lead_assignment_workflow", "type": "READS", "to": "territory_assignment"},
    {"from": "lead_assignment_workflow", "type": "WRITES", "to": "sales_owner"},
    {"from": "owner_round_robin", "type": "READS", "to": "region"},
    {"from": "owner_round_robin", "type": "READS", "to": "territory_assignment"},
    {"from": "renewal_reminder_workflow", "type": "READS", "to": "sales_owner"},
    {"from": "billing_contact_sync", "type": "READS", "to": "contact"},
    {"from": "close_date_nudge", "type": "WRITES", "to": "close_date"},
    {"from": "forecast_commit", "type": "READS", "to": "mrr"},
    {"from": "ticket_sla", "type": "READS", "to": "team_support"},
    {"from": "tax_calculator", "type": "READS", "to": "mrr"},
    {"from": "tax_calculator", "type": "CALLS", "to": "billing_stripe"},
    {"from": "slack_won_alert", "type": "READS", "to": "stage_closed_won"},
    {"from": "docusign", "type": "READS", "to": "stage_contract_sent"},
    {"from": "docusign", "type": "READS", "to": "stage_negotiation"},
    {"from": "clearbit", "type": "WRITES", "to": "region"},
    {"from": "data_warehouse_sync", "type": "READS", "to": "nps_score"},
    {"from": "data_warehouse_sync", "type": "READS", "to": "mrr"},
    {"from": "team_sales_ops", "type": "CONTAINS", "to": "owner_round_robin"},
    {"from": "team_sales_ops", "type": "CONTAINS", "to": "close_date_nudge"},
    {"from": "team_sales_ops", "type": "CONTAINS", "to": "lead_assignment_workflow"},
    {"from": "team_revops", "type": "CONTAINS", "to": "forecast_commit"},
    {"from": "team_support", "type": "CONTAINS", "to": "ticket_sla"},
    {"from": "team_finance", "type": "CONTAINS", "to": "stage_finance_approval"},
    {"from": "lifecycle_sync", "type": "WRITES", "to": "contact"},
    {"from": "stage_negotiation", "type": "MOVES_TO", "to": "stage_finance_approval"},
    {"from": "stage_finance_approval", "type": "MOVES_TO", "to": "stage_contract_sent"},
    {"from": "stage_contract_sent", "type": "MOVES_TO", "to": "stage_closed_won"},
)

STATE_COLORS = {
    "UNVISITED": {"background": "#e5e7eb", "border": "#9ca3af", "highlight": "#d1d5db"},
    "CANDIDATE": {"background": "#93c5fd", "border": "#2563eb", "highlight": "#60a5fa"},
    "CURRENT": {"background": "#2563eb", "border": "#1e3a8a", "highlight": "#3b82f6"},
    "VISITED": {"background": "#a7f3d0", "border": "#059669", "highlight": "#6ee7b7"},
    "CAUSAL_PATH": {"background": "#5eead4", "border": "#0f766e", "highlight": "#2dd4bf"},
    "ROOT_CAUSE": {"background": "#ef4444", "border": "#991b1b", "highlight": "#f87171"},
}


def _node_color(state: str) -> dict[str, str]:
    return STATE_COLORS.get(state, STATE_COLORS["UNVISITED"])


def render_graph_html(
    graph: SystemGraph,
    *,
    node_states: dict[str, str] | None = None,
    incident_path: bool = False,
    selected_id: str | None = None,
    height: int = 520,
) -> str:
    states = node_states or {}
    keep = set(states) if incident_path and states else set(graph.nodes)

    nodes: list[dict[str, Any]] = []
    for node_id, node in graph.nodes.items():
        if incident_path and node_id not in keep:
            continue
        state = states.get(node_id, "UNVISITED")
        color = _node_color(state)
        nodes.append(
            {
                "id": node_id,
                "label": node_label(graph, node_id),
                "title": f"{node.get('type', '')}: {node.get('description', '')}",
                "group": node.get("type"),
                "borderWidth": 4 if node_id == selected_id or state == "ROOT_CAUSE" else 1,
                "color": color,
                "font": {"color": "#ffffff" if state in {"CURRENT", "ROOT_CAUSE"} else "#111827"},
            }
        )

    edges: list[dict[str, Any]] = []
    for index, edge in enumerate(graph.edges):
        if incident_path and (edge["from"] not in keep or edge["to"] not in keep):
            continue
        edges.append(_vis_edge(f"e{index}", edge))

    if not incident_path:
        for index, edge in enumerate(DISPLAY_ONLY_EDGES):
            if edge["from"] not in keep or edge["to"] not in keep:
                continue
            if edge["from"] not in graph.nodes or edge["to"] not in graph.nodes:
                continue
            edges.append(_vis_edge(f"d{index}", edge, decoy=True))

    payload = json.dumps({"nodes": nodes, "edges": edges})
    return f"""
<div id="cord-graph" style="height:{height}px;border:1px solid #e5e7eb;border-radius:12px;background:#fafafa;"></div>
<script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<script type="text/javascript">
  const data = {payload};
  const container = document.getElementById("cord-graph");
  const network = new vis.Network(container, {{
    nodes: new vis.DataSet(data.nodes),
    edges: new vis.DataSet(data.edges)
  }}, {{
    physics: {{
      stabilization: true,
      barnesHut: {{ gravitationalConstant: -12000, springLength: 95, springConstant: 0.04, avoidOverlap: 0.3 }}
    }},
    interaction: {{ hover: true, tooltipDelay: 120, navigationButtons: false, keyboard: false, zoomView: true, dragView: true, dragNodes: true }},
    nodes: {{ shape: "dot", size: 14, font: {{ size: 11 }} }},
    edges: {{ smooth: {{ type: "cubicBezier" }} }}
  }});
</script>
"""


def _vis_edge(edge_id: str, edge: dict[str, str], *, decoy: bool = False) -> dict[str, Any]:
    return {
        "id": edge_id,
        "from": edge["from"],
        "to": edge["to"],
        "label": edge["type"],
        "arrows": "to",
        "font": {"size": 9, "color": "#9ca3af" if decoy else "#6b7280"},
        "color": {"color": "#d1d5db" if decoy else "#9ca3af"},
    }


def assert_display_edges_are_decoys() -> None:
    for edge in DISPLAY_ONLY_EDGES:
        if edge["from"] in _DIAGNOSIS_NODE_IDS or edge["to"] in _DIAGNOSIS_NODE_IDS:
            raise AssertionError(f"Display edge touches diagnosis graph: {edge}")
