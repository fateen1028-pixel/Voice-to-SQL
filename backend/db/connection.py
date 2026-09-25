"""Database connection wrapper supporting PostgreSQL (via psycopg2) and SQLite (via sqlite3)."""
from pathlib import Path
import re
import sqlite3
import typing

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


class Database:
    def __init__(self, url: str) -> None:
        self.url = url
        self.is_postgres = url.startswith("postgresql://") or url.startswith("postgres://")
        self.is_sqlite = url.startswith("sqlite:///")
        if not (self.is_postgres or self.is_sqlite):
            raise RuntimeError(f"Unsupported DATABASE_URL dialect in '{url}'. Supported: postgresql:// or sqlite:///")

        self.sqlite_path: str | None = None
        if self.is_sqlite:
            self.sqlite_path = url.removeprefix("sqlite:///")
            if re.match(r"^/[A-Za-z]:/", self.sqlite_path):
                self.sqlite_path = self.sqlite_path[1:]

        self.connection: typing.Any = None

    def connect(self) -> None:
        if self.is_postgres:
            if not HAS_PSYCOPG2:
                raise RuntimeError("psycopg2-binary package is required to connect to PostgreSQL.")
            self.connection = psycopg2.connect(self.url)
            self.connection.autocommit = False
        else:
            path = Path(self.sqlite_path)  # type: ignore[arg-type]
            if self.sqlite_path != ":memory:" and str(path.parent) not in ("", "."):
                path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(self.sqlite_path, check_same_thread=False)  # type: ignore[arg-type]
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        if self.connection:
            try:
                self.connection.close()
            except Exception:
                pass

    def cursor(self) -> typing.Any:
        if not self.connection:
            raise RuntimeError("Database connection is not initialized.")
        if self.is_postgres:
            return self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        return self.connection.cursor()
