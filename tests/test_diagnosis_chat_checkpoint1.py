"""Checkpoint 1: Diagnose conversation store (no Streamlit, no Claude)."""

from pathlib import Path

from diagnosis.conversations import ConversationStore, DEFAULT_TITLE


def test_new_store_has_one_empty_active_thread():
    store = ConversationStore()
    threads = store.list_threads()
    assert len(threads) == 1
    active = store.active_thread()
    assert active is threads[0]
    assert active.incident_id is None
    assert active.messages == []
    assert active.title == DEFAULT_TITLE


def test_two_threads_restore_independently():
    store = ConversationStore()
    thread_a = store.active_thread()
    store.append_message("user", "Why is deal stage wrong?")
    store.append_message("assistant", "Deal stage automation writes it.")

    thread_b = store.new_thread()
    assert store.active_thread().id == thread_b.id
    store.append_message("user", "What is pricing segment?")
    store.append_message("assistant", "It is derived from customer tier.")

    store.switch_thread(thread_a.id)
    restored = store.active_thread()
    assert restored.id == thread_a.id
    assert [m.content for m in restored.messages] == [
        "Why is deal stage wrong?",
        "Deal stage automation writes it.",
    ]
    assert store.get_thread(thread_b.id).messages[0].content == "What is pricing segment?"


def test_set_incident_keeps_messages():
    store = ConversationStore()
    store.append_message("user", "Tell me about discount governance")
    store.append_message("assistant", "It writes approval required.")
    before = list(store.active_thread().messages)
    store.set_incident("INC-1188")
    thread = store.active_thread()
    assert thread.incident_id == "INC-1188"
    assert thread.messages == before
    store.set_incident(None)
    assert store.active_thread().messages == before
    assert store.active_thread().incident_id is None


def test_title_updates_after_first_user_message():
    store = ConversationStore()
    store.append_message("user", "Why did Cord inspect deal stage automation first?")
    assert "deal stage automation" in store.active_thread().title.lower()
    store.set_incident("INC-1042")
    assert store.active_thread().title.startswith("INC-1042")
    store.append_message("assistant", "It writes deal stage.")
    assert store.active_thread().title.startswith("INC-1042")


def test_conversations_module_does_not_touch_implement_chat():
    source = Path("diagnosis/conversations.py").read_text(encoding="utf-8")
    assert "import streamlit" not in source
    assert "from streamlit" not in source
    assert "dashboard.state" not in source
    assert "st.session_state" not in source
    assert "from dashboard" not in source
