"""SQLite connection helpers (standard library only — no SQLAlchemy)."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator

from .config import DB_PATH


def connect() -> sqlite3.Connection:
    """Open a SQLite connection with dictionary-like rows."""
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Yield one SQLite connection per request and always close it."""
    connection = connect()
    try:
        yield connection
    finally:
        connection.close()
