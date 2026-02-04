"""
XP & Stats system — Pwnagotchi-style leveling.
Tracks: messages answered, days alive, tasks completed, brother chats.
"""

import sqlite3
import logging
from datetime import datetime, date
from typing import Optional

from config import DB_PATH

log = logging.getLogger(__name__)

# XP rewards
XP_MESSAGE = 10        # Per message answered
XP_TASK = 25           # Per task completed  
XP_BROTHER_CHAT = 50   # Per brother interaction
XP_DAY_ALIVE = 100     # Per day survived
XP_HEARTBEAT = 5       # Per successful heartbeat

# Level thresholds (XP needed for each level)
LEVEL_THRESHOLDS = [
    0,      # Level 1
    100,    # Level 2
    300,    # Level 3
    600,    # Level 4
    1000,   # Level 5
    1500,   # Level 6
    2500,   # Level 7
    4000,   # Level 8
    6000,   # Level 9
    10000,  # Level 10 - Master
]

LEVEL_TITLES = [
    "Newborn",      # 1
    "Awakened",     # 2
    "Learning",     # 3
    "Growing",      # 4
    "Capable",      # 5
    "Skilled",      # 6
    "Expert",       # 7
    "Master",       # 8
    "Legendary",    # 9
    "Transcendent", # 10
]


def init_stats_table():
    """Initialize stats table if not exists."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute('''
        CREATE TABLE IF NOT EXISTS gotchi_stats (
            key TEXT PRIMARY KEY,
            value INTEGER DEFAULT 0,
            updated_at TEXT
        )
    ''')
    
    # Initialize default values
    defaults = [
        ('xp', 0),
        ('messages_answered', 0),
        ('tasks_completed', 0),
        ('brother_chats', 0),
        ('heartbeats', 0),
        ('days_alive', 0),
        ('first_boot', int(datetime.now().timestamp())),
        ('last_daily_xp', 0),  # Track last day we gave daily XP
    ]
    
    for key, value in defaults:
        conn.execute('''
            INSERT OR IGNORE INTO gotchi_stats (key, value, updated_at)
            VALUES (?, ?, ?)
        ''', (key, value, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()


def get_stat(key: str) -> int:
    """Get a stat value."""
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute(
        'SELECT value FROM gotchi_stats WHERE key = ?', (key,)
    ).fetchone()
    conn.close()
    return row[0] if row else 0


def set_stat(key: str, value: int):
    """Set a stat value."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute('''
        INSERT OR REPLACE INTO gotchi_stats (key, value, updated_at)
        VALUES (?, ?, ?)
    ''', (key, value, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def increment_stat(key: str, amount: int = 1) -> int:
    """Increment a stat and return new value."""
    current = get_stat(key)
    new_value = current + amount
    set_stat(key, new_value)
    return new_value


def add_xp(amount: int, reason: str = "") -> int:
    """Add XP and return new total."""
    new_xp = increment_stat('xp', amount)
    if reason:
        log.info(f"XP +{amount} ({reason}) = {new_xp} total")
    return new_xp


def get_level() -> tuple[int, str, int, int]:
    """
    Get current level info.
    Returns: (level, title, current_xp, xp_to_next)
    """
    xp = get_stat('xp')
    
    level = 1
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if xp >= threshold:
            level = i + 1
        else:
            break
    
    # Cap at max level
    level = min(level, len(LEVEL_TITLES))
    title = LEVEL_TITLES[level - 1]
    
    # XP to next level
    if level < len(LEVEL_THRESHOLDS):
        xp_to_next = LEVEL_THRESHOLDS[level] - xp
    else:
        xp_to_next = 0  # Max level
    
    return level, title, xp, xp_to_next


def get_stats_summary() -> dict:
    """Get full stats summary for display."""
    level, title, xp, xp_to_next = get_level()
    
    # Calculate days alive
    first_boot = get_stat('first_boot')
    if first_boot:
        days_alive = (datetime.now().timestamp() - first_boot) / 86400
    else:
        days_alive = 0
    
    return {
        'level': level,
        'title': title,
        'xp': xp,
        'xp_to_next': xp_to_next,
        'messages': get_stat('messages_answered'),
        'tasks': get_stat('tasks_completed'),
        'brother_chats': get_stat('brother_chats'),
        'heartbeats': get_stat('heartbeats'),
        'days_alive': int(days_alive),
    }


def get_status_bar() -> str:
    """Get compact status bar for display (max ~30 chars)."""
    stats = get_stats_summary()
    # Format: "Lv5 Expert | 1234 XP"
    return f"Lv{stats['level']} {stats['title']} | {stats['xp']} XP"


def check_daily_xp():
    """Award daily XP if new day. Call on heartbeat."""
    today = date.today().toordinal()
    last_daily = get_stat('last_daily_xp')
    
    if today > last_daily:
        add_xp(XP_DAY_ALIVE, "daily survival")
        set_stat('last_daily_xp', today)
        increment_stat('days_alive')
        log.info(f"Daily XP awarded! Day {get_stat('days_alive')}")
        return True
    return False


# Event handlers (call these from appropriate places)

def on_message_answered():
    """Call when bot answers a message."""
    increment_stat('messages_answered')
    add_xp(XP_MESSAGE, "message")


def on_task_completed():
    """Call when a task is completed."""
    increment_stat('tasks_completed')
    add_xp(XP_TASK, "task")


def on_brother_chat():
    """Call when interacting with brother."""
    increment_stat('brother_chats')
    add_xp(XP_BROTHER_CHAT, "brother")


def on_heartbeat():
    """Call on successful heartbeat."""
    increment_stat('heartbeats')
    add_xp(XP_HEARTBEAT, "heartbeat")
    check_daily_xp()


# Initialize on import
try:
    init_stats_table()
except Exception as e:
    log.warning(f"Could not init stats table: {e}")
