"""
Rate limit tracking for LLM providers.
Parses actual Retry-After from provider responses instead of guessing.
Supports auto-retry for short limits.
"""

import logging
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from config import PROJECT_DIR

log = logging.getLogger(__name__)

# Persistent storage
LIMITS_FILE = PROJECT_DIR / "rate_limits.json"

# If retry <= this, it's a short (per-minute) limit — worth auto-retrying
SHORT_LIMIT_THRESHOLD = 90  # seconds

_limits_data = {}


def _load_limits():
    global _limits_data
    if LIMITS_FILE.exists():
        try:
            _limits_data = json.loads(LIMITS_FILE.read_text())
        except Exception:
            _limits_data = {}
    return _limits_data


def _save_limits():
    try:
        LIMITS_FILE.write_text(json.dumps(_limits_data, indent=2))
    except Exception as e:
        log.warning(f"Failed to save rate limits: {e}")


def _parse_retry_after(error_msg: str) -> Optional[float]:
    """
    Parse retry delay from provider error message.
    
    Providers communicate this differently:
    - "Retry-After: 30" (header-style)
    - "retry in 30s" / "retry in 30.5s" 
    - "retry after 60 seconds"
    - "Please retry after 2025-01-15T12:00:00Z" (absolute time)
    - "try again in 45s"
    - "rate_limit_delay: 15.0"
    """
    if not error_msg:
        return None
    
    msg = error_msg.lower()
    
    # Pattern 1: "Retry-After: 30" (seconds, from header)
    m = re.search(r'retry[- ]after[:\s]+(\d+\.?\d*)', msg)
    if m:
        return float(m.group(1))
    
    # Pattern 2: "retry in 30s" / "retry in 30.5 seconds" / "try again in 45s"
    m = re.search(r'(?:retry|try again) in (\d+\.?\d*)\s*s', msg)
    if m:
        return float(m.group(1))
    
    # Pattern 3: "retry after 60 seconds"
    m = re.search(r'retry after (\d+\.?\d*)\s*second', msg)
    if m:
        return float(m.group(1))
    
    # Pattern 4: "rate_limit_delay: 15.0"
    m = re.search(r'rate_limit_delay[:\s]+(\d+\.?\d*)', msg)
    if m:
        return float(m.group(1))
    
    # Pattern 5: "Please retry after 2025-..." (absolute ISO timestamp)
    m = re.search(r'retry after (\d{4}-\d{2}-\d{2}T[\d:.]+Z?)', msg)
    if m:
        try:
            reset_time = datetime.fromisoformat(m.group(1).rstrip('Z'))
            delta = (reset_time - datetime.utcnow()).total_seconds()
            return max(delta, 0)
        except Exception:
            pass
    
    return None


def record_rate_limit(provider: str, error_msg: str = ""):
    """
    Record a rate limit hit with actual provider data.
    Parses Retry-After from error message.
    """
    _load_limits()
    
    now = datetime.utcnow()
    retry_seconds = _parse_retry_after(error_msg)
    
    # Calculate actual reset time
    if retry_seconds is not None:
        reset_at = (now + timedelta(seconds=retry_seconds)).isoformat()
        limit_type = "short" if retry_seconds <= SHORT_LIMIT_THRESHOLD else "long"
        log.info(f"Rate limit for {provider}: retry in {retry_seconds:.0f}s ({limit_type})")
    else:
        # No Retry-After — use conservative fallback
        reset_at = (now + timedelta(minutes=60)).isoformat()
        limit_type = "unknown"
        log.info(f"Rate limit for {provider}: no Retry-After, assuming 60min")
    
    _limits_data[provider] = {
        "last_hit": now.isoformat(),
        "retry_seconds": retry_seconds,
        "reset_at": reset_at,
        "limit_type": limit_type,
        "error_preview": error_msg[:300] if error_msg else None
    }
    
    _save_limits()


def is_limited(provider: str) -> bool:
    """Check if a provider is currently rate limited."""
    _load_limits()
    
    if provider not in _limits_data:
        return False
    
    data = _limits_data[provider]
    reset_at = data.get("reset_at")
    
    if not reset_at:
        return False
    
    try:
        reset_time = datetime.fromisoformat(reset_at)
        if datetime.utcnow() >= reset_time:
            # Limit expired — auto-clear
            clear_limit(provider)
            return False
        return True
    except Exception:
        return False


def get_retry_after(provider: str) -> Optional[float]:
    """
    Get seconds until rate limit resets for a provider.
    Returns None if not limited, 0 if expired.
    """
    _load_limits()
    
    if provider not in _limits_data:
        return None
    
    data = _limits_data[provider]
    reset_at = data.get("reset_at")
    
    if not reset_at:
        return None
    
    try:
        reset_time = datetime.fromisoformat(reset_at)
        remaining = (reset_time - datetime.utcnow()).total_seconds()
        return max(remaining, 0)
    except Exception:
        return None


def should_auto_retry(provider: str) -> Optional[float]:
    """
    Check if we should auto-retry (short limit).
    Returns wait time in seconds, or None if we shouldn't retry.
    """
    remaining = get_retry_after(provider)
    
    if remaining is None:
        return None
    
    if remaining <= SHORT_LIMIT_THRESHOLD and remaining > 0:
        return remaining
    
    return None


def get_limit_status(provider: str) -> dict:
    """Get rate limit status for a provider."""
    _load_limits()
    
    if provider not in _limits_data:
        return {"status": "ok", "message": "No limits hit"}
    
    data = _limits_data[provider]
    remaining = get_retry_after(provider)
    
    if remaining is None or remaining <= 0:
        return {"status": "ok", "message": "Limit expired"}
    
    # Format remaining time
    if remaining < 60:
        time_str = f"{int(remaining)}s"
    elif remaining < 3600:
        time_str = f"{int(remaining / 60)}m {int(remaining % 60)}s"
    else:
        hours = int(remaining / 3600)
        mins = int((remaining % 3600) / 60)
        time_str = f"{hours}h {mins}m"
    
    return {
        "status": "limited",
        "provider": provider,
        "remaining_seconds": remaining,
        "reset_estimate": time_str,
        "limit_type": data.get("limit_type", "unknown"),
        "can_retry": remaining <= SHORT_LIMIT_THRESHOLD,
    }


def get_all_limits_summary() -> str:
    """Get summary of all rate limits for /status."""
    _load_limits()
    
    if not _limits_data:
        return "✅ No rate limits"
    
    lines = []
    for provider in list(_limits_data.keys()):
        status = get_limit_status(provider)
        if status["status"] == "limited":
            icon = "⏳" if not status.get("can_retry") else "🔄"
            lines.append(f"{icon} {provider}: ~{status['reset_estimate']} left")
        elif status["status"] == "ok":
            # Auto-cleaned, no need to show
            pass
    
    return "\n".join(lines) if lines else "✅ All clear"


def clear_limit(provider: str):
    """Clear a rate limit (on success or expiry)."""
    _load_limits()
    if provider in _limits_data:
        del _limits_data[provider]
        _save_limits()
        log.debug(f"Rate limit cleared for {provider}")
