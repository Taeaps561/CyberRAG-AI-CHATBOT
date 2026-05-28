"""
utils.py — Chat History Persistence Layer (SQLite)
Provides session-based chat history management for the Cyber-RAG Chatbot.
"""

import os
import json
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
                sources      TEXT DEFAULT '[]',
                created_at   TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            )
        """)
        # [Bug Fix #3] Safe migration: add sources column for existing databases
        try:
            conn.execute("ALTER TABLE messages ADD COLUMN sources TEXT DEFAULT '[]'")
        except sqlite3.OperationalError:
            pass  # Column already exists — skip

        # [Phase 2] Analytics: query_logs table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS query_logs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id      TEXT,
                query           TEXT NOT NULL,
                response_ms     INTEGER,
                doc_count       INTEGER DEFAULT 0,
                folder          TEXT DEFAULT 'ทั้งหมด',
                used_web        INTEGER DEFAULT 0,
                created_at      TEXT DEFAULT (datetime('now','localtime'))
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

def save_chat_history_db(session_id: str, role: str, content: str, sources: list = None) -> None:
    """Append a message to a session. Creates the session if it doesn't exist.
    [Bug Fix #3] sources are now persisted to DB as JSON.
    """
    sources_json = json.dumps(sources or [], ensure_ascii=False)
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
            "INSERT INTO messages (session_id, role, content, sources) VALUES (?, ?, ?, ?)",
            (session_id, role, content, sources_json)
        )
        conn.commit()


def load_chat_history_db(session_id: str) -> List[dict]:
    """Load all messages for a session, ordered by insertion time.
    [Bug Fix #3] Now also returns sources from DB.
    """
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content, sources FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,)
        ).fetchall()
    return [
        {
            "role": r["role"],
            "content": r["content"],
            "sources": json.loads(r["sources"] or "[]"),
        }
        for r in rows
    ]


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


# ---------------------------------------------------------------------------
# [Phase 1] Export Utilities
# ---------------------------------------------------------------------------

def export_session_md(session_id: str, session_title: str = "") -> str:
    """Export a chat session to a Markdown string.
    Includes full conversation with role labels, content, and cited sources.
    """
    messages = load_chat_history_db(session_id)
    title = session_title or "Chat Export"
    lines = [
        f"# 🛡️ {title}",
        f"> Exported from Cyber-RAG Enterprise\n",
    ]
    for m in messages:
        if m["role"] == "user":
            lines.append(f"### 🙋 User\n{m['content']}\n")
        else:
            lines.append(f"### 🤖 Assistant\n{m['content']}\n")
            if m.get("sources"):
                lines.append("**📚 Sources:**")
                for s in m["sources"]:
                    lines.append(f"- 📍 {s}")
                lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# [Phase 2] Analytics Functions
# ---------------------------------------------------------------------------

def log_query(
    session_id: str,
    query: str,
    response_ms: int,
    doc_count: int,
    folder: str = "ทั้งหมด",
    used_web: bool = False,
) -> None:
    """Record a query event for analytics tracking."""
    try:
        with _get_conn() as conn:
            conn.execute(
                """INSERT INTO query_logs
                   (session_id, query, response_ms, doc_count, folder, used_web)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, query, response_ms, doc_count, folder, int(used_web)),
            )
            conn.commit()
    except Exception:
        pass  # analytics are non-critical


def get_analytics(days: int = 7) -> dict:
    """Return aggregated analytics for the dashboard.

    Returns a dict with:
      total_queries, avg_response_ms, web_ratio, daily_counts (list of dicts),
      top_queries (list of dicts), total_sessions
    """
    with _get_conn() as conn:
        # Overall stats
        row = conn.execute("""
            SELECT COUNT(*) AS total,
                   AVG(response_ms) AS avg_ms,
                   SUM(used_web) AS web_count
            FROM query_logs
            WHERE created_at >= datetime('now', ?, 'localtime')
        """, (f"-{days} days",)).fetchone()

        total = row["total"] or 0
        avg_ms = round(row["avg_ms"] or 0)
        web_count = row["web_count"] or 0

        # Daily activity (last N days)
        daily_rows = conn.execute("""
            SELECT DATE(created_at) AS day, COUNT(*) AS count
            FROM query_logs
            WHERE created_at >= datetime('now', ?, 'localtime')
            GROUP BY day
            ORDER BY day ASC
        """, (f"-{days} days",)).fetchall()

        daily_counts = [{"day": r["day"], "count": r["count"]} for r in daily_rows]

        # Top 10 most frequent queries (by keyword similarity — group by first 40 chars)
        top_rows = conn.execute("""
            SELECT SUBSTR(query, 1, 50) AS short_query, COUNT(*) AS freq
            FROM query_logs
            GROUP BY SUBSTR(query, 1, 50)
            ORDER BY freq DESC
            LIMIT 10
        """).fetchall()
        top_queries = [{"query": r["short_query"], "freq": r["freq"]} for r in top_rows]

        # Total unique sessions
        sess_row = conn.execute("SELECT COUNT(*) AS cnt FROM sessions").fetchone()
        total_sessions = sess_row["cnt"] or 0

    return {
        "total_queries": total,
        "avg_response_ms": avg_ms,
        "web_ratio": round(web_count / total * 100, 1) if total else 0.0,
        "daily_counts": daily_counts,
        "top_queries": top_queries,
        "total_sessions": total_sessions,
    }
