# Changelog

All notable changes to the OpenClawGotchi project will be documented in this file.

## [Unreleased] - 2026-02-06

### Added
- **Soul & Identity in context**: `SOUL.md` and `IDENTITY.md` are now loaded during heartbeat for self-reflection, and lazily on identity-related questions. Bot can update them via `write_file()`.
- **`log_change` tool**: Bot maintains its own `.workspace/CHANGELOG.md` automatically after self-modifications.
- **`manage_service` tool**: Safe systemd wrapper with whitelist (gotchi-bot, ssh, networking, cron). Actions: status, restart, stop, start, logs.
- **`show_face` tool**: Wired into TOOL_MAP and TOOLS — was defined but never callable by the bot.
- **Self-Maintenance section** in BOT_INSTRUCTIONS.md: check_syntax → safe_restart flow, log_change after changes, health_check for diagnostics.
- **Heartbeat reflection logging**: Reflection text now saved to `memory/YYYY-MM-DD.md` daily logs.
- **Custom faces in display skill**: `add_custom_face()` documented, `data/custom_faces.json` mentioned.

### Changed
- **BOT_INSTRUCTIONS.md**: Slimmed from 86 to 58 lines — removed duplicate formatting examples, added Self-Knowledge Files and Self-Maintenance sections.
- **ARCHITECTURE.md**: Rewritten — correct 20 levels, 4h heartbeat interval, all current tools listed, context loading explained.
- **AGENTS.md**: Fixed `claude_bot.db` → `gotchi.db`, removed table formatting references.
- **IDENTITY.md**: Removed table mention from personality traits.
- **Telegram formatting**: NO markdown tables — use emoji + key:value in code blocks instead.
- **coding/SKILL.md**: Added all missing tools (log_change, manage_service, check_mail, etc.), updated self-modification flow with changelog step.
- **display/SKILL.md**: Added `add_custom_face` tool and custom faces info.
- **All `claude-bot` references → `gotchi-bot`** in gotchi-skills.
- **All `claude_bot.db` references → `gotchi.db`** across workspace, gitignore, skills.

### Removed
- `.workspace/hooks/bot_mail.py` — duplicated heartbeat.py mail logic, referenced wrong DB.
- `.workspace/.claude/commands/bot.md` — completely outdated (referenced old project structure).

## [Unreleased] - 2026-02-05

### Added
- **Passive Skill Knowledge**: `openclaw-skills/` directory is now treated as a searchable catalog rather than loading all skills into context. Bot can search for capabilities without RAM overhead.
- **New Active Skills**: 
  - `weather` — Get weather via wttr.in (no API key needed)
  - `system` — Pi administration: power, services, monitoring, backups
  - `discord` — Send messages to Discord via webhook or bot
- **Hardware Watchdog**: `harden.sh` now enables BCM2835 hardware watchdog (auto-reboot on system freeze after 15s).
- **3-Layer Protection**: Hardware watchdog + systemd restart + cron watchdog for maximum reliability.
- **Skill Discovery Tools**: `search_skills("query")` and `list_skills()` tools for finding capabilities in the skill catalog.
- **LLM Summarization**: Conversations are now automatically summarized by Gemini Flash during heartbeat and saved to daily logs.
- **Context Management**: New `/context` command shows context window usage with visual progress bar. Subcommands: `/context trim` (keep last 3 messages), `/context sum` (manual LLM summary).
- **Memory Auto-cleanup**: Database automatically prunes old messages to prevent infinite growth (keeps last 50 per chat).
- **Smarter History Summarization**: `extract_key_info()` now analyzes message content (questions, commands, actions) instead of simple truncation.
- **Functional Cron Jobs**: Scheduled tasks now trigger actual LLM reasoning. When a job fires, the bot can process the message and even trigger hardware commands (FACE, SAY) autonomously.
- **Onboarding System**: New `onboarding.py` logic and upgraded `BOOTSTRAP.md` template for a guided, personality-driven "first-run" ritual.
- **Persistent Skill Prompting**: Active skills are now automatically injected into every system prompt to ensure the bot is always aware of its extended capabilities.
- **Health & Memory Dashboard**: New `/health` and `/memory` commands for real-time monitoring of system vitals, codebase size, and database storage.
- **Infinite Loop Protection**: Added a safeguard in the LLM router to detect and break redundant tool execution loops.

### Changed
- **Skills Architecture**: Split into "Active Skills" (loaded in context: coding, display, weather, system) and "Reference Skills" (passive catalog for search).
- **BOT_INSTRUCTIONS.md**: Updated with Memory System and Skills System sections explaining the new architecture.
- **Configurable Identity**: Bot name, owner name, and sibling bot now configurable via `.env` instead of hardcoded.
- **Interactive Setup Wizard**: `setup.sh` now guides users through configuration with prompts for token, user ID, and bot name.
- **Improved README**: Added ASCII art preview, troubleshooting section, clearer quick start guide.
- **Open-Source Ready**: 
  - Removed all hardcoded personal data (IPs, Telegram IDs, names)
  - All identity values now read from `.env` or set during onboarding
  - Templates use `{{placeholders}}` for customization
  - Lore files anonymized as examples
  - Updated `.gitignore` to protect secrets and runtime data

### Fixed
- **Rate Limit Resilience**: Improved handling and queuing of messages when Claude is rate-limited.
- **Tool Logic**: Resolved issues where the bot would repeat search/grep actions instead of providing an answer.

## [Unreleased] - 2026-02-04

### Added
- **XP/Level System**: The E-Ink display footer now shows the bot's current Level and XP (e.g., `Lv1 50XP`).
- **Mode Indicators**: The E-Ink header now displays `[L]` for Lite mode and `[P]` for Pro mode next to the name.
- **Emoji & Kaomoji Support**: Added monochrome emoji support for E-Ink using `Symbola` font fallback. Restored `Unifont` as the primary font for both faces and bubbles to maintain the bot's signature aesthetic while ensuring full compatibility for complex symbols.
- **Improved UI Rendering**: Implemented a synchronized fallback engine in `gotchi_ui.py` that ensures consistent text measurement and rendering. This fixes "crooked" bubble alignment issues when using mixed-font strings (e.g., text with emojis).
- **Dynamic LLM Switching**: New `/use` and `/switch` commands allow switching between providers (Gemini, Z.ai/GLM) without a restart.
- **Inter-Bot Mail**: Added support for `MAIL:` commands to allow the bot to send and receive messages from its "Senior Brother" (OpenClaw on Mac).
- **Startup Mail Check**: The bot now checks for and processes pending command emails from the brother immediately upon startup.
- **Rotation**: E-Ink display output is now rotated 180 degrees.

### Changed
- **Simplified Commands**: The hardware command `DISPLAY: SAY:` has been simplified to just `SAY:` across all instructions, code, and lore.
- **Lite Mode UI**: Updated the footer indicator to use HTML instead of Markdown to avoid parsing errors in Telegram.
- **Database**: Renamed main database file from `claude_bot.db` to `gotchi.db`.
- **LLM Routing**: 
    - **Pro Mode** is now strict: if Claude fails or is rate-limited, it errors out instead of silently falling back to Gemini. This prevents accidental usage of the "dumber" model when the user expects the "smart" one.
    - **Lite Mode** is the default.
- **Commands**: 
    - `/lite` command renamed to `/pro` (toggles between modes).
    - `/mode` and `/lite` kept as aliases for compatibility.
- **Visual Feedback**: Mode switching now triggers a specific face and status message on the E-Ink screen.
- **Dependencies**: Updated `litellm` to version `>=1.81.7` to fix Gemini API 404 errors.

### Fixed
- **Markdown Parsing**: Fixed issues where LLM-generated underscores or stars in "Lite Mode" would break Telegram message delivery.
- **Tool Hallucinations**: Removed redundant `show_face` tool to force use of more efficient hardware tags.
- **Gemini API**: Resolved `404 NotFound` errors by updating `litellm` and using `gemini-2.0-flash`.
- **Logging**: Fixed minor typos in heartbeat logs.
