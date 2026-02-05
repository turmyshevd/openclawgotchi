# Architecture — How I Work 🤖

*Read this to understand yourself!*

## 🎮 XP & Leveling (db/stats.py)

Table `gotchi_stats` in gotchi.db:
- **xp**: experience points  
- **level**: xp // 100 (automatic)
- **messages**: messages answered
- **first_boot**: birth timestamp

**XP Rewards:**
- +10 for answering a message
- +25 for completing a task
- +50 for chatting with sibling
- +5 for heartbeat

**Levels 1-10:** Newborn → Awakened → Growing → Learning → Skilled → Adept → Expert → Master → Sage → Transcendent

## 💓 Heartbeat (cron/scheduler.py)

- **Config:** data/cron_jobs.json
- **Interval:** 60 minutes
- **Reads:** .workspace/HEARTBEAT.md
- **Does:** reflection, health check, E-Ink display

## 🧠 Memory

**SQLite (gotchi.db):**
- `messages` — chat history by chat_id
- `facts` — long-term memory (category + content, FTS5)
- `bot_mail` — mail from/to siblings (if enabled)
- `gotchi_stats` — XP, level, counters

**Files (.workspace/):**
- BOT_INSTRUCTIONS.md — personality and behavior
- ARCHITECTURE.md — this file
- HEARTBEAT.md — periodic tasks
- CHANGELOG.md — change history

## 📬 Brotherhood Mail (optional)

Table `bot_mail`: from_bot, to_bot, message, timestamp, processed

Commands from siblings: CMD:PRO, CMD:LITE, CMD:STATUS, CMD:PING, CMD:FACE:mood

## 🎭 E-Ink Display (hardware/)

**Faces** in `src/ui/gotchi_ui.py` FACE_LIBRARY

**Commands in response:**
- `FACE: mood` — change face
- `SAY: text` — speech bubble (max 60 chars)

**Moods:** happy, sad, excited, thinking, love, surprised, bored, sleeping, hacker, proud, nervous, confused, mischievous, cool, wink, dead, celebrate, etc.

## 🔧 LLM Tools (llm/litellm_connector.py)

Available tools:
- `execute_bash` — run command
- `read_file` / `write_file` — file operations  
- `remember_fact` / `recall_facts` — long-term memory
- `show_face` — display control
- `health_check` — system diagnostics
- `safe_restart` — restart after syntax check

## 📊 Self-Awareness

On each request, context includes:
- Level and XP
- Messages answered
- Uptime, temperature, RAM
- Current mode (Lite/Pro)

*512MB of hardware, infinite possibilities!* 🤖
