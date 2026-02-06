"""
System stats — temperature, memory, uptime.
"""

import subprocess
from dataclasses import dataclass


@dataclass
class SystemStats:
    uptime: str = "?"
    temp: str = "?"
    memory: str = "?"
    
    def __str__(self) -> str:
        return f"Uptime: {self.uptime} | Temp: {self.temp} | RAM: {self.memory}"
    
    def to_dict(self) -> dict:
        return {"uptime": self.uptime, "temp": self.temp, "memory": self.memory}


def get_stats() -> SystemStats:
    """Gather current system stats."""
    stats = SystemStats()
    
    # Uptime
    try:
        result = subprocess.run(
            ["uptime", "-p"], 
            capture_output=True, 
            text=True, 
            timeout=5
        )
        stats.uptime = result.stdout.strip()
    except Exception:
        pass
    
    # Temperature
    try:
        # Try vcgencmd first (Raspberry Pi)
        result = subprocess.run(
            ["vcgencmd", "measure_temp"], 
            capture_output=True, 
            text=True, 
            timeout=5
        )
        if result.returncode == 0:
            stats.temp = result.stdout.strip()
        else:
            # Fallback to thermal zone
            result = subprocess.run(
                ["cat", "/sys/class/thermal/thermal_zone0/temp"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                temp_c = int(result.stdout.strip()) / 1000
                stats.temp = f"{temp_c:.1f}'C"
    except Exception:
        pass
    
    # Memory
    try:
        result = subprocess.run(
            ["free", "-h"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.splitlines()
            if len(lines) > 1:
                parts = lines[1].split()
                if len(parts) >= 7:
                    stats.memory = f"Free: {parts[6]}"
    except Exception:
        pass
    
    return stats


def get_stats_string() -> str:
    """Get stats as formatted string for prompts (with self-awareness)."""
    stats = get_stats()
    
    # Add gotchi stats for self-awareness
    try:
        from db.stats import get_stats_summary
        g = get_stats_summary()
        self_info = f"[SELF] Level {g['level']} {g['title']} | XP: {g['xp']} | Messages: {g['messages']}"
    except Exception:
        self_info = "[SELF] Stats loading..."
    
    try:
        from config import PROJECT_DIR, DB_PATH
        paths_info = f"[PATHS] Project: {PROJECT_DIR} | DB: {DB_PATH}"
    except Exception:
        paths_info = ""
    
    return f"{self_info}\n[SYSTEM] Uptime: {stats.uptime} | Temp: {stats.temp} | RAM: {stats.memory}\n{paths_info}"
