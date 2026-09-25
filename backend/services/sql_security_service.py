"""SQL Security firewall and permission enforcement service."""
import re


class SqlSecurityService:
    BLOCKED_DDL = {"DROP", "TRUNCATE", "ALTER", "CREATE", "ATTACH", "DETACH", "PRAGMA", "VACUUM", "REINDEX"}
    ALLOWED_MUTATIONS = {"INSERT", "UPDATE", "DELETE"}

    # Example role restrictions mapping: role -> restricted table.column or table
    RESTRICTIONS = {
        "user": {
            "restricted_columns": [("employees", "ssn"), ("users", "password_hash")],
        },
        "hr": {
            "restricted_columns": [("employees", "salary_secret")],
        }
    }

    def operation(self, sql: str) -> str:
        clean = self._clean_sql(sql)
        match = re.match(r"^\s*([A-Za-z]+)", clean)
        return match.group(1).upper() if match else "UNKNOWN"

    def validate(self, sql: str, allow_ddl: bool = False, user_role: str | None = "user") -> list[str]:
        issues: list[str] = []
        clean = self._clean_sql(sql)

        # Prevent stacked / multi-statement execution
        # Count non-trailing semicolons
        semis = [s for s in clean.split(";") if s.strip()]
        if len(semis) > 1:
            return ["Multiple SQL statements separated by semicolons are strictly blocked."]

        op = self.operation(clean)
        if op in self.BLOCKED_DDL and not allow_ddl:
            return [f"Destructive operation {op} is blocked by database security policy."]

        if op not in {"SELECT", *self.ALLOWED_MUTATIONS}:
            return [f"SQL operation '{op}' is not permitted."]

        # Check role column restrictions
        if user_role and user_role in self.RESTRICTIONS:
            role_config = self.RESTRICTIONS[user_role]
            for table, col in role_config.get("restricted_columns", []):
                if re.search(r"\b" + re.escape(col) + r"\b", clean, re.I):
                    issues.append(f"Access denied: Role '{user_role}' is restricted from accessing column '{table}.{col}'.")

        return issues

    def _clean_sql(self, sql: str) -> str:
        # Strip comments -- or /* */
        s = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
        s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
        return s.strip()
