"""AI主播大脑 - 会话历史管理"""

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

MAX_HISTORY_PER_SESSION = 50


@dataclass
class MessageEntry:
    role: str
    content: str
    sender: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "sender": self.sender,
            "timestamp": self.timestamp,
        }


class SessionHistory:
    def __init__(self, max_entries: int = MAX_HISTORY_PER_SESSION):
        self._messages: list[MessageEntry] = []
        self._max_entries = max_entries
        self._answered_ids: set[str] = set()

    def add(self, role: str, content: str, sender: str = "") -> MessageEntry:
        entry = MessageEntry(role=role, content=content, sender=sender)
        self._messages.append(entry)
        if len(self._messages) > self._max_entries:
            self._messages = self._messages[-self._max_entries:]
        return entry

    def add_user_message(self, content: str, sender: str = "", msg_id: str = "") -> MessageEntry:
        if msg_id:
            self._answered_ids.add(msg_id)
        return self.add("user", content, sender)

    def add_assistant_message(self, content: str) -> MessageEntry:
        return self.add("assistant", content, "AI主播")

    def is_answered(self, msg_id: str) -> bool:
        return msg_id in self._answered_ids

    def get_recent(self, n: int = 10) -> list[MessageEntry]:
        return self._messages[-n:]

    def get_recent_dicts(self, n: int = 10) -> list[dict]:
        return [m.to_dict() for m in self.get_recent(n)]

    def clear(self):
        self._messages.clear()
        self._answered_ids.clear()

    @property
    def message_count(self) -> int:
        return len(self._messages)


_sessions: dict[str, SessionHistory] = {}


def get_session(room_id: int | str) -> SessionHistory:
    key = str(room_id)
    if key not in _sessions:
        _sessions[key] = SessionHistory()
    return _sessions[key]


def clear_session(room_id: int | str):
    key = str(room_id)
    if key in _sessions:
        _sessions[key].clear()
