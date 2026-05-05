"""
Database operations — messages, facts, pending tasks.
"""

import sqlite3
from datetime import datetime
from typing import Optional

from config import DB_PATH, HISTORY_LIMIT


def get_connection():
    """Get SQLite connection."""
    return sqlite3.connect(str(DB_PATH))


from contextlib import contextmanager

@contextmanager
def get_db():
    """Get SQLite connection as context manager (auto-closes)."""
    conn = sqlite3.connect(str(DB_PATH))
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize database tables."""
    conn = get_connection()
    
    # Messages table (conversation history)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT,
            timestamp TEXT
        )
    """)
    
    # User info
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_info (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            first_seen TEXT
        )
    """)
    
    # Pending tasks (for retry queue)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_text TEXT,
            sender_name TEXT,
            is_group BOOLEAN,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Long-term memory with FTS5
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS facts USING fts5(
            content,
            category,
            timestamp
        )
    """)
    
    # Feedback events — negative signals from user (used in heartbeat)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_text TEXT,
            bot_response_preview TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            surfaced INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


# --- Messages ---

def save_message(user_id: int, role: str, content: str):
    """Save a message to history, auto-cleanup old messages."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO messages (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (user_id, role, content, datetime.now().isoformat()),
    )
    
    # Auto-cleanup: keep only last 50 messages per chat (5x HISTORY_LIMIT buffer)
    max_messages = HISTORY_LIMIT * 5
    conn.execute("""
        DELETE FROM messages WHERE user_id = ? AND id NOT IN (
            SELECT id FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?
        )
    """, (user_id, user_id, max_messages))
    
    conn.commit()
    conn.close()


def get_history(user_id: int, limit: int = HISTORY_LIMIT) -> list[dict]:
    """Get conversation history for a user/chat."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def clear_history(user_id: int):
    """Clear conversation history for a user/chat."""
    conn = get_connection()
    conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_message_count(user_id: int) -> int:
    """Get number of messages in history."""
    conn = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    conn.close()
    return count


# --- User Info ---

def save_user(user_id: int, username: str, first_name: str, last_name: str):
    """Save user info (first time only)."""
    conn = get_connection()
    conn.execute(
        """INSERT OR IGNORE INTO user_info (user_id, username, first_name, last_name, first_seen)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, username, first_name, last_name, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


# --- Facts (Long-term Memory) ---

def add_fact(content: str, category: str = "general"):
    """Add a fact to long-term memory."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO facts (content, category, timestamp) VALUES (?, ?, ?)",
        (content, category, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def search_facts(query: str, limit: int = 5) -> list[dict]:
    """Search facts using FTS5."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT content, category, timestamp FROM facts WHERE facts MATCH ? ORDER BY bm25(facts) LIMIT ?",
            (query, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        # Fallback to LIKE if FTS fails
        rows = conn.execute(
            "SELECT content, category, timestamp FROM facts WHERE content LIKE ? LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
    conn.close()
    return [{"content": r[0], "category": r[1], "timestamp": r[2]} for r in rows]


def get_recent_facts(limit: int = 10) -> list[dict]:
    """Get most recent facts."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT content, category, timestamp FROM facts ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [{"content": r[0], "category": r[1], "timestamp": r[2]} for r in rows]


def get_all_facts_count() -> int:
    """Get total number of facts."""
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    conn.close()
    return count


def get_facts(limit: int = 100) -> list[dict]:
    """Get all facts (for heartbeat context)."""
    return get_recent_facts(limit)


# --- Pending Tasks ---

def save_pending_task(chat_id: int, user_text: str, sender_name: str, is_group: bool):
    """Save a task for later retry."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO pending_tasks (chat_id, user_text, sender_name, is_group) VALUES (?, ?, ?, ?)",
        (chat_id, user_text, sender_name, is_group)
    )
    conn.commit()
    conn.close()


def get_pending_tasks() -> list[tuple]:
    """Get all pending tasks."""
    conn = get_connection()
    tasks = conn.execute(
        "SELECT id, chat_id, user_text, sender_name, is_group FROM pending_tasks ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return tasks


def delete_pending_task(task_id: int):
    """Delete a pending task."""
    conn = get_connection()
    conn.execute("DELETE FROM pending_tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()


# --- Feedback Events ---

def save_feedback_event(chat_id: int, user_text: str, bot_response_preview: str = ""):
    """Save a negative feedback signal from the user."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO feedback_events (chat_id, user_text, bot_response_preview) VALUES (?, ?, ?)",
        (chat_id, user_text[:300], bot_response_preview[:200]),
    )
    conn.commit()
    conn.close()


def get_unsurfaced_feedback(limit: int = 5) -> list[dict]:
    """Get feedback events not yet shown in heartbeat."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, chat_id, user_text, bot_response_preview, timestamp "
        "FROM feedback_events WHERE surfaced = 0 ORDER BY id ASC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [
        {"id": r[0], "chat_id": r[1], "user_text": r[2],
         "bot_response": r[3], "timestamp": r[4]}
        for r in rows
    ]


def mark_feedback_surfaced(ids: list[int]):
    """Mark feedback events as seen by heartbeat."""
    if not ids:
        return
    conn = get_connection()
    placeholders = ",".join("?" * len(ids))
    conn.execute(
        f"UPDATE feedback_events SET surfaced = 1 WHERE id IN ({placeholders})", ids
    )
    conn.commit()
    conn.close()
