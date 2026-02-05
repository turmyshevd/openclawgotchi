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


def load_architecture() -> str:
    """Load ARCHITECTURE.md — technical self-knowledge."""
    arch_file = WORKSPACE_DIR / "ARCHITECTURE.md"
    if arch_file.exists():
        return arch_file.read_text()
    return ""


def load_tools() -> str:
    """Load TOOLS.md — hardware and tool notes."""
    tools_file = WORKSPACE_DIR / "TOOLS.md"
    if tools_file.exists():
        return tools_file.read_text()
    return ""


# Keywords that trigger loading extra context
ARCHITECTURE_KEYWORDS = [
    "how do you work", "how are you built", "architecture", "xp", "level",
    "memory system", "database", "heartbeat", "mail", "brotherhood",
    "tools", "skills", "technical", "internal", "explain yourself"
]

TOOLS_KEYWORDS = [
    "camera", "display", "e-ink", "hardware", "gpio", "sensor",
    "ssh", "config", "setup"
]


def needs_extra_context(user_message: str) -> dict:
    """
    Detect if query needs extra context files.
    Returns dict of what to load.
    """
    msg_lower = user_message.lower()
    
    return {
        "architecture": any(kw in msg_lower for kw in ARCHITECTURE_KEYWORDS),
        "tools": any(kw in msg_lower for kw in TOOLS_KEYWORDS)
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
            name = skill.get("name", "unknown")
            desc = skill.get("description", "").split("\n")[0][:60]  # First line, truncated
            lines.append(f"- **{name}**: {desc}")
        
        return "\n".join(lines)
    except Exception:
        # Silently fail if skills not available
        return ""


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
    
    # Always include current stats (small)
    parts.append(f"\n---\n## System Status\n{get_stats_string()}")
    
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
