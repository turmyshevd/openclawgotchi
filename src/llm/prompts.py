"""
Shared prompt loading logic for all LLM connectors.

Single source of truth: BOT_INSTRUCTIONS.md in .workspace/
Both Claude CLI and LiteLLM use the same files.
"""

from pathlib import Path

from config import PROJECT_DIR, WORKSPACE_DIR
from hardware.system import get_stats_string


def load_bot_instructions() -> str:
    """
    Load BOT_INSTRUCTIONS.md — the main system prompt.
    
    Priority:
    1. .workspace/BOT_INSTRUCTIONS.md (live bot personality)
    2. templates/BOT_INSTRUCTIONS.md (default)
    3. Minimal fallback
    """
    # Try workspace first
    workspace_file = WORKSPACE_DIR / "BOT_INSTRUCTIONS.md"
    if workspace_file.exists():
        return workspace_file.read_text()
    
    # Fallback to templates
    templates_file = PROJECT_DIR / "templates" / "BOT_INSTRUCTIONS.md"
    if templates_file.exists():
        return templates_file.read_text()
    
    # Minimal fallback
    return """You are an AI assistant on Raspberry Pi Zero 2W.
You have a 2.13" E-Ink display. Use show_face(mood, text) or output FACE: <mood> to express emotions.
Available moods: happy, sad, excited, thinking, love, surprised, bored, sleeping, hacker, disappointed, angry, crying, proud, nervous, confused, mischievous, cool, wink, dead, shock, suspicious, smug, cheering, celebrate.
Be concise and expressive."""


def build_system_context() -> str:
    """
    Build full system context: instructions + current stats.
    Used by all connectors to ensure consistent persona.
    """
    instructions = load_bot_instructions()
    stats = get_stats_string()
    
    return f"{instructions}\n\n---\n## Current System Status\n{stats}"


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
