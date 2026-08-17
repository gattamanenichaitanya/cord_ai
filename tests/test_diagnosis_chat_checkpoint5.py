"""Checkpoint 5: sidebar threads and rerun-from-chat."""

from pathlib import Path

from dashboard.diagnose.chat import rerun_active_thread
from diagnosis.conversations import ConversationStore
from diagnosis.loop import DiagnosisResult
from tests.test_diagnosis_chat_checkpoint3 import StubClient


RENDER = Path("dashboard/diagnose/render.py").read_text(encoding="utf-8")
CHAT = Path("dashboard/diagnose/chat.py").read_text(encoding="utf-8")


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


def test_sidebar_chat_starts_new_conversation_not_a_button():
    sidebar = RENDER.split("def render_diagnose_sidebar")[1].split("def render_diagnose()")[0]
    assert 'button("New chat"' not in sidebar
    assert "diag_new_chat" not in sidebar
    assert "start_new_chat" in sidebar
    assert "list_saved_threads" in sidebar
    assert 'type="tertiary"' in sidebar
    assert "recent_chats" not in sidebar
    assert "Rerun diagnosis" in CHAT


def test_empty_draft_is_not_listed_until_there_are_messages():
    store = ConversationStore()
    assert store.list_saved_threads() == []
    store.append_message("user", "What writes deal stage?")
    assert len(store.list_saved_threads()) == 1
    store.start_new_chat()
    assert store.active_thread().messages == []
    assert len(store.list_saved_threads()) == 1
    store.start_new_chat()
    assert len(store.list_threads()) == 2


def test_switching_threads_restores_messages():
    store = ConversationStore()
    first = store.active_thread()
    store.append_message("user", "What writes deal stage?")
    store.append_message("assistant", "Deal stage automation.")
    second = store.new_thread()
    store.append_message("user", "What is pricing segment?")
    store.switch_thread(first.id)
    assert [m.content for m in store.active_thread().messages] == [
        "What writes deal stage?",
        "Deal stage automation.",
    ]
    store.switch_thread(second.id)
    assert store.active_thread().messages[0].content == "What is pricing segment?"


def test_rerun_with_ticket_calls_runner_and_appends():
    store = ConversationStore()
    store.set_incident("INC-1042")
    called = []

    def runner(incident_id: str) -> DiagnosisResult:
        called.append(incident_id)
        return _diagnosed()

    client = StubClient(answer="Derive pricing segment is the root cause.")
    ran = rerun_active_thread(store, client=client, run_diagnosis=runner, results={})
    assert ran is True
    assert called == ["INC-1042"]
    assert store.active_thread().messages[-1].role == "assistant"
    assert "pricing" in store.active_thread().messages[-1].content.lower()


def test_revive_upgrades_stale_store_without_dropping_messages():
    class Legacy:
        def __init__(self):
            store = ConversationStore()
            store.append_message("user", "Keep this")
            self._threads = store._threads
            self._order = store._order
            self.active_id = store.active_id

    revived = ConversationStore.revive(Legacy())
    assert hasattr(revived, "list_saved_threads")
    assert revived.list_saved_threads()[0].messages[0].content == "Keep this"


def test_rerun_without_ticket_does_not_call_runner():
    store = ConversationStore()
    called = []

    def runner(incident_id: str) -> DiagnosisResult:
        called.append(incident_id)
        return _diagnosed()

    ran = rerun_active_thread(store, client=StubClient(), run_diagnosis=runner, results={})
    assert ran is False
    assert called == []
    assert store.active_thread().messages == []
