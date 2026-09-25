"""Database query execution runner for PostgreSQL and SQLite with automatic transaction rollback safety."""
import re
from db.connection import Database


def run_select(database: Database, sql: str, params: tuple | list | None = None, max_rows: int = 500) -> tuple[list[str], list[dict]]:
    try:
        cursor = database.cursor()
        cursor.execute(sql, params or ())
        if database.is_postgres:
            raw_rows = cursor.fetchmany(max_rows + 1)
            rows = [dict(r) for r in raw_rows[:max_rows]]
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
        else:
            columns = [item[0] for item in cursor.description or []]
            raw_rows = cursor.fetchmany(max_rows + 1)
            rows = [dict(row) for row in raw_rows[:max_rows]]
        return columns, rows
    except Exception:
        database.rollback()
        raise


def run_mutation(database: Database, sql: str, params: tuple | list | None = None) -> int:
    try:
        cursor = database.cursor()
        cursor.execute(sql, params or ())
        rowcount = cursor.rowcount
        database.connection.commit()
        return max(rowcount, 0)
    except Exception:
        database.rollback()
        raise


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
        database.rollback()
        return None


def explain_query(database: Database, sql: str) -> None:
    try:
        cursor = database.cursor()
        if database.is_postgres:
            cursor.execute(f"EXPLAIN {sql}")
        else:
            cursor.execute(f"EXPLAIN QUERY PLAN {sql}")
    except Exception:
        database.rollback()
        raise
