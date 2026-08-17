"""Diagnose chat thread store. Pure Python; no Streamlit, no Implement session chat.

Rollback: see diagnosis/CHAT_BUILD_ROLLBACK.txt (git tag pre-diagnose-chat).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

TITLE_MAX = 48
DEFAULT_TITLE = "New chat"


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class ConversationThread:
    id: str
    title: str = DEFAULT_TITLE
    incident_id: str | None = None
    messages: list[ChatMessage] = field(default_factory=list)


def _first_user_snippet(thread: ConversationThread) -> str:
    for message in thread.messages:
        if message.role == "user" and message.content.strip():
            snippet = " ".join(message.content.split())
            if len(snippet) > TITLE_MAX:
                return snippet[: TITLE_MAX - 3].rstrip() + "..."
            return snippet
    return ""


def refresh_title(thread: ConversationThread) -> None:
    snippet = _first_user_snippet(thread)
    if thread.incident_id and snippet:
        thread.title = f"{thread.incident_id} · {snippet}"
    elif thread.incident_id:
        thread.title = thread.incident_id
    elif snippet:
        thread.title = snippet
    else:
        thread.title = DEFAULT_TITLE


class ConversationStore:
    """Newest threads first. Starts with one empty active thread."""

    def __init__(self) -> None:
        self._threads: dict[str, ConversationThread] = {}
        self._order: list[str] = []
        self.active_id: str | None = None
        self.new_thread()

    def new_thread(self) -> ConversationThread:
        thread = ConversationThread(id=str(uuid4()))
        self._threads[thread.id] = thread
        self._order.insert(0, thread.id)
        self.active_id = thread.id
        return thread

    def list_threads(self) -> list[ConversationThread]:
        return [self._threads[thread_id] for thread_id in self._order]

    def list_saved_threads(self) -> list[ConversationThread]:
        """Threads with messages — empty drafts do not appear in the sidebar."""
        return [thread for thread in self.list_threads() if thread.messages]

    def start_new_chat(self) -> ConversationThread:
        """Reuse an empty active draft, otherwise open a fresh thread."""
        active = self.active_thread()
        if active.messages:
            self.new_thread()
        self._drop_empty_inactive()
        return self.active_thread()

    def _drop_empty_inactive(self) -> None:
        keep: list[str] = []
        for thread_id in self._order:
            thread = self._threads[thread_id]
            if thread.messages or thread.id == self.active_id:
                keep.append(thread_id)
            else:
                del self._threads[thread_id]
        self._order = keep

    def get_thread(self, thread_id: str) -> ConversationThread:
        if thread_id not in self._threads:
            raise KeyError(f"Unknown conversation: {thread_id}")
        return self._threads[thread_id]

    def active_thread(self) -> ConversationThread:
        if self.active_id is None:
            raise RuntimeError("No active conversation")
        return self.get_thread(self.active_id)

    @classmethod
    def revive(cls, existing: object | None) -> ConversationStore:
        """Rebuild after a code reload so Streamlit session objects pick up new methods."""
        if isinstance(existing, cls) and hasattr(existing, "list_saved_threads"):
            return existing
        revived = cls()
        threads = getattr(existing, "_threads", None)
        order = getattr(existing, "_order", None)
        if not threads or not order:
            return revived
        revived._threads = dict(threads)
        revived._order = list(order)
        revived.active_id = getattr(existing, "active_id", None)
        if revived.active_id not in revived._threads:
            revived.active_id = revived._order[0]
        return revived

    def switch_thread(self, thread_id: str) -> ConversationThread:
        thread = self.get_thread(thread_id)
        self.active_id = thread.id
        return thread

    def append_message(
        self,
        role: str,
        content: str,
        *,
        thread_id: str | None = None,
    ) -> ChatMessage:
        if role not in {"user", "assistant"}:
            raise ValueError(f"Unsupported message role: {role}")
        thread = self.get_thread(thread_id) if thread_id else self.active_thread()
        message = ChatMessage(role=role, content=content)
        thread.messages.append(message)
        refresh_title(thread)
        return message

    def set_incident(self, incident_id: str | None, *, thread_id: str | None = None) -> ConversationThread:
        thread = self.get_thread(thread_id) if thread_id else self.active_thread()
        thread.incident_id = incident_id
        refresh_title(thread)
        return thread
