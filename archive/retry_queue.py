#!/usr/bin/env python3
"""
Manually process pending tasks queue (one-time retry).
Usage: ./retry_queue.py
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent.resolve()
DB_PATH = PROJECT_DIR / "memory.db"
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

def send_telegram_message(chat_id, text):
    """Send a message via Telegram Bot API."""
    import urllib.request
    import urllib.parse
    import json
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        'chat_id': chat_id,
        'text': text
    }).encode()
    
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())
    except Exception as e:
        print(f"Failed to send message: {e}")
        return None

def main():
    if not BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)

    # 1. Check queue
    conn = sqlite3.connect(DB_PATH)
    tasks = conn.execute(
        "SELECT id, chat_id, user_text, sender_name, is_group FROM pending_tasks ORDER BY id ASC LIMIT 1"
    ).fetchall()
    conn.close()

    if not tasks:
        print("No pending tasks.")
        return

    task_id, chat_id, user_text, sender_name, is_group = tasks[0]
    print(f"Processing task #{task_id}: {user_text[:60]}...")

    # 2. Try calling Claude
    try:
        result = subprocess.run(
            ["claude", "-p", "--dangerously-skip-permissions", "--output-format", "text", user_text],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(PROJECT_DIR)
        )
        
        if result.returncode != 0:
            err = result.stderr.strip()
            if "limit" in err.lower() or "429" in err or "quota" in err.lower():
                print(f"Still rate limited: {err}")
                send_telegram_message(chat_id, "💤 Still rate limited. Will retry later.")
                return
            else:
                print(f"Claude error: {err}")
                send_telegram_message(chat_id, f"[Error processing queued task]\n{err[:500]}")
                return
        
        response = result.stdout.strip()
        print(f"Success! Response: {response[:100]}...")
        
        # 3. Send response
        send_telegram_message(chat_id, f"🔔 [Delayed Reply]\n\n{response}")
        
        # 4. Delete from queue
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM pending_tasks WHERE id = ?", (task_id,))
        conn.commit()
        conn.close()
        
        print(f"Task #{task_id} completed and removed from queue.")
        
    except subprocess.TimeoutExpired:
        print("Claude timeout.")
        send_telegram_message(chat_id, "⏱️ Processing timed out. Will retry later.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
