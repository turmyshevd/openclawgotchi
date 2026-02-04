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
    """Get stats as formatted string for prompts."""
    stats = get_stats()
    return f"[SYSTEM STATS]\nUptime: {stats.uptime}\nTemp: {stats.temp}\nMemory: {stats.memory}"
