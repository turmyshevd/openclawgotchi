# BOOT.md — Startup Checklist

_Add short, explicit instructions for what the bot should do on startup._

## On Service Start

When the bot service starts, do these checks:

1. Verify hardware is healthy (temp < 70C, mem > 50MB free)
2. Update display if available (show "Online" or current mood)
3. Optionally send a startup message to owner

## Example Tasks

```
# Check system health
# If temp > 70C: FACE: sad, DM: "I'm overheating!"
# If mem < 50MB: FACE: thinking, DM: "Low memory warning"
# Otherwise: FACE: happy, DISPLAY: Online
```

## Keep It Short

This file runs on every restart. Keep it minimal to avoid token burn.

If the task sends a message, just do it — no confirmation needed.

---

_Delete or comment out this content if you don't need startup tasks._
