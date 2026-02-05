"""
XP & Stats system — Pwnagotchi-style leveling.
Tracks: messages answered, days alive, tasks completed, brother chats.
"""

import sqlite3
import logging
from datetime import datetime, date
from typing import Optional, Callable

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

# Level-up callback (set by main.py or display module)
_level_up_callback: Optional[Callable[[int, str], None]] = None


def set_level_up_callback(callback: Callable[[int, str], None]):
    """Set callback for level-up notifications. callback(level, title)"""
    global _level_up_callback
    _level_up_callback = callback


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
        ("xp", 0),
        ("messages_answered", 0),
        ("tasks_completed", 0),
        ("brother_chats", 0),
        ("heartbeats", 0),
        ("first_boot", int(datetime.now().timestamp())),
        ("last_daily_xp", 0),
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
        "SELECT value FROM gotchi_stats WHERE key = ?", (key,)
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


def get_level_for_xp(xp: int) -> int:
    """Calculate level for given XP."""
    level = 1
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if xp >= threshold:
            level = i + 1
    return min(level, len(LEVEL_TITLES))


def add_xp(amount: int, reason: str = "") -> int:
    """Add XP, check for level-up, return new total."""
    old_xp = get_stat("xp")
    old_level = get_level_for_xp(old_xp)
    
    new_xp = increment_stat("xp", amount)
    new_level = get_level_for_xp(new_xp)
    
    if reason:
        log.info(f"XP +{amount} ({reason}) = {new_xp} total")
    
    # Check for level-up!
    if new_level > old_level:
        title = LEVEL_TITLES[new_level - 1]
        log.info(f"LEVEL UP! Now Level {new_level} {title}!")
        
        # Trigger callback if set
        if _level_up_callback:
            try:
                _level_up_callback(new_level, title)
            except Exception as e:
                log.error(f"Level-up callback failed: {e}")
    
    return new_xp


def get_level() -> tuple[int, str, int, int]:
    """
    Get current level info.
    Returns: (level, title, current_xp, xp_to_next)
    """
    xp = get_stat("xp")
    level = get_level_for_xp(xp)
    title = LEVEL_TITLES[level - 1]
    
    # XP to next level
    if level < len(LEVEL_THRESHOLDS):
        xp_to_next = LEVEL_THRESHOLDS[level] - xp
    else:
        xp_to_next = 0  # Max level
    
    return level, title, xp, max(0, xp_to_next)


def get_days_alive() -> int:
    """Calculate days alive from first_boot timestamp."""
    first_boot = get_stat("first_boot")
    if first_boot:
        return int((datetime.now().timestamp() - first_boot) / 86400)
    return 0


def get_stats_summary() -> dict:
    """Get full stats summary for display."""
    level, title, xp, xp_to_next = get_level()
    
    return {
        "level": level,
        "title": title,
        "xp": xp,
        "xp_to_next": xp_to_next,
        "messages": get_stat("messages_answered"),
        "tasks": get_stat("tasks_completed"),
        "brother_chats": get_stat("brother_chats"),
        "heartbeats": get_stat("heartbeats"),
        "days_alive": get_days_alive(),  # Now consistent!
    }


def get_status_bar() -> str:
    """Get compact status bar for display (max ~30 chars)."""
    stats = get_stats_summary()
    return f"Lv{stats['level']} {stats['title']} | {stats['xp']} XP"


def check_daily_xp():
    """Award daily XP if new day. Call on heartbeat."""
    today = date.today().toordinal()
    last_daily = get_stat("last_daily_xp")
    
    if today > last_daily:
        add_xp(XP_DAY_ALIVE, "daily survival")
        set_stat("last_daily_xp", today)
        log.info(f"Daily XP awarded! Day {get_days_alive()}")
        return True
    return False


# Event handlers

def on_message_answered():
    """Call when bot answers a message."""
    increment_stat("messages_answered")
    add_xp(XP_MESSAGE, "message")


def on_task_completed():
    """Call when a task is completed."""
    increment_stat("tasks_completed")
    add_xp(XP_TASK, "task")


def on_brother_chat():
    """Call when interacting with brother."""
    increment_stat("brother_chats")
    add_xp(XP_BROTHER_CHAT, "brother")


def on_heartbeat():
    """Call on successful heartbeat."""
    increment_stat("heartbeats")
    add_xp(XP_HEARTBEAT, "heartbeat")
    check_daily_xp()


# Initialize on import
try:
    init_stats_table()
except Exception as e:
    log.warning(f"Could not init stats table: {e}")
