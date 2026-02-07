"""
Auto-mood system — Pwnagotchi-style reactive emotions.
Sets face based on system state: temp, RAM, uptime, time of day.
"""

import logging
import re
from datetime import datetime
from typing import Optional

from hardware.system import get_stats
from hardware.display import show_face

log = logging.getLogger(__name__)

# Thresholds
TEMP_HOT = 65       # °C — start sweating
TEMP_CRITICAL = 75  # °C — panic mode
RAM_LOW = 80        # MB free — getting nervous  
RAM_CRITICAL = 50   # MB free — panic
UPTIME_PROUD = 86400  # 1 day — achievement!
UPTIME_LEGEND = 604800  # 1 week — legendary

# Time-based moods
NIGHT_START = 23
NIGHT_END = 7
MORNING_START = 7
MORNING_END = 10


def get_auto_mood() -> tuple[str, str]:
    """
    Determine mood based on system state.
    Returns: (mood, status_text)
    """
    stats = get_stats()
    hour = datetime.now().hour
    
    # Parse values
    try:
        temp_match = re.search(r"(-?\d+(?:\.\d+)?)", str(stats.temp))
        temp = float(temp_match.group(1)) if temp_match else 45.0
    except Exception:
        temp = 45.0
    
    try:
        # Memory format: "used/total (XX% free)" or similar
        mem_parts = stats.memory.split()
        for part in mem_parts:
            if 'MB' in part or part.isdigit():
                # Try to extract free memory
                pass
        # Fallback: parse from free command
        import subprocess
        result = subprocess.run(['free', '-m'], capture_output=True, text=True)
        lines = result.stdout.strip().split('\n')
        mem_line = lines[1].split()
        ram_free = int(mem_line[6]) if len(mem_line) > 6 else int(mem_line[3])
    except:
        ram_free = 200
    
    try:
        # Uptime format: "Xd Xh" or "Xh Xm"
        uptime_str = stats.uptime
        uptime_seconds = 0
        if 'd' in uptime_str:
            days = int(uptime_str.split('d')[0])
            uptime_seconds += days * 86400
        if 'h' in uptime_str:
            hours_part = uptime_str.split('d')[-1] if 'd' in uptime_str else uptime_str
            hours = int(hours_part.split('h')[0].strip())
            uptime_seconds += hours * 3600
    except:
        uptime_seconds = 3600
    
    # Priority checks (highest priority first)
    
    # 1. CRITICAL states
    if temp >= TEMP_CRITICAL:
        return "dead", f"OVERHEATING {temp}°C!"
    
    if ram_free <= RAM_CRITICAL:
        return "dead", f"OOM! {ram_free}MB left"
    
    # 2. Warning states  
    if temp >= TEMP_HOT:
        return "nervous", f"Hot! {temp}°C"
    
    if ram_free <= RAM_LOW:
        return "nervous", f"Low RAM: {ram_free}MB"
    
    # 3. Achievement states
    if uptime_seconds >= UPTIME_LEGEND:
        days = uptime_seconds // 86400
        return "proud", f"LEGEND! {days}d uptime"
    
    if uptime_seconds >= UPTIME_PROUD:
        days = uptime_seconds // 86400
        return "proud", f"{days}d uptime!"
    
    # 4. Time-based moods
    if hour >= NIGHT_START or hour < NIGHT_END:
        return "sleeping", "Zzz..."
    
    if MORNING_START <= hour < MORNING_END:
        return "awakening", "Morning!"
    
    # 5. Default states (vary by context)
    # Could add more variety here based on recent activity
    moods = [
        ("happy", "All good!"),
        ("cool", "Chillin'"),
        ("observing", "Watching..."),
    ]
    
    # Pick based on minute for variety
    idx = datetime.now().minute % len(moods)
    return moods[idx]


def apply_auto_mood(override_text: Optional[str] = None) -> tuple[str, str]:
    """
    Apply auto-mood to display.
    Returns: (mood, text) that was applied.
    """
    mood, text = get_auto_mood()
    
    if override_text:
        text = override_text
    
    try:
        show_face(mood, text)
        log.info(f"Auto-mood applied: {mood} - {text}")
    except Exception as e:
        log.error(f"Failed to apply auto-mood: {e}")
    
    return mood, text
