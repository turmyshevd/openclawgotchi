"""
Conversation summarization for context optimization.
Keeps last N messages verbatim, summarizes older ones.
"""

import logging
from typing import List, Dict

log = logging.getLogger(__name__)

VERBATIM_COUNT = 5  # Keep last 5 messages as-is


def summarize_old_messages(messages: List[Dict]) -> str:
    """
    Create a brief summary of older messages.
    Simple extraction of key topics/questions.
    """
    if not messages:
        return ""
    
    # Extract key content
    topics = []
    for msg in messages:
        content = msg.get("content", "")[:100]  # First 100 chars
        role = msg.get("role", "user")
        if role == "user":
            # Likely a question or request
            topics.append(f"User: {content.strip()}")
        else:
            # Bot response - just note it happened
            if len(content) > 50:
                topics.append(f"Bot replied about: {content[:50].strip()}...")
    
    if not topics:
        return ""
    
    # Keep it brief
    summary = "[Earlier in conversation: " + "; ".join(topics[:3]) + "]"
    return summary


def optimize_history(history: List[Dict]) -> List[Dict]:
    """
    Optimize conversation history for context window.
    Returns: condensed history with summary + recent messages.
    """
    if len(history) <= VERBATIM_COUNT:
        return history
    
    # Split into old and recent
    old_messages = history[:-VERBATIM_COUNT]
    recent_messages = history[-VERBATIM_COUNT:]
    
    # Summarize old messages
    summary = summarize_old_messages(old_messages)
    
    if summary:
        # Insert summary as a system note at the start
        summary_msg = {
            "role": "system",
            "content": summary
        }
        return [summary_msg] + recent_messages
    
    return recent_messages
