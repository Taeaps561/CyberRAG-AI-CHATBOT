"""
utils.py — Chat History Persistence Layer (SQLite)
Provides session-based chat history management for the Cyber-RAG Chatbot.
"""

import os
import sqlite3
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Database Setup
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), "cyber_rag.db")


def _get_conn() -> sqlite3.Connection:
    """Return a thread-safe SQLite connection."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id   TEXT PRIMARY KEY,
                title        TEXT,
                created_at   TEXT DEFAULT (datetime('now','localtime')),
                updated_at   TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id   TEXT NOT NULL,
                role         TEXT NOT NULL,
                content      TEXT NOT NULL,
                created_at   TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            )
        """)
        conn.commit()


# Run on import
init_db()


# ---------------------------------------------------------------------------
# Session Dataclass
# ---------------------------------------------------------------------------
@dataclass
class Session:
    session_id: str
    title: Optional[str]
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_chat_history_db(session_id: str, role: str, content: str) -> None:
    """Append a message to a session. Creates the session if it doesn't exist."""
    with _get_conn() as conn:
        # Upsert session row
        conn.execute("""
            INSERT INTO sessions (session_id, title, updated_at)
            VALUES (?, ?, datetime('now','localtime'))
            ON CONFLICT(session_id) DO UPDATE SET updated_at = datetime('now','localtime')
        """, (session_id, None))

        # Auto-title: use first user message (truncated to 40 chars)
        if role == "user":
            row = conn.execute(
                "SELECT title FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row and not row["title"]:
                title = content[:40] + ("..." if len(content) > 40 else "")
                conn.execute(
                    "UPDATE sessions SET title = ? WHERE session_id = ?",
                    (title, session_id)
                )

        conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content)
        )
        conn.commit()


def load_chat_history_db(session_id: str) -> List[dict]:
    """Load all messages for a session, ordered by insertion time."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,)
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def get_all_sessions_db(search_query: str = "") -> List[Session]:
    """Return all sessions ordered by most recently updated, with optional title search."""
    with _get_conn() as conn:
        if search_query:
            rows = conn.execute("""
                SELECT session_id, title, created_at, updated_at
                FROM sessions
                WHERE title LIKE ?
                ORDER BY updated_at DESC
            """, (f"%{search_query}%",)).fetchall()
        else:
            rows = conn.execute("""
                SELECT session_id, title, created_at, updated_at
                FROM sessions
                ORDER BY updated_at DESC
            """).fetchall()
    return [
        Session(
            session_id=r["session_id"],
            title=r["title"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


def delete_session_db(session_id: str) -> bool:
    """Delete a session and all its messages. Returns True on success."""
    try:
        with _get_conn() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
        return True
    except Exception:
        return False


def rename_session_db(session_id: str, new_title: str) -> bool:
    """Rename the title of a session. Returns True on success."""
    try:
        with _get_conn() as conn:
            conn.execute(
                "UPDATE sessions SET title = ?, updated_at = datetime('now','localtime') WHERE session_id = ?",
                (new_title.strip(), session_id)
            )
            conn.commit()
        return True
    except Exception:
        return False
