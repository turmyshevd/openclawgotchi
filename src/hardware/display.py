"""
E-Ink Display control — faces, text, command parsing.

UI script: config.UI_SCRIPT = src/ui/gotchi_ui.py (E-Ink, epd2in13_V4).
Do not use any gotchiui.py (no underscore) at project root — that is an old LCD (lcddriver) script.
"""

import subprocess
import logging
import re
import threading
import time

from config import UI_SCRIPT, PROJECT_DIR

log = logging.getLogger(__name__)

# E-Ink ghosting: every N-th update do full refresh so the panel actually redraws
_display_update_count = 0
FULL_REFRESH_EVERY = 3

# Only one UI script at a time — avoids "GPIO busy" from overlapping runs
_display_lock = threading.Lock()
_DISPLAY_TIMEOUT = 45  # seconds
_DISPLAY_BUSY_RETRY_WAIT = 4  # seconds before retry when display was busy


def _run_display_update(cmd: list):
    """Run UI script; hold lock so no overlapping runs. Retry once if busy."""
    if not _display_lock.acquire(blocking=False):
        log.warning("Display busy, will retry once in %ss", _DISPLAY_BUSY_RETRY_WAIT)
        time.sleep(_DISPLAY_BUSY_RETRY_WAIT)
        if not _display_lock.acquire(blocking=False):
            log.warning("Display still busy after retry, skipping")
            return
    try:
        subprocess.run(
            cmd,
            cwd=str(PROJECT_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=_DISPLAY_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        log.error("Display update timed out")
    except Exception as e:
        log.error(f"Display error: {e}")
    finally:
        _display_lock.release()


def update_display(mood: str = None, text: str = None, full_refresh: bool = False):
    """Update display with mood and/or text in a single call."""
    global _display_update_count
    if not mood and not text:
        return

    _display_update_count += 1
    if not full_refresh and _display_update_count % FULL_REFRESH_EVERY == 0:
        full_refresh = True  # Force full redraw periodically to avoid stuck E-Ink

    cmd = ["sudo", "python3", str(UI_SCRIPT)]
    if mood:
        cmd.extend(["--mood", mood])
    if text:
        cmd.extend(["--text", text])
    if full_refresh:
        cmd.append("--full")

    try:
        thread = threading.Thread(target=_run_display_update, args=(cmd,), daemon=True)
        thread.start()
        log.info(f"Display update: mood={mood}, text={text}")
    except Exception as e:
        log.error(f"Display error: {e}")


def show_face(mood: str, text: str = "", full_refresh: bool = False):
    """Display a face (and optional text) on E-Ink."""
    update_display(mood=mood, text=text, full_refresh=full_refresh)


def show_text(text: str):
    """Display text on E-Ink (status bar or speech bubble)."""
    update_display(text=text)


def parse_and_execute_commands(response: str) -> tuple[str, dict]:
    """
    Parse LLM response for hardware commands, execute them, return clean text.
    
    Returns:
        tuple: (clean_text, commands_dict)
        - clean_text: Response with FACE:/DISPLAY: lines removed
        - commands_dict: {"face": mood, "display": text, "dm": message, "group": message}
    """
    lines = response.strip().splitlines()
    clean_lines = []
    commands = {"face": None, "display": None, "dm": None, "group": None, "mail": None}
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        
        # FACE: <mood>
        if stripped.upper().startswith("FACE:"):
            mood = stripped[5:].strip().lower()
            commands["face"] = mood
            log.info(f"CMD FACE: {mood}")
        
        # DISPLAY: <text>
        elif stripped.upper().startswith("DISPLAY:"):
            text = stripped[8:].strip()
            commands["display"] = text
            log.info(f"CMD DISPLAY: {text}")
        
        # SAY: <text> (Direct speech bubble)
        elif stripped.upper().startswith("SAY:"):
            text = stripped[4:].strip()
            commands["display"] = f"SAY:{text}"
            log.info(f"CMD SAY: {text}")
        
        # DM: <message> — for heartbeat to send private message
        elif stripped.upper().startswith("DM:"):
            msg = stripped[3:].strip()
            commands["dm"] = msg
        
        # GROUP: <message> — for heartbeat to send group message
        elif stripped.upper().startswith("GROUP:"):
            msg = stripped[6:].strip()
            commands["group"] = msg
        
        # STATUS: OK — heartbeat acknowledgment, skip
        elif stripped.upper().startswith("STATUS:"):
            continue
        
        # REMEMBER: <fact> — for auto-saving memory
        elif stripped.upper().startswith("REMEMBER:"):
            fact = stripped[9:].strip()
            commands["remember"] = fact

        # MAIL: <message> — reply to brother
        elif stripped.upper().startswith("MAIL:"):
            msg = stripped[5:].strip()
            commands["mail"] = msg
            log.info(f"CMD MAIL: {msg[:50]}...")

        # Skip lone HTML-like tags (LLM sometimes outputs </...> before FACE:)
        elif re.match(r"^\s*</?\w+>\s*$", stripped):
            continue

        # Regular text — keep it
        else:
            clean_lines.append(stripped)
    
    # Execute batch update if needed
    if commands["face"] or commands["display"]:
        disp_text = commands["display"]
        update_display(mood=commands["face"], text=disp_text)
    
    clean_text = "\n".join(clean_lines)
    return clean_text, commands


def boot_screen():
    """Show boot screen."""
    update_display(mood="sleeping", text="Zzz...", full_refresh=True)


def online_screen():
    """Show online screen."""
    update_display(mood="happy", text="Online", full_refresh=True)

def error_screen(error_msg: str):
    """Show error screen with context-aware face and Japanese text."""
    err_lower = error_msg.lower()
    
    # Default
    mood = "dead"
    short_error = "Error"
    jp_msg = "システムエラー発生" # System Error Occurred
    
    # 1. Rate Limit / Quota
    if "ratelimit" in err_lower or "quota" in err_lower:
        mood = "dizzy"
        short_error = "Rate Limited" if "ratelimit" in err_lower else "Quota Full"
        jp_msg = "レート制限超過!" # Rate Limit Exceeded
        
    # 2. Network / Timeout
    elif "timeout" in err_lower or "connect" in err_lower:
        mood = "bored"
        short_error = "Timeout"
        jp_msg = "接続タイムアウト" # Connection Timeout
        
    # 3. Auth / Permission
    elif "auth" in err_lower or "permission" in err_lower or "denied" in err_lower:
        mood = "suspicious"
        short_error = "Access Denied"
        jp_msg = "アクセス拒否!" # Access Denied
        
    # 4. Parsing / Logic
    elif "parse" in err_lower or "syntax" in err_lower or "value" in err_lower:
        mood = "confused"
        short_error = "Bad Syntax"
        jp_msg = "構文エラー発生" # Syntax Error
        
    # 5. Generic LLM Error
    elif "llm" in err_lower:
        mood = "dizzy" 
        short_error = "Brain Freeze"
        jp_msg = "処理不能エラー" # Processing Failed

    # Fallback: try to extract short code
    if short_error == "Error":
        short_error = error_msg.split(':')[0] if ':' in error_msg else error_msg[:15]
        
    # Extract numeric code (e.g. 429)
    code_prefix = ""
    code_match = re.search(r'"code":\s*(\d+)', error_msg)
    if not code_match:
        code_match = re.search(r'status code:?\s*(\d+)', error_msg, re.IGNORECASE)
    
    if code_match:
         code_prefix = f"[{code_match.group(1)}] "
        
    update_display(mood=mood, text=f"SAY: {code_prefix}{jp_msg} | STATUS: ERR: {short_error}", full_refresh=True)
