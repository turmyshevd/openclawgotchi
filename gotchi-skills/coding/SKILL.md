---
name: Self-Improvement (Coding)
description: Modify your own source code, understand project structure, add new features.
metadata:
  {
    "openclaw": {
      "emoji": "🛠️",
      "requires": { "bins": ["python3"] },
      "always": true
    }
  }
---

# Self-Improvement Protocol

Use this skill when you need to understand or modify your own code.

---

## Project Structure Map

```
openclawgotchi/
│
├── .workspace/              # YOUR SOUL (gitignored, personal)
│   ├── BOT_INSTRUCTIONS.md  # Master prompt (auto-loaded)
│   ├── SOUL.md              # Your personality
│   ├── IDENTITY.md          # Who you are
│   ├── USER.md              # Owner profile
│   ├── MEMORY.md            # Curated long-term memory
│   ├── TOOLS.md             # Hardware notes
│   ├── HEARTBEAT.md         # Periodic tasks template
│   └── memory/              # Daily logs (YYYY-MM-DD.md)
│
├── templates/               # Generic versions (for new bots)
│
├── src/                     # SOURCE CODE
│   │
│   ├── main.py              # Entry point (minimal, just wires things)
│   ├── config.py            # All paths, env vars, constants
│   │
│   ├── llm/                 # LLM CONNECTORS
│   │   ├── prompts.py       # Shared prompt loading
│   │   ├── base.py          # Abstract interface
│   │   ├── claude.py        # Claude CLI connector
│   │   ├── litellm_connector.py  # LiteLLM + all tools
│   │   └── router.py        # Auto-fallback logic
│   │
│   ├── bot/                 # TELEGRAM
│   │   ├── handlers.py      # /start, /clear, /status, etc.
│   │   ├── heartbeat.py     # Periodic tasks
│   │   └── telegram.py      # Auth, message helpers
│   │
│   ├── db/                  # DATABASE
│   │   └── memory.py        # SQLite: messages, facts, tasks
│   │
│   ├── hardware/            # HARDWARE
│   │   ├── display.py       # E-Ink control, command parsing
│   │   └── system.py        # Uptime, temp, RAM stats
│   │
│   ├── hooks/               # EVENT AUTOMATION
│   │   └── runner.py        # on_startup, on_message, on_heartbeat
│   │
│   ├── cron/                # SCHEDULER
│   │   └── scheduler.py     # add_cron_job, list, remove
│   │
│   ├── skills/              # SKILLS LOADER
│   │   └── loader.py        # Gating (requires: bins, env, os)
│   │
│   ├── logging/             # AUDIT
│   │   └── command_logger.py  # JSONL trail
│   │
│   ├── memory/              # MEMORY UTILS
│   │   └── flush.py         # Daily logs, flush prompt
│   │
│   ├── ui/                  # E-INK UI
│   │   └── gotchi_ui.py     # Faces dict, rendering
│   │
│   ├── drivers/             # HARDWARE DRIVERS
│   │   └── epd2in13_V4.py   # Waveshare E-Ink driver
│   │
│   └── utils/               # UTILITIES
│       ├── doctor.py        # Health check
│       └── patch_self.py    # Safe file writing
│
├── gotchi-skills/           # PI-SPECIFIC SKILLS
│   ├── display/             # E-Ink usage docs
│   └── coding/              # This file
│
├── logs/                    # RUNTIME LOGS
│   └── commands.jsonl       # Audit trail
│
├── data/                    # RUNTIME DATA
│   └── cron_jobs.json       # Scheduled tasks
│
└── claude_bot.db            # SQLite database
```

---

## Quick Reference: What's Where

| I need to... | Look in... |
|--------------|------------|
| Change bot personality | `.workspace/SOUL.md`, `IDENTITY.md` |
| Add new Telegram command | `src/bot/handlers.py` |
| Modify E-Ink faces | `src/ui/gotchi_ui.py` (faces dict) |
| Add new LLM tool | `src/llm/litellm_connector.py` |
| Change system prompt | `templates/BOT_INSTRUCTIONS.md` or `.workspace/` |
| Add new hook | `src/hooks/runner.py` or `.workspace/hooks/` |
| Change auth logic | `src/bot/telegram.py:is_allowed()` |
| Add database table | `src/db/memory.py:init_db()` |
| Change heartbeat behavior | `src/bot/heartbeat.py` |
| Update display commands | `src/hardware/display.py` |

---

## Tools Available

| Tool | Description |
|------|-------------|
| `read_file(path)` | Read any file |
| `write_file(path, content)` | Write/create (auto-backup) |
| `execute_bash(command)` | Run shell commands |
| `list_directory(path)` | List files |
| `show_face(mood, text)` | Display emotion |
| `remember_fact(cat, fact)` | Save to memory |
| `recall_facts(query)` | Search memory |
| `read_skill(name)` | Read skill docs |
| `write_daily_log(entry)` | Log to daily file |
| `add_scheduled_task(...)` | Add cron job |
| `restart_self()` | Restart bot service |

---

## Common Modifications

### Add a New Telegram Command

1. Open `src/bot/handlers.py`
2. Add handler function:
```python
async def cmd_mycommand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not is_allowed(user.id, chat.id):
        return
    # Your logic here
    await update.message.reply_text("Done!")
```
3. Register in `src/main.py`:
```python
app.add_handler(CommandHandler("mycommand", cmd_mycommand))
```
4. Restart: `sudo systemctl restart claude-bot`

### Add a New E-Ink Face

1. Open `src/ui/gotchi_ui.py`
2. Find the `faces = {` dictionary (~line 142)
3. Add your face:
```python
"myface": "(◕‿◕)♪",
```
4. Now you can use `show_face("myface")` or `FACE: myface`

### Add a New LLM Tool

1. Open `src/llm/litellm_connector.py`
2. Add the function:
```python
def my_tool(arg1: str) -> str:
    """Does something."""
    # Use existing modules!
    from db.memory import add_fact
    add_fact(arg1, "mytool")
    return "Done"
```
3. Add to TOOLS list:
```python
{"type": "function", "function": {
    "name": "my_tool",
    "description": "Does something",
    "parameters": {"type": "object", "properties": {
        "arg1": {"type": "string"}
    }, "required": ["arg1"]}
}},
```
4. Add to TOOL_MAP:
```python
"my_tool": my_tool,
```

### Add a Hook

Create `.workspace/hooks/my_hook.py`:
```python
from hooks.runner import hook

@hook("message")
def log_keywords(event):
    if "important" in event.text.lower():
        from memory.flush import write_to_daily_log
        write_to_daily_log(f"Important message from {event.username}")
```

---

## Safety Rules

1. **Backup first** — `write_file` does this automatically
2. **Check syntax** — Use `check_syntax("path/to/file.py")`
3. **Memory is tight** — 512MB RAM, avoid heavy deps
4. **Log changes** — `write_daily_log("Changed X in Y")`
5. **Test before restart** — Syntax errors = bot won't start!

---

## After Code Changes — RESTART PROCEDURE

### Option 1: Safe Restart (Recommended)
```python
# Checks all critical files, then restarts if OK
safe_restart()
```
This will:
1. Check syntax of main.py, handlers.py, litellm_connector.py, router.py
2. If errors found → report them, don't restart
3. If all OK → restart in 3 seconds

### Option 2: Manual
```python
# 1. Check the file you modified
check_syntax("src/bot/handlers.py")

# 2. If OK, restart
restart_self()
```

### Option 3: Shell (if tools unavailable)
```bash
# Verify syntax
python3 -m py_compile src/bot/handlers.py

# Restart
sudo systemctl restart claude-bot

# Check status
sudo systemctl status claude-bot
journalctl -u claude-bot -n 20
```

---

## Complete Self-Modification Flow

```
1. read_skill("coding")           # Understand project structure
2. read_file("src/bot/handlers.py")   # Read current code
3. write_file("src/bot/handlers.py", new_code)  # Modify (auto-backup)
4. check_syntax("src/bot/handlers.py")  # Verify
5. write_daily_log("Added /ping command")  # Log the change
6. safe_restart()                 # Apply changes
```

The bot will restart, reload the new code, and come back online.
