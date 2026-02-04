"""
Memory Flush — Prompt to save important info before context limit.
Inspired by OpenClaw's pre-compaction memory flush.
"""

import logging
from datetime import datetime
from pathlib import Path

from config import WORKSPACE_DIR, HISTORY_LIMIT

log = logging.getLogger(__name__)

# Threshold: when history is this % full, suggest memory flush
FLUSH_THRESHOLD = 0.8  # 80% of HISTORY_LIMIT


def should_flush(current_messages: int) -> bool:
    """Check if we should suggest a memory flush."""
    threshold = int(HISTORY_LIMIT * FLUSH_THRESHOLD)
    return current_messages >= threshold


def get_flush_prompt() -> str:
    """Get the memory flush prompt to inject."""
    return """
[SYSTEM NOTE: Context is nearing capacity. If you learned anything important in this conversation that should be remembered long-term, write it to memory now using:
- /remember <category> <fact> — for searchable facts
- Or append to MEMORY.md for curated context

Reply normally if nothing needs to be saved.]
"""


def check_and_inject_flush(history: list[dict]) -> str:
    """
    Check if flush is needed and return prompt to inject.
    Returns empty string if no flush needed.
    """
    if should_flush(len(history)):
        log.info(f"Memory flush suggested ({len(history)}/{HISTORY_LIMIT} messages)")
        return get_flush_prompt()
    return ""


def write_to_daily_log(entry: str):
    """Write an entry to today's daily log."""
    today = datetime.now().strftime("%Y-%m-%d")
    memory_dir = WORKSPACE_DIR / "memory"
    memory_dir.mkdir(exist_ok=True)
    
    log_path = memory_dir / f"{today}.md"
    
    if not log_path.exists():
        log_path.write_text(f"# {today}\n\n")
    
    with open(log_path, "a") as f:
        timestamp = datetime.now().strftime("%H:%M")
        f.write(f"- [{timestamp}] {entry}\n")
    
    log.debug(f"Logged to {today}.md: {entry[:50]}...")


def get_daily_log(date: str = None) -> str:
    """Read a daily log file."""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    log_path = WORKSPACE_DIR / "memory" / f"{date}.md"
    
    if log_path.exists():
        return log_path.read_text()
    return ""


def get_recent_daily_logs(days: int = 2) -> str:
    """Get content from recent daily logs."""
    from datetime import timedelta
    
    content = []
    today = datetime.now()
    
    for i in range(days):
        date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        log_content = get_daily_log(date)
        if log_content:
            content.append(log_content)
    
    return "\n\n".join(content)
