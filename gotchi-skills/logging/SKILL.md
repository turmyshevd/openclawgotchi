---
name: Logging
description: Where logs live and when to write them — errors, daily, system
metadata:
  {
    "openclaw": {
      "emoji": "📋",
      "requires": {},
      "always": false
    }
  }
---

# Logging

You have several log sinks. Use them so you (and Dmitry) can see what broke and when.

## Where logs are

| What | Where | How to read |
|------|--------|-------------|
| **Critical errors** | `data/ERROR_LOG.md` | `read_file("data/ERROR_LOG.md")` or tool `log_error()` to append |
| **Display failures** | `data/display_error.log` | `read_file("data/display_error.log")` — written by gotchi_ui.py on crash |
| **Daily notes** | `memory/YYYY-MM-DD.md` | `write_daily_log(entry)` to append; read via read_file |
| **Code changes** | `CHANGELOG.md` | `log_change(description)` to append |
| **Service / system** | journalctl | `manage_service(gotchi-bot, logs)` or bash `journalctl -u gotchi-bot -n 50` |
| **Conversation** | `gotchi.db` (messages) | `recall_messages(limit)` |

## When to use what

- **Something broke (display, service, disk, health):**  
  Call `log_error("short description")` so it’s in `data/ERROR_LOG.md`. Then you can say “last error was …” or read the file when asked.

- **health_check() found problems:**  
  Call `log_error("health_check: <what’s wrong>")` so there’s a record.

- **User says “what went wrong”:**  
  Read `data/ERROR_LOG.md` (and optionally `data/display_error.log`) and summarize.

- **Daily / notable events:**  
  Use `write_daily_log(entry)`.

- **You changed code/config:**  
  Use `log_change(description)`.

## No direct system log “tool”

You don’t have a function that returns raw system logs; use `manage_service(service, action=logs)` or `execute_bash("journalctl -u gotchi-bot -n 50")` when you need recent service output.

## Size limits (so we don't fill disk on Pi)

- **ERROR_LOG.md** — only last 300 lines kept; older lines are dropped when appending.
- **display_error.log** — only last 200 lines kept.
- Daily logs and CHANGELOG are not auto-trimmed; trim manually if needed.

## Summary

- **Errors** → `log_error(message)` → `data/ERROR_LOG.md`
- **Display crash** → already in `data/display_error.log` (no tool needed)
- **“When did something break?”** → read `data/ERROR_LOG.md`
