from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationResult:
    valid: bool
    issues: list[str] = field(default_factory=list)
    operation: str = "UNKNOWN"
    tables: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)


@dataclass
class PendingExecution:
    sql: str
    operation: str
    conversation_id: str | None = None
    user_role: str | None = "user"
