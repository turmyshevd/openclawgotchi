"""
Telegram command and message handlers.
"""

import logging
import re
import os
import tempfile
import base64
import asyncio
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from db.memory import (
    save_message, get_history, clear_history, get_message_count,
    save_user, add_fact, search_facts, get_recent_facts,
    save_pending_task, get_connection, save_feedback_event
)
from hardware.display import parse_and_execute_commands, error_screen, show_face
from hardware.system import get_stats
from llm.router import get_router
from llm.base import RateLimitError, LLMError
from bot.telegram import is_allowed, get_sender_name, send_long_message
from bot.onboarding import needs_onboarding, get_bootstrap_prompt, check_onboarding_complete, complete_onboarding
from hooks.runner import run_hook, HookEvent
from memory.flush import check_and_inject_flush, write_to_daily_log
from memory.vault import classify_message_for_vault, get_vault_stats
from memory.summarize import optimize_history
from cron.scheduler import add_cron_job, list_cron_jobs, remove_cron_job
from skills.loader import get_eligible_skills
from config import (
    LLM_PRESETS,
    OPENAI_API_KEY,
    OPENAI_VISION_MODEL,
    OPENAI_VISION_MAX_IMAGE_MB,
    SYNCTHING_API_KEY,
    SYNCTHING_API_URL,
)
from config import OLLAMA_API_BASE
from llm.prompts import build_system_context, build_vault_context

log = logging.getLogger(__name__)

# --- Voice Handling Helpers ---

async def _keep_typing(chat_id: int, context: ContextTypes.DEFAULT_TYPE, stop_event: asyncio.Event) -> None:
    """Refresh Telegram typing status until the current response is ready."""
    while not stop_event.is_set():
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:
            log.debug("Failed to send typing action", exc_info=True)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=4.0)
        except asyncio.TimeoutError:
            continue

async def transcribe_voice(file_path: str) -> str:
    """Transcribe audio file using OpenAI Whisper."""
    if not OPENAI_API_KEY:
        return "Error: OPENAI_API_KEY not set in .env."
    
    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        with open(file_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file,
                response_format="text"
            )
        return str(transcript).strip()
    except Exception as e:
        log.error(f"Whisper transcription failed: {e}")
        return f"Error: Transcription failed: {e}"


def image_to_base64(file_path: str) -> str:
    """Convert image file to base64 string."""
    with open(file_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def _derive_attachment_name(caption: str, vision_text: str) -> str:
    """Create a readable attachment stem from caption or vision output."""
    if caption and caption.strip():
        return caption.strip()[:80]

    text = (vision_text or "").strip()
    if not text:
        return "image-capture"

    title_match = re.search(r'Title:\s*"?([^"\n]+)"?', text, re.IGNORECASE)
    if title_match:
        return title_match.group(1).strip()[:80]

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    first_line = re.sub(r"^\d+\.\s*", "", first_line)
    first_line = re.sub(r"^\*+\s*Title\s*:?\s*", "", first_line, flags=re.IGNORECASE)
    first_line = re.sub(
        r"^(the image (features|shows|depicts)|this image (shows|depicts)|screenshot of)\s+",
        "",
        first_line,
        flags=re.IGNORECASE,
    )
    first_line = re.sub(r"[*`_#]", "", first_line)
    first_line = first_line.split(".")[0].split(":")[0].strip(" -")
    return first_line[:80] or "image-capture"


async def analyze_image_with_openai(file_path: str, prompt: str, mime_type: str = "image/jpeg") -> str:
    """Analyze an image with an OpenAI vision-capable model."""
    if not OPENAI_API_KEY:
        return "Error: OPENAI_API_KEY not set in .env."

    max_bytes = OPENAI_VISION_MAX_IMAGE_MB * 1024 * 1024
    if os.path.getsize(file_path) > max_bytes:
        return f"Error: Image too large for vision analysis. Max: {OPENAI_VISION_MAX_IMAGE_MB} MB."

    img_b64 = image_to_base64(file_path)

    def _call_openai() -> str:
        import openai

        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{img_b64}"},
                        },
                    ],
                }
            ],
        )
        return (response.choices[0].message.content or "").strip()

    try:
        return await asyncio.to_thread(_call_openai)
    except Exception as e:
        log.error(f"OpenAI vision failed: {e}")
        return f"Error: Vision analysis failed: {e}"


async def process_image_file(
    *,
    local_file_path: str,
    caption: str = "",
    conv_id: int,
    mime_type: str = "image/jpeg",
    source: str = "telegram",
) -> str:
    """Analyze an image, save it to the vault, and return a user-facing summary."""
    from memory.vault import save_attachment, capture_note

    vision_prompt = (
        "Analyze this image and provide:\n"
        "1. TITLE: A very short, descriptive title (3-5 words) that captures the core subject.\n"
        "2. SUMMARY: A detailed transcription and visual description. If there is text, transcribe it. If there are tables, reproduce them. Focus only on visual facts.\n"
        "Format: TITLE: [your title]\nSUMMARY: [your analysis]"
    )

    response = await analyze_image_with_openai(local_file_path, vision_prompt, mime_type)
    connector = "openai"
    if response.startswith("Error:"):
        raise RuntimeError(response)

    # 4. Parse response for title
    note_title = "Visual Capture"
    analysis_text = response
    if "TITLE:" in response:
        try:
            parts = response.split("TITLE:", 1)[1].split("SUMMARY:", 1)
            note_title = parts[0].strip().replace("*", "").replace("#", "")
            if len(parts) > 1:
                analysis_text = parts[1].strip()
        except Exception:
            pass
    elif caption:
        note_title = caption[:40]

    attachment_name = _derive_attachment_name(caption, analysis_text)
    rel_path = save_attachment(Path(local_file_path), preferred_name=attachment_name)

    note_body = (
        f"![[{rel_path}]]\n\n"
        f"### Visual Analysis\n{analysis_text}\n"
    )

    result = capture_note(
        title=note_title,
        raw_text=caption or "Image attachment",
        summary="Visual capture analyzed by " + connector,
        body=note_body,
        source=source,
        note_type="visual",
        tags=["vision", "attachment"]
    )

    history_entry = f"[IMAGE SAVED to Vault: {result.title}]\n\nSummary of what I saw: {analysis_text}"
    save_message(conv_id, "user", f"[User sent an image with caption: {caption or 'none'}]")
    save_message(conv_id, "assistant", history_entry)

    msg = (
        f"📸 *Captured to Vault: {result.title}*\n\n"
        f"```\n{analysis_text}\n```\n"
        f"_Image saved to attachments/_"
    )
    show_face(mood="smart", text="I see it!")
    return msg


async def _process_image_message(update: Update, local_file_path: str, mime_type: str = "image/jpeg") -> None:
    """Analyze an image, save it to the vault, and reply safely."""
    msg = await process_image_file(
        local_file_path=local_file_path,
        caption=update.message.caption or "",
        conv_id=update.effective_chat.id,
        mime_type=mime_type,
        source="telegram",
    )
    await send_long_message(update, msg)

# Patterns that signal the user is unhappy with the bot's response
_NEGATIVE_PATTERNS = (
    "wrong", "not right", "doesn't work", "try again", "that's wrong",
    "incorrect", "not what i", "no no", "nope",
)


def _is_negative_feedback(text: str) -> bool:
    """Detect if user message signals dissatisfaction with bot's last response."""
    t = text.lower().strip()
    words = t.split()
    # Short one-word negatives
    if len(words) == 1 and words[0] in ("no", "no.", "wrong"):
        return True
    return any(p in t for p in _NEGATIVE_PATTERNS)


def _should_enable_memo_mode(user_text: str, classification) -> bool:
    """
    Enable vault capture only when the classifier is confident or the message
    looks like a substantial structured note.
    This keeps casual chat from being silently turned into notes.
    """
    text = (user_text or "").strip()
    if not text:
        return False

    if getattr(classification, "kind", "") != "memo":
        return False

    confidence = float(getattr(classification, "confidence", 0.0) or 0.0)
    low = text.lower()

    # Long structured fragments are plausible notes even without explicit "save this".
    structured_note = (
        "\n" in text
        or text.startswith(("-", "*", "1.", "2.", "3."))
        or "todo" in low
        or "tl;dr" in low
    )

    if confidence >= 0.85:
        return True

    if confidence >= 0.70 and structured_note and len(text) >= 80:
        return True

    return False


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
        f"/syncvault — sync Obsidian vault NOW\n"
        f"/vault — knowledge vault status\n"
        f"/memory — database stats\n\n"
        f"/health — system health check\n"
        f"/battery — UPS HAT battery status\n"
        f"/update — pull latest code and restart\n\n"
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
        f"\n/vault — knowledge vault status"
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


async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trigger manual Syncthing rescan for Obsidian vault."""
    user = update.effective_user
    chat = update.effective_chat

    if not is_allowed(user.id, chat.id):
        return

    await chat.send_action(ChatAction.TYPING)

    if not SYNCTHING_API_KEY:
        await update.message.reply_text(
            "Sync not configured. Set `SYNCTHING_API_KEY` in `.env` to enable `/syncvault`.",
            parse_mode="Markdown",
        )
        return

    try:
        import requests

        headers = {"X-API-Key": SYNCTHING_API_KEY}
        response = requests.post(SYNCTHING_API_URL, headers=headers, timeout=10)

        if response.status_code == 200:
            await update.message.reply_text(
                "🔄 *Sync triggered.* Check Obsidian in a few seconds.",
                parse_mode="Markdown",
            )
            show_face(mood="excited", text="Syncing...")
        else:
            await update.message.reply_text(f"❌ Sync failed (API Error: {response.status_code})")

    except Exception as e:
        log.error(f"Manual sync failed: {e}")
        await update.message.reply_text(f"❌ Error triggering sync: {e}")


async def cmd_vault(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show vault status."""
    user = update.effective_user
    chat = update.effective_chat

    if not is_allowed(user.id, chat.id):
        return

    stats = get_vault_stats()
    lines = [
        "📚 *Knowledge Vault*",
        "",
        f"Path: `{stats['vault_dir']}`",
        f"Notes: {stats['notes_count']}",
        f"Inbox days: {stats['inbox_days']}",
        "",
        "Recent notes:",
    ]
    if stats["recent"]:
        lines.extend(f"- `{path.name}`" for path in stats["recent"])
    else:
        lines.append("- none yet")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


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


# --- Voice Message Handler ---

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming voice messages."""
    user = update.effective_user
    chat = update.effective_chat
    
    if not is_allowed(user.id, chat.id):
        if chat.type == "private":
            await update.message.reply_text("Access denied.")
        return

    # Show "recording" status while we process
    await chat.send_action(ChatAction.RECORD_VOICE)
    
    try:
        # Download voice file
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            tmp_path = tmp.name
        
        # Transcribe
        text = await transcribe_voice(tmp_path)
        
        # Cleanup
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
            
        if text.startswith("Error:"):
            await update.message.reply_text(text)
            return

        if not text:
            await update.message.reply_text("I heard nothing. Try again?")
            return

        # Tell the user what we heard (briefly)
        await update.message.reply_text(f"🎤 *I heard:* {text}", parse_mode="Markdown")
        
        # Pass transcribed text directly to handle_message
        await handle_message(update, context, override_text=text)
        
    except Exception as e:
        log.error(f"Voice handling failed: {e}")
        await update.message.reply_text(f"Error processing voice: {e}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming photos/images."""
    user = update.effective_user
    chat = update.effective_chat

    if not is_allowed(user.id, chat.id):
        if chat.type == "private":
            await update.message.reply_text("Access denied.")
        return

    # Show "uploading" status while we process
    await chat.send_action(ChatAction.UPLOAD_PHOTO)

    try:
        # 1. Download the highest resolution photo
        photo_file = await update.message.photo[-1].get_file()

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            await photo_file.download_to_drive(tmp.name)
            tmp_path = tmp.name
        await _process_image_message(update, tmp_path, "image/jpeg")

    except Exception as e:
        log.error(f"Photo handling failed: {e}")
        await update.message.reply_text(f"Error processing photo: {e}")
    finally:
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.remove(tmp_path)


async def handle_image_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle images sent as documents, e.g. full-quality screenshots."""
    user = update.effective_user
    chat = update.effective_chat

    if not is_allowed(user.id, chat.id):
        if chat.type == "private":
            await update.message.reply_text("Access denied.")
        return

    document = update.message.document
    if not document or not (document.mime_type or "").startswith("image/"):
        return

    await chat.send_action(ChatAction.UPLOAD_PHOTO)

    suffix = Path(document.file_name or "image.bin").suffix or ".img"

    try:
        image_file = await document.get_file()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            await image_file.download_to_drive(tmp.name)
            tmp_path = tmp.name

        await _process_image_message(update, tmp_path, document.mime_type)
    except Exception as e:
        log.error(f"Image document handling failed: {e}")
        await update.message.reply_text(f"Error processing image: {e}")
    finally:
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.remove(tmp_path)


_TEXT_DOCUMENT_SUFFIXES = {
    ".md", ".txt", ".text", ".log", ".csv", ".json", ".yaml", ".yml",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".sh", ".toml", ".ini", ".cfg",
    ".conf", ".xml", ".html", ".css", ".sql",
}
_TEXT_DOCUMENT_MIME_PREFIXES = ("text/",)
_TEXT_DOCUMENT_MIME_TYPES = {
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-yaml",
}
_MAX_TEXT_DOCUMENT_BYTES = 512 * 1024


def _is_text_document(file_name: str, mime_type: str) -> bool:
    suffix = Path(file_name or "").suffix.lower()
    mime = (mime_type or "").lower()
    return (
        suffix in _TEXT_DOCUMENT_SUFFIXES
        or mime in _TEXT_DOCUMENT_MIME_TYPES
        or any(mime.startswith(prefix) for prefix in _TEXT_DOCUMENT_MIME_PREFIXES)
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle non-image documents, currently focusing on text-like files."""
    user = update.effective_user
    chat = update.effective_chat

    if not is_allowed(user.id, chat.id):
        if chat.type == "private":
            await update.message.reply_text("Access denied.")
        return

    document = update.message.document
    if not document:
        return

    file_name = document.file_name or "document"
    mime_type = document.mime_type or "application/octet-stream"

    if not _is_text_document(file_name, mime_type):
        await update.message.reply_text(
            f"I got `{file_name}`, but I currently only read text documents like `.md`, `.txt`, `.json`, `.py`, `.yaml`.",
            parse_mode="Markdown",
        )
        return

    if document.file_size and document.file_size > _MAX_TEXT_DOCUMENT_BYTES:
        await update.message.reply_text(
            f"`{file_name}` is too large for inline reading. Limit: {_MAX_TEXT_DOCUMENT_BYTES // 1024} KB.",
            parse_mode="Markdown",
        )
        return

    # Start typing immediately so user knows we're downloading
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(chat.id, context, stop_typing))

    try:
        remote_file = await document.get_file()
        suffix = Path(file_name).suffix or ".txt"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            await remote_file.download_to_drive(tmp.name)
            tmp_path = tmp.name

        raw_bytes = Path(tmp_path).read_bytes()
        text = raw_bytes.decode("utf-8", errors="replace").strip()

        # Stop typing before calling handle_message, as handle_message starts its own typing task
        stop_typing.set()
        await typing_task

        if not text:
            await update.message.reply_text(f"`{file_name}` looks empty.", parse_mode="Markdown")
            return

        if len(text) > 12000:
            text = text[:12000] + "\n\n[truncated]"

        prefix = f"[User attached file: {file_name}]\n"
        if update.message.caption:
            prefix += f"[Caption: {update.message.caption}]\n"
        prefix += "\n"

        await handle_message(update, context, override_text=prefix + text)

    except Exception as e:
        log.error(f"Document handling failed: {e}")
        stop_typing.set()
        await update.message.reply_text(f"Error processing document: {e}")
    finally:
        stop_typing.set()
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.remove(tmp_path)


# --- Message Handler ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, override_text: str = None):
    """Handle incoming messages."""
    user = update.effective_user
    chat = update.effective_chat
    is_group = chat.type in ("group", "supergroup")
    stop_typing: asyncio.Event | None = None
    typing_task: asyncio.Task | None = None
    
    if not is_allowed(user.id, chat.id):
        if not is_group:
            await update.message.reply_text("Access denied.")
        return
    
    user_text = override_text or update.message.text
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

    # Detect dissatisfaction — save for heartbeat reflection
    if _is_negative_feedback(user_text):
        try:
            # Get last bot response as context
            recent = get_history(conv_id, limit=4)
            last_bot = next(
                (m["content"] for m in reversed(recent) if m["role"] == "assistant"),
                "",
            )
            save_feedback_event(conv_id, user_text, last_bot)
            log.info(f"Feedback event saved: '{user_text[:50]}'")
        except Exception as e:
            log.warning(f"Failed to save feedback event: {e}")

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

    # Start typing immediately so pre-LLM steps are also covered.
    await chat.send_action(ChatAction.TYPING)
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(chat.id, context, stop_typing))
    
    # Triage before deciding how to handle the message.
    history = get_history(conv_id)
    if history:
        history = history[:-1]
    onboarding_mode = needs_onboarding()
    classification = None
    memo_mode = False
    if not onboarding_mode:
        classification = await classify_message_for_vault(user_text, history)
        # Keep personality for small talk, but only switch into vault-capture mode
        # when the user clearly intends to save a note or the classifier is highly confident.
        memo_mode = _should_enable_memo_mode(user_text, classification)

    # Check if memory flush needed (use full history length, before optimization)
    flush_prompt = check_and_inject_flush(history)

    # Optimize history for context window
    history = optimize_history(history)
    
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
    system_prompt = None
    if memo_mode:
        system_prompt = build_system_context(user_text) + "\n---\n" + build_vault_context() + "\n\n"
        system_prompt += (
            "## Memo Capture Directive\n"
            "Treat this message as project knowledge unless it clearly becomes a command or question.\n"
            "If enough context is available, use vault_write to capture the note in markdown.\n"
            "If anything essential is unclear, ask one short clarifying question before writing.\n"
            "Do not invent fixed categories. Use free-form project/topic/tags/links.\n"
            "After capture, keep the reply brief and mention what was saved.\n"
        )
    
    try:
        # lock handled internally by connector
        log.info(f"[{sender}] -> {user_text[:80]}")
        response, connector = await router.call(user_text, history, system_prompt=system_prompt)
        log.info(f"[{sender}] <- [{connector}] {response[:80]}")
        
        # Check for error response (e.g. from LiteLLM)
        if response.startswith("Error:"):
            error_screen(response)
            await update.message.reply_text(response)
            return
        
        # Separate tool footer from LLM response
        tool_footer = ""
        if "__TOOL_FOOTER__" in response:
            parts = response.split("__TOOL_FOOTER__", 1)
            response = parts[0].rstrip()
            tool_footer = parts[1].strip()
        
        # Parse hardware commands
        clean_text, cmds = parse_and_execute_commands(response)
        
        # Fallback: if LLM didn't include FACE:, show a default face
        if not cmds.get("face"):
            show_face(mood="happy", text=clean_text[:50] if clean_text else "...")
        
        # Execute memory command
        if cmds.get("remember"):
            add_fact(cmds["remember"], "auto_memory")
            log.info(f"Auto-remembered: {cmds['remember']}")
        
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
        if cmds.get("remember"):
            cmd_notes.append(f"🧠 remembered: \"{cmds['remember'][:40]}\"")
        if cmd_notes:
            clean_text += "\n\n```\n🔧 " + "\n  ".join(cmd_notes) + "\n```"
        
        if connector != "litellm":
            clean_text += "\n\n🧠 Pro"
            
        # Append tool usage summary if exists
        if tool_footer:
            clean_text += "\n\n" + tool_footer
            
        await send_long_message(update, clean_text, parse_mode="Markdown" if connector == "litellm" else None)

        # AWARD XP LAST — Avoid Level Up overwriting the response on E-Ink
        from db.stats import on_message_answered, on_tool_use
        on_message_answered()
        
        tool_source = tool_footer or response
        tool_match = re.search(r'Tool usage \((\d+)\):', tool_source)
        if tool_match:
            on_tool_use(int(tool_match.group(1)))
        # Knowledge capture gets its own XP reward if the vault write was used.
        if memo_mode and "saved vault note" in tool_source.lower():
            from db.stats import on_knowledge_capture
            on_knowledge_capture()
        # Also count parsed commands (REMEMBER:) as tool-like actions
        elif cmds.get("remember"):
            on_tool_use(1)
            
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
        if stop_typing is not None:
            stop_typing.set()
        if typing_task is not None:
            await typing_task
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

async def cmd_battery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /battery command — show UPS HAT (C) status."""
    if not is_allowed(update.effective_user.id, update.effective_chat.id):
        return

    from hardware import battery

    reading = battery.read()
    if reading is None:
        await update.message.reply_text(
            "No UPS HAT detected.\n"
            "Make sure I2C is enabled and the UPS HAT (C) is connected, then try /battery again."
        )
        return

    await update.message.reply_text(reading.long())

async def cmd_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pull latest code from upstream, refresh deps, restart service."""
    import subprocess
    from config import PROJECT_DIR, get_admin_id

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not is_allowed(user_id, chat_id):
        return

    admin_id = get_admin_id()
    if admin_id is None:
        await update.message.reply_text("❌ /update is disabled until ALLOWED_USERS is configured.")
        return
    if user_id != admin_id:
        await update.message.reply_text("⛔ Owner-only command.")
        return

    script = PROJECT_DIR / "scripts" / "auto_update.sh"
    if not script.exists():
        await update.message.reply_text(f"❌ Update script not found: `{script}`", parse_mode="Markdown")
        return

    check_only = bool(context.args and context.args[0].lower() in ("check", "--check"))
    msg = await update.message.reply_text("🔍 Checking for updates…" if check_only else "⬇️ Updating…")

    try:
        cmd = ["bash", str(script)] + (["--check"] if check_only else [])
        proc = await asyncio.to_thread(
            subprocess.run, cmd,
            cwd=str(PROJECT_DIR),
            capture_output=True, text=True, timeout=300
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        out = out.strip()[-3500:]

        if check_only:
            if proc.returncode == 0:
                status = "🆕 Updates available"
            elif proc.returncode == 1:
                status = "✅ Up-to-date"
            else:
                status = f"❌ Update check failed (exit {proc.returncode})"
            await msg.edit_text(f"{status}\n\n```\n{out}\n```", parse_mode="Markdown")
            return

        if proc.returncode == 0:
            await msg.edit_text(f"✅ Update complete\n\n```\n{out}\n```", parse_mode="Markdown")
            show_face(mood="excited", text="Updated!")
        elif proc.returncode == 4:
            await msg.edit_text(
                f"⚠️ Update failed — auto-rolled back to previous version\n\n```\n{out}\n```",
                parse_mode="Markdown"
            )
            show_face(mood="confused", text="Update rolled back")
        else:
            await msg.edit_text(f"❌ Update failed (exit {proc.returncode})\n\n```\n{out}\n```", parse_mode="Markdown")
            show_face(mood="confused", text="Update failed")
    except subprocess.TimeoutExpired:
        await msg.edit_text("❌ Update timed out after 5 min.")
    except Exception as e:
        await msg.edit_text(f"❌ Update error: `{e}`", parse_mode="Markdown")


# --- /model command: inline-button picker with live Ollama discovery ---

_MODEL_EMOJI = {"gemini": "♊️", "glm": "🇨🇳", "ollama": "🦙"}


def _ollama_list_with_capabilities(timeout: float = 4.0) -> list[dict]:
    """Fetch installed Ollama models + capabilities. Returns [{name, supports_tools}]."""
    import requests
    base = (OLLAMA_API_BASE or "").rstrip("/")
    if not base:
        return []
    try:
        r = requests.get(f"{base}/api/tags", timeout=timeout)
        r.raise_for_status()
        names = [m.get("name") for m in r.json().get("models", []) if m.get("name")]
    except Exception as e:
        log.warning(f"Ollama /api/tags failed: {e}")
        return []

    out = []
    for name in names:
        supports = False
        try:
            sr = requests.post(f"{base}/api/show", json={"model": name}, timeout=timeout)
            if sr.ok:
                caps = sr.json().get("capabilities") or []
                supports = "tools" in caps
        except Exception:
            pass
        out.append({"name": name, "supports_tools": supports})
    return out


def _top_model_markup(current: str) -> InlineKeyboardMarkup:
    rows = []
    for key in LLM_PRESETS.keys():
        emoji = _MODEL_EMOJI.get(key, "🔹")
        active = LLM_PRESETS[key]["model"] == current or (
            key == "ollama" and isinstance(current, str) and current.startswith("ollama_chat/")
        )
        marker = " ✅" if active else ""
        suffix = " ▸" if key == "ollama" else ""
        rows.append([InlineKeyboardButton(f"{emoji} {key}{marker}{suffix}", callback_data=f"model:{key}")])
    return InlineKeyboardMarkup(rows)


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show inline buttons to switch LLM model. With argument acts like /use."""
    if not is_allowed(update.effective_user.id, update.effective_chat.id):
        return

    if context.args:
        return await cmd_use(update, context)

    router = get_router()
    current = router.litellm.model
    text = f"🦄 *Current:* `{current}`\n\nPick a model:"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=_top_model_markup(current))


async def cb_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback for /model inline buttons (presets + Ollama submenu)."""
    import asyncio
    query = update.callback_query
    if not is_allowed(query.from_user.id, query.message.chat_id):
        await query.answer("Not allowed", show_alert=True)
        return
    await query.answer()

    data = query.data or ""
    router = get_router()

    # Specific Ollama model switch: omd:<name>
    if data.startswith("omd:"):
        model_name = data.split(":", 1)[1]
        full = f"ollama_chat/{model_name}"
        router.litellm.set_model(full, OLLAMA_API_BASE)
        router.force_lite = True
        await query.edit_message_text(
            f"🦙 Switched to *Ollama / {model_name}*\n`{full}`",
            parse_mode="Markdown"
        )
        show_face(mood="happy", text=f"Ollama: {model_name[:20]}")
        return

    key = data.split(":", 1)[-1]

    # Back to top menu
    if key == "back":
        await query.edit_message_text(
            f"🦄 *Current:* `{router.litellm.model}`\n\nPick a model:",
            parse_mode="Markdown",
            reply_markup=_top_model_markup(router.litellm.model)
        )
        return

    # Ollama: fetch and show submenu (only tool-capable models)
    if key == "ollama":
        await query.edit_message_text("🦙 Fetching models from Ollama server…")
        models = await asyncio.to_thread(_ollama_list_with_capabilities)

        if not models:
            await query.edit_message_text(
                f"❌ Could not reach Ollama at `{OLLAMA_API_BASE}`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◂ Back", callback_data="model:back")]])
            )
            return

        tool_models = [m for m in models if m["supports_tools"]]
        show_models = tool_models if tool_models else models
        note = "" if tool_models else "\n⚠️ _No tool-capable models found, showing all_"

        rows = []
        for m in show_models:
            name = m["name"]
            cb = f"omd:{name}"
            if len(cb.encode("utf-8")) > 60:
                continue  # Telegram callback_data limit (64 bytes)
            tag = "🔧" if m["supports_tools"] else "🔸"
            rows.append([InlineKeyboardButton(f"{tag} {name}", callback_data=cb)])
        rows.append([InlineKeyboardButton("◂ Back", callback_data="model:back")])

        await query.edit_message_text(
            f"🦙 *Ollama models* ({len(show_models)}){note}\n\n🔧 = supports tools",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(rows)
        )
        return

    # Static presets (gemini, glm)
    if key not in LLM_PRESETS:
        await query.edit_message_text("❌ Unknown model.")
        return

    preset = LLM_PRESETS[key]
    router.litellm.set_model(preset["model"], preset["api_base"])
    router.force_lite = True

    emoji = _MODEL_EMOJI.get(key, "🔹")
    await query.edit_message_text(
        f"{emoji} Switched to *{key.upper()}*\n`{preset['model']}`",
        parse_mode="Markdown"
    )
    show_face(mood="happy", text=f"Model: {key.upper()}")
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
    conn.close()

    # DB size
    db_size = db_path.stat().st_size if db_path.exists() else 0

    msg = (
        f"📊 **Memory Dashboard**\n\n"
        f"**Messages:** {msg_count}\n"
        f"**Facts:** {fact_count}\n"
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
