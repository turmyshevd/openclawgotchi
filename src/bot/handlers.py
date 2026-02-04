"""
Telegram command and message handlers.
"""

import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from db.memory import (
    save_message, get_history, clear_history, get_message_count,
    save_user, add_fact, search_facts, get_recent_facts,
    save_pending_task
)
from hardware.display import parse_and_execute_commands, error_screen, show_face
from hardware.system import get_stats
from llm.router import get_router
from llm.base import RateLimitError, LLMError
from bot.telegram import is_allowed, get_sender_name, send_long_message
from hooks.runner import run_hook, HookEvent
from memory.flush import check_and_inject_flush, write_to_daily_log
from cron.scheduler import add_cron_job, list_cron_jobs, remove_cron_job
from skills.loader import get_eligible_skills

log = logging.getLogger(__name__)


# --- Command Handlers ---

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    chat = update.effective_chat
    
    if not is_allowed(user.id, chat.id):
        if chat.type == "private":
            await update.message.reply_text("Access denied.")
        return
    
    save_user(user.id, user.username or "", user.first_name or "", user.last_name or "")
    
    # Fire command hook
    run_hook(HookEvent(
        event_type="command",
        action="/start",
        user_id=user.id,
        chat_id=chat.id,
        username=get_sender_name(user)
    ))
    
    await update.message.reply_text(
        f"Hi {user.first_name}! I'm your AI assistant on Raspberry Pi.\n\n"
        f"Commands:\n"
        f"/clear - clear conversation history\n"
        f"/status - system status\n"
        f"/pro - toggle Pro (Claude) mode\n"
        f"/remember <cat> <fact> - save to memory\n"
        f"/recall <query> - search memory\n"
        f"/cron <name> <minutes> <message> - add scheduled task\n"
        f"/jobs - list scheduled tasks"
    )


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /clear command."""
    user = update.effective_user
    chat = update.effective_chat
    
    if not is_allowed(user.id, chat.id):
        return
    
    # Fire command hook
    run_hook(HookEvent(
        event_type="command",
        action="/clear",
        user_id=user.id,
        chat_id=chat.id,
        username=get_sender_name(user)
    ))
    
    clear_history(chat.id)
    await update.message.reply_text("History cleared.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command — with XP and rate limit info."""
    user = update.effective_user
    chat = update.effective_chat
    
    if not is_allowed(user.id, chat.id):
        return
    
    from hardware.system import get_stats
    from db.stats import get_stats_summary
    from llm.router import get_router
    from skills.loader import get_eligible_skills
    from cron.scheduler import list_cron_jobs
    from hardware.display import show_face
    
    stats = get_stats()
    gotchi_stats = get_stats_summary()
    router = get_router()
    mode = "Lite ⚡" if router.force_lite else "Pro 🧠"
    
    skills = get_eligible_skills()
    jobs = list_cron_jobs()
    active_jobs = len([j for j in jobs if j.enabled])
    
    # Build status message
    msg = (
        f"🎮 *Lv{gotchi_stats['level']} {gotchi_stats['title']}*\n"
        f"XP: {gotchi_stats['xp']} | Next: {gotchi_stats['xp_to_next']}\n"
        f"Days: {gotchi_stats['days_alive']} | Msgs: {gotchi_stats['messages']}\n\n"
        f"*System*\n"
        f"⏱ {stats.uptime} | 🌡 {stats.temp}\n"
        f"💾 {stats.memory}\n\n"
        f"*Bot*\n"
        f"Mode: {mode}\n"
        f"Skills: {len(skills)} | Jobs: {active_jobs}"
    )
    
    # Update display with status
    show_face("smart", f"SAY:Status check! | STATUS:{mode}")
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_pro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /pro command — toggle between Lite and Pro."""
    user = update.effective_user
    chat = update.effective_chat
    
    if not is_allowed(user.id, chat.id):
        return
    
    router = get_router()
    is_lite = router.toggle_lite_mode()
    
    if is_lite:
        show_face("cool", "SAY: Fast & Free! | MODE: L | STATUS: Lite Mode")
        await update.message.reply_text("✨ Mode: Lite (Gemini) — Fast & Free")
    else:
        show_face("smart", "SAY: Heavy thinking... | MODE: P | STATUS: Pro Mode")
        await update.message.reply_text("🧠 Mode: Pro (Claude Code) — Smart & Heavy")


async def cmd_remember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /remember command — save to long-term memory."""
    user = update.effective_user
    chat = update.effective_chat
    
    if not is_allowed(user.id, chat.id):
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /remember <category> <fact>\n"
            "Example: /remember preference I like coffee"
        )
        return
    
    category = context.args[0]
    fact = " ".join(context.args[1:])
    
    add_fact(fact, category)
    
    # Also write to daily log
    write_to_daily_log(f"Remembered [{category}]: {fact}")
    
    await update.message.reply_text(f"📝 Saved [{category}]: {fact}")


async def cmd_recall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /recall command — search long-term memory."""
    user = update.effective_user
    chat = update.effective_chat
    
    if not is_allowed(user.id, chat.id):
        return
    
    if not context.args:
        # Show recent facts
        facts = get_recent_facts(5)
        if not facts:
            await update.message.reply_text("No facts in memory yet.")
            return
        
        msg = "📚 Recent facts:\n\n"
        for f in facts:
            ts = f['timestamp'][:10]
            msg += f"[{ts}] ({f['category']}) {f['content']}\n"
        await update.message.reply_text(msg)
        return
    
    query = " ".join(context.args)
    facts = search_facts(query)
    
    if not facts:
        await update.message.reply_text(f"🔍 No facts found for: {query}")
        return
    
    msg = f"🔍 Found {len(facts)} fact(s):\n\n"
    for f in facts:
        ts = f['timestamp'][:10]
        msg += f"[{ts}] ({f['category']}) {f['content']}\n"
    await update.message.reply_text(msg)


async def cmd_cron(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /cron command — add a scheduled task.
    Usage: /cron <name> <minutes> <message>
    Example: /cron "Check email" 30 "Check inbox for urgent messages"
    """
    user = update.effective_user
    chat = update.effective_chat
    
    if not is_allowed(user.id, chat.id):
        return
    
    if not context.args or len(context.args) < 3:
        await update.message.reply_text(
            "Usage: /cron <name> <minutes> <message>\n"
            "Example: /cron reminder 30 Check inbox\n\n"
            "Or for one-shot:\n"
            "/cron reminder 20m Call back (runs once in 20 min)"
        )
        return
    
    name = context.args[0]
    interval_str = context.args[1]
    message = " ".join(context.args[2:])
    
    # Parse interval
    if interval_str.endswith("m"):
        # One-shot: "20m" means run once in 20 minutes
        job = add_cron_job(
            name=name,
            message=message,
            run_at=interval_str,
            delete_after_run=True
        )
        await update.message.reply_text(
            f"⏰ One-shot job added: {name}\n"
            f"Runs in: {interval_str}\n"
            f"Message: {message}"
        )
    else:
        # Recurring
        try:
            minutes = int(interval_str)
        except ValueError:
            await update.message.reply_text("Invalid interval. Use number or '20m' format.")
            return
        
        job = add_cron_job(
            name=name,
            message=message,
            interval_minutes=minutes
        )
        await update.message.reply_text(
            f"⏰ Cron job added: {name}\n"
            f"Interval: every {minutes} min\n"
            f"Message: {message}\n"
            f"ID: {job.id}"
        )


async def cmd_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /jobs command — list scheduled tasks."""
    user = update.effective_user
    chat = update.effective_chat
    
    if not is_allowed(user.id, chat.id):
        return
    
    jobs = list_cron_jobs()
    
    if not jobs:
        await update.message.reply_text("No scheduled jobs.")
        return
    
    # Check if removing a job
    if context.args and context.args[0] == "rm":
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /jobs rm <job_id>")
            return
        
        job_id = context.args[1]
        if remove_cron_job(job_id):
            await update.message.reply_text(f"Removed job: {job_id}")
        else:
            await update.message.reply_text(f"Job not found: {job_id}")
        return
    
    msg = "⏰ *Scheduled Jobs*\n\n"
    for job in jobs:
        status = "✓" if job.enabled else "✗"
        if job.interval_minutes:
            schedule = f"every {job.interval_minutes}m"
        elif job.run_at:
            schedule = f"at {job.run_at[:16]}"
        else:
            schedule = "unknown"
        
        msg += f"{status} *{job.name}* ({job.id})\n"
        msg += f"   Schedule: {schedule}\n"
        msg += f"   Runs: {job.run_count}\n"
    
    msg += "\nRemove with: /jobs rm <job_id>"
    
    await update.message.reply_text(msg, parse_mode="Markdown")


# --- Message Handler ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages."""
    user = update.effective_user
    chat = update.effective_chat
    is_group = chat.type in ("group", "supergroup")
    
    if not is_allowed(user.id, chat.id):
        if not is_group:
            await update.message.reply_text("Access denied.")
        return
    
    user_text = update.message.text
    if not user_text:
        return
    
    conv_id = chat.id
    sender = get_sender_name(user)
    
    # Fire message hook (for logging)
    run_hook(HookEvent(
        event_type="message",
        user_id=user.id,
        chat_id=chat.id,
        username=sender,
        text=user_text
    ))
    
    # Save message to history (always, for passive listening in groups)
    if is_group:
        save_message(conv_id, "user", f"[{sender}]: {user_text}")
    else:
        save_message(conv_id, "user", user_text)
    
    # Check if we should respond (in groups: only when mentioned/replied)
    if is_group:
        bot_username = context.bot.username
        is_mentioned = f"@{bot_username}" in user_text
        is_reply = (
            update.message.reply_to_message and 
            update.message.reply_to_message.from_user.id == context.bot.id
        )
        
        if not (is_mentioned or is_reply):
            return  # Saved to DB, but staying silent
        
        # Clean mention from text
        user_text = user_text.replace(f"@{bot_username}", "").strip()
    
    save_user(user.id, user.username or "", user.first_name or "", user.last_name or "")
    
    # Show typing
    await chat.send_action(ChatAction.TYPING)
    
    # Get history (excluding current message)
    history = get_history(conv_id)
    if history:
        history = history[:-1]
    
    # Check if memory flush needed
    flush_prompt = check_and_inject_flush(history)
    if flush_prompt:
        # Prepend flush reminder to user message
        user_text = user_text + flush_prompt
    
    # Call LLM
    router = get_router()
    
    # Call LLM
    router = get_router()
    
    try:
        # lock handled internally by connector
        log.info(f"[{sender}] -> {user_text[:80]}")
        response, connector = await router.call(user_text, history)
        log.info(f"[{sender}] <- [{connector}] {response[:80]}")
        
        # Check for error response (e.g. from LiteLLM)
        if response.startswith("Error:"):
            error_screen(response)
            await update.message.reply_text(response)
            return
        
        # Parse hardware commands
        clean_text, cmds = parse_and_execute_commands(response)
        
        # Execute memory command
        if cmds.get("remember"):
            add_fact(cmds["remember"], "auto_memory")
            # Subtle confirmation? Or just silent. Silent is better for fluidity.
            log.info(f"Auto-remembered: {cmds['remember']}")
        
        # Save response
        save_message(conv_id, "assistant", response)
        # Award XP for answering
        from db.stats import on_message_answered
        on_message_answered()
        
        # Log response
        from audit_logging.command_logger import log_bot_response
        pass # avoiding circular import issues if any, essentially just ensure logging happens
        # Actually proper import was above
        # log_bot_response(conv_id, response, connector) 
        # Re-adding the import and call correctly as it was in original but unindented
        
        from audit_logging.command_logger import log_bot_response
        log_bot_response(conv_id, response, connector)
        
        # Add lite mode indicator
        if connector == "litellm":
            clean_text += "\n\n_⚡ Lite Mode_"
            await send_long_message(update, clean_text, parse_mode="Markdown")
        else:
            await send_long_message(update, clean_text)
            
    except RateLimitError:
        # Queue for later
        save_pending_task(conv_id, user_text, sender, is_group)
        await update.message.reply_text("💤 Rate limited. Queued for later.")
        
        # Show on screen
        error_screen("Rate Limit")
        
        from audit_logging.command_logger import log_error
        log_error("rate_limit", "Claude rate limited", {"chat_id": conv_id})
        
    except LLMError as e:
        log.error(f"LLM error: {e}")
        await update.message.reply_text(f"Error: {e}")
        
        # Show on screen
        error_screen(str(e))
        
        from audit_logging.command_logger import log_error
        log_error("llm_error", str(e), {"chat_id": conv_id})
        
    except Exception as e:
        log.error(f"Unexpected error: {e}")
        await update.message.reply_text(f"Error: {e}")
        
        # Show on screen
        error_screen(str(e))
        
        from audit_logging.command_logger import log_error
        log_error("unexpected", str(e), {"chat_id": conv_id})
