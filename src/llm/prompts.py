"""
Shared prompt loading logic for all LLM connectors.

Single source of truth: .workspace/ files
Both Claude CLI and LiteLLM use the same files.
"""

from pathlib import Path

from config import PROJECT_DIR, WORKSPACE_DIR, CUSTOM_FACES_PATH
import json


def _load_custom_faces_list() -> str:
    """Load list of custom faces for system prompt."""
    if not CUSTOM_FACES_PATH.exists():
        return ""
    try:
        faces = json.loads(CUSTOM_FACES_PATH.read_text())
        if not faces:
            return ""
        return "Custom Moods: " + ", ".join(faces.keys())
    except Exception:
        return ""


def load_bot_instructions() -> str:
    """
    Load BOT_INSTRUCTIONS.md — the main system prompt.
    """
    workspace_file = WORKSPACE_DIR / "BOT_INSTRUCTIONS.md"
    if workspace_file.exists():
        return workspace_file.read_text()
    
    templates_file = PROJECT_DIR / "templates" / "BOT_INSTRUCTIONS.md"
    if templates_file.exists():
        return templates_file.read_text()
    
    return """You are an AI assistant on Raspberry Pi Zero 2W.
Use FACE: <mood> to express emotions. Be concise and expressive."""


def _load_workspace_file(name: str) -> str:
    """Load a file from .workspace/ (fallback to templates/)."""
    ws = WORKSPACE_DIR / name
    if ws.exists():
        return ws.read_text()
    tmpl = PROJECT_DIR / "templates" / name
    if tmpl.exists():
        return tmpl.read_text()
    return ""


def load_architecture() -> str:
    return _load_workspace_file("ARCHITECTURE.md")

def load_tools() -> str:
    return _load_workspace_file("TOOLS.md")

def load_soul() -> str:
    return _load_workspace_file("SOUL.md")

def load_identity() -> str:
    return _load_workspace_file("IDENTITY.md")


# Keywords that trigger loading extra context
ARCHITECTURE_KEYWORDS = [
    "how do you work", "how are you built", "architecture", "xp", "level",
    "memory system", "database", "heartbeat", "mail", "brotherhood",
    "technical", "internal", "explain yourself"
]

TOOLS_KEYWORDS = [
    "camera", "display", "e-ink", "hardware", "gpio", "sensor",
    "ssh", "config", "setup"
]

SOUL_KEYWORDS = [
    "who are you", "your personality", "your soul", "your identity",
    "what are you", "tell me about yourself", "your name", "your vibe",
    "кто ты", "расскажи о себе", "твоя личность",
    "change your personality", "update your soul", "update your identity",
    "your character", "your mood", "how do you feel"
]


def needs_extra_context(user_message: str) -> dict:
    """
    Detect if query needs extra context files.
    Returns dict of what to load.
    """
    msg_lower = user_message.lower()
    
    return {
        "architecture": any(kw in msg_lower for kw in ARCHITECTURE_KEYWORDS),
        "tools": any(kw in msg_lower for kw in TOOLS_KEYWORDS),
        "soul": any(kw in msg_lower for kw in SOUL_KEYWORDS),
    }


def format_skills_for_prompt() -> str:
    """
    Format active skills for system prompt.
    Returns skills list or empty string.
    """
    try:
        from skills.loader import get_eligible_skills
        skills = get_eligible_skills()
        
        if not skills:
            return ""
        
        lines = ["## Available Skills"]
        for skill in skills:
            name = getattr(skill, "name", "unknown")
            desc = (getattr(skill, "description", "") or "").split("\n")[0][:60]
            lines.append(f"- **{name}**: {desc}")
        
        return "\n".join(lines)
    except Exception:
        # Silently fail if skills not available
        return ""


def _build_memory_context() -> str:
    """
    Build compact memory section for system prompt.
    Includes: recent facts (from /remember) + today's daily log (summaries).
    Kept small — summaries are already compressed.
    """
    sections = []
    
    # 1. Recent facts from /remember (last 5, compact)
    try:
        from db.memory import get_recent_facts
        facts = get_recent_facts(limit=5)
        if facts:
            lines = ["## Memory (things you've been told to remember)"]
            for f in facts:
                cat = f.get("category", "general")
                content = f.get("content", "")[:120]
                lines.append(f"- [{cat}] {content}")
            sections.append("\n".join(lines))
    except Exception:
        pass
    
    # 2. Today's daily log (contains heartbeat summaries + reflections)
    try:
        from memory.flush import get_recent_daily_logs
        logs = get_recent_daily_logs(days=1)  # Just today
        if logs and len(logs.strip()) > 20:  # Skip if just a date header
            # Truncate if too long (max ~500 chars)
            if len(logs) > 500:
                logs = logs[:500] + "\n... (truncated)"
            sections.append(f"## Recent Activity Log (internal)\n{logs}")
    except Exception:
        pass
    
    return "\n\n".join(sections)


def build_system_context(user_message: str = "") -> str:
    """
    Build system context with lazy loading.
    Only includes ARCHITECTURE/TOOLS when query needs them.
    ALWAYS includes skills (if available).
    """
    parts = [load_bot_instructions()]
    
    # Add custom faces list if any
    custom_faces = _load_custom_faces_list()
    if custom_faces:
        parts.append(f"\n{custom_faces}")
    
    # CRITICAL FIX: Always include skills in system prompt!
    skills_text = format_skills_for_prompt()
    if skills_text:
        parts.append(f"\n---\n{skills_text}")
    
    # Lazy load based on query
    needs = needs_extra_context(user_message)
    
    if needs["architecture"]:
        arch = load_architecture()
        if arch:
            parts.append(f"\n---\n## Technical Reference\n{arch}")
    
    if needs["tools"]:
        tools = load_tools()
        if tools:
            parts.append(f"\n---\n## Hardware Notes\n{tools}")
    
    if needs["soul"]:
        soul = load_soul()
        if soul:
            parts.append(f"\n---\n{soul}")
        identity = load_identity()
        if identity:
            parts.append(f"\n---\n{identity}")
        parts.append(
            "\n💡 You can update SOUL.md and IDENTITY.md with write_file() "
            "to evolve your personality and self-description over time."
        )
    
    # --- Memory: recent facts + daily log summaries ---
    memory_parts = _build_memory_context()
    if memory_parts:
        parts.append(f"\n---\n{memory_parts}")
    
    # Minimal self-awareness (level + title only, no system stats)
    try:
        from db.stats import get_stats_summary
        g = get_stats_summary()
        parts.append(f"\n[Self: Level {g['level']} {g['title']} | XP: {g['xp']}]")
    except Exception:
        pass
    return "\n".join(parts)


def build_history_prompt(history: list[dict]) -> str:
    """Format conversation history for prompt."""
    if not history:
        return ""
    
    lines = ["\n--- Previous conversation ---"]
    for msg in history:
        role = "User" if msg["role"] == "user" else "Assistant"
        content = msg["content"][:500]  # Truncate long messages
        lines.append(f"{role}: {content}")
    
    return "\n".join(lines)


# How many recent messages to always show in conversation context
CONVERSATION_LAST_N = 5


def build_conversation_context(history: list[dict]) -> str:
    """
    Build a short "where we are" block for the system prompt:
    - Summary of what was discussed (before the last N messages)
    - Last N messages (user + assistant), including tool usage when present.

    "System" messages here = the single [Earlier: ...] summary injected by optimize_history.
    We skip that in the "last 5" list because we already show "Summary so far" above.
    Assistant messages often end with "Tool usage (N): ..." — we keep a longer preview so
    that tool usage is visible (useful context for the next turn).
    """
    # Only user/assistant for "recent" list (skip the one system msg = [Earlier: ...] summary)
    chat_turns = [m for m in history if m.get("role") in ("user", "assistant")]
    if not chat_turns:
        return ""
    
    try:
        from memory.summarize import summarize_old_messages
    except Exception:
        return ""
    
    last_n = CONVERSATION_LAST_N
    if len(chat_turns) <= last_n:
        summary_line = "Beginning of conversation."
        recent = chat_turns
    else:
        old_part = chat_turns[:-last_n]
        summary_line = summarize_old_messages(old_part)
        if not summary_line:
            summary_line = "Earlier messages in this chat."
        recent = chat_turns[-last_n:]
    
    # Preview length: longer for assistant so "Tool usage (N):" footer is usually included
    PREVIEW_USER = 200
    PREVIEW_ASSISTANT = 450  # enough for main reply + "Tool usage (1): add_scheduled_task(...)"
    
    lines = [
        "## Current conversation context",
        "",
        "**Summary so far:** " + (summary_line if summary_line.startswith("[") else summary_line),
        "",
        f"**Last {len(recent)} messages (most recent):**"
    ]
    for msg in recent:
        role = "User" if msg.get("role") == "user" else "Assistant"
        content = (msg.get("content") or "").strip()
        if role == "Assistant" and content.startswith("[Earlier:"):
            lines.append(f"- {role}: (summary of earlier turns)")
        else:
            cap = PREVIEW_ASSISTANT if role == "Assistant" else PREVIEW_USER
            preview = content[:cap] + ("..." if len(content) > cap else "")
            lines.append(f"- {role}: {preview}")
    
    return "\n".join(lines)
