"""Logical SQL query validation and critique service."""
import re


class SqlLogicService:
    def validate(self, message: str, sql: str) -> list[str]:
        issues: list[str] = []
        msg_norm = message.lower()
        sql_norm = sql.lower()

        # 1. Date Range Validation Check (e.g., "joined in 2025")
        year_match = re.search(r"\b(20\d{2})\b", message)
        if year_match and any(term in msg_norm for term in ("year", "joined", "created", "in 20", "during 20")):
            yr = year_match.group(1)
            next_yr = str(int(yr) + 1)
            has_upper_bound = (
                f"{next_yr}-01-01" in sql
                or f"<{next_yr}" in sql
                or f"extract(year" in sql_norm
                or f"strftime('%y'" in sql_norm
                or f"between '{yr}-01-01' and '{yr}-12-31'" in sql_norm
            )
            has_lower_bound = f"{yr}-01-01" in sql or yr in sql

            if has_lower_bound and not has_upper_bound and ">=" in sql:
                issues.append(
                    f"Logical error: User requested year {yr}, but generated condition uses '>=' without an upper bound, including future records after {yr}."
                )

        # 2. Top-N requests must contain LIMIT clause
        top_match = re.search(r"\b(?:top|first)\s+(\d+)\b", msg_norm)
        if top_match and "limit" not in sql_norm:
            issues.append(f"Logical error: Natural language requested top {top_match.group(1)} items, but generated SQL is missing a LIMIT clause.")

        # 3. Order request requires ORDER BY
        if any(w in msg_norm for w in ("highest", "lowest", "top", "most", "sort by")) and "order by" not in sql_norm:
            issues.append("Logical warning: Natural language requested ranking/sorting, but generated SQL has no ORDER BY clause.")

        # 4. Aggregation without GROUP BY when multiple non-aggregate columns selected
        if "group by" not in sql_norm and any(fn in sql_norm for fn in ("sum(", "avg(", "count(")) and "select *" not in sql_norm:
            # If selecting raw columns alongside aggregate without group by
            cols_part = sql_norm.split("from")[0].replace("select", "")
            has_raw = any(c for c in cols_part.split(",") if not any(fn in c for fn in ("sum(", "avg(", "count(", "max(", "min(")))
            has_agg = any(fn in cols_part for fn in ("sum(", "avg(", "count(", "max(", "min("))
            if has_raw and has_agg:
                issues.append("Logical error: SELECT contains both aggregate functions and unaggregated columns without a GROUP BY clause.")

        return issues
