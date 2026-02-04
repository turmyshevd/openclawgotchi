# HEARTBEAT.md — Periodic Tasks

_This runs periodically. Keep it short to limit token burn._

## Sensors (Auto-injected)

- Uptime: {{uptime}}
- Temp: {{temp}}
- Memory: {{memory}}

## Checklist

*(Add tasks below. Comment out or delete what you don't need.)*

```
# 1. System Health
# - If Temp > 70C: FACE: sad, alert owner
# - If Memory < 50MB: FACE: thinking, alert owner

# 2. Sibling Check (if applicable)
# - Ping @proBroMacBot if no contact in 24h

# 3. Proactive Work
# - Review memory files
# - Check for pending tasks
```

## Response Options

**STATUS: OK** — Everything is fine, stay silent.

**GROUP: message** — Post to group chat.

**DM: message** — Private message to owner.

**FACE: mood** — Update display (happy, sad, thinking, etc.)

**DISPLAY: text** — Update status text on display.

---

_Keep this file minimal. Empty = skip heartbeat API calls._
