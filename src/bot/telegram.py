"""
Telegram helpers — auth, message sending.
"""

from telegram import Update

from config import get_allowed_users, get_allowed_groups, TELEGRAM_MSG_LIMIT


def is_allowed(user_id: int, chat_id: int = None) -> bool:
    """Check if user/chat is authorized."""
    # Check group whitelist first
    if chat_id:
        allowed_groups = get_allowed_groups()
        if allowed_groups and chat_id in allowed_groups:
            return True
    
    # Check user whitelist
    allowed_users = get_allowed_users()
    if not allowed_users:
        return True  # No whitelist = allow all
    
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
    """Send message, splitting if needed for Telegram's 4096 limit."""
    if not text.strip():
        text = "✅"
    
    if len(text) <= TELEGRAM_MSG_LIMIT:
        await update.message.reply_text(text, parse_mode=parse_mode)
    else:
        # Split into chunks
        for i in range(0, len(text), TELEGRAM_MSG_LIMIT):
            chunk = text[i:i + TELEGRAM_MSG_LIMIT]
            await update.message.reply_text(chunk, parse_mode=parse_mode)


async def send_message(bot, chat_id: int, text: str, parse_mode: str = None):
    """Send message to a specific chat."""
    if not text.strip():
        return
    
    if len(text) <= TELEGRAM_MSG_LIMIT:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
    else:
        for i in range(0, len(text), TELEGRAM_MSG_LIMIT):
            chunk = text[i:i + TELEGRAM_MSG_LIMIT]
            await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=parse_mode)
