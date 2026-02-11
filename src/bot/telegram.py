"""
Telegram helpers — auth, message sending.
"""

import re
import logging
from telegram import Update
from telegram.error import BadRequest

from config import get_allowed_users, get_allowed_groups, TELEGRAM_MSG_LIMIT, ALLOW_ALL_USERS

log = logging.getLogger(__name__)


def sanitize_markdown(text: str) -> str:
    """Fix unclosed markdown that breaks Telegram parse."""
    # Fix unclosed code blocks
    if text.count("```") % 2 != 0:
        text += "\n```"
    # Fix unclosed inline code (outside of code blocks)
    temp = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    if temp.count("`") % 2 != 0:
        text += "`"
    # Fix unclosed bold
    if text.count("**") % 2 != 0:
        text += "**"
    # Fix unclosed italic (single underscore)
    # Count underscores not inside words
    underscore_count = len(re.findall(r"(?<![\w])_|_(?![\w])", text))
    if underscore_count % 2 != 0:
        text += "_"
    return text


def strip_markdown(text: str) -> str:
    """Remove markdown formatting entirely."""
    # Remove code blocks
    text = re.sub(r"```.*?```", lambda m: m.group(0).replace("```", ""), text, flags=re.DOTALL)
    # Remove inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Remove bold
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    # Remove italic
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    return text


def is_allowed(user_id: int, chat_id: int = None) -> bool:
    """Check if user/chat is authorized."""
    if chat_id:
        allowed_groups = get_allowed_groups()
        if allowed_groups and chat_id in allowed_groups:
            return True
    
    allowed_users = get_allowed_users()
    if not allowed_users:
        return bool(ALLOW_ALL_USERS)
    
    return user_id in allowed_users


def get_sender_name(user) -> str:
    """Get display name for user."""
    if user.username:
        return f"@{user.username}"
    return user.first_name or "Unknown"


async def send_long_message(
    update: Update, 
    text: str, 
    parse_mode: str = None
):
    """Send message, splitting if needed. Falls back to plain text on parse error."""
    if not text.strip():
        text = "✅"
    
    # Try with markdown first
    if parse_mode:
        text = sanitize_markdown(text)
    
    async def send_chunk(chunk: str, mode: str = None):
        try:
            await update.message.reply_text(chunk, parse_mode=mode)
            return True
        except BadRequest as e:
            if "parse entities" in str(e).lower() or "can't parse" in str(e).lower():
                log.warning(f"Markdown parse failed, falling back to plain text: {e}")
                # Fallback: strip markdown and send plain
                plain = strip_markdown(chunk)
                await update.message.reply_text(plain)
                return True
            raise
    
    if len(text) <= TELEGRAM_MSG_LIMIT:
        await send_chunk(text, parse_mode)
    else:
        for i in range(0, len(text), TELEGRAM_MSG_LIMIT):
            chunk = text[i:i + TELEGRAM_MSG_LIMIT]
            await send_chunk(chunk, parse_mode)


async def send_message(bot, chat_id: int, text: str, parse_mode: str = None):
    """Send message to a specific chat."""
    if not text.strip():
        return
    
    if parse_mode:
        text = sanitize_markdown(text)
    
    async def send_chunk(chunk: str, mode: str = None):
        try:
            await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=mode)
            return True
        except BadRequest as e:
            if "parse entities" in str(e).lower() or "can't parse" in str(e).lower():
                log.warning(f"Markdown parse failed, sending plain: {e}")
                plain = strip_markdown(chunk)
                await bot.send_message(chat_id=chat_id, text=plain)
                return True
            raise
    
    if len(text) <= TELEGRAM_MSG_LIMIT:
        await send_chunk(text, parse_mode)
    else:
        for i in range(0, len(text), TELEGRAM_MSG_LIMIT):
            chunk = text[i:i + TELEGRAM_MSG_LIMIT]
            await send_chunk(chunk, parse_mode)
