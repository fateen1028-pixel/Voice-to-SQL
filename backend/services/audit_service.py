"""Query audit logging service."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from uuid import uuid4

logger = logging.getLogger("audit")


@dataclass
class AuditRecord:
    audit_id: str
    request_id: str
    timestamp: str
    input_type: str
    user_request: str
    sql: str | None
    validation_status: str
    confirmation_status: str | None
    affected_rows: int | None
    user_role: str | None


class AuditService:
    def __init__(self) -> None:
        self.logs: list[AuditRecord] = []

    def log(
        self,
        request_id: str,
        input_type: str,
        user_request: str,
        sql: str | None,
        validation_status: str,
        confirmation_status: str | None = None,
        affected_rows: int | None = None,
        user_role: str | None = "user",
    ) -> str:
        audit_id = f"aud_{uuid4().hex[:12]}"
        record = AuditRecord(
            audit_id=audit_id,
            request_id=request_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            input_type=input_type,
            user_request=self._sanitize(user_request),
            sql=sql,
            validation_status=validation_status,
            confirmation_status=confirmation_status,
            affected_rows=affected_rows,
            user_role=user_role,
        )
        self.logs.append(record)
        logger.info("AUDIT LOG [%s] req=%s type=%s valid=%s op=%s", audit_id, request_id, input_type, validation_status, record.sql)
        return audit_id

    def get_by_request_id(self, request_id: str) -> dict | None:
        for rec in reversed(self.logs):
            if rec.request_id == request_id or rec.audit_id == request_id:
                return {
                    "audit_id": rec.audit_id,
                    "request_id": rec.request_id,
                    "timestamp": rec.timestamp,
                    "input_type": rec.input_type,
                    "user_request": rec.user_request,
                    "sql": rec.sql,
                    "validation_status": rec.validation_status,
                    "confirmation_status": rec.confirmation_status,
                    "affected_rows": rec.affected_rows,
                    "user_role": rec.user_role,
                }
        return None

    def _sanitize(self, text: str) -> str:
        # Redact potential sensitive tokens or passwords
        return text.replace("password", "[REDACTED]").replace("secret", "[REDACTED]")
