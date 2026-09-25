"""Context-aware conversation tracking service."""
from dataclasses import dataclass, field
from datetime import datetime, timezone


from model.query_models import StructuredIntent


@dataclass
class PendingClarification:
    message: str
    conversation_id: str | None
    user_role: str | None = "user"


@dataclass
class PendingClarificationIntent:
    request_id: str
    conversation_id: str | None
    original_message: str
    intent: StructuredIntent
    user_role: str | None = "user"


import threading
from uuid import uuid4

SHARED_FORBIDDEN_IDS = {"default", "global", "public", "shared"}


@dataclass
class ConversationStore:
    clarifications: dict[str, PendingClarification] = field(default_factory=dict)
    pending_intents: dict[str, PendingClarificationIntent] = field(default_factory=dict)
    history: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    active_tables: dict[str, str] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def sanitize_id(self, conversation_id: str | None) -> str | None:
        if not conversation_id:
            return None
        clean_id = conversation_id.strip()
        if clean_id.lower() in SHARED_FORBIDDEN_IDS:
            return f"conv_{uuid4().hex[:12]}"
        return clean_id

    def remember(self, conversation_id: str | None, message: str, sql: str | None, table: str | None = None) -> None:
        cid = self.sanitize_id(conversation_id)
        if cid:
            with self._lock:
                entry = {
                    "message": message,
                    "sql": sql or "",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                self.history.setdefault(cid, []).append(entry)
                if table:
                    self.active_tables[cid] = table

    def get_active_table(self, conversation_id: str | None) -> str | None:
        cid = self.sanitize_id(conversation_id)
        if not cid:
            return None
        with self._lock:
            return self.active_tables.get(cid)

    def get_last_sql(self, conversation_id: str | None) -> str | None:
        cid = self.sanitize_id(conversation_id)
        if not cid or cid not in self.history:
            return None
        with self._lock:
            items = self.history.get(cid, [])
            return items[-1]["sql"] if items else None

    def get_and_pop_pending_intent_for_conversation(self, conversation_id: str | None) -> PendingClarificationIntent | None:
        cid = self.sanitize_id(conversation_id)
        with self._lock:
            if not self.pending_intents:
                return None
            if cid:
                for req_id, pending in list(self.pending_intents.items()):
                    if self.sanitize_id(pending.conversation_id) == cid:
                        return self.pending_intents.pop(req_id)
            # Fallback: if no match by cid or cid is None/unmatched, pop the most recent pending intent
            req_id = list(self.pending_intents.keys())[-1]
            return self.pending_intents.pop(req_id)


