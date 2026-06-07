from __future__ import annotations

import os
import sqlite3
from contextlib import closing

DB_PATH = "sidreader.db"
UPLOAD_DIR = "uploads"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    current_card_index INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def init_db() -> None:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with closing(get_conn()) as conn, conn:
        conn.executescript(_SCHEMA)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def upsert_document(
    conn: sqlite3.Connection,
    doc_id: str,
    filename: str,
    path: str,
    page_count: int,
) -> dict:
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO documents (id, filename, path, page_count) "
            "VALUES (?, ?, ?, ?)",
            (doc_id, filename, path, page_count),
        )
        conn.execute(
            "UPDATE documents SET last_opened_at = CURRENT_TIMESTAMP WHERE id = ?",
            (doc_id,),
        )
    return _row_to_dict(
        conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    )


def list_documents(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM documents ORDER BY last_opened_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_document(conn: sqlite3.Connection, doc_id: str) -> dict | None:
    return _row_to_dict(
        conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    )


def get_current_document(conn: sqlite3.Connection) -> dict | None:
    return _row_to_dict(
        conn.execute(
            "SELECT * FROM documents ORDER BY last_opened_at DESC LIMIT 1"
        ).fetchone()
    )


def set_position(
    conn: sqlite3.Connection, doc_id: str, card_index: int
) -> dict | None:
    with conn:
        cur = conn.execute(
            "UPDATE documents SET current_card_index = ?, "
            "last_opened_at = CURRENT_TIMESTAMP WHERE id = ?",
            (card_index, doc_id),
        )
        if cur.rowcount == 0:
            return None
    return get_document(conn, doc_id)


def touch_document(conn: sqlite3.Connection, doc_id: str) -> dict | None:
    with conn:
        cur = conn.execute(
            "UPDATE documents SET last_opened_at = CURRENT_TIMESTAMP WHERE id = ?",
            (doc_id,),
        )
        if cur.rowcount == 0:
            return None
    return get_document(conn, doc_id)
