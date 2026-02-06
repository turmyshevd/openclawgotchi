"""
Onboarding — First-run setup for new bots.
Checks for BOOTSTRAP.md and guides user through setup.
"""

import logging
from pathlib import Path

from config import WORKSPACE_DIR, PROJECT_DIR

log = logging.getLogger(__name__)

BOOTSTRAP_FILE = WORKSPACE_DIR / "BOOTSTRAP.md"


def needs_onboarding() -> bool:
    """
    Check if bot needs onboarding (BOOTSTRAP.md exists).
    Also checks templates/ as fallback if workspace is missing.
    """
    if BOOTSTRAP_FILE.exists():
        return True
    
    # Fallback: check templates (workspace might not be created yet)
    templates_bootstrap = PROJECT_DIR / "templates" / "BOOTSTRAP.md"
    if templates_bootstrap.exists() and not WORKSPACE_DIR.exists():
        log.warning("Workspace not initialized — onboarding should trigger after first message")
        return True
    
    return False


def get_bootstrap_prompt() -> str:
    """Get the bootstrap prompt for LLM."""
    # Try workspace first, then templates
    if BOOTSTRAP_FILE.exists():
        template = BOOTSTRAP_FILE.read_text()
    else:
        templates_bootstrap = PROJECT_DIR / "templates" / "BOOTSTRAP.md"
        if templates_bootstrap.exists():
            template = templates_bootstrap.read_text()
        else:
            return ""
    
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
    """
    Check if bot indicated onboarding is done.
    Triggers on explicit completion phrases or file deletion commands.
    """
    indicators = [
        # Explicit completion
        "deleting my bootstrap",
        "deleting bootstrap",
        "onboarding complete",
        "onboarding done",
        "setup complete",
        "i'm me now",
        "ready to go",
        "i know who i am",
        # File deletion commands
        "rm .workspace/bootstrap",
        "rm bootstrap.md",
        "delete bootstrap",
        # Writing identity (means they got the info)
        "saved to identity.md",
        "updated identity.md",
        "wrote identity.md",
    ]
    response_lower = response.lower()
    return any(ind in response_lower for ind in indicators)
