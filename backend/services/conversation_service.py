"""Context-aware conversation tracking service."""
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PendingClarification:
    message: str
    conversation_id: str | None
    user_role: str | None = "user"


@dataclass
class ConversationStore:
    clarifications: dict[str, PendingClarification] = field(default_factory=dict)
    history: dict[str, list[dict[str, str]]] = field(default_factory=dict)

    def remember(self, conversation_id: str | None, message: str, sql: str | None) -> None:
        if conversation_id:
            entry = {
                "message": message,
                "sql": sql or "",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self.history.setdefault(conversation_id, []).append(entry)

    def get_last_sql(self, conversation_id: str | None) -> str | None:
        if not conversation_id or conversation_id not in self.history:
            return None
        items = self.history[conversation_id]
        return items[-1]["sql"] if items else None
