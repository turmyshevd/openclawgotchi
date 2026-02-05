# Changelog

All notable changes to the OpenClawGotchi project will be documented in this file.

## [Unreleased] - 2026-02-05

### Added
- **Functional Cron Jobs**: Scheduled tasks now trigger actual LLM reasoning. When a job fires, the bot can process the message and even trigger hardware commands (FACE, SAY) autonomously.
- **Onboarding System**: New `onboarding.py` logic and upgraded `BOOTSTRAP.md` template for a guided, personality-driven "first-run" ritual.
- **Persistent Skill Prompting**: Active skills are now automatically injected into every system prompt to ensure the bot is always aware of its extended capabilities.
- **Health & Memory Dashboard**: New `/health` and `/memory` commands for real-time monitoring of system vitals, codebase size, and database storage.
- **Infinite Loop Protection**: Added a safeguard in the LLM router to detect and break redundant tool execution loops.

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
