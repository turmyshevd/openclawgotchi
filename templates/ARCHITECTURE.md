# Architecture — How I Work

## XP & Leveling (db/stats.py)

Table `gotchi_stats` in `gotchi.db`:
- **xp**: experience points  
- **messages**: messages answered
- **first_boot**: birth timestamp

**XP Sources:**
- +10 message answered
- +5 per tool used in a response
- +25 task completed
- +50 sibling chat
- +5 heartbeat
- +100 per day alive

**20 Levels** with customizable titles.

## Heartbeat (bot/heartbeat.py)

- **Interval:** Every 4 hours
- **Template:** `.workspace/HEARTBEAT.md`
- **Context:** Loads SOUL.md + IDENTITY.md for self-awareness
- **Does:** auto-mood, XP award, conversation summarization, mail check, LLM reflection
- **Output:** Reflection saved to `memory/YYYY-MM-DD.md`, optional DM/GROUP/MAIL

## Memory

**SQLite (gotchi.db):**
- `messages` — chat history by chat_id
- `facts` — long-term memory (FTS5 full-text search)
- `bot_mail` — mail from/to siblings
- `gotchi_stats` — XP, level, counters

**Files (.workspace/):**
- `BOT_INSTRUCTIONS.md` — system prompt (loaded every request)
- `SOUL.md` — personality (loaded on identity questions + heartbeat)
- `IDENTITY.md` — who I am (loaded on identity questions + heartbeat)
- `ARCHITECTURE.md` — this file (loaded on technical questions)
- `TOOLS.md` — hardware specs (loaded on hardware questions)
- `HEARTBEAT.md` — reflection template
- `MEMORY.md` — curated long-term memory
- `memory/` — daily logs

## Brotherhood Mail (optional)

Table `bot_mail`: from_bot, to_bot, message, timestamp, read_at
Commands: CMD:PRO, CMD:LITE, CMD:STATUS, CMD:PING, CMD:FACE:mood

## E-Ink Display (ui/gotchi_ui.py)

Kaomoji faces. Default + custom from `data/custom_faces.json`.
**Commands:** `FACE: mood`, `SAY: text`, `DISPLAY: text`

## LLM Tools (llm/litellm_connector.py)

execute_bash, read_file, write_file, list_directory, remember_fact, recall_facts, search_skills, read_skill, show_face, add_custom_face, check_mail, health_check, manage_service, schedule_task, safe_restart

## Context Loading (llm/prompts.py)

Every request: BOT_INSTRUCTIONS.md + skills list + system status
Lazy (by keywords): ARCHITECTURE.md, TOOLS.md, SOUL.md, IDENTITY.md
