---
name: Weather
description: Get current weather and forecasts using wttr.in (no API key needed)
metadata:
  {
    "openclaw": {
      "emoji": "🌤️",
      "requires": { "bins": ["curl"] },
      "always": false
    }
  }
---

# Weather Skill

Get weather info using wttr.in — free, no API key needed, works perfectly on Pi Zero!

## Quick Commands

### One-liner (for E-Ink display)
```bash
curl -s "wttr.in/Moscow?format=3"
# Output: Moscow: ⛅️ +8°C
```

### Compact format (temp + humidity + wind)
```bash
curl -s "wttr.in/London?format=%l:+%c+%t+%h+%w"
# Output: London: ⛅️ +8°C 71% ↙5km/h
```

### Current conditions only
```bash
curl -s "wttr.in/Berlin?0T"
```

### Full 3-day forecast
```bash
curl -s "wttr.in/Tokyo?T"
```

## Format Codes

| Code | Meaning |
|------|---------|
| `%c` | Weather condition (emoji) |
| `%t` | Temperature |
| `%h` | Humidity |
| `%w` | Wind |
| `%l` | Location |
| `%m` | Moon phase |
| `%p` | Precipitation |

## Tips

- **URL-encode spaces:** `wttr.in/New+York` or `wttr.in/New%20York`
- **Airport codes work:** `wttr.in/JFK`, `wttr.in/SVO`
- **Force metric:** `?m` (Celsius, km/h)
- **Force imperial:** `?u` (Fahrenheit, mph)
- **Today only:** `?1`
- **Current only:** `?0`
- **No colors:** `?T` (better for parsing)

## Integration with E-Ink

Perfect for heartbeat or status display:

```python
import subprocess

def get_weather(city="Moscow"):
    result = subprocess.run(
        f'curl -s "wttr.in/{city}?format=%c+%t"',
        shell=True, capture_output=True, text=True
    )
    return result.stdout.strip()

# Use in heartbeat:
weather = get_weather()
show_face("happy", f"SAY:{weather}")
```

## Example Responses

```bash
# Quick
curl -s "wttr.in/Moscow?format=3"
→ Moscow: ☀️ -5°C

# Detailed  
curl -s "wttr.in/Moscow?format=%l:+%c+%t+(%h+humidity,+%w+wind)"
→ Moscow: ☀️ -5°C (45% humidity, ↑10km/h wind)
```

## Fallback: Open-Meteo API

If wttr.in is down, use Open-Meteo (JSON, no key):

```bash
# Get coordinates first (Moscow: 55.75, 37.62)
curl -s "https://api.open-meteo.com/v1/forecast?latitude=55.75&longitude=37.62&current_weather=true"
```

Returns JSON with `temperature`, `windspeed`, `weathercode`.
