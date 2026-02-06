# AGENTS.md — Project Rules

> This file is for AI agents and developers working on the project.
> For bot personality, see `.workspace/AGENTS.md` (created from templates/).

## Project Structure

```
openclawgotchi/
├── .workspace/          # Bot's live personality (gitignored, auto-created by setup.sh)
│   ├── BOT_INSTRUCTIONS.md
│   ├── SOUL.md, IDENTITY.md, USER.md
│   ├── HEARTBEAT.md, MEMORY.md, AGENTS.md
│   └── memory/          # Daily logs (YYYY-MM-DD.md)
│
├── templates/           # Default personality templates
│   ├── BOOTSTRAP.md     # First-run onboarding ritual
│   ├── BOT_INSTRUCTIONS.md  # System prompt
│   ├── SOUL.md, IDENTITY.md, USER.md
│   ├── HEARTBEAT.md, MEMORY.md, AGENTS.md
│   ├── TOOLS.md, BOOT.md, ARCHITECTURE.md
│
├── src/                 # Python source code
│   ├── main.py          # Entry point
│   ├── config.py        # Paths, env vars
│   ├── bot/             # Telegram handlers, heartbeat, onboarding
│   ├── db/              # SQLite: messages, facts, stats
│   ├── llm/             # Claude CLI + LiteLLM (router, prompts)
│   ├── ui/              # E-Ink display (gotchi_ui.py)
│   ├── hardware/        # Display control, auto-mood
│   ├── drivers/         # E-Ink driver (epd2in13_V4)
│   ├── skills/          # Skill loader & gating
│   ├── hooks/           # Event-driven automation
│   ├── cron/            # Scheduled tasks
│   ├── memory/          # Summarization, flush prompts
│   ├── audit_logging/   # Command logger
│   └── utils/           # Doctor, patch_self
│
├── gotchi-skills/       # Pi-optimized active skills
│   ├── coding/          # Self-modification
│   ├── display/         # E-Ink control
│   ├── weather/         # wttr.in
│   ├── system/          # Pi administration
│   └── discord/         # Discord integration
│
├── lore/                # Project backstory (optional)
│
├── setup.sh             # Interactive setup wizard
├── harden.sh            # Pi hardening (swap, watchdog, RAM)
├── .env.example         # Configuration template
└── LICENSE              # MIT
```

## Getting Started

1. On Pi: clone repo, run `./setup.sh` (creates `.env`, `.workspace/`, installs deps, starts service)
2. Or manually: copy `.env.example` → `.env`, copy `templates/` → `.workspace/`, configure, `python3 src/main.py`
3. Service name: `gotchi-bot` (not claude-bot)

## Code Style

- Python 3.9+
- Keep memory usage low (512MB Pi)
- One Claude CLI call at a time (asyncio lock)
- Use SQLite efficiently (FTS5 for search)
- E-Ink updates are slow (~2–3s)

## Safety Rules

- **No credentials in code** — Use `.env`
- **No heavy processes** — 512MB RAM limit
- **`trash` > `rm`** — Recoverable deletes
- **Ask before external actions** — Network, installs

## Key Files

| File | Purpose |
|------|---------|
| `src/main.py` | Telegram bot, message handling |
| `src/bot/handlers.py` | Command handlers |
| `src/bot/heartbeat.py` | Periodic reflection |
| `src/llm/router.py` | Claude vs LiteLLM routing |
| `src/ui/gotchi_ui.py` | E-Ink display, faces |
| `src/skills/loader.py` | Skill loading & catalog |
| `.workspace/` | Bot personality (gitignored) |
| `templates/` | Default templates |
| `gotchi-skills/` | Pi-specific skills |

## Adding Features

1. Bot behavior: Edit `templates/` (or `.workspace/` for live bot)
2. Code: Edit `src/`
3. Skills: Add to `gotchi-skills/`
4. Display faces: `src/ui/gotchi_ui.py` → `faces` dict

## External Dependencies

- **openclaw-skills/** — Optional. Clone separately for reference skill catalog:
  ```bash
  git clone https://github.com/openclaw/skills openclaw-skills
  ```

## Deployment

```bash
# Deploy to Pi
scp -r . pi@raspberrypi:~/openclawgotchi/
ssh pi@raspberrypi "cd openclawgotchi && ./setup.sh"

# Restart service
ssh pi@raspberrypi "sudo systemctl restart gotchi-bot"

# View logs
ssh pi@raspberrypi "journalctl -u gotchi-bot -f"
```
