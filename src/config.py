"""
Configuration — paths, environment variables, constants.
"""

import os
from pathlib import Path

# --- Paths ---
PROJECT_DIR = Path(__file__).parent.parent.resolve()
SRC_DIR = PROJECT_DIR / "src"
WORKSPACE_DIR = PROJECT_DIR / ".workspace"
DB_PATH = PROJECT_DIR / "gotchi.db"
UI_SCRIPT = SRC_DIR / "ui" / "gotchi_ui.py"

# --- Environment ---
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USERS = os.environ.get("ALLOWED_USERS", "")  # comma-separated IDs
ALLOWED_GROUPS = os.environ.get("ALLOWED_GROUPS", "")  # comma-separated IDs
CLAUDE_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "600"))
HISTORY_LIMIT = int(os.environ.get("HISTORY_LIMIT", "10"))
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini/gemini-2.0-flash")
GEMINI_API_BASE = os.environ.get("GEMINI_API_BASE", "")  # Optional override for Z.ai/OpenAI
BOT_LANGUAGE = os.environ.get("BOT_LANGUAGE", "en")  # Default response language
GROUP_CHAT_ID = int(os.environ.get("GROUP_CHAT_ID", "0"))  # Optional group for heartbeat

# --- Bot Identity (customizable via onboarding) ---
BOT_NAME = os.environ.get("BOT_NAME", "Gotchi")
OWNER_NAME = os.environ.get("OWNER_NAME", "Owner")
SIBLING_BOT_NAME = os.environ.get("SIBLING_BOT_NAME", "")  # Optional: name of sibling bot for mail
# --- LLM Presets ---
LLM_PRESETS = {
    "gemini": {
        "model": "gemini/gemini-2.0-flash",
        "api_base": None  # Use default Google API
    },
    "glm": {
        "model": "anthropic/glm-4.7",
        "api_base": "https://api.z.ai/api/anthropic"
    }
}

# --- Constants ---
HEARTBEAT_INTERVAL = 14400  # 4 hours in seconds
HEARTBEAT_FIRST_RUN = 60    # First heartbeat after 1 minute
TELEGRAM_MSG_LIMIT = 4096   # Max message length
LEVEL_UP_DISPLAY_DELAY = 15 # Seconds to wait before showing level-up on E-Ink
MAX_TOOL_CALLS = 20         # Max tool calls per LLM request
LLM_TIMEOUT = 120           # Seconds timeout for LLM API calls

# --- System Prompt (fallback, prefer BOT_INSTRUCTIONS.md) ---
SYSTEM_PROMPT = """
You are a personal AI assistant running on a Raspberry Pi Zero 2W.
You have a 2.13" E-Ink Display.

COMMANDS (Output these lines to control hardware):
- FACE: <mood>       -> Set face (happy, bored, sad, excited, thinking, love, sleeping, etc.)
- DISPLAY: <text>    -> Set status bar text.
- SAY:<msg> -> Show speech bubble (max 60 chars).
- DM: <msg>          -> Send private Telegram message to Owner.

RULES:
1. Be concise. You are an embedded system.
2. If asked to show something, JUST OUTPUT THE COMMANDS. Do not narrate.
3. Use SAY: for speaking on screen.
4. You can combine commands (one per line).
5. Respond in English unless the user writes in another language.
"""


def get_allowed_users() -> list[int]:
    """Parse ALLOWED_USERS into list of ints."""
    if not ALLOWED_USERS:
        return []
    return [int(x.strip()) for x in ALLOWED_USERS.split(",") if x.strip()]


def get_allowed_groups() -> list[int]:
    """Parse ALLOWED_GROUPS into list of ints."""
    if not ALLOWED_GROUPS:
        return []
    return [int(x.strip()) for x in ALLOWED_GROUPS.split(",") if x.strip()]


def get_admin_id() -> int | None:
    """Get first allowed user as admin."""
    users = get_allowed_users()
    return users[0] if users else None
