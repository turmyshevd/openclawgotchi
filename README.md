# 🤖 OpenClawGotchi

> Your AI companion on a tiny Pi — with personality!

A lightweight, AI-powered personal assistant designed for **Raspberry Pi Zero 2W**.  
Chat via Telegram, express emotions on an E-Ink display, and let it grow its own personality.

Inspired by [OpenClaw](https://github.com/openclaw/openclaw) but optimized for extreme resource constraints (runs on 512MB RAM).

```
┌─────────────────────────────────┐
│  Gotchi [L]     T:42°C | 14:30  │
│─────────────────────────────────│
│                                 │
│          (◕‿◕)                  │
│                                 │
│    ╭──────────────────╮         │
│    │ Hello! How can   │         │
│    │ I help today?    │         │
│    ╰──────────────────╯         │
│                                 │
│─────────────────────────────────│
│  Lv3 | 250 XP | ❤️ Happy        │
└─────────────────────────────────┘
```

## ✨ Features

- **Telegram Bot** — Chat with your Pi from anywhere
- **Claude CLI Integration** — Full Claude Code capabilities on a tiny device
- **E-Ink Display** — Expressive kaomoji faces and speech bubbles (24 moods!)
- **Smart Memory** — Context window + auto-summaries + FTS5 facts search
- **Personality Templates** — OpenClaw-style customizable identity
- **LiteLLM Fallback** — Gemini Flash when Claude hits rate limits
- **Self-Modification** — Bot can improve its own code
- **Skills System** — Active skills (weather, system) + searchable skill catalog
- **Cron Jobs** — Schedule periodic tasks with LLM reasoning
- **Hooks** — Event-driven automation (startup, message, heartbeat)

## 📋 Requirements

**Hardware:**
- Raspberry Pi Zero 2W (or any Pi with 512MB+ RAM)
- microSD card (8GB+)
- Optional: Waveshare 2.13" E-Ink Display V4

**Software:**
- Raspberry Pi OS (64-bit Lite recommended)
- Python 3.9+ (pre-installed on Pi OS)
- Internet connection

**Accounts (free):**
- Telegram Bot Token — get from [@BotFather](https://t.me/BotFather)
- Your Telegram ID — get from [@userinfobot](https://t.me/userinfobot)
- Optional: [Gemini API key](https://aistudio.google.com/app/apikey) for LLM fallback

## 🚀 Quick Start (5 minutes)

### Before You Start

1. **Create a Telegram bot**: Message [@BotFather](https://t.me/BotFather), send `/newbot`, save the token
2. **Get your Telegram ID**: Message [@userinfobot](https://t.me/userinfobot), save the number

### Installation

```bash
# On your Pi — one command does everything!
git clone https://github.com/yourusername/openclawgotchi.git
cd openclawgotchi
./setup.sh
```

The setup wizard will:
- Ask for your Telegram token and user ID
- Ask what to name your bot
- Install all dependencies
- Create and start the service

**That's it!** Send a message to your bot on Telegram.

### First Message

On the first message, your bot will:
1. Show an excited face on the E-Ink display
2. Introduce itself
3. Ask about its personality (onboarding)
4. Save everything and become "itself"

### Manual Setup (if needed)

```bash
# Edit config manually
nano .env

# Edit personality
nano .workspace/SOUL.md
nano .workspace/IDENTITY.md

# Restart to apply changes
sudo systemctl restart gotchi-bot
```

### Useful Commands

```bash
sudo systemctl status gotchi-bot   # Check status
sudo systemctl restart gotchi-bot  # Restart
journalctl -u gotchi-bot -f        # Live logs
./harden.sh                        # Production hardening (swap, watchdog)
```

## 📁 Project Structure

```
openclawgotchi/
├── .workspace/          # Your bot's personality (gitignored, auto-created)
│   ├── SOUL.md          # Who the bot is
│   ├── IDENTITY.md      # Bot metadata
│   ├── USER.md          # Owner profile
│   ├── BOT_INSTRUCTIONS.md  # System prompt
│   └── memory/          # Daily logs (YYYY-MM-DD.md)
│
├── templates/           # Default templates (copied to .workspace/ on first run)
│
├── src/
│   ├── main.py          # Entry point
│   ├── config.py        # Configuration
│   ├── bot/             # Telegram handlers, heartbeat, onboarding
│   ├── db/              # SQLite: messages, facts, stats
│   ├── llm/             # Claude CLI + LiteLLM connectors
│   ├── ui/              # E-Ink display (gotchi_ui.py)
│   ├── hardware/        # Display control, auto-mood
│   ├── skills/          # Skill loader & gating
│   ├── hooks/           # Event-driven automation
│   ├── cron/            # Scheduled tasks
│   ├── memory/          # Summarization, flush prompts
│   └── utils/           # Doctor, backups
│
├── gotchi-skills/       # Pi-optimized active skills
│   ├── coding/          # Self-modification
│   ├── display/         # E-Ink face control
│   ├── weather/         # Weather via wttr.in
│   ├── system/          # Pi administration
│   └── discord/         # Discord integration
│
├── openclaw-skills/     # Reference skill catalog (passive knowledge)
│
├── setup.sh             # Interactive setup wizard
├── harden.sh            # Pi hardening (swap, watchdog, RAM optimization)
└── .env.example         # Configuration template
```

## 🎭 E-Ink Display

The bot expresses emotions through kaomoji on the E-Ink display (24 moods available):

| Mood | Face | Mood | Face |
|------|------|------|------|
| happy | (◕‿◕) | sad | (╥﹏╥) |
| excited | (ﾉ◕ヮ◕)ﾉ✧ | thinking | (￣ω￣) |
| love | (♥ω♥) | bored | (￣ε￣) |
| confused | (⊙_⊙)? | sleeping | (－ω－) zzZ |
| angry | (╬ಠ益ಠ) | proud | (๑•̀ㅂ•́)و✧ |
| cool | (⌐■_■) | mischievous | (◕ᴗ◕✿) |

Full list in `src/ui/gotchi_ui.py`. Bot chooses faces based on context!

## 💬 Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/clear` | Clear conversation history |
| `/status` | System status (RAM, temp, uptime, skills) |
| `/context` | View context window usage |
| `/context trim` | Keep only last 3 messages |
| `/context sum` | Trigger LLM summarization |
| `/remember <cat> <fact>` | Save to long-term memory |
| `/recall <query>` | Search memories |
| `/memory` | Database stats |
| `/health` | System health check |
| `/pro` | Toggle Claude/Gemini mode |
| `/cron <interval> <task>` | Schedule a task |
| `/jobs` | List scheduled jobs |

## 🧠 Memory System

| Layer | Storage | Usage |
|-------|---------|-------|
| **Context Window** | Last 10 messages | Active conversation |
| **Auto-Summaries** | Daily logs | LLM-generated every 4h |
| **Facts DB** | SQLite FTS5 | Searchable with `/recall` |
| **Long-term** | `MEMORY.md` | Curated important info |

Memory is automatically managed:
- Old messages are pruned (keeps last 50 per chat)
- Conversations are summarized during heartbeat
- Use `/context` to check usage, `/context sum` to manually summarize

## 🛠️ Skills System

**Active Skills** (loaded, always available):
- `coding` — Self-modification, project structure
- `display` — E-Ink face and speech control
- `weather` — Weather via wttr.in (no API key!)
- `system` — Pi administration, backups, monitoring
- `discord` — Send messages to Discord (webhook or bot)

**Reference Skills** (`openclaw-skills/`):
- 50+ skills from the OpenClaw ecosystem
- Bot can search with `search_skills("weather")` 
- Read docs with `read_skill("github")`
- Many require macOS — bot knows to check compatibility

## ⚙️ Configuration

All settings are in `.env` (created by setup wizard):

```bash
# Required
TELEGRAM_BOT_TOKEN=your_token_from_botfather
ALLOWED_USERS=your_telegram_id

# Identity (set during onboarding or manually)
BOT_NAME=Gotchi              # Shown on E-Ink display
OWNER_NAME=YourName          # Used in templates

# Optional
GEMINI_API_KEY=your_key      # For LLM fallback
BOT_LANGUAGE=en              # Default response language
SIBLING_BOT_NAME=            # For bot-to-bot mail
```

See `.env.example` for all options.

## 🔧 Hardware Setup

### E-Ink Display (Waveshare 2.13" V4)

1. Enable SPI: `sudo raspi-config` → Interface Options → SPI
2. Connect display to GPIO pins
3. Test: `sudo python3 src/ui/gotchi_ui.py --mood happy`

### Recommended Pi Settings

```bash
# Run hardening script (recommended!)
./harden.sh

# This configures:
# - 1GB swap (Pi Zero needs it)
# - Hardware watchdog (auto-reboot on system freeze)
# - Service watchdog (auto-restart bot if crashed)
# - Disables audio/bluetooth (~80MB RAM saved)
```

## ❓ Troubleshooting

### Bot doesn't respond
```bash
# Check if running
sudo systemctl status gotchi-bot

# Check logs for errors
journalctl -u gotchi-bot -n 50

# Restart
sudo systemctl restart gotchi-bot
```

### "Access denied" message
- Make sure your Telegram ID is in `ALLOWED_USERS` in `.env`
- Get your ID from [@userinfobot](https://t.me/userinfobot)

### E-Ink display not working
```bash
# Check SPI is enabled
ls /dev/spidev*  # Should show spidev0.0

# Enable SPI if missing
sudo raspi-config  # Interface Options → SPI → Enable

# Test display
sudo python3 src/ui/gotchi_ui.py --mood happy --text "Test"
```

### Out of memory
```bash
# Check memory
free -h

# Run hardening script (adds swap)
./harden.sh

# Restart bot
sudo systemctl restart gotchi-bot
```

### Bot is slow
- Pi Zero 2W is slow by design — patience!
- First response takes 10-30 seconds
- Use `/pro` to switch to faster Gemini mode

## 🤝 Contributing

1. Fork the repo
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## 📜 License

MIT License — see [LICENSE](LICENSE)

## 🙏 Acknowledgments

- [OpenClaw](https://github.com/openclaw/openclaw) — Inspiration and skills library
- [Pwnagotchi](https://github.com/evilsocket/pwnagotchi) — E-Ink UI inspiration
- [Claude](https://anthropic.com) — The brain behind the bot

---

**Made with 💙 for tiny computers with big personalities**
