"""Master natural-language to database query pipeline orchestrator."""
import logging
from uuid import uuid4

from config.settings import Settings
from db.connection import Database
from db.query_runner import estimate_mutation_affected_rows, run_mutation, run_select
from model.query_models import PendingExecution
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

    def process(self, message: str, conversation_id: str | None = None, prior_sql: str | None = None, user_role: str | None = "user", input_type: str = "text") -> dict:
        request_id = str(uuid4())

        # 1. Prompt Injection Defense
        if self.intent.is_prompt_injection(message):
            audit_id = self.audit.log(request_id, input_type, message, None, "BLOCKED_PROMPT_INJECTION", user_role=user_role)
            return {
                "status": "SECURITY_VIOLATION",
                "request_id": request_id,
                "audit_id": audit_id,
                "message": "Request blocked by security firewall: Potential prompt injection detected.",
            }

        # 2. Ambiguity & Clarification Check
        clarification_result = self.intent.detect_clarification(message, self.schema.get())
        if clarification_result:
            question, options = clarification_result
            audit_id = self.audit.log(request_id, input_type, message, None, "CLARIFICATION_REQUIRED", user_role=user_role)
            return {
                "status": "CLARIFICATION_REQUIRED",
                "request_id": request_id,
                "audit_id": audit_id,
                "question": question,
                "options": options,
            }

        # 3. Dynamic Relevant Schema Retrieval
        relevant_schema = self.schema.relevant(message)

        # 4. SQL Generation
        try:
            sql = self.generator.generate(message, relevant_schema, prior_sql=prior_sql, is_postgres=self.database.is_postgres)
        except SqlGenerationError as exc:
            audit_id = self.audit.log(request_id, input_type, message, None, "GENERATION_FAILED", user_role=user_role)
            return {
                "status": "FAILED",
                "request_id": request_id,
                "audit_id": audit_id,
                "message": str(exc),
            }

        # 5. Validation (Syntax + Schema + EXPLAIN + Role Permissions)
        val = self.validator.validate(sql, self.schema.get(), allow_ddl=self.settings.allow_ddl, user_role=user_role)
        logic_issues = self.logic.validate(message, sql)
        val["issues"].extend(logic_issues)
        val["valid"] = len(val["issues"]) == 0

        # 6. Automatic Repair Loop (if validation or logic fails)
        if not val["valid"]:
            repaired_sql, _ = self.repair.repair_query(sql, val["issues"], relevant_schema, message)
            if repaired_sql != sql:
                sql = repaired_sql
                val = self.validator.validate(sql, self.schema.get(), allow_ddl=self.settings.allow_ddl, user_role=user_role)
                val["issues"].extend(self.logic.validate(message, sql))
                val["valid"] = len(val["issues"]) == 0

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

        # 7. Execution Path based on Query Firewall
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
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "validation": val,
                "explanation": self.results.explain(rows, message),
                "visualization": self.visualization.recommend(columns, rows),
            }

        # 8. Database-modifying query (INSERT / UPDATE / DELETE) -> Require Explicit Confirmation
        token = f"tok_{uuid4().hex}"
        self.pending_executions[token] = PendingExecution(
            sql=sql,
            operation=operation,
            conversation_id=conversation_id,
            user_role=user_role,
        )

        affected_est = self.execution.estimate_affected_rows(sql, operation)

        if operation == "DELETE":
            msg = f"🚨 DELETE OPERATION: This action will permanently delete records. Please confirm before execution."
        else:
            msg = f"This operation will modify database records ({operation}). Please confirm before execution."

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

    def confirm(self, confirmation_token: str) -> dict:
        pending = self.pending_executions.pop(confirmation_token, None)
        if not pending:
            return {
                "status": "INVALID_CONFIRMATION",
                "message": "Confirmation token is invalid, expired, or already used.",
            }

        try:
            affected = self.execution.execute_mutation(pending.sql)
        except Exception:
            return {
                "status": "EXECUTION_FAILED",
                "sql": pending.sql,
                "message": "The confirmed query could not be executed safely on the database.",
            }

        return {
            "status": "SUCCESS",
            "sql": pending.sql,
            "operation": pending.operation,
            "row_count": affected,
            "message": f"Successfully executed {pending.operation}. {affected} record(s) affected.",
        }

    def get_request_by_id(self, request_id: str) -> dict | None:
        return self.audit.get_by_request_id(request_id)
