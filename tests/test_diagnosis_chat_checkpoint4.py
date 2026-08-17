"""Checkpoint 4: always-on Diagnose Chat page (source + store wiring)."""

from pathlib import Path

from dashboard.diagnose.chat import NONE_TICKET, ticket_select_options
from diagnosis.conversations import ConversationStore
from diagnosis.incidents import load_incidents


RENDER = Path("dashboard/diagnose/render.py").read_text(encoding="utf-8")
CHAT = Path("dashboard/diagnose/chat.py").read_text(encoding="utf-8")


def test_chat_is_not_gated_on_diagnosis():
    assert "Run diagnosis on this ticket first" not in RENDER
    assert "Run diagnosis on this ticket first" not in CHAT
    assert "st.chat_input" in CHAT
    assert "frames[-1].log_lines" not in RENDER
    assert "frames[-1].log_lines" not in CHAT


def test_ticket_dropdown_includes_none():
    assert "NONE_TICKET" in CHAT
    assert NONE_TICKET == "None"
    options = ticket_select_options(list(load_incidents()))
    assert options[0] == "None"
    assert "INC-1042" in options


def test_ensure_state_inits_diagnose_store_not_implement_history():
    ensure = RENDER.split("def _ensure_state")[1].split("def _lifecycle_status")[0]
    assert "ensure_conversation_store" in ensure
    assert "load_graph" in ensure
    assert "chat_history" not in ensure
    assert "diagnose_conversations" in CHAT
    store = ConversationStore()
    assert store.active_thread().messages == []


def test_chat_uses_grounded_answer_turn():
    assert "answer_turn" in CHAT
    assert "intent_classifier" not in CHAT
