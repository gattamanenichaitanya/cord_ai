"""Checkpoint 5: ticket parser + graph anchors. No RCA/path in parser output."""

from diagnosis.anchors import retrieve_anchors
from diagnosis.fields import CANONICAL_FIELDS
from diagnosis.graph import load_graph
from diagnosis.incidents import get_incident, load_incidents
from diagnosis.parser import FORBIDDEN_PARSE_KEYS, parse_incident, parse_ticket
from diagnosis.roles import SemanticRole
import pytest


RCA_WORKFLOWS = {
    "derive_pricing_segment",
    "discount_governance",
    "legacy_discount_override",
    "fulfillment_workflow",
}


def test_incident_catalog_has_no_diagnosis_fields():
    for incident in load_incidents().values():
        assert incident.deal_id.startswith("DEAL-")
        raw = incident.__dict__
        assert FORBIDDEN_PARSE_KEYS.isdisjoint(raw)


def test_parser_4821_extracts_clues_not_rca():
    parsed = parse_incident("INC-1042")
    payload = parsed.as_dict()
    assert FORBIDDEN_PARSE_KEYS.isdisjoint(payload)
    assert parsed.record_id == "DEAL-4821"
    assert parsed.mentioned_values["deal_amount"] == 250000
    assert parsed.mentioned_values["discount_pct"] == 22
    assert parsed.mentioned_values["customer_tier"] == "Enterprise"
    subjects = {claim.subject for claim in parsed.observed_claims}
    assert subjects <= CANONICAL_FIELDS
    assert "deal_stage" in subjects
    assert "approval_required" in subjects
    assert RCA_WORKFLOWS.isdisjoint(payload)
    assert RCA_WORKFLOWS.isdisjoint(subjects)
    assert "derive_pricing_segment" not in str(payload)


def test_parser_5101_marks_stage_expected_and_fulfillment_unexpected():
    parsed = parse_incident("INC-3310")
    by_subject = {claim.subject: claim for claim in parsed.observed_claims}
    assert by_subject["deal_stage"].value == "Contract Sent"
    assert by_subject["deal_stage"].qualifier == "expected"
    assert by_subject["fulfillment_started"].value is False
    assert by_subject["fulfillment_started"].qualifier == "unexpected"


def test_parser_5033_does_not_treat_finance_phrase_as_contract_sent():
    parsed = parse_incident("INC-2201")
    by_subject = {claim.subject: claim for claim in parsed.observed_claims}
    assert by_subject["deal_stage"].value == "Finance Approval"
    assert parsed.mentioned_values["customer_tier"] == "SMB"
    assert parsed.mentioned_values["deal_amount"] == 50000


def test_parser_paraphrase_keeps_canonical_clues():
    text = "The $250,000 Enterprise opportunity went to Contract Sent with no Finance approval at 22 percent discount."
    parsed = parse_ticket(text)
    assert parsed.mentioned_values["deal_amount"] == 250000
    assert parsed.mentioned_values["discount_pct"] == 22
    subjects = {claim.subject for claim in parsed.observed_claims}
    assert "deal_stage" in subjects
    assert "approval_required" in subjects
    assert FORBIDDEN_PARSE_KEYS.isdisjoint(parsed.as_dict())


def test_anchors_are_real_graph_nodes():
    graph = load_graph()
    parsed = parse_incident("INC-1042")
    anchors = retrieve_anchors(graph, parsed)
    assert anchors
    for anchor in anchors:
        assert graph.get_node(anchor.node_id) is not None


def test_4821_anchors_include_symptom_properties_not_as_rca():
    graph = load_graph()
    anchors = retrieve_anchors(graph, parse_incident("INC-1042"))
    ids = [a.node_id for a in anchors]
    assert ids[0] in {"deal_stage", "approval_required"}
    assert "deal_stage" in ids
    assert "approval_required" in ids
    assert ids[0] not in RCA_WORKFLOWS


def test_5101_anchors_include_fulfillment_and_deal_stage():
    graph = load_graph()
    ids = [a.node_id for a in retrieve_anchors(graph, parse_incident("INC-3310"))]
    assert "deal_stage" in ids
    assert "fulfillment_started" in ids


def test_anchor_expansion_only_adds_real_producers():
    graph = load_graph()
    anchors = retrieve_anchors(graph, parse_incident("INC-1042"))
    ids = {a.node_id for a in anchors}
    if "deal_stage_automation" in ids:
        neighbor = graph.find_neighbor("deal_stage", "deal_stage_automation", edge_type="WRITES")
        assert neighbor is not None
        assert neighbor.semantic_role == SemanticRole.UPSTREAM_PRODUCER.value


def test_parser_does_not_map_incident_to_workflow():
    source = open("diagnosis/parser.py", encoding="utf-8").read()
    assert "derive_pricing_segment" not in source
    assert "INC-1042" not in source
    parsed = parse_incident("INC-1042")
    assert "root_cause" not in parsed.as_dict()
    with pytest.raises(KeyError):
        get_incident("INC-MISSING")
