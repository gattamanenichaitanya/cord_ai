"""Grounded Diagnose chat reply. Claude paraphrases a backend evidence pack only."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from diagnosis.chat_context import build_chat_evidence
from diagnosis.conversations import ChatMessage
from diagnosis.graph import SystemGraph
from diagnosis.logutil import emit
from diagnosis.loop import DiagnosisResult
from diagnosis.prose import plain_user_prose

HISTORY_LIMIT = 6

NO_TICKET_RERUN = "Select a ticket before running diagnosis. Diagnosis is not started from a generic chat."

CHAT_RESTRICTIONS = {
    "use_only_this_json": True,
    "do_not_invent_components_fields_or_values": True,
    "do_not_use_markdown_backticks_or_latex": True,
}

CHAT_SYSTEM_PROMPT = """You answer an operations user about a configuration graph or a diagnosis.

Use ONLY the evidence JSON. Every component, field, number, and value you mention must appear there.
Do not invent workflows, properties, stages, systems, or runtime values.
If the evidence cannot answer the question, say that clearly. Do not guess.
Do not use markdown, backticks, bold, or LaTeX.
Write ordinary English. Use how_to_refer strings as given (sentence case).
Do not mention action ids, semantic_role, or planner JSON keys.
Two to four short sentences.
"""

RERUN_PHRASES = (
    "rerun",
    "re-run",
    "diagnose again",
    "run diagnosis",
    "run diagnose",
    "diagnose this ticket",
)


class ChatIntent(str, Enum):
    EXPLAIN = "explain"
    RERUN = "rerun"


class ChatReplyCopy(BaseModel):
    answer: str = Field(min_length=1)


@dataclass
class ChatTurn:
    intent: ChatIntent
    text: str
    evidence: dict[str, Any] | None
    result: DiagnosisResult | None


def classify_chat_intent(question: str) -> ChatIntent:
    text = question.lower()
    if any(phrase in text for phrase in RERUN_PHRASES):
        return ChatIntent.RERUN
    return ChatIntent.EXPLAIN


def _history_blob(prior_messages: Sequence[ChatMessage] | Sequence[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for message in prior_messages[-HISTORY_LIMIT:]:
        if isinstance(message, ChatMessage):
            rows.append({"role": message.role, "content": message.content})
        else:
            rows.append({"role": message["role"], "content": message["content"]})
    return rows


def _paraphrase(client: Any, *, question: str, evidence: dict[str, Any], history: list[dict[str, str]]) -> str:
    payload = {
        "restrictions": CHAT_RESTRICTIONS,
        "recent_messages": history,
        "question": question,
        "evidence": evidence,
    }
    prompt = "Answer from this evidence only.\n\n" + json.dumps(payload, indent=2, default=str)
    copy, _meta = client.call_with_structured_output(
        prompt=prompt,
        output_model=ChatReplyCopy,
        system_prompt=CHAT_SYSTEM_PROMPT,
        max_tokens=512,
    )
    return plain_user_prose(copy.answer)


def answer_turn(
    question: str,
    *,
    incident_id: str | None = None,
    result: DiagnosisResult | None = None,
    prior_messages: Sequence[ChatMessage] | Sequence[dict[str, str]] = (),
    client: Any,
    run_diagnosis: Callable[[str], DiagnosisResult] | None = None,
    graph: SystemGraph | None = None,
) -> ChatTurn:
    intent = classify_chat_intent(question)
    history = _history_blob(prior_messages)
    emit(
        f"Chat turn intent={intent.value} ticket={incident_id or 'none'} question={question[:120]}"
    )

    if intent is ChatIntent.RERUN:
        if not incident_id:
            return ChatTurn(intent=intent, text=NO_TICKET_RERUN, evidence=None, result=result)
        if run_diagnosis is None:
            raise ValueError("run_diagnosis is required to rerun a ticket")
        result = run_diagnosis(incident_id)

    evidence = build_chat_evidence(question, incident_id=incident_id, result=result, graph=graph)
    text = _paraphrase(client, question=question, evidence=evidence, history=history)
    return ChatTurn(intent=intent, text=text, evidence=evidence, result=result)
