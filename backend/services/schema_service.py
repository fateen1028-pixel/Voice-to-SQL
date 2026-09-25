"""Dynamic schema retrieval and RAG filtering service."""
import re
from db.connection import Database
from db.schema_inspector import inspect_schema


class SchemaService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self) -> dict[str, dict]:
        return inspect_schema(self.database)

    def relevant(self, message: str) -> dict[str, dict]:
        all_tables = self.get()
        if not all_tables:
            return {}

        normalized = message.lower()
        words = set(re.findall(r"\b\w+\b", normalized))

        matched: dict[str, dict] = {}
        for table_name, meta in all_tables.items():
            t_lower = table_name.lower()
            t_singular = t_lower.rstrip("s")
            
            # Match table name or singular form in message
            if t_lower in words or t_singular in words or t_lower in normalized:
                matched[table_name] = meta
                continue

            # Match column names
            col_names = [c["name"].lower() for c in meta.get("columns", [])]
            if any(col in words for col in col_names):
                matched[table_name] = meta

        # Always include related foreign key tables
        if matched:
            extra: dict[str, dict] = {}
            for t_name, meta in matched.items():
                for fk in meta.get("foreign_keys", []):
                    target = fk.get("foreign_table")
                    if target and target in all_tables and target not in matched:
                        extra[target] = all_tables[target]
            matched.update(extra)

        return matched or all_tables
