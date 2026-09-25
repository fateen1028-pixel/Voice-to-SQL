"""Query execution safety service isolating database access and execution validation."""
import logging
from typing import Any
from db.connection import Database
from db.query_runner import estimate_mutation_affected_rows, run_mutation, run_select

logger = logging.getLogger(__name__)


class QueryExecutionService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def execute_select(self, sql: str, params: tuple | list | None = None) -> tuple[list[str], list[dict[str, Any]]]:
        """Execute a validated SELECT query and return (columns, rows)."""
        try:
            return run_select(self.database, sql, params)
        except Exception as exc:
            logger.error("Failed to execute SELECT query '%s': %s", sql, exc)
            raise RuntimeError(f"Database execution error: {exc}") from exc

    def execute_mutation(self, sql: str, params: tuple | list | None = None) -> int:
        """Execute a validated INSERT, UPDATE, or DELETE query and return affected row count."""
        try:
            return run_mutation(self.database, sql, params)
        except Exception as exc:
            logger.error("Failed to execute mutation query '%s': %s", sql, exc)
            raise RuntimeError(f"Database execution error: {exc}") from exc

    def estimate_affected_rows(self, sql: str, operation: str) -> int | None:
        """Estimate the number of affected rows for UPDATE/DELETE operations without mutating data."""
        return estimate_mutation_affected_rows(self.database, sql, operation)
