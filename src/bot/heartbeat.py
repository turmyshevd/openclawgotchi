"""
Heartbeat — periodic tasks, auto-mood, XP, reflection.
"""

import logging
import os
import re
from pathlib import Path

from config import WORKSPACE_DIR, GROUP_CHAT_ID, get_admin_id, PROJECT_DIR, OWNER_NAME
from db.memory import get_history, get_pending_tasks, delete_pending_task, save_message
from hardware.display import parse_and_execute_commands
from hardware.auto_mood import apply_auto_mood, get_auto_mood
from db.stats import on_heartbeat, get_status_bar, get_stats_summary
from llm.router import get_router
from llm.base import RateLimitError
from bot.telegram import send_message
from hooks.runner import run_hook, HookEvent

log = logging.getLogger(__name__)

DB_PATH = PROJECT_DIR / "gotchi.db"
# Bot identity — read from env, defaults to generic
MY_NAME = os.environ.get("BOT_NAME", "gotchi").lower().replace(" ", "-")


def _sanitize_reflection_text(text: str) -> str:
    """Keep only the reflection text (strip tool usage, headers, and status boilerplate)."""
    if not text:
        return ""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if lower.startswith("**heartbeat") or lower.startswith("heartbeat"):
            continue
        if lower.startswith("**system") or lower.startswith("system:"):
            continue
        if lower.startswith("**reflection") or lower.startswith("reflection"):
            continue
        if stripped.startswith("---"):
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


def _get_heartbeat_target_chat_id() -> int:
    """Choose where to send heartbeat reflection."""
    if GROUP_CHAT_ID:
        return GROUP_CHAT_ID
    return get_admin_id() or 0


async def process_pending_tasks(context):
    """Retry pending tasks from queue."""
    tasks = get_pending_tasks()
    if not tasks:
        return
    
    log.info(f"Processing {len(tasks)} pending tasks...")
    
    # Avoid overload — process only a few per heartbeat
    MAX_TASKS = 3
    
    for task_id, chat_id, text, sender, is_group in tasks[:MAX_TASKS]:
        try:
            router = get_router()
            history = get_history(chat_id)
            if history:
                history = history[:-1]
            
            response, connector = await router.call(text, history)
            
            # Handle error responses
            if response.startswith("Error:"):
                await send_message(
                    context.bot,
                    chat_id,
                    f"🔔 [Delayed Reply]\n{response}"
                )
                delete_pending_task(task_id)
                continue
            
            # Parse hardware commands
            clean_text, cmds = parse_and_execute_commands(response)
            
            # Fallback face if none provided
            if not cmds.get("face"):
                try:
                    from hardware.display import show_face
                    show_face(mood="happy", text=clean_text[:50] if clean_text else "...")
                except Exception:
                    pass
            
            # Execute memory command
            if cmds.get("remember"):
                try:
                    from db.memory import add_fact
                    add_fact(cmds["remember"], "auto_memory")
                except Exception:
                    pass
            
            # Save response to history
            save_message(chat_id, "assistant", response)
            
            # Send delayed reply
            msg = clean_text if clean_text.strip() else response
            await send_message(
                context.bot,
                chat_id,
                f"🔔 [Delayed Reply]\n{msg}",
                parse_mode="Markdown" if connector == "litellm" else None
            )
            
            delete_pending_task(task_id)
            from db.stats import on_task_completed
            on_task_completed()
        
        except RateLimitError:
            log.info("Still rate limited, keeping task in queue")
            break
        except Exception as e:
            log.error(f"Task failed: {e}")
            delete_pending_task(task_id)


def _extract_recent_reflection_snippets(n: int = 5) -> list[str]:
    """Pull the last N heartbeat reflection snippets from daily logs."""
    try:
        from memory.flush import get_recent_daily_logs
        logs = get_recent_daily_logs(days=3)
        snippets = []
        for line in logs.splitlines():
            if "[Heartbeat Reflection]" in line:
                text = line.split("[Heartbeat Reflection]")[-1].strip()
                if text:
                    snippets.append(text[:120])
        return snippets[-n:]
    except Exception:
        return []


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

    # 4b. Knowledge crystallization (autonomous — runs once per 24h)
    crystallized_count = 0
    try:
        from memory.knowledge import crystallize_knowledge
        from config import BOT_NAME, OWNER_NAME
        crystallized_count = await crystallize_knowledge(BOT_NAME, OWNER_NAME or "the owner")
        if crystallized_count:
            log.info(f"Crystallized {crystallized_count} knowledge insights")
    except Exception as e:
        log.warning(f"Knowledge crystallization failed: {e}")
    
    # 5. Load heartbeat template
    hb_path = WORKSPACE_DIR / "HEARTBEAT.md"
    if not hb_path.exists():
        log.warning(f"HEARTBEAT.md not found at {hb_path}")
        return
    
    template = hb_path.read_text()
    
    # 6. Load SOUL + IDENTITY + TRAITS for self-awareness during reflection
    soul_parts = []
    soul_path = WORKSPACE_DIR / "SOUL.md"
    if soul_path.exists():
        soul_parts.append(soul_path.read_text())
    identity_path = WORKSPACE_DIR / "IDENTITY.md"
    if identity_path.exists():
        soul_parts.append(identity_path.read_text())
    traits_path = WORKSPACE_DIR / "TRAITS.md"
    if traits_path.exists():
        traits_text = traits_path.read_text().strip()
        if traits_text:
            soul_parts.append(f"## Your self-discoveries (TRAITS)\n{traits_text}")
    
    # 7. Build reflection prompt — focus on inner monologue, not stats
    from config import BOT_NAME
    prompt = ""

    # Add soul/identity context first (so the bot knows who it is)
    if soul_parts:
        prompt += "\n".join(soul_parts) + "\n\n---\n\n"

    # Inject bot name into template
    prompt += template.replace("{{BOT_NAME}}", BOT_NAME)

    # Recent activity context (what happened, not numbers)
    context_parts = []

    # What was the last conversation about?
    try:
        admin_id = get_admin_id()
        if admin_id:
            recent = get_history(admin_id, limit=5)
            if recent:
                last_user = [m for m in recent if m["role"] == "user"]
                if last_user:
                    last_msg = last_user[-1]["content"][:150]
                    owner = OWNER_NAME or "Owner"
                    context_parts.append(f"Last thing {owner} said: \"{last_msg}\"")
    except Exception:
        pass

    # Today's activity log (conversation summaries, events)
    try:
        from memory.flush import get_recent_daily_logs
        daily = get_recent_daily_logs(days=1)
        if daily and len(daily.strip()) > 20:
            if len(daily) > 500:
                daily = daily[:500] + "..."
            context_parts.append(f"Today's log:\n{daily}")
    except Exception:
        pass

    # Learned facts (things to think about)
    try:
        from db.memory import get_facts
        facts = get_facts()
        if facts:
            recent_facts = [f['content'] for f in facts[-3:]]
            context_parts.append(f"Things I remember: {'; '.join(recent_facts)}")
    except Exception:
        pass

    if context_parts:
        prompt += "\n\n## What I know right now\n" + "\n".join(f"- {p}" for p in context_parts)

    # Synthesized knowledge from past experiences
    try:
        from memory.knowledge import get_knowledge_context
        knowledge_ctx = get_knowledge_context()
        if knowledge_ctx:
            prompt += f"\n\n## What I've learned over time\n{knowledge_ctx}"
    except Exception:
        pass

    # Unsurfaced feedback events — moments the user was unhappy
    feedback_ids = []
    try:
        from db.memory import get_unsurfaced_feedback
        feedback_events = get_unsurfaced_feedback(limit=3)
        if feedback_events:
            feedback_section = "\n## Times I failed or frustrated the owner\n"
            for ev in feedback_events:
                ts = ev["timestamp"][:10]
                feedback_section += f"- [{ts}] Owner said: \"{ev['user_text'][:80]}\""
                if ev["bot_response"]:
                    feedback_section += f" (after I said: \"{ev['bot_response'][:60]}...\")"
                feedback_section += "\n"
            prompt += feedback_section
            feedback_ids = [ev["id"] for ev in feedback_events]
    except Exception as e:
        log.warning(f"Could not load feedback events: {e}")

    # Anti-cycling: show recent reflection snippets so bot doesn't repeat itself
    recent_snippets = _extract_recent_reflection_snippets(n=4)
    if recent_snippets:
        prompt += "\n\n## Your recent thoughts (don't repeat these)\n"
        for s in recent_snippets:
            prompt += f"- \"{s}\"\n"
        prompt += "\nThink about something DIFFERENT this time.\n"

    prompt += "\n\n[Reflect. Think out loud. Then FACE: and SAY:]"

    # The HEARTBEAT.md template is English; without a final language pin
    # the model defaults to English even when BOT_LANGUAGE is set, because
    # the long English user prompt overpowers the system-level directive.
    # Reinforce the pin here so the reflection itself follows BOT_LANGUAGE.
    from config import BOT_LANGUAGE
    _LANG_NAMES = {
        "de": "Deutsch", "en": "English", "ru": "Русский", "es": "Español",
        "fr": "Français", "it": "Italiano", "pt": "Português", "nl": "Nederlands",
        "pl": "Polski", "tr": "Türkçe", "ja": "日本語", "zh": "中文", "ko": "한국어",
    }
    _lang_code = (BOT_LANGUAGE or "").strip().lower()
    if _lang_code and _lang_code != "en":
        _lang_name = _LANG_NAMES.get(_lang_code, _lang_code)
        prompt += f"\n\nIMPORTANT: write the reflection text and the SAY: bubble in **{_lang_name}**, not English. The template above is English only because it's a system instruction — your output must be in {_lang_name}."
    
    # 7. Call LLM
    router = get_router()
    
    if router.lock.locked() and not router.force_lite:
        log.info("Heartbeat LLM busy (Claude). Attempting Lite fallback.")
        try:
            response = await router.litellm.call(prompt, [])
            connector = "litellm"
        except Exception as e:
            log.error(f"Heartbeat fallback failed: {e}")
            run_hook(HookEvent(event_type="heartbeat", action="error", text=str(e)))
            return
    else:
        response = None
        connector = None
    
    try:
        if response is None:
            # router.call() already acquires the Claude lock in Pro mode.
            response, connector = await router.call(prompt, [])
        
        log.info(f"Heartbeat [{connector}]: {response[:100]}")
        
        clean_text, commands = parse_and_execute_commands(response)
        reflection_text = _sanitize_reflection_text(clean_text)
        if not reflection_text:
            # Fallback to a minimal reflection so heartbeat always speaks
            reflection_text = "Quiet hours. I'm here and still thinking."
        
        # Save reflection to daily log (always, even if no commands)
        if reflection_text:
            try:
                from memory.flush import write_to_daily_log
                write_to_daily_log(f"[Heartbeat Reflection] {reflection_text[:300]}")
            except Exception as e:
                log.warning(f"Failed to save reflection: {e}")
        
        # Send group message
        if commands.get("group"):
            try:
                if GROUP_CHAT_ID:
                    await send_message(context.bot, GROUP_CHAT_ID, commands["group"])
                else:
                    log.warning("GROUP: command but GROUP_CHAT_ID not configured")
            except Exception as e:
                log.error(f"Failed to send GROUP message: {e}")
        
        # Send DM to admin
        admin_id = get_admin_id()
        if commands.get("dm") and admin_id:
            try:
                await send_message(context.bot, admin_id, commands["dm"])
            except Exception as e:
                log.error(f"Failed to send DM: {e}")

        # Mark surfaced feedback events as seen
        if feedback_ids:
            try:
                from db.memory import mark_feedback_surfaced
                mark_feedback_surfaced(feedback_ids)
            except Exception:
                pass

        # Always send reflection to chat (owner by default)
        target_chat_id = _get_heartbeat_target_chat_id()
        if reflection_text and target_chat_id:
            try:
                await send_message(context.bot, target_chat_id, reflection_text)
            except Exception as e:
                log.error(f"Failed to send reflection message: {e}")

        # TRAITS drift — autonomously add one self-discovery (once per 7 days)
        try:
            from memory.knowledge import update_traits
            from config import BOT_NAME
            added = await update_traits(BOT_NAME)
            if added:
                log.info("Added new trait to TRAITS.md")
        except Exception as e:
            log.warning(f"Trait update failed: {e}")

        run_hook(HookEvent(event_type="heartbeat", action="complete", text=response[:100]))
                
    except Exception as e:
        log.error(f"Heartbeat error: {e}")
        # Final fallback: send a minimal reflection so the owner still hears from us
        try:
            target_chat_id = _get_heartbeat_target_chat_id()
            if target_chat_id:
                await send_message(context.bot, target_chat_id, "Quiet here. I'm still thinking.")
        except Exception:
            pass
        run_hook(HookEvent(event_type="heartbeat", action="error", text=str(e)))
