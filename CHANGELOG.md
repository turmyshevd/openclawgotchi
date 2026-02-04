# Changelog

All notable changes to the OpenClawGotchi project will be documented in this file.

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
