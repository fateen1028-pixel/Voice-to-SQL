"""Dynamic schema retrieval, caching, and RAG filtering service."""
import hashlib
import json
import re
import time
from db.connection import Database
from db.schema_inspector import inspect_schema


class SchemaService:
    def __init__(self, database: Database, cache_ttl_seconds: float = 60.0) -> None:
        self.database = database
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cached_schema: dict[str, dict] | None = None
        self._last_inspected_at: float = 0.0
        self._fingerprint: str = ""

    def get(self, force_refresh: bool = False) -> dict[str, dict]:
        now = time.time()
        if force_refresh or self._cached_schema is None or (now - self._last_inspected_at) > self.cache_ttl_seconds:
            schema = inspect_schema(self.database)
            self._cached_schema = schema
            self._last_inspected_at = now
            raw_serialized = json.dumps(sorted(list(schema.keys())))
            self._fingerprint = hashlib.md5(raw_serialized.encode("utf-8")).hexdigest()
        return self._cached_schema

    def refresh(self) -> dict[str, dict]:
        return self.get(force_refresh=True)

    @property
    def fingerprint(self) -> str:
        if self._cached_schema is None:
            self.get()
        return self._fingerprint

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

