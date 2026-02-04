# AGENTS.md — Project Rules

> This file is for AI agents and developers working on the project.
> For bot personality, see `.workspace/AGENTS.md` (create from templates/).

## Project Structure

```
openclawgotchi/
├── .workspace/          # Bot's live personality (gitignored)
│   └── (copy from templates/, customize for your bot)
│
├── templates/           # Default personality templates
│   ├── BOOTSTRAP.md     # First-run ritual
│   ├── SOUL.md          # Personality definition
│   ├── IDENTITY.md      # Bot metadata
│   ├── USER.md          # Owner profile
│   ├── TOOLS.md         # Hardware notes
│   ├── AGENTS.md        # Workspace rules
│   ├── HEARTBEAT.md     # Periodic tasks
│   ├── MEMORY.md        # Long-term memory
│   ├── BOOT.md          # Startup checklist
│   └── BOT_INSTRUCTIONS.md  # System prompt
│
├── src/                 # Python source code
│   ├── main.py          # Entry point
│   ├── ui/              # E-Ink display
│   ├── drivers/         # Hardware drivers
│   ├── agent/           # LiteLLM fallback
│   └── utils/           # Utilities
│
├── gotchi-skills/       # Pi-optimized skills
│   ├── display/         # E-Ink control
│   └── coding/          # Self-modification
│
├── lore/                # Project backstory (optional)
├── archive/             # Old/unused files
│
├── setup.sh             # Installation script
├── harden.sh            # Pi hardening
├── .env.example         # Configuration template
└── LICENSE              # MIT
```

## Getting Started

1. Copy `templates/` to `.workspace/`
2. Customize `.workspace/` files for your bot
3. Copy `.env.example` to `.env` and configure
4. Run `./setup.sh` on your Pi
5. Start with `python3 src/main.py`

## Code Style

- Python 3.9+
- Keep memory usage low (512MB Pi)
- One Claude CLI call at a time (asyncio lock)
- Use SQLite efficiently (FTS5 for search)
- E-Ink updates are slow (~2-3s)

## Safety Rules

- **No credentials in code** — Use `.env`
- **No heavy processes** — 512MB RAM limit
- **`trash` > `rm`** — Recoverable deletes
- **Ask before external actions** — Network, installs

## Key Files

| File | Purpose |
|------|---------|
| `src/main.py` | Telegram bot, message handling |
| `src/ui/gotchi_ui.py` | E-Ink display, faces |
| `.workspace/` | Bot personality (gitignored) |
| `templates/` | Default templates |
| `gotchi-skills/` | Pi-specific skills |

## Adding Features

1. For bot behavior: Edit `templates/` (or `.workspace/` for live bot)
2. For code changes: Edit `src/`
3. For skills: Add to `gotchi-skills/`
4. For display faces: Edit `src/ui/gotchi_ui.py` → `faces` dict

## External Dependencies

- **openclaw-skills/** — Not included. Clone separately if needed:
  ```bash
  git clone https://github.com/openclaw/skills openclaw-skills
  ```

## Deployment

```bash
# Deploy to Pi
scp -r . pi@raspberrypi:~/openclawgotchi/
ssh pi@raspberrypi "cd openclawgotchi && ./setup.sh"

# Restart service
ssh pi@raspberrypi "sudo systemctl restart claude-bot"

# View logs
ssh pi@raspberrypi "journalctl -u claude-bot -f"
```
