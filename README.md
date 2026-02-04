# 🤖 OpenClawGotchi

A lightweight, AI-powered personal assistant designed for **Raspberry Pi Zero 2W**. 

Inspired by [OpenClaw](https://github.com/openclaw/openclaw) but optimized for extreme resource constraints (~20MB RAM vs 300MB+).

## ✨ Features

- **Telegram Bot** — Chat with your Pi from anywhere
- **Claude CLI Integration** — Full Claude Code capabilities on a tiny device
- **E-Ink Display** — Expressive kaomoji faces and speech bubbles
- **Dual Memory System** — Short-term (SQLite) + long-term (FTS5 search)
- **Personality Templates** — OpenClaw-style customizable identity
- **LiteLLM Fallback** — Gemini Flash when Claude hits rate limits
- **Self-Modification** — Bot can improve its own code

## 📋 Requirements

- Raspberry Pi Zero 2W (512MB RAM)
- Raspberry Pi OS (64-bit recommended)
- Python 3.9+
- [Claude CLI](https://github.com/anthropics/claude-cli) installed
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Optional: Waveshare 2.13" E-Ink Display V4

## 🚀 Quick Start

### 1. Clone & Setup

```bash
# On your Pi
git clone https://github.com/yourusername/openclawgotchi.git
cd openclawgotchi

# Install dependencies
./setup.sh

# Configure
cp .env.example .env
nano .env  # Add your tokens
```

### 2. Create Your Bot's Personality

```bash
# Copy templates to workspace
cp -r templates/ .workspace/

# Edit to customize your bot
nano .workspace/IDENTITY.md
nano .workspace/SOUL.md
```

### 3. Start

```bash
# Manual run
python3 src/main.py

# Or as a service
sudo systemctl start claude-bot
sudo systemctl enable claude-bot
```

## 📁 Project Structure

```
openclawgotchi/
├── .workspace/          # Your bot's personality (gitignored)
│   ├── SOUL.md          # Who the bot is
│   ├── IDENTITY.md      # Bot metadata
│   ├── USER.md          # Owner profile
│   └── ...
│
├── templates/           # Default templates (copy to .workspace/)
│
├── src/
│   ├── main.py          # Telegram bot entry point
│   ├── ui/              # E-Ink display (gotchi_ui.py)
│   ├── drivers/         # Hardware drivers
│   ├── agent/           # LiteLLM fallback
│   └── utils/           # Utilities
│
├── gotchi-skills/       # Pi-optimized skills
│   ├── display/         # E-Ink face control
│   └── coding/          # Self-modification
│
├── setup.sh             # Installation script
├── harden.sh            # Pi hardening (swap, watchdog)
└── .env.example         # Configuration template
```

## 🎭 E-Ink Display

The bot expresses emotions through kaomoji on the E-Ink display:

| Emotion | Face |
|---------|------|
| Happy | (◕‿◕) |
| Sad | (✖╭╮✖) |
| Excited | (ﾉ◕ヮ◕)ﾉ |
| Thinking | (￣ω￣) |
| Love | (♥ω♥) |
| Bored | (⌐■_■) |

Add custom faces in `src/ui/gotchi_ui.py`.

## 💬 Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/clear` | Clear conversation history |
| `/status` | System status (RAM, temp, uptime) |
| `/remember <cat> <fact>` | Save to long-term memory |
| `/recall <query>` | Search memories |
| `/lite` | Toggle Gemini fallback mode |

## 🧠 Memory System

- **Short-term**: Last 20 messages (SQLite `messages` table)
- **Long-term**: Searchable facts (SQLite FTS5 `facts` table)
- **Static**: `MEMORY.md` for curated context
- **Daily logs**: `.workspace/memory/YYYY-MM-DD.md`

## ⚙️ Configuration

See `.env.example` for all options:

```bash
TELEGRAM_BOT_TOKEN=your_token
ALLOWED_USERS=123456789
CLAUDE_TIMEOUT=600
GEMINI_API_KEY=optional_fallback_key
```

## 🔧 Hardware Setup

### E-Ink Display (Waveshare 2.13" V4)

1. Enable SPI: `sudo raspi-config` → Interface Options → SPI
2. Connect display to GPIO pins
3. Test: `sudo python3 src/ui/gotchi_ui.py --mood happy`

### Recommended Pi Settings

```bash
# Run hardening script
./harden.sh

# This configures:
# - 1GB swap (Pi Zero needs it)
# - Watchdog timer
# - Memory optimizations
```

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
