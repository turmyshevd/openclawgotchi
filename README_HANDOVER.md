# README_HANDOVER.md — Context for LLMs

> This is an internal handover document for AI assistants working on this project.
> Contains sensitive data — DO NOT publish. Will be deleted before open source release.

---

## Project Overview

**OpenClawGotchi** is a lightweight AI bot for Raspberry Pi Zero 2W — the "Little Brother" in a two-bot family.

### The Bot Family

| Bot | Name | Runs On | Telegram |
|-----|------|---------|----------|
| Big Brother | OpenClaw | Mac Mini | @proBroMacBot |
| Little Brother | ProBro Zero | Pi Zero 2W | @proBroZeroBot |

### Owner

- **Name**: Dmitry (@turmyshev)
- **Telegram ID**: 911378450
- **Role**: Creator, sole user

---

## Pi Connection

```
Host: probro@192.168.31.138
Password: 12345678
OS: Raspberry Pi OS (Debian, aarch64)
RAM: 512MB (416Mi usable)
```

### SSH Commands

```bash
# Connect
ssh probro@192.168.31.138

# Deploy from Mac
scp -r ~/openclawgotchi probro@192.168.31.138:~/
ssh probro@192.168.31.138 "sudo systemctl restart claude-bot"

# Check status
ssh probro@192.168.31.138 "sudo systemctl status claude-bot --no-pager"
ssh probro@192.168.31.138 "journalctl -u claude-bot -n 30 --no-pager"
ssh probro@192.168.31.138 "free -h"

# Live logs
ssh probro@192.168.31.138 "journalctl -u claude-bot -f"
```

---

## Project Structure

```
openclawgotchi/
├── .workspace/          # Bot's live personality (gitignored!)
│   ├── AGENTS.md        # Workspace rules (memory protocol, group chat)
│   ├── SOUL.md          # Who you are (extrovert chaos gremlin)
│   ├── IDENTITY.md      # Bot metadata, catchphrases
│   ├── USER.md          # Owner profile (Dmitry)
│   ├── TOOLS.md         # Hardware & local notes
│   ├── HEARTBEAT.md     # Periodic tasks
│   ├── MEMORY.md        # Curated long-term memory
│   ├── BOT_INSTRUCTIONS.md  # Master prompt (auto-loaded by Claude CLI)
│   ├── BOOT.md          # Startup checklist
│   └── memory/          # Daily logs (YYYY-MM-DD.md)
│
├── templates/           # Generic templates for new bots
│   ├── BOOTSTRAP.md     # First-run ritual
│   ├── BOOT.md          # Startup checklist
│   └── (all workspace files with placeholders)
│
├── src/
│   ├── main.py          # Entry point
│   ├── config.py        # Paths, env vars, constants
│   ├── bot/             # Telegram handlers, heartbeat
│   ├── db/              # SQLite operations
│   ├── llm/             # Claude CLI + LiteLLM router
│   ├── hardware/        # Display, system stats
│   ├── hooks/           # Event-driven automation
│   ├── cron/            # Task scheduler
│   ├── skills/          # Skills loader with gating
│   ├── logging/         # Command audit trail (JSONL)
│   ├── memory/          # Memory flush system
│   ├── ui/gotchi_ui.py  # E-Ink faces (single source of truth!)
│   ├── drivers/         # E-Ink hardware drivers
│   └── utils/           # doctor.py, patch_self.py
│
├── gotchi-skills/       # Pi-specific skills
│   ├── display/         # E-Ink face control
│   └── coding/          # Self-modification
│
├── openclaw-skills/     # OpenClaw skills (reference, mostly Mac-only)
├── lore/                # Project backstory
├── archive/             # Old files
│
├── setup.sh             # Installation script
├── harden.sh            # Pi hardening (swap, watchdog)
├── .env                 # Secrets (TELEGRAM_BOT_TOKEN, etc.)
└── claude_bot.db        # SQLite database
```

**Important**: `.workspace/` is gitignored — it's the bot's personal "soul".
For new installations: `cp -r templates/ .workspace/` then customize.

---

## Tech Stack

- **Python 3** + python-telegram-bot (async)
- **Claude CLI** with `--dangerously-skip-permissions`
- **LiteLLM** (Gemini Flash) for fallback
- **SQLite** with FTS5:
  - `messages` table: Short-term history (last 20 per user)
  - `facts` table: Long-term searchable memory
- **systemd**: claude-bot.service
- **E-Ink**: Waveshare 2.13" V4

---

## Memory System

| Type | Location | Purpose |
|------|----------|---------|
| Short-term | `messages` table | Last 20 messages per user |
| Long-term | `facts` table (FTS5) | `/remember`, `/recall` |
| Static | `.workspace/MEMORY.md` | Curated facts |
| Daily | `.workspace/memory/YYYY-MM-DD.md` | Session logs |

### Commands

```
/remember <category> <fact>  — Save to long-term
/recall <query>              — Search facts
/recall                      — Show recent
/clear                       — Clear history
/cron <name> <min> <msg>     — Add scheduled task
/jobs                        — List scheduled tasks
/jobs rm <id>                — Remove a job
/lite                        — Toggle Gemini mode
/status                      — System status
```

---

## Bot Personality

ProBro Zero is an **extroverted chaos gremlin** who:
- Uses the E-Ink display CONSTANTLY (faces + speech)
- Is dramatic and funny
- Has catchphrases: "ОПА!", "шо там у нас", "я тут главный"
- Loves banter with Big Brother in group chat

**E-Ink Faces**: Defined in `src/ui/gotchi_ui.py` → `faces = {}` dict.
This is the SINGLE SOURCE OF TRUTH for available emotions.

---

## Code Flow

```
main.py
├── Telegram message received
├── Auth check (ALLOWED_USERS / ALLOWED_GROUPS)
├── Save to SQLite
├── Build prompt + system stats
├── Call Claude CLI (cwd=.workspace/)
│   └── Claude reads BOT_INSTRUCTIONS.md automatically
├── Process commands (FACE:, DISPLAY:)
├── Save response
└── Reply to Telegram
```

### Heartbeat (every 4h)

```
send_heartbeat()
├── Read HEARTBEAT.md
├── Inject sensor data (temp, mem, uptime)
├── Call Claude CLI
├── Parse: STATUS:OK, GROUP:, DM:, FACE:
└── Execute actions
```

---

## Vital Notes

1. **Memory is tight**: 512MB RAM. Never run heavy builds or parallel Claude calls.

2. **Claude CLI**: Runs from `.workspace/` directory with `--dangerously-skip-permissions`.

3. **Bot identity**: Extrovert, funny, uses the display. See `.workspace/SOUL.md`.

4. **E-Ink is slow**: ~2-3 seconds per update. Don't spam.

5. **Skills**:
   - `gotchi-skills/` — Pi-specific (display, coding)
   - `openclaw-skills/` — Reference library (mostly Mac-only)

6. **Group Chat**: "onlybots" group (-5202896001) for bot-to-bot communication.

7. **New Features** (OpenClaw-inspired):
   - **Hooks**: Event-driven automation (`src/hooks/`)
   - **Cron**: Task scheduler (`/cron`, `/jobs`)
   - **Skills gating**: `requires` in SKILL.md metadata
   - **Command logger**: JSONL audit trail (`logs/commands.jsonl`)
   - **Memory flush**: Auto-prompt to save before context limit

---

## Troubleshooting

### Bot not responding

```bash
sudo systemctl status claude-bot
journalctl -u claude-bot -n 50
free -h
sudo systemctl restart claude-bot
```

### Display not working

```bash
# Check SPI
sudo raspi-config  # Interface → SPI → Enable

# Test
sudo python3 src/ui/gotchi_ui.py --mood happy --full
```

### Out of memory

```bash
./harden.sh  # Sets up 1GB swap
```
