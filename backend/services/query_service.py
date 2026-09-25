from datetime import datetime, timedelta, timezone
from hashlib import sha256
import logging
import re
import threading
from typing import Any
from uuid import uuid4

from config.settings import Settings
from db.connection import Database
from model.query_models import PendingExecution, StructuredIntent
from services.audit_service import AuditService
from services.clarification_service import ClarificationService
from services.intent_service import IntentService
from services.query_execution_service import QueryExecutionService
from services.result_service import ResultService
from services.schema_service import SchemaService
from services.sql_generation_service import SqlGenerationError, SqlGenerationService
from services.sql_logic_service import SqlLogicService
from services.sql_repair_service import SqlRepairService
from services.sql_security_service import SqlSecurityService
from services.sql_validation_service import SqlValidationService
from services.visualization_service import VisualizationService

logger = logging.getLogger(__name__)


class QueryService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings

        self.audit = AuditService()
        self.schema = SchemaService(database)
        self.clarification = ClarificationService(database)
        self.intent = IntentService(self.clarification)
        self.security = SqlSecurityService()
        self.validator = SqlValidationService(database, self.security)
        self.logic = SqlLogicService()
        self.repair = SqlRepairService(max_attempts=settings.max_repair_attempts)
        self.generator = SqlGenerationService(settings)
        self.results = ResultService()
        self.visualization = VisualizationService()
        self.execution = QueryExecutionService(database)

        self.pending_executions: dict[str, PendingExecution] = {}
        self._lock = threading.Lock()

    def process(
        self,
        message: str,
        conversation_id: str | None = None,
        session_id: str | None = None,
        prior_sql: str | None = None,
        active_context_table: str | None = None,
        user_role: str | None = "user",
        input_type: str = "text",
        intent: Any | None = None,
    ) -> dict:
        request_id = str(uuid4())

        # 1. Layered Prompt Injection Defense
        if self.intent.is_prompt_injection(message):
            audit_id = self.audit.log(request_id, input_type, message, None, "BLOCKED_PROMPT_INJECTION", user_role=user_role)
            return {
                "status": "SECURITY_VIOLATION",
                "request_id": request_id,
                "audit_id": audit_id,
                "message": "Request blocked by security firewall: Potential prompt injection detected.",
            }

        # 2. Extract & Evaluate Structured Intent Completeness
        schema_dict = self.schema.get()
        if not intent:
            intent = self.intent.extract_intent(message, schema_dict, active_context_table=active_context_table)

        if not intent.is_complete:
            missing_slot = intent.missing_slots[0]
            question, field, options = self.clarification.build_clarification(intent, missing_slot, schema_dict)
            audit_id = self.audit.log(request_id, input_type, message, None, "CLARIFICATION_REQUIRED", user_role=user_role)
            return {
                "status": "CLARIFICATION_REQUIRED",
                "request_id": request_id,
                "audit_id": audit_id,
                "question": question,
                "field": field,
                "options": options,
                "intent": intent,
            }

        # 3. Dynamic Relevant Schema Retrieval
        relevant_schema = self.schema.relevant(intent.table or message)

        # 4. SQL Generation (Requires complete intent)
        try:
            sql = self.generator.generate(message, relevant_schema, prior_sql=prior_sql, is_postgres=self.database.is_postgres, intent=intent)
        except SqlGenerationError as exc:
            audit_id = self.audit.log(request_id, input_type, message, None, "GENERATION_FAILED", user_role=user_role)
            return {
                "status": "FAILED",
                "request_id": request_id,
                "audit_id": audit_id,
                "message": str(exc),
            }

        # 5. Intent <-> SQL Consistency Gate
        consistency_issue = self._verify_intent_sql_consistency(intent, sql, schema_dict)
        if consistency_issue:
            audit_id = self.audit.log(request_id, input_type, message, sql, "VALIDATION_FAILED", user_role=user_role)
            return {
                "status": "VALIDATION_FAILED",
                "request_id": request_id,
                "audit_id": audit_id,
                "sql": sql,
                "message": f"Generated SQL failed intent consistency check: {consistency_issue}",
            }

        # 6. Validation (AST Syntax + Schema + EXPLAIN + Role Permissions)
        val = self.validator.validate(sql, schema_dict, allow_ddl=self.settings.allow_ddl, user_role=user_role)
        logic_issues = self.logic.validate(message, sql)
        val["issues"].extend(logic_issues)
        val["valid"] = len(val["issues"]) == 0

        # 7. Automatic Repair Loop (re-validation restarts full pipeline)
        if not val["valid"]:
            repaired_sql, _ = self.repair.repair_query(sql, val["issues"], relevant_schema, message)
            if repaired_sql != sql:
                sql = repaired_sql
                consistency_issue = self._verify_intent_sql_consistency(intent, sql, schema_dict)
                if consistency_issue:
                    val["issues"].append(f"Repaired SQL failed intent consistency: {consistency_issue}")
                val = self.validator.validate(sql, schema_dict, allow_ddl=self.settings.allow_ddl, user_role=user_role)
                val["issues"].extend(self.logic.validate(message, sql))
                val["valid"] = (len(val["issues"]) == 0) and not consistency_issue

        if not val["valid"]:
            audit_id = self.audit.log(request_id, input_type, message, sql, "VALIDATION_FAILED", user_role=user_role)
            return {
                "status": "VALIDATION_FAILED",
                "request_id": request_id,
                "audit_id": audit_id,
                "sql": sql,
                "validation": val,
                "message": "Generated query did not pass syntax, schema, or logical validation.",
            }

        operation = val["operation"]

        # 8. Execution Path based on Query Firewall
        if operation == "SELECT":
            try:
                columns, rows = self.execution.execute_select(sql)
            except Exception as exc:
                audit_id = self.audit.log(request_id, input_type, message, sql, "EXECUTION_FAILED", user_role=user_role)
                return {
                    "status": "EXECUTION_FAILED",
                    "request_id": request_id,
                    "audit_id": audit_id,
                    "sql": sql,
                    "message": "The query could not be executed safely on the database.",
                }

            audit_id = self.audit.log(request_id, input_type, message, sql, "SUCCESS", affected_rows=len(rows), user_role=user_role)
            return {
                "status": "SUCCESS",
                "request_id": request_id,
                "audit_id": audit_id,
                "sql": sql,
                "operation": "SELECT",
                "table": (intent.table if intent and hasattr(intent, "table") and intent.table else (val.get("tables", [None])[0] if val.get("tables") else None)),
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "validation": val,
                "explanation": self.results.explain(rows, message),
                "visualization": self.visualization.recommend(columns, rows),
            }

        # 9. Database-modifying query (INSERT / UPDATE / DELETE) -> Strict Safety & Confirmation Token
        upper_sql = sql.upper()
        if operation in ("UPDATE", "DELETE") and " WHERE " not in upper_sql and "WHERE\n" not in upper_sql:
            audit_id = self.audit.log(request_id, input_type, message, sql, "SECURITY_VIOLATION", user_role=user_role)
            return {
                "status": "SECURITY_VIOLATION",
                "request_id": request_id,
                "audit_id": audit_id,
                "sql": sql,
                "message": f"Destructive operation {operation} without a targeted WHERE predicate is blocked by security policy.",
            }

        if operation in ("UPDATE", "DELETE") and re.search(r"WHERE\s+1\s*=\s*1\b", upper_sql):
            audit_id = self.audit.log(request_id, input_type, message, sql, "SECURITY_VIOLATION", user_role=user_role)
            return {
                "status": "SECURITY_VIOLATION",
                "request_id": request_id,
                "audit_id": audit_id,
                "sql": sql,
                "message": f"Destructive operation {operation} with trivial predicate (WHERE 1=1) is blocked by security policy.",
            }

        affected_est = self.execution.estimate_affected_rows(sql, operation)
        if affected_est is not None and affected_est > self.settings.max_mutation_rows:
            audit_id = self.audit.log(request_id, input_type, message, sql, "SECURITY_VIOLATION", user_role=user_role)
            return {
                "status": "SECURITY_VIOLATION",
                "request_id": request_id,
                "audit_id": audit_id,
                "sql": sql,
                "message": f"Operation blocked: Estimated affected records ({affected_est}) exceeds maximum permitted limit ({self.settings.max_mutation_rows}).",
            }

        # Create single-use token with TTL & binding
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self.settings.confirmation_ttl_seconds)
        token = f"tok_{uuid4().hex}"
        sql_hash = sha256(sql.encode("utf-8")).hexdigest()

        pending = PendingExecution(
            sql=sql,
            operation=operation,
            request_id=request_id,
            session_id=session_id,
            conversation_id=conversation_id,
            user_role=user_role,
            created_at=now,
            expires_at=expires_at,
            structured_intent=intent,
            sql_hash=sql_hash,
            used=False,
        )

        with self._lock:
            self.pending_executions[token] = pending

        if operation == "DELETE":
            msg = f"🚨 DELETE OPERATION: Intha action records ah permanent ah delete pannum. Execute panna confirm pannunga."
        else:
            msg = f"Intha operation database records ah modify pannum ({operation}). Execute panna confirm pannunga."

        audit_id = self.audit.log(request_id, input_type, message, sql, "CONFIRMATION_REQUIRED", user_role=user_role)
        return {
            "status": "CONFIRMATION_REQUIRED",
            "request_id": request_id,
            "audit_id": audit_id,
            "confirmation_token": token,
            "sql": sql,
            "operation": operation,
            "estimated_affected_rows": affected_est,
            "message": msg,
            "validation": val,
        }

    def confirm(self, confirmation_token: str, session_id: str | None = None, user_role: str | None = None) -> dict:
        now = datetime.now(timezone.utc)

        with self._lock:
            pending = self.pending_executions.get(confirmation_token)
            if not pending or pending.used:
                return {
                    "status": "INVALID_CONFIRMATION",
                    "message": "Confirmation token is invalid, expired, or already used.",
                }
            # Consume token atomically
            pending.used = True
            self.pending_executions.pop(confirmation_token, None)

        # 1. TTL Expiration Check
        if now > pending.expires_at:
            return {
                "status": "CONFIRMATION_EXPIRED",
                "message": "Confirmation token has expired. Please resubmit your query.",
            }

        # 2. Session Binding Check
        if pending.session_id and session_id and pending.session_id != session_id:
            return {
                "status": "SECURITY_VIOLATION",
                "message": "Confirmation token is bound to a different session.",
            }

        # 3. Pre-Execution Full Re-Validation Pipeline
        schema_dict = self.schema.get()
        if pending.structured_intent:
            consistency_issue = self._verify_intent_sql_consistency(pending.structured_intent, pending.sql, schema_dict)
            if consistency_issue:
                return {
                    "status": "VALIDATION_FAILED",
                    "sql": pending.sql,
                    "message": f"Confirmed query failed intent re-verification: {consistency_issue}",
                }

        effective_role = user_role or pending.user_role or "user"
        val = self.validator.validate(pending.sql, schema_dict, allow_ddl=self.settings.allow_ddl, user_role=effective_role)
        if not val["valid"]:
            return {
                "status": "VALIDATION_FAILED",
                "sql": pending.sql,
                "validation": val,
                "message": "Confirmed query failed pre-execution security re-validation.",
            }

        # 4. Execute exact server-side stored SQL
        try:
            affected = self.execution.execute_mutation(pending.sql)
        except Exception as exc:
            logger.error("Mutation execution failed for token '%s': %s", confirmation_token, exc)
            return {
                "status": "EXECUTION_FAILED",
                "sql": pending.sql,
                "message": "The confirmed query could not be executed safely on the database.",
            }

        self.audit.log(pending.request_id, "confirm", pending.sql, pending.sql, "SUCCESS", affected_rows=affected, user_role=effective_role)
        return {
            "status": "SUCCESS",
            "sql": pending.sql,
            "operation": pending.operation,
            "row_count": affected,
            "message": f"{pending.operation} operation success ah execute aaiduchu. {affected} record(s) affect aachu.",
        }

    def _verify_intent_sql_consistency(self, intent: StructuredIntent, sql: str, schema: dict[str, dict]) -> str | None:
        if not intent or not sql:
            return None

        clean_sql = sql.strip().upper()
        # Verify operation consistency
        if intent.operation == "SELECT" and not clean_sql.startswith("SELECT") and not clean_sql.startswith("WITH"):
            return f"Intent specifies SELECT operation, but SQL begins with {clean_sql.split()[0]}"

        if intent.operation == "INSERT" and "INSERT" not in clean_sql:
            return "Intent specifies INSERT operation, but generated SQL is not an INSERT statement"

        if intent.operation == "DELETE" and "DELETE" not in clean_sql:
            return "Intent specifies DELETE operation, but generated SQL is not a DELETE statement"

        if intent.operation == "UPDATE" and "UPDATE" not in clean_sql:
            return "Intent specifies UPDATE operation, but generated SQL is not an UPDATE statement"

        # Verify target table consistency
        if intent.table and intent.table in schema:
            tbl_lower = intent.table.lower()
            sql_lower = sql.lower()
            if tbl_lower not in sql_lower:
                return f"Intent table '{intent.table}' is missing from generated SQL"

        return None

    def get_request_by_id(self, request_id: str) -> dict | None:
        return self.audit.get_by_request_id(request_id)

