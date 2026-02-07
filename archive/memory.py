#!/usr/bin/env python3
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# DB Path (same as bot.py)
DB_PATH = Path(__file__).parent.parent / "memory.db"

def init_fts():
    conn = sqlite3.connect(DB_PATH)
    # Using FTS5 for full-text search
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            content, 
            timestamp
        )
    """)
    conn.commit()
    conn.close()

def add_memory(text):
    conn = sqlite3.connect(DB_PATH)
    ts = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO memories_fts (content, timestamp) VALUES (?, ?)",
        (text, ts)
    )
    conn.commit()
    conn.close()
    print(f"Memory stored: {text}")

def search_memory(query):
    conn = sqlite3.connect(DB_PATH)
    # Simple FTS search
    # We order by rank (relevance)
    rows = conn.execute(
        "SELECT content, timestamp FROM memories_fts WHERE content MATCH ? ORDER BY rank LIMIT 5",
        (query,)
    ).fetchall()
    conn.close()
    
    if not rows:
        print("No matches found.")
        return

    print(f"Found {len(rows)} memories:")
    for row in rows:
        content, ts = row
        print(f"- [{ts[:10]}] {content}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: ./memory.py [add|search] 'text'")
        sys.exit(1)

    cmd = sys.argv[1]
    arg = sys.argv[2]
    
    # Ensure table exists
    init_fts()

    if cmd == "add":
        add_memory(arg)
    elif cmd == "search":
        search_memory(arg)
    else:
        print("Unknown command. Use 'add' or 'search'.")
