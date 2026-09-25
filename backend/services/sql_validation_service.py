"""Deterministic SQL syntax and schema validation service using sqlglot and EXPLAIN query plan checks."""
import re
import sqlglot
from sqlglot.errors import ParseError

from db.connection import Database
from db.query_runner import explain_query
from services.sql_security_service import SqlSecurityService


class SqlValidationService:
    def __init__(self, database: Database, security: SqlSecurityService) -> None:
        self.database = database
        self.security = security

    def validate(self, sql: str, schema: dict[str, dict], allow_ddl: bool = False, user_role: str | None = "user") -> dict:
        issues = self.security.validate(sql, allow_ddl=allow_ddl, user_role=user_role)
        operation = self.security.operation(sql)

        dialect = "postgres" if self.database.is_postgres else "sqlite"

        # 1. Deterministic SQL syntax parser validation via sqlglot
        try:
            parsed_statements = sqlglot.parse(sql, read=dialect)
            if not parsed_statements or parsed_statements[0] is None:
                issues.append("Malformed SQL statement syntax.")
        except ParseError as exc:
            issues.append(f"SQL syntax error: {str(exc).splitlines()[0]}")

        # 2. Extract referenced tables and validate against schema
        tables_used = set(re.findall(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+([A-Za-z_][\w]*)", sql, re.I))
        unknown_tables = {t for t in tables_used if t.lower() not in {k.lower() for k in schema}}
        if unknown_tables:
            issues.append(f"Unknown table(s) referenced in query: {', '.join(sorted(unknown_tables))}")

        # 3. Column existence check for target tables
        for t_name in tables_used:
            t_meta = schema.get(t_name, {})
            known_cols = {c["name"].lower() for c in t_meta.get("columns", [])}
            if known_cols and operation == "UPDATE":
                # Check SET col = val
                set_matches = re.findall(r"\bSET\s+([A-Za-z_][\w]*)\s*=", sql, re.I)
                for col in set_matches:
                    if col.lower() not in known_cols:
                        issues.append(f"Unknown column '{col}' for table '{t_name}'.")

        # Extract identifiers for summary
        identifiers = set(re.findall(r"\b([A-Za-z_][\w]*)\b", sql))
        keywords = {
            "SELECT", "FROM", "WHERE", "JOIN", "ON", "GROUP", "BY", "ORDER", "ASC", "DESC",
            "LIMIT", "AND", "OR", "AS", "COUNT", "SUM", "AVG", "MIN", "MAX", "IN", "NOT",
            "NULL", "IS", "UPDATE", "SET", "DELETE", "INSERT", "INTO", "VALUES", "INNER",
            "LEFT", "RIGHT", "OUTER", "HAVING", "DISTINCT", "EXPLAIN", "INTEGER", "PRIMARY",
            "FOREIGN", "KEY", "REFERENCES", "PRAGMA", "TRUE", "FALSE"
        }
        potential_cols = {i.lower() for i in identifiers if i.upper() not in keywords and not i.isdigit()}

        # 4. EXPLAIN dry-run validation on connected DB engine
        if not issues:
            try:
                explain_query(self.database, sql)
            except Exception as exc:
                err_msg = str(exc).splitlines()[0]
                issues.append(f"Database query plan validation failed: {err_msg}")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "operation": operation,
            "tables": sorted(list(tables_used)),
            "columns": sorted(list(potential_cols)),
        }
