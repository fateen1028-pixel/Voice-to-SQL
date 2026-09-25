from dataclasses import dataclass, field
from typing import Any


from datetime import datetime, timezone


@dataclass
class ValidationResult:
    valid: bool
    issues: list[str] = field(default_factory=list)
    operation: str = "UNKNOWN"
    tables: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)


@dataclass
class StructuredIntent:
    operation: str  # SELECT, DELETE, UPDATE, INSERT, UNKNOWN
    table: str | None = None
    target: str | None = None
    vague_terms: list[str] = field(default_factory=list)
    ordering_column: str | None = None
    ordering_direction: str | None = "DESC"
    ordering_definition: str | None = None
    filter_column: str | None = None
    filter_value: Any = None
    set_columns: dict[str, Any] = field(default_factory=dict)
    metric: str | None = None
    limit: int | None = None
    resolved_slots: dict[str, Any] = field(default_factory=dict)
    missing_slots: list[str] = field(default_factory=list)
    is_complete: bool = False
    raw_message: str = ""


@dataclass
class PendingExecution:
    sql: str
    operation: str
    request_id: str
    session_id: str | None = None
    conversation_id: str | None = None
    user_role: str | None = "user"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    structured_intent: StructuredIntent | None = None
    sql_hash: str = ""
    used: bool = False


