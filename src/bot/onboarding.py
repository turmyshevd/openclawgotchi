"""
Onboarding — First-run setup for new bots.
Checks for BOOTSTRAP.md and guides user through setup.
"""

import logging
from pathlib import Path

from config import WORKSPACE_DIR

log = logging.getLogger(__name__)

BOOTSTRAP_FILE = WORKSPACE_DIR / "BOOTSTRAP.md"


def needs_onboarding() -> bool:
    """Check if bot needs onboarding (BOOTSTRAP.md exists)."""
    return BOOTSTRAP_FILE.exists()


def get_bootstrap_prompt() -> str:
    """Get the bootstrap prompt for LLM."""
    if not BOOTSTRAP_FILE.exists():
        return ""
    
    template = BOOTSTRAP_FILE.read_text()
    
    prompt = (
        "[FIRST RUN - ONBOARDING MODE]\n\n"
        "This is your FIRST conversation ever. Follow the bootstrap instructions:\n\n"
        f"{template}\n\n"
        "Start the conversation warmly. Ask about your identity and their info. "
        "Use your E-Ink face to express yourself!"
    )
    
    return prompt


def complete_onboarding():
    """Mark onboarding as complete by deleting BOOTSTRAP.md."""
    if BOOTSTRAP_FILE.exists():
        BOOTSTRAP_FILE.unlink()
        log.info("Onboarding complete — BOOTSTRAP.md deleted")
        return True
    return False


def check_onboarding_complete(response: str) -> bool:
    """Check if bot indicated onboarding is done."""
    indicators = [
        "deleting my bootstrap",
        "deleting bootstrap",
        "rm .workspace/BOOTSTRAP.md",
        "onboarding complete",
        "i'm me now",
        "ready to go"
    ]
    response_lower = response.lower()
    return any(ind in response_lower for ind in indicators)
