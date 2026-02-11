#!/usr/bin/env python3
"""
OpenClawGotchi — Lightweight AI bot for Raspberry Pi Zero 2W.

Entry point. All logic is in modules:
- config.py         — paths, env vars
- db/               — SQLite operations
- hardware/         — display, system stats
- llm/              — Claude CLI, LiteLLM, router
- bot/              — Telegram handlers, heartbeat
- hooks/            — Event-driven automation
- cron/             — Task scheduling
- skills/           — Skills loading with gating
- logging/          — Command audit trail
- memory/           — Memory flush system
"""

import sys
import logging
from pathlib import Path

# Add src to path for imports
SRC_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SRC_DIR))

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from config import BOT_TOKEN, HEARTBEAT_INTERVAL, HEARTBEAT_FIRST_RUN, LEVEL_UP_DISPLAY_DELAY
from db.memory import init_db
from hardware.display import boot_screen, online_screen, show_face
from bot.handlers import (
    cmd_start, cmd_clear, cmd_context, cmd_status, cmd_xp, cmd_pro, cmd_use,
    cmd_remember, cmd_recall, cmd_cron, cmd_memory, cmd_health, cmd_jobs,
    handle_message
)
from bot.heartbeat import send_heartbeat
from hooks.runner import run_hook, HookEvent, discover_and_load_hooks
from cron.scheduler import get_scheduler
from skills.loader import load_all_skills, get_eligible_skills

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)


async def run_cron_job(job):
    """Callback for cron scheduler — trigger LLM with chat context and send reply to owner."""
    log.info(f"Cron job triggered: {job.name}")
    
    from audit_logging.command_logger import log_command
    log_command(
        action=f"cron:{job.name}",
        user_id=0,
        chat_id=0,
        source="cron",
        extra={"job_id": job.id, "message": job.message}
    )
    
    from config import get_admin_id
    from telegram import Bot
    
    def is_internal_reminder(j) -> bool:
        """Internal self-reminders should not be sent to user chat."""
        text = f"{getattr(j, 'name', '')} {getattr(j, 'message', '')}".lower()
        return "heartbeat.md" in text or "hourly heartbeat" in text

    internal_reminder = is_internal_reminder(job)

    # Send to same chat where user asked, or owner's private chat (unless internal)
    chat_id = getattr(job, "target_chat_id", 0) or get_admin_id()
    if not chat_id and not internal_reminder:
        log.warning("Cron job: no chat_id/admin_id, cannot send message")
        return
    
    bot = Bot(token=BOT_TOKEN)
    fallback_text = f"⏰ Напоминание: {job.name}"
    
    async def send_to_owner(text: str):
        if internal_reminder:
            return False
        if not text or not text.strip():
            return False
        try:
            await bot.send_message(chat_id=chat_id, text=text.strip()[:4000])
            log.info(f"Cron job {job.name}: sent to owner (len={len(text)})")
            return True
        except Exception as e:
            log.error(f"Cron job send_message failed: {e}")
            return False
    
    # Call LLM with full context: recent chat history + explicit "scheduled reminder" instruction
    from llm.router import get_router
    from hardware.display import parse_and_execute_commands, show_face
    from db.memory import get_history
    
    reminder_topic = (job.message or job.name or "Remind the user.").strip()
    history = get_history(chat_id, limit=12)  # last 12 messages — LLM sees how user asked for the reminder
    
    if internal_reminder:
        cron_system = (
            "Internal self-reminder for the bot. Do NOT send a user-facing message. "
            "Only output FACE: and SAY: for the E-Ink display."
        )
        prompt = f"Self-reminder: «{reminder_topic}»"
    else:
        cron_system = (
            "Scheduled reminder. The user asked to be reminded at this time. "
            "Reply with ONE short, friendly message to send them in Telegram right now. "
            "Use the same language as the user. End with FACE: and SAY:."
        )
        prompt = f"Reminder time. Send the user this reminder now: «{reminder_topic}»"
    
    if get_router().lock.locked():
        if internal_reminder:
            log.info(f"Cron job {job.name}: LLM busy, skipping internal reminder send")
            return
        log.info(f"Cron job {job.name}: LLM busy, sending fallback only")
        await send_to_owner(fallback_text)
        return
    
    try:
        async with get_router().lock:
            response, connector = await get_router().call(
                prompt, history, system_prompt=cron_system
            )
        log.info(f"Cron [{connector}]: {response[:80]}...")
        clean_text, _ = parse_and_execute_commands(response)
        if not internal_reminder:
            if clean_text and clean_text.strip():
                await send_to_owner(clean_text.strip())
            else:
                await send_to_owner(fallback_text)
    except Exception as e:
        log.error(f"Cron job {job.name} LLM failed: {e}")
        show_face("confused", f"Cron: {str(e)[:25]}")
        if not internal_reminder:
            await send_to_owner(fallback_text)


def ensure_workspace():
    """Ensure .workspace/ exists — create from templates if needed."""
    from config import WORKSPACE_DIR, PROJECT_DIR
    import shutil
    
    if WORKSPACE_DIR.exists():
        return True
    
    templates_dir = PROJECT_DIR / "templates"
    if not templates_dir.exists():
        log.error("Neither .workspace/ nor templates/ found!")
        return False
    
    log.info("First run: creating .workspace/ from templates/")
    shutil.copytree(templates_dir, WORKSPACE_DIR)
    log.info(f"Created {WORKSPACE_DIR}")
    return True


def main():
    """Start the bot."""
    
    # Check token
    if not BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
        print("Copy .env.example to .env and configure it.", file=sys.stderr)
        sys.exit(1)
    
    # Ensure workspace exists (creates from templates on first run)
    if not ensure_workspace():
        print("Error: Could not initialize workspace", file=sys.stderr)
        sys.exit(1)
    
    # Initialize database
    init_db()
    log.info("Database initialized")
    
    # Set up level-up callback (runs in background thread to avoid blocking)
    from db.stats import set_level_up_callback
    from hardware.display import show_face
    import threading
    
    def on_level_up(level, title):
        def delayed_display():
            import time
            time.sleep(LEVEL_UP_DISPLAY_DELAY)
            show_face("celebrate", f"SAY:LEVEL UP! Lv{level}! | STATUS:{title}")
        threading.Thread(target=delayed_display, daemon=True).start()
        log.info(f"Level up notification: Lv{level} {title}")
    set_level_up_callback(on_level_up)
    
    # Load skills
    skills = load_all_skills()
    eligible = get_eligible_skills()
    log.info(f"Loaded {len(skills)} skills ({len(eligible)} eligible)")
    
    # Discover and load hooks
    discover_and_load_hooks()
    
    # Show boot screen
    boot_screen()
    
    # Fire startup hook
    run_hook(HookEvent(event_type="startup"))

    async def chill_mode(context):
        """Switch to chill mode after boot."""
        show_face(mood="cool", text="Chilling...")
        log.info("Switched to chill mode")

    async def post_init(application: Application):
        """Async post-initialization hook."""
        # Start cron scheduler
        scheduler = get_scheduler()
        scheduler.on_job_run(run_cron_job)
        scheduler.start()
        log.info(f"Cron scheduler started ({len(scheduler.jobs)} jobs)")
        
        # Process any pending command mail from sibling on startup
        from bot.heartbeat import get_unread_mail, process_command_mail, send_mail, SIBLING_BOT
        for mail in get_unread_mail():
            cmd_response = process_command_mail(mail["message"])
            if cmd_response and SIBLING_BOT:
                send_mail(SIBLING_BOT, cmd_response)
                log.info(f"Startup: processed command mail -> {cmd_response[:50]}")

        # Show online screen (Start sleeping)
        show_face(mood="sleeping", text="Online (Zzz...)")
        log.info("Bot is running...")
        
        # Schedule chill mode in 60 seconds
        if application.job_queue:
            application.job_queue.run_once(chill_mode, 60)
    
    # Build application
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Register handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("context", cmd_context))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("xp", cmd_xp))
    app.add_handler(CommandHandler("pro", cmd_pro))
    app.add_handler(CommandHandler("lite", cmd_pro)) 
    app.add_handler(CommandHandler("mode", cmd_pro))
    app.add_handler(CommandHandler("use", cmd_use))
    app.add_handler(CommandHandler("switch", cmd_use))
    app.add_handler(CommandHandler("remember", cmd_remember))
    app.add_handler(CommandHandler("recall", cmd_recall))
    app.add_handler(CommandHandler("cron", cmd_cron))
    app.add_handler(CommandHandler("jobs", cmd_jobs))

    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Schedule heartbeat
    if app.job_queue:
        app.job_queue.run_repeating(
            send_heartbeat, 
            interval=HEARTBEAT_INTERVAL, 
            first=HEARTBEAT_FIRST_RUN
        )
        log.info(f"Heartbeat scheduled (every {HEARTBEAT_INTERVAL//3600}h)")
    else:
        log.warning("JobQueue not available — heartbeat disabled")
    
    # Start polling
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
