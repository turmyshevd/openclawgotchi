# Changelog

All notable changes to the OpenClawGotchi project will be documented in this file.

## [Unreleased] - 2026-05-09

### Added
- **`/model` Telegram command**: inline-keyboard model picker. Without args it opens buttons for every preset (gemini, glm, ollama). With an argument (`/model glm`) it falls through to the existing `/use` flow. `/use` and `/switch` remain as text aliases.
- **Live Ollama discovery**: tapping `🦙 ollama ▸` queries the configured Ollama server (`/api/tags` + `/api/show`), filters by `capabilities.tools`, and only lists tool-capable models. Falls back to all installed models with a warning when none advertise tools. Includes `◂ Back` button and a graceful "could not reach server" state. New env vars: `OLLAMA_MODEL` (default `qwen2.5:14b`) and `OLLAMA_API_BASE` (placeholder default `http://ollama-server:11434`).
- **Persistent model choice**: `/model` and `/use` now write the selection to `data/active_model.json` (gitignored). On startup `LiteLLMConnector` restores it before falling back to `DEFAULT_LITE_PRESET`. Survives `systemctl restart` and reboots.
- **`/update` Telegram command + `scripts/auto_update.sh`**: owner-only command that fetches `origin/main`, fast-forwards if there are new commits, refreshes venv deps when `requirements.txt` changed, and restarts the systemd service. Supports `/update check` for dry-run. Cron-friendly so the bot can also auto-update unattended.
- **Update safety net**: before pulling, the script tarballs `gotchi.db` + `data/` + `.env` to `backups/pre-update-<timestamp>-<sha>.tar.gz` (rolling, keeps last 3 — see `OCG_BACKUP_KEEP`). If the service fails to come back up after the new code is in place, the script auto-rolls-back to the previous commit, reinstalls deps if needed, restarts, and exits with code 4 to flag the failed upgrade. Disable with `OCG_NO_BACKUP=1` / `OCG_NO_ROLLBACK=1`.
- **`gotchi-update` sudoers entry** in `setup.sh`: lets the bot user `systemctl restart gotchi-bot.service` without a password — needed by `/update` and the unattended cron path.
- **UPS HAT (C) battery monitoring** (Waveshare): new `hardware/battery.py` reads bus voltage, current and power from the on-board INA219 over I2C and reports a 0–100 % estimate based on the 2× 18650 voltage curve (6.0 V empty → 8.4 V full). Auto-detects the sensor and gracefully degrades when I2C is disabled or the HAT is absent — every public function returns `None` rather than raising.
- **`/battery` Telegram command**: shows the current reading (`🔋 87 % — 8.12 V, +120 mA (charging, 974 mW)`) or a friendly "no UPS HAT detected" hint with `i2cdetect` instructions.
- **System status line includes battery** (when present): `get_stats_string()` adds a `[BATTERY] …` line, so heartbeat reflections and the bot's self-awareness pick up battery state automatically.
- **Optional dep `smbus2`** added to `requirements.txt` (pure-Python, ~30 KB). Drop the line to disable battery support entirely.

### Changed
- **HTTP timeouts** raised via `Application.builder()` (`read=60`, `write=60`, `connect=30`, `pool=30`). Pi Zero 2W's WiFi can otherwise time out polling Telegram while a long Ollama reply is streaming, surfacing as `httpx.ReadError` / `Timed out`.

### Fixed
- **`BOT_LANGUAGE` was dead code in the system prompt**: defined in `config.py` and exposed via `.env`, but never injected anywhere — heartbeat reflections and the SAY: speech bubble would happily drift into Japanese/Chinese on Qwen-family models because no language was pinned. New `_language_directive()` in `llm/prompts.py` is part of `build_system_context()` and applies to every system prompt path (replies, heartbeat, SAY:). Codes mapped to readable names (`de` → "German (Deutsch)" etc.) for common languages; unknown codes pass through verbatim.
- **`error_screen()` SAY: text now respects `BOT_LANGUAGE`**: previously hardcoded Japanese (`システムエラー発生` etc.), which renders as garbled glyphs for owners who don't read it. Localized into `ja` / `en` / `de` / `ru` / `es` / `fr`. Default (when `BOT_LANGUAGE` is unset) stays Japanese to preserve the original cyberpunk aesthetic; unknown codes fall back to English.
- **Onboarding loop never exited**: `BOOTSTRAP.md` was only deleted when the LLM emitted a magic completion phrase ("onboarding complete", "saved to identity.md", …). Models that update `IDENTITY.md` correctly without that phrase left the bootstrap stale forever and re-triggered onboarding on every restart. `needs_onboarding()` now auto-completes when `IDENTITY.md` mtime > `BOOTSTRAP.md` mtime.

## [Unreleased] - 2026-04-29

### Added
- **Obsidian-Pro Skill**: Advanced knowledge capture based on `kepano/obsidian-skills`. Includes support for Obsidian Callouts (`[!abstract]`, `[!quote]`), YAML properties (status, project, topic), and wikilink prioritization.
- **Smart Message Heuristics**: Added a fast-path classifier in `vault.py` that identifies common casual phrases (greetings, acks) locally. This skips LLM calls, saving tokens and reducing response latency by ~2s on Raspberry Pi.
- **Digital Gardening Metadata**: New notes are automatically tagged with `status: "seedling"` in YAML frontmatter for Obsidian-compatible life-cycle tracking.

### Changed
- **Softened Casual Filter**: Casual messages no longer return a flat "ok". The bot now responds using its full personality (`SOUL.md`) while skipping the knowledge vault injection to keep the context clean.
- **`VAULT.md` Template**: Updated with instructions for "Obsidian-native" formatting and cross-note linking.
- **`README.md`**: Added sections on "Obsidian Pro" and the "Knowledge Vault" origin story.

## [Unreleased] - 2026-02-06

### Added
- **Soul & Identity in context**: `SOUL.md` and `IDENTITY.md` are now loaded during heartbeat for self-reflection, and lazily on identity-related questions. Bot can update them via `write_file()`.
- **`log_change` tool**: Bot maintains its own `.workspace/CHANGELOG.md` automatically after self-modifications.
- **`manage_service` tool**: Safe systemd wrapper with whitelist (gotchi-bot, ssh, networking, cron). Actions: status, restart, stop, start, logs.
- **`show_face` tool**: Wired into TOOL_MAP and TOOLS — was defined but never callable by the bot.
- **Self-Maintenance section** in BOT_INSTRUCTIONS.md: check_syntax → safe_restart flow, log_change after changes, health_check for diagnostics.
- **Heartbeat reflection logging**: Reflection text now saved to `memory/YYYY-MM-DD.md` daily logs.
- **Custom faces in display skill**: `add_custom_face()` documented, `data/custom_faces.json` mentioned.

### Added
- **Function Calling**: Enabled by default (`ENABLE_LITELLM_TOOLS=True`). The bot will now append tool usage (e.g., `remember_fact`, `check_mail`) to its replies.

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
- **Tool Logging**: Restored visibility of tool execution in Telegram messages.
- **Custom Face Consistency**: Removed redundant `show_face` tool. This fixes a bug where the bot would set a face via tool, but then the Telegram handler would overwrite it with a "happy" fallback because the `FACE:` tag was missing from the final text.

## [1.2.0] - 2026-02-07
### Added
- **Internal Reminders Logic**: Smart filtering for technical cron jobs (like heartbeat). The bot now handles technical tasks silently via E-Ink without spamming the user chat.
- **Dynamic Face Injection**: Custom faces are now dynamically injected into the system prompt, ensuring the bot "remembers" its expanded repertoire.
- **Enhanced GPIO Cleanup**: Robust `try...finally` blocks in UI rendering to prevent hardware freezes.

### Restored
- **Codebase Integrity**: Restored the project from the 2026-02-07 backup, which contains the most stable and feature-rich implementation of hooks, audit logging, and hardware management.

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
