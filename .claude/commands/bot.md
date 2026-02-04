# Claude Telegram Bot — Project Context

## Architecture
Lightweight Telegram bot on Raspberry Pi Zero 2W that bridges messages to Claude Code CLI.
Inspired by OpenClaw but minimal: ~20MB RAM instead of 300-500MB.

## Pi Connection
- Host: `probro@192.168.31.138`
- SSH key auth configured (no password needed)
- OS: Raspberry Pi OS (Debian, aarch64)
- RAM: 512MB (416Mi usable)

## Project Structure (local)
```
~/claude-telegram-bot/
├── bot.py                  # Main Telegram bot (python-telegram-bot + asyncio)
├── .env                    # TELEGRAM_BOT_TOKEN, ALLOWED_USERS, timeouts
├── CLAUDE.md               # Soul/personality for Claude Code
├── memory.db               # SQLite — conversation history (created at runtime on Pi)
├── setup.sh                # Install deps + systemd service on Pi
├── .claude/commands/        # Claude Code skills (this file, etc.)
└── openclaw-skills/         # All 52 OpenClaw skills (reference)
    ├── weather/SKILL.md
    ├── github/SKILL.md
    ├── ...
```

## Project Structure (on Pi: ~/claude-telegram-bot/)
Same as local, deployed via scp.

## Key Commands

### Deploy to Pi
```bash
scp -r ~/claude-telegram-bot probro@192.168.31.138:~/
ssh probro@192.168.31.138 "sudo systemctl restart claude-bot"
```

### Check status
```bash
ssh probro@192.168.31.138 "sudo systemctl status claude-bot --no-pager"
ssh probro@192.168.31.138 "journalctl -u claude-bot -n 30 --no-pager"
ssh probro@192.168.31.138 "free -h"
```

### View logs live
```bash
ssh probro@192.168.31.138 "journalctl -u claude-bot -f"
```

## Telegram Bot
- Bot: @proBroZeroBot
- Token: in .env
- Owner Telegram ID: 911378450 (@turmyshev, Dmitry)

## Adding Skills
OpenClaw skills are in `openclaw-skills/`. To adapt one:
1. Read `openclaw-skills/<name>/SKILL.md`
2. Extract the instructions (markdown body after YAML frontmatter)
3. Create `.claude/commands/<name>.md` with adapted instructions
4. Deploy to Pi

## Tech Stack
- Python 3 + python-telegram-bot (on Pi)
- Claude Code CLI with `--dangerously-skip-permissions` (on Pi)
- SQLite for conversation memory
- systemd for daemon management
- cron for scheduled tasks (HEARTBEAT equivalent)
