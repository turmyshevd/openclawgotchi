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
    save_pending_task, get_connection
)
from hardware.display import parse_and_execute_commands, error_screen, show_face
from hardware.system import get_stats
from llm.router import get_router
from llm.base import RateLimitError, LLMError
from bot.telegram import is_allowed, get_sender_name, send_long_message
from bot.onboarding import needs_onboarding, get_bootstrap_prompt, check_onboarding_complete, complete_onboarding
from hooks.runner import run_hook, HookEvent
from memory.flush import check_and_inject_flush, write_to_daily_log
from memory.summarize import optimize_history
from cron.scheduler import add_cron_job, list_cron_jobs, remove_cron_job
from skills.loader import get_eligible_skills
from config import LLM_PRESETS

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
        f"*Commands:*\n"
        f"/status — system & XP\n"
        f"/xp — XP rules & progress\n"
        f"/context — view/trim context window\n"
        f"/clear — wipe conversation history\n"
        f"/pro — switch to Pro mode\n"
        f"/lite — switch to Lite mode\n"
        f"/mode — toggle Lite/Pro mode\n"
        f"/memory — database stats\n\n"
        f"*Memory:*\n"
        f"/remember <cat> <fact> — save fact\n"
        f"/recall <query> — search memory\n\n"
        f"*Automation:*\n"
        f"/cron <name> <min> <msg> — schedule task\n"
        f"/jobs — list/remove tasks"
    , parse_mode="Markdown")


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


async def cmd_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /context command — show context window status."""
    user = update.effective_user
    chat = update.effective_chat
    
    if not is_allowed(user.id, chat.id):
        return
    
    from config import HISTORY_LIMIT, MODEL_CONTEXT_TOKENS
    
    msg_count = get_message_count(chat.id)
    history = get_history(chat.id)  # last HISTORY_LIMIT messages only
    
    # Tokens actually sent to model (history only; system prompt is extra)
    total_chars = sum(len(m.get("content", "")) for m in history)
    est_tokens = total_chars // 4
    # Model context window usage (history vs model limit)
    usage_pct_model = min(100, (est_tokens * 100) // MODEL_CONTEXT_TOKENS)
    filled = min(10, (usage_pct_model * 10) // 100)
    bar = "█" * filled + "░" * (10 - filled)
    
    msg = (
        f"📊 *Context Window*\n\n"
        f"*Model window:* ~{est_tokens:,} / {MODEL_CONTEXT_TOKENS:,} tokens\n"
        f"[{bar}] {usage_pct_model}%\n"
        f"Messages in context: {len(history)}/{HISTORY_LIMIT} (total in DB: {msg_count})\n\n"
        f"On each message we send this history to the model (no persistent session).\n"
        f"*To clear model context:*\n"
        f"/clear — wipe all history (model sees nothing next time)\n"
        f"/context trim — keep last 3 messages\n"
        f"/context sum — summarize & save to memory"
    )
    
    # Handle subcommands
    if context.args:
        subcmd = context.args[0].lower()
        if subcmd == "trim":
            # Keep only last 3 messages
            conn = get_connection()
            conn.execute("""
                DELETE FROM messages WHERE user_id = ? AND id NOT IN (
                    SELECT id FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT 3
                )
            """, (chat.id, chat.id))
            conn.commit()
            conn.close()
            
            new_count = get_message_count(chat.id)
            await update.message.reply_text(
                f"✂️ Trimmed! Kept last 3 messages.\n"
                f"Before: {msg_count} → After: {new_count}"
            )
            return
        
        elif subcmd == "summarize" or subcmd == "sum":
            # Manually trigger LLM summarization
            await update.message.reply_text("🧠 Summarizing conversation...")
            
            from memory.flush import summarize_conversation_with_llm, write_to_daily_log
            
            summary = await summarize_conversation_with_llm(history)
            if summary:
                write_to_daily_log(f"[Manual Summary]\n{summary}")
                await update.message.reply_text(f"📝 *Summary saved:*\n\n{summary}", parse_mode="Markdown")
            else:
                await update.message.reply_text("No summary needed (not enough messages or already summarized)")
            return
    
    await update.message.reply_text(msg, parse_mode="Markdown")


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
    from llm.rate_limits import get_all_limits_summary
    
    stats = get_stats()
    gotchi_stats = get_stats_summary()
    router = get_router()
    mode = "Lite ⚡" if router.force_lite else "Pro 🧠"
    
    skills = get_eligible_skills()
    jobs = list_cron_jobs()
    active_jobs = len([j for j in jobs if j.enabled])
    
    # RPG-style XP progress bar (10 segments)
    xp_in = gotchi_stats.get("xp_in_level", 0)
    xp_need = gotchi_stats.get("xp_needed_this_level") or 1
    max_lv = gotchi_stats.get("max_level", 20)
    if gotchi_stats["level"] >= max_lv:
        xp_bar = "█" * 10 + " MAX"
    else:
        filled = min(10, int(10 * xp_in / xp_need)) if xp_need else 0
        xp_bar = "█" * filled + "░" * (10 - filled)
        xp_bar += f" {xp_in}/{xp_need}"
    
    msg = (
        f"🎮 *Lv{gotchi_stats['level']} {gotchi_stats['title']}*\n"
        f"XP: {gotchi_stats['xp']} | {xp_bar}\n"
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


async def cmd_xp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /xp — RPG-style XP rules and current progress (no tables for Telegram)."""
    user = update.effective_user
    chat = update.effective_chat
    
    if not is_allowed(user.id, chat.id):
        return
    
    from db.stats import get_level_progress, get_xp_rules
    
    prog = get_level_progress()
    rules = get_xp_rules()
    
    # Progress bar
    xp_in = prog["xp_in_level"]
    xp_need = prog["xp_needed_this_level"] or 1
    if prog["level"] >= prog["max_level"]:
        xp_bar = "█" * 10 + " MAX"
        progress_line = f"Lv{prog['level']} {prog['title']} — {xp_bar}"
    else:
        filled = min(10, int(10 * xp_in / xp_need)) if xp_need else 0
        xp_bar = "█" * filled + "░" * (10 - filled)
        progress_line = f"Lv{prog['level']} {prog['title']} — {xp_bar} {xp_in}/{xp_need} to Lv{prog['level'] + 1}"
    
    lines = [
        "📊 *XP & Levels*",
        "",
        progress_line,
        f"Total XP: {prog['xp']}",
        "",
        "*How you earn XP:*",
    ]
    for action, amount, desc in rules:
        lines.append(f"• {action}: *+{amount}* — {desc}")
    lines.append("")
    lines.append(f"Levels 1–{prog['max_level']}. Use /status for full stats.")
    
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_pro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /pro, /lite, /mode — toggle or set Lite/Pro."""
    user = update.effective_user
    chat = update.effective_chat
    
    if not is_allowed(user.id, chat.id):
        return
    
    router = get_router()
    # Detect explicit mode requests (so /lite doesn't toggle)
    cmd_text = ""
    if update.message and update.message.text:
        cmd_text = update.message.text.split()[0].lower()
    requested = None
    if cmd_text == "/lite":
        requested = "lite"
    elif cmd_text == "/pro":
        requested = "pro"
    elif cmd_text == "/mode" and context.args:
        arg = context.args[0].lower()
        if arg in ("lite", "pro"):
            requested = arg

    if requested == "lite":
        if not router.force_lite:
            router.force_lite = True
        is_lite = True
    elif requested == "pro":
        if router.force_lite:
            router.force_lite = False
        is_lite = False
    else:
        # Default: toggle for /mode (no args) or legacy usage
        is_lite = router.toggle_lite_mode()
    
    if is_lite:
        show_face("cool", "SAY: Fast & Free! | MODE: L | STATUS: Lite Mode")
        current = router.litellm.model.split("/")[-1] if getattr(router.litellm, "model", None) else "LiteLLM"
        await update.message.reply_text(f"✨ Mode: Lite — {current}\n(Use /use gemini or /use glm to switch backend)")
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
            delete_after_run=True,
            target_chat_id=chat.id
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
            interval_minutes=minutes,
            target_chat_id=chat.id
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
        
        # Check if anything left after removing mention
        if not user_text:
            return  # Nothing to process
    
    save_user(user.id, user.username or "", user.first_name or "", user.last_name or "")
    
    # Show typing
    await chat.send_action(ChatAction.TYPING)
    
    # Get history (excluding current message)
    history = get_history(conv_id)
    if history:
        history = history[:-1]
    
    # Check if memory flush needed (use full history length, before optimization)
    flush_prompt = check_and_inject_flush(history)

    # Optimize history for context window
    history = optimize_history(history)
    
    # Check for onboarding (first-run setup)
    onboarding_mode = needs_onboarding()
    if onboarding_mode:
        bootstrap_prompt = get_bootstrap_prompt()
        user_text = bootstrap_prompt + " [USER]: " + user_text
        log.info("Onboarding mode active")
    
    if flush_prompt:
        # Prepend flush reminder to user message
        user_text = user_text + flush_prompt
    
    # Call LLM (set cron target so one-shot reminders go to this chat)
    from llm import litellm_connector
    litellm_connector.set_cron_target_chat_id(conv_id)
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
        
        # Fallback: if LLM didn't include FACE:, show a default face
        if not cmds.get("face"):
            show_face(mood="happy", text=clean_text[:50] if clean_text else "...")
        
        # Execute memory command
        if cmds.get("remember"):
            add_fact(cmds["remember"], "auto_memory")
            log.info(f"Auto-remembered: {cmds['remember']}")
        
        # Execute mail command (MAIL: in LLM response)
        if cmds.get("mail"):
            try:
                from bot.heartbeat import send_mail
                from config import SIBLING_BOT_NAME
                if SIBLING_BOT_NAME:
                    send_mail(SIBLING_BOT_NAME, cmds["mail"])
                    log.info(f"Mail sent to {SIBLING_BOT_NAME}: {cmds['mail'][:50]}")
                else:
                    log.warning("MAIL: command but no SIBLING_BOT_NAME configured")
            except Exception as e:
                log.error(f"Failed to send mail: {e}")
        
        # Save response
        save_message(conv_id, "assistant", response)
        
        # Check if onboarding completed
        if onboarding_mode and check_onboarding_complete(response):
            complete_onboarding()
            log.info("Onboarding completed!")
        
        # Log response
        from audit_logging.command_logger import log_bot_response
        log_bot_response(conv_id, response, connector)
        
        # Action confirmations for parsed commands (not tools)
        cmd_notes = []
        if cmds.get("mail"):
            from config import SIBLING_BOT_NAME
            if SIBLING_BOT_NAME:
                cmd_notes.append(f"📨 mail → {SIBLING_BOT_NAME}: \"{cmds['mail'][:40]}\" ✓")
        if cmds.get("remember"):
            cmd_notes.append(f"🧠 remembered: \"{cmds['remember'][:40]}\"")
        if cmd_notes:
            clean_text += "\n\n```\n🔧 " + "\n  ".join(cmd_notes) + "\n```"
        
        # Mode indicator only for Pro (Lite = default, no label)
        if connector != "litellm":
            clean_text += "\n\n🧠 Pro"
        
        # Send main response (which now includes tool usage as before)
        await send_long_message(update, clean_text, parse_mode="Markdown" if connector == "litellm" else None)

        # AWARD XP LAST — Avoid Level Up overwriting the response on E-Ink
        from db.stats import on_message_answered, on_tool_use
        on_message_answered()
        
        # Count tool actions from response footer for XP bonus
        import re
        tool_match = re.search(r'Tool usage \((\d+)\):', response)
        if tool_match:
            on_tool_use(int(tool_match.group(1)))
        # Also count parsed commands (MAIL:, REMEMBER:) as tool-like actions
        elif cmds.get("mail") or cmds.get("remember"):
            on_tool_use(sum(1 for k in ("mail", "remember") if cmds.get(k)))
            
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
    finally:
        litellm_connector.set_cron_target_chat_id(None)

async def cmd_use(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch LLM model (Gemini <-> GLM)."""
    if not is_allowed(update.effective_user.id, update.effective_chat.id):
        return

    if not context.args:
        # Show current model
        router = get_router()
        current = router.litellm.model
        msg = f"🦄 *Current Model:* `{current}`\n\nUsage: `/use [gemini|glm]`"
        await update.message.reply_markdown(msg)
        return

    model_key = context.args[0].lower()
    
    if model_key not in LLM_PRESETS:
        await update.message.reply_text(f"❌ Unknown model preset. Use: {', '.join(LLM_PRESETS.keys())}")
        return
        
    preset = LLM_PRESETS[model_key]
    
    # 1. Switch LiteLLM
    router = get_router()
    router.litellm.set_model(preset["model"], preset["api_base"])
    
    # 2. Force Lite mode so next query uses it
    router.force_lite = True
    
    # 3. UI Feedback
    emoji = "🇨🇳" if "glm" in model_key else "🇺🇸"
    if "gemini" in model_key: emoji = "♊️"
    
    await update.message.reply_text(f"{emoji} Switched to *{model_key.upper()}*!\nModel: {preset['model']}", parse_mode="Markdown")
    
    # Visual update
    show_face(mood="happy", text=f"Model: {model_key.upper()}")


async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /memory command — show database stats."""
    user = update.effective_user
    chat = update.effective_chat

    if not is_allowed(user.id, chat.id):
        return

    from db.memory import get_message_count, get_all_facts_count
    from db.stats import get_stats_summary
    from hardware.system import get_stats
    import sqlite3
    from pathlib import Path

    stats = get_stats()
    gotchi_stats = get_stats_summary()
    from config import DB_PATH
    db_path = DB_PATH

    # Count messages
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM messages")
    msg_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM facts")
    fact_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM bot_mail")
    mail_count = cursor.fetchone()[0]
    conn.close()

    # DB size
    db_size = db_path.stat().st_size if db_path.exists() else 0

    msg = (
        f"📊 **Memory Dashboard**\n\n"
        f"**Messages:** {msg_count}\n"
        f"**Facts:** {fact_count}\n"
        f"**Mail:** {mail_count}\n"
        f"**Database:** {db_size // 1024} KB\n\n"
        f"**System**\n"
        f"{stats.uptime} | {stats.temp}\n"
        f"{stats.memory}\n\n"
        f"**XP:** {gotchi_stats['xp']} (Lv{gotchi_stats['level']})"
    )

    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /health command — detailed system health."""
    user = update.effective_user
    chat = update.effective_chat

    if not is_allowed(user.id, chat.id):
        return

    from hardware.system import get_stats
    from db.stats import get_stats_summary
    from config import SRC_DIR, DB_PATH
    import subprocess

    stats = get_stats()
    gotchi_stats = get_stats_summary()

    # Code stats
    result = subprocess.run(
        f"find {SRC_DIR} -name '*.py' | wc -l",
        shell=True, capture_output=True, text=True
    )
    py_files = result.stdout.strip() or "unknown"

    msg = (
        f"🏥 **Health Report**\n\n"
        f"**System**\n"
        f"⏱ {stats.uptime}\n"
        f"🌡 {stats.temp}\n"
        f"💾 {stats.memory}\n\n"
        f"**Bot**\n"
        f"Level {gotchi_stats['level']} {gotchi_stats['title']}\n"
        f"XP: {gotchi_stats['xp']} | Messages: {gotchi_stats['messages']}\n"
        f"Days alive: {gotchi_stats['days_alive']}\n\n"
        f"**Codebase**\n"
        f"Python files: {py_files}\n\n"
        f"**Database**\n"
        f"Size: {DB_PATH.stat().st_size // 1024} KB"
    )

    await update.message.reply_text(msg, parse_mode="Markdown")
