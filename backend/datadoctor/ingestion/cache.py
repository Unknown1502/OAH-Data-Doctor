"""SQLite-backed HTTP response cache (raw bodies are retained verbatim for evidence)."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS http_cache (
    url TEXT PRIMARY KEY,
    status INTEGER NOT NULL,
    body TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
"""


class HttpCache:
    def __init__(self, db_path: Path, ttl_s: int) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.execute(_SCHEMA)
        self._ttl = ttl_s

    def get(self, url: str) -> tuple[int, str, float] | None:
        row = self._db.execute("SELECT status, body, fetched_at FROM http_cache WHERE url = ?", (url,)).fetchone()
        if row is None or time.time() - row[2] > self._ttl:
            return None
        return int(row[0]), str(row[1]), float(row[2])

    def put(self, url: str, status: int, body: str) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO http_cache (url, status, body, fetched_at) VALUES (?, ?, ?, ?)",
            (url, status, body, time.time()),
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()
