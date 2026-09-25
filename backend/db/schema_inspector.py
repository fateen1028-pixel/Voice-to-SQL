"""Database schema inspector for PostgreSQL and SQLite."""
from db.connection import Database


def inspect_schema(database: Database) -> dict[str, dict]:
    if database.is_postgres:
        return _inspect_postgres(database)
    return _inspect_sqlite(database)


def _inspect_postgres(database: Database) -> dict[str, dict]:
    tables: dict[str, dict] = {}
    try:
        cursor = database.cursor()

        # Retrieve all public user tables
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
              AND table_type = 'BASE TABLE'
        """)
        table_rows = cursor.fetchall()
        table_names = [row["table_name"] for row in table_rows]

        for table in table_names:
            # Columns metadata
            cursor.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
            """, (table,))
            col_rows = cursor.fetchall()

            # Primary keys
            cursor.execute("""
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_schema = 'public'
                  AND tc.table_name = %s
            """, (table,))
            pk_cols = {row["column_name"] for row in cursor.fetchall()}

            columns = []
            for c in col_rows:
                columns.append({
                    "name": c["column_name"],
                    "type": c["data_type"].upper(),
                    "nullable": c["is_nullable"] == "YES",
                    "primary_key": c["column_name"] in pk_cols,
                })

            # Foreign keys
            cursor.execute("""
                SELECT kcu.column_name, ccu.table_name AS foreign_table_name, ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_name = tc.constraint_name
                 AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = 'public'
                  AND tc.table_name = %s
            """, (table,))
            fk_rows = cursor.fetchall()
            foreign_keys = [
                {
                    "column": fk["column_name"],
                    "foreign_table": fk["foreign_table_name"],
                    "foreign_column": fk["foreign_column_name"],
                }
                for fk in fk_rows
            ]

            tables[table] = {
                "columns": columns,
                "foreign_keys": foreign_keys,
                "indexes": [],
            }

        return tables
    except Exception:
        database.rollback()
        raise


def _inspect_sqlite(database: Database) -> dict[str, dict]:
    tables: dict[str, dict] = {}
    cursor = database.cursor()
    rows = cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    for row in rows:
        name = row["name"]
        raw_cols = [dict(item) for item in cursor.execute(f'PRAGMA table_info("{name}")')]
        raw_fks = [dict(item) for item in cursor.execute(f'PRAGMA foreign_key_list("{name}")')]
        raw_indexes = [dict(item) for item in cursor.execute(f'PRAGMA index_list("{name}")')]

        columns = [
            {
                "name": c["name"],
                "type": (c.get("type") or "TEXT").upper(),
                "nullable": not c.get("notnull", 0),
                "primary_key": bool(c.get("pk", 0)),
            }
            for c in raw_cols
        ]
        foreign_keys = [
            {
                "column": fk.get("from"),
                "foreign_table": fk.get("table"),
                "foreign_column": fk.get("to"),
            }
            for fk in raw_fks
        ]
        tables[name] = {"columns": columns, "foreign_keys": foreign_keys, "indexes": raw_indexes}
    return tables
