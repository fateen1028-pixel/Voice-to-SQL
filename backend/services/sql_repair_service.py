"""Bounded automatic SQL repair service."""
import logging
import re
from typing import Callable

logger = logging.getLogger(__name__)


class SqlRepairService:
    def __init__(self, max_attempts: int = 3) -> None:
        self.max_attempts = max_attempts

    def repair_query(
        self,
        original_sql: str,
        issues: list[str],
        schema: dict[str, dict],
        message: str,
        repair_fn: Callable[[str, list[str], dict[str, dict]], str] | None = None,
    ) -> tuple[str, list[str]]:
        current_sql = original_sql
        current_issues = issues
        attempts = 0

        while current_issues and attempts < self.max_attempts:
            attempts += 1
            logger.info("SQL Repair attempt %d/%d for SQL: %s with issues: %s", attempts, self.max_attempts, current_sql, current_issues)

            if repair_fn:
                try:
                    repaired = repair_fn(current_sql, current_issues, schema)
                    if repaired and repaired != current_sql:
                        current_sql = repaired
                        break
                except Exception as exc:
                    logger.warning("Custom repair function failed: %s", exc)

            # Heuristic deterministic repairs
            repaired = self._apply_deterministic_repairs(current_sql, current_issues, schema, message)
            if repaired == current_sql:
                break
            current_sql = repaired

        return current_sql, current_issues

    def _apply_deterministic_repairs(self, sql: str, issues: list[str], schema: dict[str, dict], message: str) -> str:
        repaired = sql

        for issue in issues:
            # Repair date range >= without upper bound
            if "uses '>=' without an upper bound" in issue:
                yr_match = re.search(r"\b(20\d{2})\b", message)
                if yr_match:
                    yr = yr_match.group(1)
                    next_yr = str(int(yr) + 1)
                    col_match = re.search(rf"([a-z0-9_]+)\s*>=\s*'{yr}-01-01'", repaired, re.IGNORECASE)
                    date_col = col_match.group(1) if col_match else None
                    if not date_col and schema:
                        for meta in schema.values():
                            d_col = next((c["name"] for c in meta.get("columns", []) if any(term in c["name"].lower() for term in ("date", "created", "joined", "timestamp"))), None)
                            if d_col:
                                date_col = d_col
                                break
                    date_col = date_col or "created_at"
                    repaired = re.sub(
                        rf"(>=\s*'{yr}-01-01')",
                        rf"\1 AND {date_col} < '{next_yr}-01-01'",
                        repaired,
                        flags=re.IGNORECASE,
                    )


            # Repair missing LIMIT for top-N
            if "missing a LIMIT clause" in issue or "requires a LIMIT" in issue:
                top_match = re.search(r"\b(?:top|first)\s+(\d+)\b", message, re.I)
                n = top_match.group(1) if top_match else "10"
                if "LIMIT" not in repaired.upper():
                    repaired = repaired.rstrip(";") + f" LIMIT {n}"

            # Repair trailing semicolon in subquery
            if "Multiple SQL statements" in issue:
                repaired = re.sub(r";+", ";", repaired).strip().rstrip(";")

        return repaired
