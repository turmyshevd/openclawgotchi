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
Be concise and expressive."""


def load_architecture() -> str:
    """
    Load ARCHITECTURE.md — technical self-knowledge.
    This helps any model understand how the bot works internally.
    """
    arch_file = WORKSPACE_DIR / "ARCHITECTURE.md"
    if arch_file.exists():
        return arch_file.read_text()
    return ""


def build_system_context() -> str:
    """
    Build full system context: personality + architecture + stats.
    Used by all connectors to ensure consistent persona across models.
    """
    instructions = load_bot_instructions()
    architecture = load_architecture()
    stats = get_stats_string()
    
    context = instructions
    
    if architecture:
        context += f"\n\n---\n{architecture}"
    
    context += f"\n\n---\n## Current System Status\n{stats}"
    
    return context


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
