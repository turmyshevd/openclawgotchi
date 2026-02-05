"""
Rate limit tracking for LLM providers.
Tracks when we hit 429 and estimates reset times.
"""

import logging
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from config import PROJECT_DIR

log = logging.getLogger(__name__)

# Storage file
LIMITS_FILE = PROJECT_DIR / "rate_limits.json"

# Gemini free tier resets at midnight PT (UTC-8)
GEMINI_DAILY_RESET_HOUR_UTC = 8

_limits_data = {}


def _load_limits():
    global _limits_data
    if LIMITS_FILE.exists():
        try:
            _limits_data = json.loads(LIMITS_FILE.read_text())
        except:
            _limits_data = {}
    return _limits_data


def _save_limits():
    try:
        LIMITS_FILE.write_text(json.dumps(_limits_data, indent=2))
    except Exception as e:
        log.warning(f"Failed to save rate limits: {e}")


def record_rate_limit(provider: str, error_msg: str = ""):
    """Record that we hit a rate limit."""
    _load_limits()
    
    now = datetime.utcnow().isoformat()
    
    # Parse retry delay if available
    retry_seconds = None
    if "retry in" in error_msg.lower():
        match = re.search(r"retry in ([\d.]+)", error_msg.lower())
        if match:
            retry_seconds = float(match.group(1))
    
    _limits_data[provider] = {
        "last_hit": now,
        "retry_seconds": retry_seconds,
        "error_preview": error_msg[:200] if error_msg else None
    }
    
    _save_limits()
    log.info(f"Rate limit recorded for {provider}")


def get_limit_status(provider: str) -> dict:
    """Get rate limit status for a provider."""
    _load_limits()
    
    if provider not in _limits_data:
        return {"status": "ok", "message": "No limits hit"}
    
    data = _limits_data[provider]
    last_hit = datetime.fromisoformat(data["last_hit"])
    now = datetime.utcnow()
    
    elapsed = now - last_hit
    elapsed_minutes = int(elapsed.total_seconds() / 60)
    
    if provider in ("gemini", "litellm"):
        # Gemini daily reset at midnight PT
        next_reset = now.replace(hour=GEMINI_DAILY_RESET_HOUR_UTC, minute=0, second=0, microsecond=0)
        if now.hour >= GEMINI_DAILY_RESET_HOUR_UTC:
            next_reset += timedelta(days=1)
        
        time_to_reset = next_reset - now
        hours_left = int(time_to_reset.total_seconds() / 3600)
        mins_left = int((time_to_reset.total_seconds() % 3600) / 60)
        
        return {
            "status": "limited",
            "provider": "Gemini",
            "last_hit_mins": elapsed_minutes,
            "reset_estimate": f"{hours_left}h {mins_left}m",
            "reset_time": next_reset.strftime("%H:%M UTC")
        }
    
    elif provider == "claude":
        # Claude ~4h cycles
        estimated_reset = last_hit + timedelta(hours=4)
        time_to_reset = estimated_reset - now
        
        if time_to_reset.total_seconds() < 0:
            return {"status": "ok", "message": "Should be reset"}
        
        hours_left = int(time_to_reset.total_seconds() / 3600)
        mins_left = int((time_to_reset.total_seconds() % 3600) / 60)
        
        return {
            "status": "limited",
            "provider": "Claude",
            "last_hit_mins": elapsed_minutes,
            "reset_estimate": f"{hours_left}h {mins_left}m",
        }
    
    return {"status": "unknown", "last_hit_mins": elapsed_minutes}


def get_all_limits_summary() -> str:
    """Get summary of all rate limits for /status."""
    _load_limits()
    
    if not _limits_data:
        return "✅ No rate limits"
    
    lines = []
    for provider in _limits_data:
        status = get_limit_status(provider)
        if status["status"] == "limited":
            lines.append(f"⏳ {status.get('provider', provider)}: ~{status['reset_estimate']} left")
        elif status["status"] == "ok":
            lines.append(f"✅ {provider}: OK")
    
    return "\n".join(lines) if lines else "✅ All clear"


def clear_limit(provider: str):
    """Clear a rate limit (call on successful request)."""
    _load_limits()
    if provider in _limits_data:
        del _limits_data[provider]
        _save_limits()
        log.info(f"Rate limit cleared for {provider}")
