"""SQL Security firewall and permission enforcement service using AST analysis via sqlglot."""
import logging
import re
import sqlglot
import sqlglot.expressions as exp

logger = logging.getLogger(__name__)


class SqlSecurityService:
    BLOCKED_DDL = {"DROP", "TRUNCATE", "ALTER", "CREATE", "ATTACH", "DETACH", "PRAGMA", "VACUUM", "REINDEX"}
    ALLOWED_MUTATIONS = {"INSERT", "UPDATE", "DELETE"}

    DEFAULT_RESTRICTIONS = {
        "user": {
            "restricted_patterns": ["ssn", "password_hash", "secret_token", "credit_card", "ssn_secret"],
            "restricted_columns": [("employees", "ssn"), ("users", "password_hash")],
        },
        "hr": {
            "restricted_columns": [("employees", "salary_secret")],
        }
    }

    def __init__(self, restrictions: dict | None = None) -> None:
        self.restrictions = restrictions or self.DEFAULT_RESTRICTIONS

    def operation(self, sql: str, is_postgres: bool = False) -> str:
        clean = self._clean_sql(sql)
        dialect = "postgres" if is_postgres else "sqlite"
        try:
            parsed_list = sqlglot.parse(clean, read=dialect)
            if parsed_list and parsed_list[0]:
                stmt = parsed_list[0]
                if isinstance(stmt, exp.Select):
                    return "SELECT"
                elif isinstance(stmt, exp.Insert):
                    return "INSERT"
                elif isinstance(stmt, exp.Update):
                    return "UPDATE"
                elif isinstance(stmt, exp.Delete):
                    return "DELETE"
                elif isinstance(stmt, exp.Drop):
                    return "DROP"
                elif isinstance(stmt, exp.Create):
                    return "CREATE"
                elif isinstance(stmt, exp.AlterTable):
                    return "ALTER"
        except Exception:
            pass

        match = re.match(r"^\s*([A-Za-z]+)", clean)
        return match.group(1).upper() if match else "UNKNOWN"

    def validate(self, sql: str, allow_ddl: bool = False, user_role: str | None = "user", is_postgres: bool = False) -> list[str]:
        issues: list[str] = []
        clean = self._clean_sql(sql)

        # 1. Prevent stacked / multi-statement execution
        dialect = "postgres" if is_postgres else "sqlite"
        try:
            parsed_statements = sqlglot.parse(clean, read=dialect)
            valid_stmts = [s for s in parsed_statements if s is not None]
            if len(valid_stmts) > 1:
                return ["Multiple SQL statements separated by semicolons are strictly blocked."]
        except Exception:
            semis = [s for s in clean.split(";") if s.strip()]
            if len(semis) > 1:
                return ["Multiple SQL statements separated by semicolons are strictly blocked."]

        op = self.operation(clean, is_postgres=is_postgres)

        if op in self.BLOCKED_DDL and not allow_ddl:
            return [f"Destructive operation {op} is blocked by database security policy."]

        if op not in {"SELECT", *self.ALLOWED_MUTATIONS}:
            return [f"SQL operation '{op}' is not permitted."]

        # 2. AST-Based Authorization Check
        if user_role and user_role in self.restrictions:
            role_config = self.restrictions[user_role]
            restricted_cols = role_config.get("restricted_columns", [])
            restricted_pats = [p.lower() for p in role_config.get("restricted_patterns", [])]

            cols_found: set[str] = set()
            try:
                parsed_list = sqlglot.parse(clean, read=dialect)
                if parsed_list and parsed_list[0]:
                    stmt = parsed_list[0]
                    for col_node in stmt.find_all(exp.Column):
                        if col_node.this:
                            cols_found.add(col_node.this.name.lower())
                    for ident in stmt.find_all(exp.Identifier):
                        if ident.name:
                            cols_found.add(ident.name.lower())
            except Exception:
                for ident in re.findall(r"\b([A-Za-z_][\w]*)\b", clean):
                    cols_found.add(ident.lower())

            clean_lower = clean.lower()

            for table, col in restricted_cols:
                col_low = col.lower()
                if col_low in cols_found or re.search(r"\b" + re.escape(col_low) + r"\b", clean_lower):
                    issues.append(f"Access denied: Role '{user_role}' is restricted from accessing column '{table}.{col}'.")

            for pattern in restricted_pats:
                if pattern in cols_found or re.search(r"\b" + re.escape(pattern) + r"\b", clean_lower):
                    issues.append(f"Access denied: Role '{user_role}' is restricted from accessing column '{pattern}'.")

        return issues

    def _clean_sql(self, sql: str) -> str:
        s = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
        s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
        return s.strip()

