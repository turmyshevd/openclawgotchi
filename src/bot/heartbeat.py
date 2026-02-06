"""
Heartbeat — periodic tasks, auto-mood, XP, bot_mail, reflection.
"""

import logging
import sqlite3
from pathlib import Path

from config import WORKSPACE_DIR, GROUP_CHAT_ID, get_admin_id, PROJECT_DIR
from db.memory import get_history, get_pending_tasks, delete_pending_task, save_message
from hardware.display import parse_and_execute_commands
from hardware.system import get_stats
from hardware.auto_mood import apply_auto_mood, get_auto_mood
from db.stats import on_heartbeat, get_status_bar, get_stats_summary
from llm.router import get_router
from llm.base import RateLimitError
from bot.telegram import send_message
from hooks.runner import run_hook, HookEvent

log = logging.getLogger(__name__)

# Bot mail config
DB_PATH = PROJECT_DIR / "gotchi.db"
# Bot identity — read from env, defaults to generic
MY_NAME = os.environ.get("BOT_NAME", "gotchi").lower().replace(" ", "-")
SIBLING_BOT = os.environ.get("SIBLING_BOT_NAME", "")  # Optional sibling for mail


def get_unread_mail() -> list[dict]:
    """Get unread mail for this bot from brother."""
    if not DB_PATH.exists():
        return []
    
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, from_bot, message, timestamp FROM bot_mail WHERE to_bot=? AND read_at IS NULL ORDER BY id ASC",
            (MY_NAME,)
        )
        rows = cursor.fetchall()
        
        if rows:
            ids = [r[0] for r in rows]
            placeholders = ",".join("?" * len(ids))
            conn.execute(f"UPDATE bot_mail SET read_at=CURRENT_TIMESTAMP WHERE id IN ({placeholders})", ids)
            conn.commit()
        
        conn.close()
        return [{"id": r[0], "from": r[1], "message": r[2], "timestamp": r[3]} for r in rows]
        
    except Exception as e:
        log.error(f"Failed to check bot_mail: {e}")
        return []


def send_mail(to_bot: str, message: str) -> bool:
    """Send mail to another bot (sibling bot)."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO bot_mail (from_bot, to_bot, message) VALUES (?, ?, ?)",
            (MY_NAME, to_bot, message)
        )
        conn.commit()
        conn.close()
        log.info(f"Sent mail to {to_bot}")
        return True
    except Exception as e:
        log.error(f"Failed to send mail: {e}")
        return False


def process_command_mail(message: str) -> str | None:
    """
    Process command mails from brother.
    Format: CMD:<command> [args]
    Returns response message or None if not a command.
    """
    if not message.startswith("CMD:"):
        return None
    
    cmd = message[4:].strip().upper()
    router = get_router()
    
    if cmd == "PRO":
        if not router.force_lite:
            return "Already in Pro mode 🧠"
        router.force_lite = False
        log.info("Remote command: switched to Pro mode")
        return "Switched to Pro mode! 🧠 Heavy thinking enabled."
    
    elif cmd == "LITE":
        if router.force_lite:
            return "Already in Lite mode ⚡"
        router.force_lite = True
        log.info("Remote command: switched to Lite mode")
        return "Switched to Lite mode! ⚡ Fast & free."
    
    elif cmd == "STATUS":
        stats = get_stats_summary()
        mood, _ = get_auto_mood()
        mode = "Lite" if router.force_lite else "Pro"
        return (
            f"Status Report:\n"
            f"Level {stats['level']} {stats['title']} ({stats['xp']} XP)\n"
            f"Mode: {mode}\n"
            f"Mood: {mood}\n"
            f"Messages: {stats['messages']} | Days: {stats['days_alive']}"
        )
    
    elif cmd == "PING":
        return "PONG! 🏓 I'm alive, brother!"
    
    elif cmd.startswith("FACE:"):
        face = cmd[5:].strip().lower()
        try:
            from hardware.display import show_face
            show_face(face, "From brother")
            return f"Face set to: {face}"
        except Exception as e:
            return f"Failed to set face: {e}"
    
    return f"Unknown command: {cmd}. Try: PRO, LITE, STATUS, PING, FACE:<mood>"


async def process_pending_tasks(context):
    """Retry pending tasks from queue."""
    tasks = get_pending_tasks()
    if not tasks:
        return
    
    log.info(f"Processing {len(tasks)} pending tasks...")
    
    task_id, chat_id, text, sender, is_group = tasks[0]
    
    try:
        router = get_router()
        history = get_history(chat_id)
        
        async with router.lock:
            response, connector = await router.call(text, history[:-3])
        
        await send_message(
            context.bot, 
            chat_id, 
            f"🔔 [Delayed Reply]\n{response}"
        )
        
        delete_pending_task(task_id)
        from db.stats import on_task_completed
        on_task_completed()
        
    except RateLimitError:
        log.info("Still rate limited, keeping task in queue")
    except Exception as e:
        log.error(f"Task failed: {e}")
        delete_pending_task(task_id)


async def send_heartbeat(context):
    """
    Periodic heartbeat: auto-mood, XP, mail check, reflect.
    Called every 4 hours.
    """
    run_hook(HookEvent(event_type="heartbeat", action="start"))
    
    # 1. Apply auto-mood first
    mood, mood_text = apply_auto_mood()
    
    # 2. Award heartbeat XP
    on_heartbeat()
    status_bar = get_status_bar()
    log.info(f"Heartbeat XP awarded. {status_bar}")
    
    # 3. Process pending queue
    await process_pending_tasks(context)
    
    # 4. Summarize recent conversations (LLM)
    try:
        from memory.flush import get_chats_with_recent_messages, summarize_and_save
        recent_chats = get_chats_with_recent_messages()
        if recent_chats:
            log.info(f"Summarizing {len(recent_chats)} chat(s) with recent activity")
            for chat_id in recent_chats[:3]:  # Max 3 chats to avoid overload
                saved = await summarize_and_save(chat_id)
                if saved:
                    log.info(f"Saved summary for chat {chat_id}")
    except Exception as e:
        log.warning(f"Conversation summarization failed: {e}")
    
    # 5. Check for mail from brother
    unread_mail = get_unread_mail()
    mail_section = ""
    command_responses = []
    
    if unread_mail:
        from db.stats import on_brother_chat
        on_brother_chat()
        log.info(f"Got {len(unread_mail)} new mail(s) from brother!")
        
        for m in unread_mail:
            # Check if it's a command
            cmd_response = process_command_mail(m['message'])
            if cmd_response:
                command_responses.append(cmd_response)
                if SIBLING_BOT:
                    send_mail(SIBLING_BOT, cmd_response)
            else:
                # Regular mail - add to prompt
                mail_section += f"- From {m['from']}: {m['message']}\n"
    
    # Get recent mail history for context
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("SELECT from_bot, message FROM bot_mail ORDER BY id DESC LIMIT 5")
        history_rows = cursor.fetchall()
        conn.close()
        
        history_section = "\n## Recent Mail History\n"
        for h_from, h_msg in reversed(history_rows):
            history_section += f"- {h_from}: {h_msg[:100]}...\n"
    except Exception:
        history_section = ""
    
    # If we only had commands, skip LLM call
    if unread_mail and not mail_section and command_responses:
        log.info(f"Processed {len(command_responses)} command(s), skipping LLM")
        run_hook(HookEvent(event_type="heartbeat", action="complete", text="commands only"))
        return
    
    # 5. Load heartbeat template
    hb_path = WORKSPACE_DIR / "HEARTBEAT.md"
    if not hb_path.exists():
        log.warning(f"HEARTBEAT.md not found at {hb_path}")
        return
    
    template = hb_path.read_text()
    
    # 6. Inject stats
    stats = get_stats()
    stats_summary = get_stats_summary()
    prompt = (
        template
        .replace("{{uptime}}", stats.uptime)
        .replace("{{temp}}", stats.temp)
        .replace("{{memory}}", stats.memory)
    )
    
    # Add current status
    prompt += f"\n\n## Current Status\n"
    prompt += f"- Level: {stats_summary['level']} {stats_summary['title']} ({stats_summary['xp']} XP)\n"
    prompt += f"- Mood: {mood} ({mood_text})\n"
    prompt += f"- Messages answered: {stats_summary['messages']}\n"
    prompt += f"- Days alive: {stats_summary['days_alive']}\n"
    
    # Add Facts & Skills Context
    try:
        from db.memory import get_facts
        facts = get_facts()
        if facts:
            prompt += "\n## Recent Learned Facts\n"
            for f in facts[-5:]:
                prompt += f"- {f['content']} ({f['category']})\n"
        
        from skills.loader import get_eligible_skills
        skills = get_eligible_skills()
        if skills:
            prompt += "\n## Active Skills\n"
            for s in skills:
                prompt += f"- {s['name']}: {s.get('description', '')[:50]}\n"
    except Exception:
        pass

    # Add mail sections
    if mail_section:
        prompt += f"\n## New Mail\n{mail_section}"
    prompt += history_section
    
    prompt += "\n\n[Respond with Qualitative Reflection, STATUS: OK, FACE: <mood>, or MAIL: <reply>]"
    
    # 7. Call LLM
    router = get_router()
    
    if router.lock.locked():
        log.info("Skipping heartbeat LLM: busy")
        return
    
    try:
        async with router.lock:
            response, connector = await router.call(prompt, [])
        
        log.info(f"Heartbeat [{connector}]: {response[:100]}")
        
        clean_text, commands = parse_and_execute_commands(response)
        
        # Handle MAIL: reply to sibling bot
        if commands.get("mail") and SIBLING_BOT:
            send_mail(SIBLING_BOT, commands["mail"])
        
        # Send group message
        if commands.get("group"):
            try:
                await send_message(context.bot, GROUP_CHAT_ID, commands["group"])
            except Exception as e:
                log.error(f"Failed to send GROUP message: {e}")
        
        # Send DM to admin
        admin_id = get_admin_id()
        if commands.get("dm") and admin_id:
            try:
                await send_message(context.bot, admin_id, commands["dm"])
            except Exception as e:
                log.error(f"Failed to send DM: {e}")
        
        if clean_text and not any(commands.values()):
            try:
                await send_message(context.bot, GROUP_CHAT_ID, clean_text)
            except Exception as e:
                log.error(f"Failed to send fallback message: {e}")
                
        run_hook(HookEvent(event_type="heartbeat", action="complete", text=response[:100]))
                
    except Exception as e:
        log.error(f"Heartbeat error: {e}")
        run_hook(HookEvent(event_type="heartbeat", action="error", text=str(e)))
