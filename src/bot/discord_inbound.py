"""
Discord inbound adapter.

Keeps Discord transport separate from Telegram handlers while reusing the same
LLM, memory, voice transcription, and vision helpers.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Optional

from config import (
    ALLOW_ALL_USERS,
    DISCORD_ALLOWED_CHANNELS,
    DISCORD_BOT_TOKEN,
    DISCORD_MAX_ATTACHMENT_MB,
    DISCORD_RESPOND_TO_ALL,
    get_discord_allowed_channels,
    get_discord_allowed_users,
)
from db.memory import (
    add_fact,
    get_history,
    save_feedback_event,
    save_message,
    save_pending_task,
    save_user,
)
from hardware.display import error_screen, parse_and_execute_commands, show_face
from hooks.runner import HookEvent, run_hook
from llm.base import LLMError, RateLimitError
from llm.prompts import build_system_context, build_vault_context
from llm.router import get_router
from memory.flush import check_and_inject_flush
from memory.summarize import optimize_history
from memory.vault import classify_message_for_vault

from bot.handlers import (
    _is_negative_feedback,
    _should_enable_memo_mode,
    process_image_file,
    transcribe_voice,
)
from bot.onboarding import (
    check_onboarding_complete,
    complete_onboarding,
    get_bootstrap_prompt,
    needs_onboarding,
)

log = logging.getLogger(__name__)

DISCORD_MSG_LIMIT = 2000
_AUDIO_SUFFIXES = {".ogg", ".mp3", ".wav", ".m4a", ".webm", ".aac", ".flac"}


def _discord_conv_id(channel_id: int) -> int:
    """Namespace Discord channels away from Telegram chat IDs."""
    return -abs(int(channel_id))


def _sender_name(author) -> str:
    return f"@{author.name}" if getattr(author, "name", "") else str(author.id)


def _is_author_allowed(author_id: int, is_dm: bool) -> bool:
    allowed_users = get_discord_allowed_users()
    if allowed_users:
        return author_id in allowed_users
    if is_dm:
        return bool(ALLOW_ALL_USERS)
    return True


def _is_channel_allowed(channel_id: int, is_dm: bool) -> bool:
    if is_dm:
        return True
    allowed_channels = get_discord_allowed_channels()
    if not allowed_channels:
        return False
    return channel_id in allowed_channels


def _attachment_kind(attachment) -> str:
    content_type = (getattr(attachment, "content_type", "") or "").lower()
    suffix = Path(getattr(attachment, "filename", "") or "").suffix.lower()
    if content_type.startswith("image/"):
        return "image"
    if content_type.startswith("audio/") or suffix in _AUDIO_SUFFIXES:
        return "audio"
    # Treat other common text-based files as documents
    if content_type.startswith("text/") or suffix in {".md", ".txt", ".py", ".json", ".yaml", ".yml", ".js", ".ts"}:
        return "document"
    return ""


async def _send_long(message, text: str) -> None:
    text = (text or "").strip() or "Done."
    chunks = [text[i:i + DISCORD_MSG_LIMIT] for i in range(0, len(text), DISCORD_MSG_LIMIT)]
    for idx, chunk in enumerate(chunks):
        if idx == 0:
            await message.reply(chunk, mention_author=False)
        else:
            await message.channel.send(chunk)


async def _download_attachment(attachment) -> str:
    suffix = Path(getattr(attachment, "filename", "") or "attachment.bin").suffix or ".bin"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
    await attachment.save(tmp_path)
    return tmp_path


async def _handle_image_attachment(message, attachment, conv_id: int) -> None:
    tmp_path = ""
    try:
        tmp_path = await _download_attachment(attachment)
        summary = await process_image_file(
            local_file_path=tmp_path,
            caption=message.content or "",
            conv_id=conv_id,
            mime_type=attachment.content_type or "image/jpeg",
            source="discord",
        )
        await _send_long(message, summary)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


async def _transcribe_audio_attachment(attachment) -> str:
    tmp_path = ""
    try:
        tmp_path = await _download_attachment(attachment)
        return await transcribe_voice(tmp_path)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


async def _handle_text_message(message, user_text: str, *, is_dm: bool, should_respond: bool) -> None:
    conv_id = _discord_conv_id(message.channel.id)
    sender = _sender_name(message.author)

    run_hook(HookEvent(
        event_type="message",
        user_id=message.author.id,
        chat_id=conv_id,
        username=sender,
        text=user_text,
    ))

    if is_dm:
        save_message(conv_id, "user", user_text)
    else:
        save_message(conv_id, "user", f"[{sender}]: {user_text}")

    if _is_negative_feedback(user_text):
        try:
            recent = get_history(conv_id, limit=4)
            last_bot = next(
                (m["content"] for m in reversed(recent) if m["role"] == "assistant"),
                "",
            )
            save_feedback_event(conv_id, user_text, last_bot)
        except Exception as e:
            log.warning("Failed to save Discord feedback event: %s", e)

    if not should_respond:
        return

    save_user(message.author.id, message.author.name or "", message.author.display_name or "", "")

    history = get_history(conv_id)
    if history:
        history = history[:-1]

    onboarding_mode = needs_onboarding()
    memo_mode = False
    if not onboarding_mode:
        classification = await classify_message_for_vault(user_text, history)
        memo_mode = _should_enable_memo_mode(user_text, classification)

    flush_prompt = check_and_inject_flush(history)
    history = optimize_history(history)

    if onboarding_mode:
        user_text = get_bootstrap_prompt() + " [USER]: " + user_text
    if flush_prompt:
        user_text = user_text + flush_prompt

    system_prompt: Optional[str] = None
    if memo_mode:
        system_prompt = build_system_context(user_text) + "\n---\n" + build_vault_context() + "\n\n"
        system_prompt += (
            "## Memo Capture Directive\n"
            "Treat this Discord message as project knowledge unless it clearly becomes a command or question.\n"
            "If enough context is available, use vault_write to capture the note in markdown.\n"
            "If anything essential is unclear, ask one short clarifying question before writing.\n"
            "After capture, keep the reply brief and mention what was saved.\n"
        )

    transport_note = (
        "\n---\n## Discord Transport Note\n"
        "You are replying in Discord. Keep replies under Discord's message limits. "
        "Scheduled reminders currently deliver through Telegram/admin fallback, not Discord channels."
    )
    system_prompt = (system_prompt or build_system_context(user_text)) + transport_note

    try:
        async with message.channel.typing():
            log.info("[discord %s] -> %s", sender, user_text[:80])
            response, connector = await get_router().call(user_text, history, system_prompt=system_prompt)
            log.info("[discord %s] <- [%s] %s", sender, connector, response[:80])

        if response.startswith("Error:"):
            error_screen(response)
            await _send_long(message, response)
            return

        tool_footer = ""
        if "__TOOL_FOOTER__" in response:
            response, tool_footer = response.split("__TOOL_FOOTER__", 1)
            response = response.rstrip()
            tool_footer = tool_footer.strip()

        clean_text, cmds = parse_and_execute_commands(response)
        if not cmds.get("face"):
            show_face(mood="happy", text=clean_text[:50] if clean_text else "...")

        if cmds.get("remember"):
            add_fact(cmds["remember"], "auto_memory")

        save_message(conv_id, "assistant", response)

        if onboarding_mode and check_onboarding_complete(response):
            complete_onboarding()

        from audit_logging.command_logger import log_bot_response
        log_bot_response(conv_id, response, connector)

        if cmds.get("remember"):
            clean_text += f"\n\n```text\nremembered: {cmds['remember'][:80]}\n```"
        if connector != "litellm":
            clean_text += "\n\nPro"
        if tool_footer:
            clean_text += "\n\n" + tool_footer

        await _send_long(message, clean_text)

        from db.stats import on_message_answered, on_tool_use, on_knowledge_capture
        on_message_answered()
        tool_source = tool_footer or response
        tool_match = re.search(r"Tool usage \((\d+)\):", tool_source)
        if tool_match:
            on_tool_use(int(tool_match.group(1)))
        if memo_mode and "saved vault note" in tool_source.lower():
            on_knowledge_capture()
        elif cmds.get("remember"):
            on_tool_use(1)

    except RateLimitError:
        save_pending_task(conv_id, user_text, sender, not is_dm)
        await _send_long(message, "Rate limited. Queued for later.")
        error_screen("Rate Limit")
    except LLMError as e:
        log.error("Discord LLM error: %s", e)
        await _send_long(message, f"Error: {e}")
        error_screen(str(e))
    except Exception as e:
        log.exception("Unexpected Discord error")
        await _send_long(message, f"Error: {e}")
        error_screen(str(e))


def start_discord_bot_background() -> Optional[threading.Thread]:
    """Start Discord inbound bot in a background thread if configured."""
    if not DISCORD_BOT_TOKEN:
        return None

    try:
        import discord
    except ImportError:
        log.warning("DISCORD_BOT_TOKEN is set, but discord.py is not installed")
        return None

    intents = discord.Intents.default()
    intents.message_content = True
    intents.messages = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        channels = DISCORD_ALLOWED_CHANNELS or "(DMs only unless mentioned in allowed channels)"
        log.info("Discord inbound bot ready as %s; channels=%s", client.user, channels)

    @client.event
    async def on_message(message):
        if message.author.bot:
            return

        is_dm = isinstance(message.channel, discord.DMChannel)
        if not _is_author_allowed(message.author.id, is_dm):
            return
        if not _is_channel_allowed(message.channel.id, is_dm):
            return

        bot_mentioned = client.user in message.mentions
        should_respond = is_dm or DISCORD_RESPOND_TO_ALL or bot_mentioned
        user_text = (message.content or "").replace(f"<@{client.user.id}>", "").strip()
        user_text = user_text.replace(f"<@!{client.user.id}>", "").strip()

        max_attachment_bytes = DISCORD_MAX_ATTACHMENT_MB * 1024 * 1024
        audio_parts: list[str] = []

        for attachment in message.attachments:
            kind = _attachment_kind(attachment)
            if not kind:
                continue
            if attachment.size and attachment.size > max_attachment_bytes:
                if should_respond:
                    await _send_long(message, f"Attachment too large. Max: {DISCORD_MAX_ATTACHMENT_MB} MB.")
                continue
            if kind == "image":
                if should_respond:
                    await _handle_image_attachment(message, attachment, _discord_conv_id(message.channel.id))
                else:
                    save_message(_discord_conv_id(message.channel.id), "user", f"[{_sender_name(message.author)} sent an image]")
            elif kind == "audio":
                if not should_respond:
                    save_message(_discord_conv_id(message.channel.id), "user", f"[{_sender_name(message.author)} sent audio]")
                    continue
                transcript = await _transcribe_audio_attachment(attachment)
                if transcript.startswith("Error:"):
                    if should_respond:
                        await _send_long(message, transcript)
                    continue
                audio_parts.append(transcript)
            elif kind == "document":
                tmp_path = ""
                try:
                    tmp_path = await _download_attachment(attachment)
                    content = ""
                    try:
                        with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                    except Exception as e:
                        log.warning("Could not read Discord attachment %s as text: %s", attachment.filename, e)
                        continue
                    
                    if content:
                        filename = getattr(attachment, "filename", "document")
                        user_text = (user_text + "\n\n" if user_text else "") + f"[DOCUMENT ATTACHED: {filename}]\n\nFILE CONTENT:\n---\n{content}\n---\n"
                        if should_respond:
                            await message.reply(f"📄 *Received file:* `{filename}`", mention_author=False)
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        os.remove(tmp_path)

        if audio_parts:
            user_text = (user_text + "\n\n" if user_text else "") + "\n".join(
                f"[Voice transcript]: {part}" for part in audio_parts if part
            )

        if user_text:
            await _handle_text_message(message, user_text, is_dm=is_dm, should_respond=should_respond)

    def _run():
        try:
            client.run(DISCORD_BOT_TOKEN)
        except Exception:
            log.exception("Discord inbound bot stopped")

    thread = threading.Thread(target=_run, name="discord-inbound", daemon=True)
    thread.start()
    return thread
