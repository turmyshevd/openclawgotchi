# Changelog

All notable changes to the OpenClawGotchi project will be documented in this file.

## [Unreleased] - 2026-02-04

### Added
- **XP/Level System**: The E-Ink display footer now shows the bot's current Level and XP (e.g., `Lv1 50XP`).
- **Mode Indicators**: The E-Ink header now displays `[L]` for Lite mode and `[P]` for Pro mode next to the name.
- **Inter-Bot Mail**: Added support for `MAIL:` commands to allow the bot to send and receive messages from its "Senior Brother" (OpenClaw on Mac).
- **Startup Mail Check**: The bot now checks for and processes pending command emails from the brother immediately upon startup.
- **Rotation**: E-Ink display output is now rotated 180 degrees.

### Changed
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
- **Gemini API**: Resolved `404 NotFound` errors by updating `litellm` and using `gemini-2.0-flash`.
- **Logging**: Fixed minor typos in heartbeat logs.
