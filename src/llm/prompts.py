"""
Shared prompt loading logic for all LLM connectors.

Single source of truth: .workspace/ files
Both Claude CLI and LiteLLM use the same files.
"""

from pathlib import Path

from config import PROJECT_DIR, WORKSPACE_DIR
from hardware.system import get_stats_string


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
    
    # Stats for context only — do NOT encourage the model to echo them
    parts.append(
        "\n---\n## System Status (internal only — do NOT include in replies)\n"
        + get_stats_string()
        + "\nDo not add 'life update', temperature, or status tables to messages unless the user explicitly asked for status."
        + "\n\n⚠️ REMINDER: If you DO output status (when asked), use emoji + key:value format in code blocks. NO markdown tables (`| table |`) — they look bad. Example: `🎮 Level: 6` not `| Level | 6 |`."
    )
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
