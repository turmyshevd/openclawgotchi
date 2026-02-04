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

from config import BOT_TOKEN, HEARTBEAT_INTERVAL, HEARTBEAT_FIRST_RUN
from db.memory import init_db
from hardware.display import boot_screen, online_screen, show_face
from bot.handlers import (
    cmd_start, cmd_clear, cmd_status, cmd_pro,
    cmd_remember, cmd_recall, cmd_cron, cmd_jobs,
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
    """Callback for cron scheduler."""
    from bot.heartbeat import send_heartbeat
    log.info(f"Cron job triggered: {job.name}")
    
    # For now, just log it
    # In future: could send message via LLM
    from audit_logging.command_logger import log_command
    log_command(
        action=f"cron:{job.name}",
        user_id=0,
        chat_id=0,
        source="cron",
        extra={"job_id": job.id, "message": job.message}
    )


def main():
    """Start the bot."""
    
    # Check token
    if not BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    
    # Initialize database
    init_db()
    log.info("Database initialized")
    
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
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("pro", cmd_pro))
    app.add_handler(CommandHandler("lite", cmd_pro)) 
    app.add_handler(CommandHandler("mode", cmd_pro))
    app.add_handler(CommandHandler("remember", cmd_remember))
    app.add_handler(CommandHandler("recall", cmd_recall))
    app.add_handler(CommandHandler("cron", cmd_cron))
    app.add_handler(CommandHandler("jobs", cmd_jobs))
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
