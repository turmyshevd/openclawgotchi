"""
Command Logger — Audit trail for all commands and messages.
Logs to JSONL file for easy parsing and analysis.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import PROJECT_DIR

log = logging.getLogger(__name__)

# Log file location
COMMANDS_LOG = PROJECT_DIR / "logs" / "commands.jsonl"


def _ensure_log_dir():
    """Ensure logs directory exists."""
    COMMANDS_LOG.parent.mkdir(parents=True, exist_ok=True)


def log_command(
    action: str,
    user_id: int,
    chat_id: int,
    username: str = "",
    text: str = "",
    source: str = "telegram",
    extra: dict = None
):
    """
    Log a command or message to the audit trail.
    
    Args:
        action: Command name (e.g., "/start", "/clear", "message")
        user_id: Telegram user ID
        chat_id: Chat/conversation ID
        username: Username or display name
        text: Message text (truncated for privacy)
        source: Channel source
        extra: Additional metadata
    """
    _ensure_log_dir()
    
    entry = {
        "ts": datetime.now().isoformat(),
        "action": action,
        "user_id": user_id,
        "chat_id": chat_id,
        "username": username,
        "source": source,
    }
    
    # Truncate text for privacy (first 100 chars)
    if text:
        entry["text_preview"] = text[:100] + ("..." if len(text) > 100 else "")
    
    if extra:
        entry.update(extra)
    
    try:
        with open(COMMANDS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        log.warning(f"Failed to log command: {e}")


def log_bot_response(
    chat_id: int,
    response_preview: str = "",
    connector: str = "claude",
    tokens: int = 0
):
    """Log bot response for analysis."""
    _ensure_log_dir()
    
    entry = {
        "ts": datetime.now().isoformat(),
        "action": "response",
        "chat_id": chat_id,
        "connector": connector,
        "response_preview": response_preview[:100] + ("..." if len(response_preview) > 100 else ""),
    }
    
    if tokens:
        entry["tokens"] = tokens
    
    try:
        with open(COMMANDS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        log.warning(f"Failed to log response: {e}")


def log_heartbeat(action: str, result: str = ""):
    """Log heartbeat events."""
    _ensure_log_dir()
    
    entry = {
        "ts": datetime.now().isoformat(),
        "action": f"heartbeat:{action}",
        "result": result[:200] if result else "",
    }
    
    try:
        with open(COMMANDS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        log.warning(f"Failed to log heartbeat: {e}")


def log_error(error_type: str, message: str, context: dict = None):
    """Log errors for debugging."""
    _ensure_log_dir()
    
    entry = {
        "ts": datetime.now().isoformat(),
        "action": "error",
        "error_type": error_type,
        "message": message[:500],
    }
    
    if context:
        entry["context"] = context
    
    try:
        with open(COMMANDS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        log.warning(f"Failed to log error: {e}")


def get_recent_commands(limit: int = 50) -> list[dict]:
    """Get recent commands from log."""
    if not COMMANDS_LOG.exists():
        return []
    
    try:
        lines = COMMANDS_LOG.read_text().strip().split("\n")
        recent = lines[-limit:] if len(lines) > limit else lines
        return [json.loads(line) for line in recent if line.strip()]
    except Exception as e:
        log.warning(f"Failed to read commands log: {e}")
        return []


def get_stats() -> dict:
    """Get command statistics."""
    commands = get_recent_commands(1000)
    
    stats = {
        "total": len(commands),
        "by_action": {},
        "by_user": {},
    }
    
    for cmd in commands:
        action = cmd.get("action", "unknown")
        user = cmd.get("username", str(cmd.get("user_id", "unknown")))
        
        stats["by_action"][action] = stats["by_action"].get(action, 0) + 1
        stats["by_user"][user] = stats["by_user"].get(user, 0) + 1
    
    return stats
