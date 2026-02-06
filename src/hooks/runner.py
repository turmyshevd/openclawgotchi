"""
Hooks System — Event-driven automation.
Simple Python hooks that run on specific events.
"""

import logging
import importlib.util
from pathlib import Path
from typing import Callable, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from config import PROJECT_DIR, WORKSPACE_DIR

log = logging.getLogger(__name__)

# Hook directories (in order of precedence)
HOOKS_DIRS = [
    WORKSPACE_DIR / "hooks",      # Per-bot hooks (highest precedence)
    PROJECT_DIR / "hooks",        # Project hooks
]


@dataclass
class HookEvent:
    """Event passed to hook handlers."""
    event_type: str              # "startup", "message", "heartbeat", "command", etc.
    action: str = ""             # Specific action (e.g., "new", "clear")
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Context
    user_id: int = 0
    chat_id: int = 0
    username: str = ""
    text: str = ""
    
    # Results (hooks can modify)
    messages: list = field(default_factory=list)  # Messages to send
    data: dict = field(default_factory=dict)      # Additional data


# Registered hooks: {event_type: [handler_functions]}
_hooks: dict[str, list[Callable]] = {}


def register_hook(event_type: str, handler: Callable):
    """Register a hook handler for an event type."""
    if event_type not in _hooks:
        _hooks[event_type] = []
    _hooks[event_type].append(handler)
    log.debug(f"Registered hook for {event_type}: {handler.__name__}")


def run_hook(event: HookEvent) -> HookEvent:
    """
    Run all hooks for an event type.
    Hooks can modify the event (add messages, data).
    """
    handlers = _hooks.get(event.event_type, [])
    
    for handler in handlers:
        try:
            handler(event)
        except Exception as e:
            log.error(f"Hook error ({handler.__name__}): {e}")
    
    return event


def load_hooks_from_file(hook_file: Path) -> int:
    """
    Load hooks from a Python file.
    File should define hooks using @hook decorator or register_hook().
    Returns number of hooks loaded.
    """
    if not hook_file.exists():
        return 0
    
    try:
        spec = importlib.util.spec_from_file_location(
            hook_file.stem, 
            hook_file
        )
        if spec and spec.loader:
            before = sum(len(handlers) for handlers in _hooks.values())
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Count only hooks added by this file
            after = sum(len(handlers) for handlers in _hooks.values())
            count = after - before
            log.info(f"Loaded {count} hook(s) from {hook_file.name}")
            return count
    except Exception as e:
        log.error(f"Failed to load hooks from {hook_file}: {e}")
    
    return 0


def discover_and_load_hooks():
    """Discover and load all hooks from hook directories."""
    total = 0
    
    for hooks_dir in HOOKS_DIRS:
        if not hooks_dir.exists():
            continue
        
        for hook_file in hooks_dir.glob("*.py"):
            if hook_file.name.startswith("_"):
                continue
            total += load_hooks_from_file(hook_file)
    
    if total > 0:
        log.info(f"Loaded {total} hooks total")


# Decorator for easy hook registration
def hook(event_type: str):
    """Decorator to register a function as a hook handler."""
    def decorator(func: Callable):
        register_hook(event_type, func)
        return func
    return decorator


# ============================================================
# BUILT-IN HOOKS
# ============================================================

def _builtin_startup_hook(event: HookEvent):
    """Built-in startup hook — log startup."""
    from audit_logging.command_logger import log_command
    log_command(
        action="startup",
        user_id=0,
        chat_id=0,
        source="system",
        extra={"event": "bot_started"}
    )

def _builtin_message_hook(event: HookEvent):
    """Built-in message hook — log all messages."""
    from audit_logging.command_logger import log_command
    log_command(
        action="message",
        user_id=event.user_id,
        chat_id=event.chat_id,
        username=event.username,
        text=event.text,
    )

def _builtin_command_hook(event: HookEvent):
    """Built-in command hook — log commands."""
    from audit_logging.command_logger import log_command
    log_command(
        action=event.action,
        user_id=event.user_id,
        chat_id=event.chat_id,
        username=event.username,
    )

def _builtin_heartbeat_hook(event: HookEvent):
    """Built-in heartbeat hook — log heartbeats."""
    from audit_logging.command_logger import log_heartbeat
    log_heartbeat(event.action, event.text)


# Register built-in hooks
register_hook("startup", _builtin_startup_hook)
register_hook("message", _builtin_message_hook)
register_hook("command", _builtin_command_hook)
register_hook("heartbeat", _builtin_heartbeat_hook)
