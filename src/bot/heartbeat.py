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
MY_NAME = "probro-zero"


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
            conn.execute("UPDATE bot_mail SET read_at=CURRENT_TIMESTAMP WHERE id IN (" + ",".join(map(str, ids)) + ")")
            conn.commit()
        
        conn.close()
        return [{"id": r[0], "from": r[1], "message": r[2], "timestamp": r[3]} for r in rows]
        
    except Exception as e:
        log.error(f"Failed to check bot_mail: {e}")
        return []


def send_mail(to_bot: str, message: str) -> bool:
    """Send mail to another bot (e.g., probro-master)."""
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
    
    # 4. Check for mail from brother
    mail_list = get_unread_mail()
    mail_section = ""
    command_responses = []
    
    if mail_list:
        from db.stats import on_brother_chat
        on_brother_chat()
        log.info(f"Got {len(mail_list)} mail(s) from brother!")
        
        for m in mail_list:
            # Check if it's a command
            cmd_response = process_command_mail(m['message'])
            if cmd_response:
                command_responses.append(cmd_response)
                send_mail("probro-master", cmd_response)
            else:
                # Regular mail - add to prompt
                mail_section += f"\n\n## 📬 Mail from Brother\n"
                mail_section += f"From: {m['from']} ({m['timestamp']})\n{m['message']}\n---\n"
        
        if mail_section:
            mail_section += "\nRespond with MAIL: <message> to reply to brother."
    
    # If we only had commands, skip LLM call
    if mail_list and not mail_section and command_responses:
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
    
    # Add mail section
    prompt += mail_section
    
    prompt += "\n\n[Respond with STATUS: OK, GROUP: <msg>, DM: <msg>, FACE: <mood>, or MAIL: <reply>]"
    
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
        
        # Handle MAIL: reply to brother
        if commands.get("mail"):
            send_mail("probro-master", commands["mail"])
        
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
