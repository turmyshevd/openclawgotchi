"""
Memory Flush — Prompt to save important info before context limit.
Inspired by OpenClaw's pre-compaction memory flush.

Includes LLM-powered conversation summarization for heartbeat.
"""

import logging
from datetime import datetime
from pathlib import Path

from config import WORKSPACE_DIR, HISTORY_LIMIT

log = logging.getLogger(__name__)

# Threshold: when history is this % full, suggest memory flush
FLUSH_THRESHOLD = 0.8  # 80% of HISTORY_LIMIT

# Track last summarized message count per chat to avoid re-summarizing
_last_summary_msg_count: dict[int, int] = {}


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


# ============================================================
# LLM SUMMARIZATION (for heartbeat)
# ============================================================

SUMMARY_PROMPT = """Summarize this conversation in 2-3 bullet points.
Focus on: key topics discussed, decisions made, important info learned about the user.
Be very concise (max 100 words total).

Conversation:
{conversation}

Summary (bullet points only):"""


async def summarize_conversation_with_llm(history: list[dict], chat_id: int = 0) -> str | None:
    """
    Use LLM to create a brief summary of conversation.
    Called during heartbeat, not in main message flow.
    
    Returns summary string or None if failed/skipped.
    """
    if not history or len(history) < 3:
        return None  # Not enough to summarize
    
    # Skip if we already summarized this chat
    last_count = _last_summary_msg_count.get(chat_id, 0)
    if len(history) <= last_count:
        log.debug(f"Skipping summary for chat {chat_id} — no new messages since last")
        return None
    
    # Format conversation for summarization
    conv_text = []
    for msg in history[-10:]:  # Last 10 messages max
        role = "User" if msg.get("role") == "user" else "Bot"
        content = msg.get("content", "")[:200]  # Truncate long messages
        # Skip display commands
        if content.strip().upper().startswith(("FACE:", "DISPLAY:", "SAY:")):
            continue
        conv_text.append(f"{role}: {content}")
    
    if len(conv_text) < 2:
        return None
    
    conversation = "\n".join(conv_text)
    prompt = SUMMARY_PROMPT.format(conversation=conversation)
    
    try:
        # Use LiteLLM for summarization (same preset as Lite mode)
        from litellm import acompletion
        from config import DEFAULT_LITE_PRESET, LLM_PRESETS
        
        preset = LLM_PRESETS.get(DEFAULT_LITE_PRESET, LLM_PRESETS["glm"])
        model = preset["model"]
        kwargs = dict(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.3,
        )
        if preset.get("api_base"):
            kwargs["api_base"] = preset["api_base"]
        
        response = await acompletion(**kwargs)
        
        summary = response.choices[0].message.content.strip()
        
        # Update tracking for this chat
        _last_summary_msg_count[chat_id] = len(history)
        
        log.info(f"LLM summary generated: {summary[:50]}...")
        return summary
        
    except Exception as e:
        log.warning(f"LLM summarization failed: {e}")
        return None


async def summarize_and_save(chat_id: int) -> bool:
    """
    Summarize recent conversation and save to daily log.
    Call this from heartbeat.
    
    Returns True if summary was saved.
    """
    from db.memory import get_history
    
    history = get_history(chat_id)
    if not history:
        return False
    
    summary = await summarize_conversation_with_llm(history, chat_id=chat_id)
    if not summary:
        return False
    
    # Save to daily log
    write_to_daily_log(f"[Conversation Summary]\n{summary}")
    
    return True


def get_chats_with_recent_messages() -> list[int]:
    """Get chat IDs that had messages since last heartbeat."""
    from db.memory import get_connection
    from datetime import timedelta
    
    # Messages in last 4 hours (heartbeat interval)
    cutoff = (datetime.now() - timedelta(hours=4)).isoformat()
    
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT DISTINCT user_id FROM messages WHERE timestamp > ? LIMIT 10",
            (cutoff,)
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception as e:
        log.warning(f"Failed to get recent chats: {e}")
        return []
