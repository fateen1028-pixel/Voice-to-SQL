"""Deterministic SQL syntax and schema validation service using sqlglot and EXPLAIN query plan checks."""
import re
import sqlglot
import sqlglot.expressions as exp
from sqlglot.errors import ParseError

from db.connection import Database
from db.query_runner import explain_query
from services.sql_security_service import SqlSecurityService


class SqlValidationService:
    def __init__(self, database: Database, security: SqlSecurityService) -> None:
        self.database = database
        self.security = security

    def validate(self, sql: str, schema: dict[str, dict], allow_ddl: bool = False, user_role: str | None = "user") -> dict:
        is_pg = self.database.is_postgres
        issues = self.security.validate(sql, allow_ddl=allow_ddl, user_role=user_role, is_postgres=is_pg)
        operation = self.security.operation(sql, is_postgres=is_pg)

        dialect = "postgres" if is_pg else "sqlite"
        tables_used: set[str] = set()
        columns_used: set[str] = set()

        # 1. Deterministic SQL syntax parser validation via sqlglot AST
        try:
            parsed_statements = sqlglot.parse(sql, read=dialect)
            if not parsed_statements or parsed_statements[0] is None:
                issues.append("Malformed SQL statement syntax.")
            else:
                stmt = parsed_statements[0]
                for tbl_node in stmt.find_all(exp.Table):
                    if tbl_node.name:
                        tables_used.add(tbl_node.name)
                for col_node in stmt.find_all(exp.Column):
                    if col_node.this:
                        columns_used.add(col_node.this.name)
        except Exception as exc:
            issues.append(f"SQL syntax error: {str(exc).splitlines()[0]}")
            # Regex fallback
            tables_used = set(re.findall(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+([A-Za-z_][\w]*)", sql, re.I))

        # 2. Extract referenced tables and validate against schema
        if not tables_used:
            tables_used = set(re.findall(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+([A-Za-z_][\w]*)", sql, re.I))

        schema_tables_lower = {k.lower(): k for k in schema}
        unknown_tables = {t for t in tables_used if t.lower() not in schema_tables_lower}
        if unknown_tables:
            issues.append(f"Unknown table(s) referenced in query: {', '.join(sorted(unknown_tables))}")

        # 3. Column existence check for target tables in schema
        all_schema_cols = {c["name"].lower() for t_meta in schema.values() for c in t_meta.get("columns", [])}
        for t_name in tables_used:
            exact_table = schema_tables_lower.get(t_name.lower())
            if exact_table and exact_table in schema:
                known_cols = {c["name"].lower() for c in schema[exact_table].get("columns", [])}
                if known_cols:
                    for col in columns_used:
                        col_low = col.lower()
                        if col_low not in known_cols and col_low not in all_schema_cols:
                            issues.append(f"Unknown column '{col}' for table '{exact_table}'.")

                    if operation == "UPDATE":
                        set_matches = re.findall(r"\bSET\s+([A-Za-z_][\w]*)\s*=", sql, re.I)
                        for col in set_matches:
                            if col.lower() not in known_cols:
                                issues.append(f"Unknown column '{col}' for table '{exact_table}'.")

        # 4. EXPLAIN dry-run validation & query plan check
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
            "columns": sorted(list(columns_used or set(re.findall(r"\b([A-Za-z_][\w]*)\b", sql)))),
        }

