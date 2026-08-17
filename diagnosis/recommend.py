"""Plain-language recommended check from fault + rule evidence.

Does not map incident ids to fixes. Does not apply the change.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from diagnosis.fault import FaultEvidence
from diagnosis.fields import CANONICAL_FIELDS
from diagnosis.runtime import RuntimeState

RECOMMENDATION_RESTRICTIONS = {
    "use_only_this_json": True,
    "do_not_invent_components_fields_or_values": True,
    "do_not_mention_incident_identifiers": True,
    "do_not_claim_the_crm_was_changed": True,
    "do_not_give_unverified_click_paths": True,
    "fix_only_this_component": True,
    "do_not_restate_downstream_symptoms": True,
    "audience": "a support or operations user",
    "length": "2 short sentences",
}

RECOMMENDATION_SYSTEM_PROMPT = """You write a short 'what to fix' note for a SaaS operations user.

Use ONLY the evidence JSON. Every component, field, number, and value you mention must appear there.
Recommend a fix for this_component only. Do not mention fields, stages, or approvals that are not in this_component.writes, this_component.reads, rule_diff, or this_deal.
Do not explain downstream effects (for example contract sent or finance approval) unless those fields are listed under this_component.writes.
Do not invent workflows, properties, stages, or systems.
Do not mention incident IDs or ticket IDs.
Do not say that Cord or anyone already changed the CRM.
Do not use internal jargon (missing_write, overlay, JSON, action_id, semantic_role).

Write ordinary English. Use the how_to_refer strings exactly as given (they are already in sentence case).
Do not Title Case workflow or field names. Say "customer tier", not "Customer Tier". Say "derive pricing segment", not "Derive Pricing Segment".
Capitalize only the first word of a sentence and proper values such as Enterprise.
Do not use markdown, backticks, bold, or LaTeX. Write amounts as ordinary text such as $250,000.
Two sentences: what is wrong on this deal, then what to change in the workflow.
"""

FIELD_LABELS = {
    "deal_amount": "deal amount",
    "discount_pct": "discount %",
    "customer_tier": "customer tier",
    "pricing_segment": "pricing segment",
    "approval_required": "approval required",
    "deal_stage": "deal stage",
    "fulfillment_started": "fulfillment started",
    "sales_process_complete": "sales process complete",
}

OP_PHRASE = {
    "==": "is",
    "!=": "is not",
    ">": "is greater than",
    ">=": "is at least",
    "<": "is less than",
    "<=": "is at most",
}


def friendly_name(node_id: str) -> str:
    if node_id in FIELD_LABELS:
        return FIELD_LABELS[node_id]
    return node_id.replace("_", " ")


def format_field_value(field: str, value: Any) -> str:
    if value is None:
        return "empty"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if field == "deal_amount" and isinstance(value, (int, float)):
        return f"${value:,.0f}"
    if field == "discount_pct" and isinstance(value, (int, float)):
        return f"{value:g}%"
    return str(value)


def _phrase_condition(condition: dict[str, Any]) -> str:
    field = condition["field"]
    op = OP_PHRASE.get(condition["op"], condition["op"])
    return f"{friendly_name(field)} {op} {format_field_value(field, condition['value'])}"


def _sig(condition: dict[str, Any]) -> tuple[str, str]:
    return (condition["field"], condition["op"])


def _case_fingerprint(case: dict[str, Any]) -> tuple[tuple[tuple[str, str, Any], ...], str, Any]:
    when = tuple(sorted((c["field"], c["op"], c["value"]) for c in case.get("when", [])))
    then = case["then"]
    return (when, then["field"], then["value"])


def _missing_cases(current: dict[str, Any], healthy: dict[str, Any]) -> list[dict[str, Any]]:
    healthy_cases = healthy.get("rule", {}).get("cases", [])
    current_cases = current.get("rule", {}).get("cases", [])
    current_fps = {_case_fingerprint(case) for case in current_cases}
    return [case for case in healthy_cases if _case_fingerprint(case) not in current_fps]


def _changed_thresholds(current: dict[str, Any], healthy: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    healthy_all = {_sig(item): item for item in healthy.get("rule", {}).get("all", [])}
    current_all = {_sig(item): item for item in current.get("rule", {}).get("all", [])}
    changed: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for sig, baseline in healthy_all.items():
        live = current_all.get(sig)
        if live is not None and live["value"] != baseline["value"]:
            changed.append((live, baseline))
    return changed


def _runtime_clause(runtime: RuntimeState | None, fields: set[str]) -> str:
    if runtime is None:
        return ""
    parts = []
    for field in fields:
        if field not in CANONICAL_FIELDS:
            continue
        value = runtime.get(field)
        if value is None:
            continue
        parts.append(f"{friendly_name(field)} is {format_field_value(field, value)}")
    if not parts:
        return ""
    return "On this deal, " + ", ".join(parts) + "."


def _rule_fields(rule: dict[str, Any]) -> set[str]:
    fields: set[str] = set()
    body = rule.get("rule", {})
    for cond in body.get("all", []):
        fields.add(cond["field"])
    if "then" in body:
        fields.add(body["then"]["field"])
    if "else" in body:
        fields.add(body["else"]["field"])
    for case in body.get("cases", []):
        for cond in case.get("when", []):
            fields.add(cond["field"])
        fields.add(case["then"]["field"])
    return fields


def _write_fields(rule: dict[str, Any], fault: FaultEvidence) -> set[str]:
    fields = set(fault.predicted) | set(fault.observed)
    body = rule.get("rule", {})
    if "then" in body:
        fields.add(body["then"]["field"])
    if "else" in body:
        fields.add(body["else"]["field"])
    for case in body.get("cases", []):
        fields.add(case["then"]["field"])
    return {field for field in fields if field in CANONICAL_FIELDS}


def recommendation_evidence(
    fault: FaultEvidence,
    current_rule: dict[str, Any],
    healthy_rule: dict[str, Any] | None = None,
    runtime: RuntimeState | None = None,
    discrepancy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Grounded facts for Claude. Scoped to this component; no incident ids."""
    del discrepancy  # Symptom/policy text pulls Claude off the actual fix.
    healthy = healthy_rule or {}
    missing = _missing_cases(current_rule, healthy) if healthy else []
    changed = _changed_thresholds(current_rule, healthy) if healthy else []
    relevant = _rule_fields(current_rule) | _rule_fields(healthy) | set(fault.predicted) | set(fault.observed)
    writes = _write_fields(current_rule, fault) | _write_fields(healthy, fault)
    reads = {field for field in relevant if field not in writes}
    deal: dict[str, Any] = {}
    if runtime is not None:
        for field in sorted(relevant):
            if field not in CANONICAL_FIELDS:
                continue
            deal[field] = {
                "how_to_refer": friendly_name(field),
                "value": runtime.get(field),
                "display_value": format_field_value(field, runtime.get(field)),
            }
    return {
        "restrictions": dict(RECOMMENDATION_RESTRICTIONS),
        "this_component": {
            "how_to_refer": friendly_name(fault.node_id),
            "enabled": current_rule.get("enabled", True),
            "reads": [{"id": field, "how_to_refer": friendly_name(field)} for field in sorted(reads)],
            "writes": [{"id": field, "how_to_refer": friendly_name(field)} for field in sorted(writes)],
        },
        "what_happened": {
            "did_not_write": [
                {"how_to_refer": friendly_name(field), "display_value": format_field_value(field, value)}
                for field, value in fault.observed.items()
                if value is None
            ],
            "wrote": [
                {"how_to_refer": friendly_name(field), "display_value": format_field_value(field, value)}
                for field, value in fault.predicted.items()
            ],
        },
        "rule_diff": {
            "missing_cases": [
                {
                    "when": [_phrase_condition(cond) for cond in case.get("when", [])],
                    "should_write": {
                        "how_to_refer": friendly_name(case["then"]["field"]),
                        "display_value": format_field_value(case["then"]["field"], case["then"]["value"]),
                    },
                }
                for case in missing
            ],
            "changed_conditions": [
                {
                    "how_to_refer": friendly_name(live["field"]),
                    "live": _phrase_condition(live),
                    "should_be": _phrase_condition(baseline),
                    "live_value": format_field_value(live["field"], live["value"]),
                    "should_be_value": format_field_value(baseline["field"], baseline["value"]),
                }
                for live, baseline in changed
            ],
        },
        "this_deal": deal,
    }


class RecommendationCopy(BaseModel):
    recommendation: str = Field(min_length=1)


def write_recommendation(evidence: dict[str, Any], client: Any) -> str:
    prompt = (
        "Write the what-to-fix recommendation from this evidence only.\n\n"
        + json.dumps(evidence, indent=2, default=str)
    )
    copy, _meta = client.call_with_structured_output(
        prompt=prompt,
        output_model=RecommendationCopy,
        system_prompt=RECOMMENDATION_SYSTEM_PROMPT,
        max_tokens=512,
    )
    text = copy.recommendation.strip()
    if not text:
        raise ValueError("empty recommendation")
    return text


def build_recommended_check(
    fault: FaultEvidence,
    current_rule: dict[str, Any],
    healthy_rule: dict[str, Any] | None = None,
    runtime: RuntimeState | None = None,
    *,
    client: Any | None = None,
    discrepancy: dict[str, Any] | None = None,
) -> str:
    """Claude paraphrases grounded evidence. Template is fallback only."""
    evidence = recommendation_evidence(fault, current_rule, healthy_rule, runtime, discrepancy)
    if client is not None:
        try:
            return write_recommendation(evidence, client)
        except Exception:
            pass
    return _fallback_recommendation(fault, current_rule, healthy_rule, runtime)


def _fallback_recommendation(
    fault: FaultEvidence,
    current_rule: dict[str, Any],
    healthy_rule: dict[str, Any] | None,
    runtime: RuntimeState | None,
) -> str:
    workflow = friendly_name(fault.node_id)
    healthy = healthy_rule or {}
    sentences: list[str] = []

    if fault.kind == "disabled":
        targets = ", ".join(friendly_name(field) for field in fault.predicted) or "its output"
        sentences.append(f"{workflow} is turned off, so it never set {targets}.")
        sentences.append("Turn that workflow back on.")
        return " ".join(sentences)

    missing = _missing_cases(current_rule, healthy) if healthy else []
    if fault.kind == "missing_write" or missing:
        if missing:
            case = missing[0]
            then = case["then"]
            when = " and ".join(_phrase_condition(c) for c in case.get("when", []))
            sentences.append(
                f"{workflow} is not setting {friendly_name(then['field'])} "
                f"to {format_field_value(then['field'], then['value'])} when {when}."
            )
            relevant = {c["field"] for c in case.get("when", [])}
            snapshot = _runtime_clause(runtime, relevant)
            if snapshot:
                sentences.append(snapshot)
            sentences.append(
                f"Put that {format_field_value(then['field'], then['value'])} case back into {workflow}."
            )
        else:
            empty = [friendly_name(field) for field, value in fault.observed.items() if value is None]
            target = empty[0] if empty else "its output field"
            sentences.append(f"{workflow} did not fill in {target}, even though the deal already has the values it reads.")
            sentences.append(f"Check {workflow} and restore the rule that writes {target}.")
        return " ".join(sentences)

    changed = _changed_thresholds(current_rule, healthy) if healthy else []
    wrote = ", ".join(
        f"{friendly_name(field)} to {format_field_value(field, value)}"
        for field, value in fault.predicted.items()
    )
    if changed:
        live, baseline = changed[0]
        field = live["field"]
        sentences.append(
            f"{workflow} only fires when {_phrase_condition(live)}, "
            f"so it set {wrote}."
        )
        snapshot_fields = {field}
        snapshot_fields.update(cond["field"] for cond in current_rule.get("rule", {}).get("all", []))
        snapshot = _runtime_clause(runtime, snapshot_fields)
        if snapshot:
            sentences.append(snapshot)
        sentences.append(
            f"Change that {friendly_name(field)} rule back to "
            f"{_phrase_condition(baseline)} so it matches finance policy."
        )
        return " ".join(sentences)

    sentences.append(f"{workflow} set {wrote}, which is not what policy requires.")
    if "else" in current_rule.get("rule", {}):
        sentences.append("Its conditions did not match this deal, so it took the fallback path.")
    sentences.append(f"Update {workflow} so it produces the required result for deals like this one.")
    return " ".join(sentences)
