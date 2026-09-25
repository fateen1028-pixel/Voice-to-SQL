"""Database query execution runner for PostgreSQL and SQLite."""
import re
from db.connection import Database


def run_select(database: Database, sql: str, params: tuple | list | None = None) -> tuple[list[str], list[dict]]:
    cursor = database.cursor()
    cursor.execute(sql, params or ())
    if database.is_postgres:
        rows = [dict(r) for r in cursor.fetchall()]
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
    else:
        columns = [item[0] for item in cursor.description or []]
        rows = [dict(row) for row in cursor.fetchall()]
    return columns, rows


def run_mutation(database: Database, sql: str, params: tuple | list | None = None) -> int:
    cursor = database.cursor()
    cursor.execute(sql, params or ())
    rowcount = cursor.rowcount
    database.connection.commit()
    return max(rowcount, 0)


def estimate_mutation_affected_rows(database: Database, sql: str, operation: str) -> int | None:
    if operation == "INSERT":
        return None
    try:
        upper_sql = sql.upper()
        if " WHERE " in upper_sql:
            where_clause = sql[upper_sql.find(" WHERE "):]
        else:
            where_clause = ""

        # Extract main target table
        tokens = sql.strip().split()
        if operation == "DELETE" and len(tokens) >= 3:
            table = tokens[2]
            if table.upper() == "FROM" and len(tokens) >= 4:
                table = tokens[3]
        elif operation == "UPDATE" and len(tokens) >= 2:
            table = tokens[1]
        else:
            return None

        table = table.strip('"').strip('`').strip("'")
        count_sql = f"SELECT COUNT(*) AS cnt FROM {table}{where_clause}"
        cols, rows = run_select(database, count_sql)
        if rows:
            return int(rows[0].get("cnt") or rows[0].get("COUNT(*)") or next(iter(rows[0].values())))
        return None
    except Exception:
        return None


def explain_query(database: Database, sql: str) -> None:
    cursor = database.cursor()
    if database.is_postgres:
        cursor.execute(f"EXPLAIN {sql}")
    else:
        cursor.execute(f"EXPLAIN QUERY PLAN {sql}")
