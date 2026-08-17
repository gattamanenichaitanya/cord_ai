"""Checkpoint 3: grounded chat reply pipeline. Stub Claude only."""

from diagnosis.chat_reply import (
    CHAT_SYSTEM_PROMPT,
    NO_TICKET_RERUN,
    ChatIntent,
    ChatReplyCopy,
    answer_turn,
    classify_chat_intent,
)
from diagnosis.conversations import ChatMessage
from diagnosis.loop import DiagnosisResult


class StubClient:
    def __init__(self, answer: str = "Deal stage automation writes deal stage."):
        self.answer = answer
        self.calls = 0
        self.prompts: list[str] = []
        self.system_prompts: list[str] = []

    def call_with_structured_output(self, **kwargs):
        self.calls += 1
        self.prompts.append(kwargs["prompt"])
        self.system_prompts.append(kwargs.get("system_prompt", ""))
        return ChatReplyCopy(answer=self.answer), {}


def _diagnosed() -> DiagnosisResult:
    return DiagnosisResult(
        status="diagnosed",
        root_cause_node="derive_pricing_segment",
        confidence=0.9,
        reason="missing write",
        record_id="DEAL-4821",
        incident_id="INC-1042",
        discrepancy={},
        visited_nodes=["derive_pricing_segment"],
        recommendation="Add an Enterprise case.",
        trace=[],
    )


def test_system_prompt_forbids_invention_and_markdown():
    assert "Do not invent" in CHAT_SYSTEM_PROMPT
    assert "markdown" in CHAT_SYSTEM_PROMPT.lower()
    assert "backticks" in CHAT_SYSTEM_PROMPT.lower()
    assert "use ONLY the evidence JSON" in CHAT_SYSTEM_PROMPT or "ONLY the evidence JSON" in CHAT_SYSTEM_PROMPT


def test_explain_without_ticket_still_calls_claude():
    client = StubClient()
    turn = answer_turn(
        "What does deal stage automation do?",
        incident_id=None,
        result=None,
        client=client,
    )
    assert turn.intent is ChatIntent.EXPLAIN
    assert client.calls == 1
    assert turn.result is None
    assert "deal_stage_automation" in client.prompts[0]
    assert turn.evidence is not None
    assert turn.evidence["diagnosis_run"] is False


def test_rerun_without_ticket_does_not_call_claude():
    client = StubClient()
    called = []

    def runner(_incident_id: str) -> DiagnosisResult:
        called.append(_incident_id)
        return _diagnosed()

    turn = answer_turn(
        "Please rerun diagnosis",
        incident_id=None,
        result=None,
        client=client,
        run_diagnosis=runner,
    )
    assert turn.intent is ChatIntent.RERUN
    assert client.calls == 0
    assert called == []
    assert turn.text == NO_TICKET_RERUN
    assert "ticket" in turn.text.lower()


def test_rerun_with_ticket_calls_runner_then_claude():
    client = StubClient()
    called = []

    def runner(incident_id: str) -> DiagnosisResult:
        called.append(incident_id)
        return _diagnosed()

    turn = answer_turn(
        "Run diagnosis again",
        incident_id="INC-1042",
        result=None,
        client=client,
        run_diagnosis=runner,
    )
    assert called == ["INC-1042"]
    assert client.calls == 1
    assert turn.intent is ChatIntent.RERUN
    assert turn.result is not None
    assert turn.result.root_cause_node == "derive_pricing_segment"
    prompt = client.prompts[0]
    assert "derive_pricing_segment" in prompt
    assert '"diagnosis_run": true' in prompt.lower() or '"diagnosis_run": True' in prompt


def test_follow_up_includes_history_and_fresh_pack():
    client = StubClient()
    first = answer_turn(
        "What does deal stage automation do?",
        incident_id=None,
        result=None,
        client=client,
    )
    history = [
        ChatMessage(role="user", content="What does deal stage automation do?"),
        ChatMessage(role="assistant", content=first.text),
    ]
    second = answer_turn(
        "What writes deal stage?",
        incident_id=None,
        result=None,
        prior_messages=history,
        client=client,
    )
    assert client.calls == 2
    follow = client.prompts[1]
    assert "What does deal stage automation do?" in follow
    assert first.text in follow
    assert '"evidence"' in follow
    assert second.evidence is not None
    assert "canonical_fields" in second.evidence


def test_classify_rerun_phrases():
    assert classify_chat_intent("rerun this") is ChatIntent.RERUN
    assert classify_chat_intent("diagnose again") is ChatIntent.RERUN
    assert classify_chat_intent("Why is deal stage contract sent?") is ChatIntent.EXPLAIN


def test_output_strips_backticks():
    client = StubClient(answer="It writes `deal_stage`.")
    turn = answer_turn("What writes deal stage?", client=client)
    assert "`" not in turn.text
    assert "deal_stage" in turn.text


def test_does_not_use_implement_intent_classifier():
    source = open("diagnosis/chat_reply.py", encoding="utf-8").read()
    assert "intent_classifier" not in source
    assert "dashboard.chat" not in source
