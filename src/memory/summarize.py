"""
Conversation summarization for context optimization.
Keeps last N messages verbatim, summarizes older ones.
"""

import logging
import re
from typing import List, Dict

log = logging.getLogger(__name__)

VERBATIM_COUNT = 20  # Keep last 20 messages as-is


def extract_key_info(content: str, role: str) -> str:
    """
    Extract key information from a message.
    Smarter than just truncating — looks for questions, commands, names.
    """
    content = content.strip()
    
    # User messages: look for questions or key requests
    if role == "user":
        # Check for question
        if "?" in content:
            # Extract the question part
            sentences = re.split(r'[.!]', content)
            for s in sentences:
                if "?" in s:
                    return s.strip()[:80]
        
        # Look for commands/requests (starts with verb)
        request_patterns = [
            r'^(show|tell|explain|help|find|search|do|make|create|add|remove|set)',
            r'^(what|how|why|when|where|who|can you)',
        ]
        for pattern in request_patterns:
            if re.match(pattern, content.lower()):
                return content[:80]
        
        # Fallback: first sentence or truncate
        first_sentence = content.split('.')[0]
        return first_sentence[:80] if len(first_sentence) > 80 else first_sentence
    
    # Bot messages: extract key actions or topics
    else:
        # Look for FACE/DISPLAY commands (skip them)
        lines = [l for l in content.split('\n') if not l.strip().upper().startswith(('FACE:', 'DISPLAY:', 'SAY:'))]
        clean_content = ' '.join(lines).strip()
        
        if not clean_content:
            return "(display update)"
        
        # First meaningful sentence
        first_sentence = clean_content.split('.')[0]
        return first_sentence[:60] + "..." if len(first_sentence) > 60 else first_sentence


def summarize_old_messages(messages: List[Dict]) -> str:
    """
    Create a brief summary of older messages.
    Extracts key topics and questions for context.
    """
    if not messages:
        return ""
    
    # Extract key content from each message
    summaries = []
    for msg in messages:
        content = msg.get("content", "")
        role = msg.get("role", "user")
        
        key_info = extract_key_info(content, role)
        if key_info and key_info != "(display update)":
            prefix = "User asked" if role == "user" else "Bot"
            summaries.append(f"{prefix}: {key_info}")
    
    if not summaries:
        return ""
    
    # Keep only most relevant (last 4 interactions max)
    summaries = summaries[-4:]
    
    return "[Earlier: " + " → ".join(summaries) + "]"


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
