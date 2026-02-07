"""
LiteLLM connector — full-featured fallback with tools.
"""

import contextvars
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

from config import PROJECT_DIR, WORKSPACE_DIR, ENABLE_LITELLM_TOOLS
from llm.base import LLMConnector, LLMError

log = logging.getLogger(__name__)

# Chat ID to use for one-shot cron reminders (per-task context, set by handler before LLM call)
_cron_target_chat_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "cron_target_chat_id", default=None
)


def set_cron_target_chat_id(chat_id: Optional[int]) -> None:
    """Set chat ID for next add_scheduled_task (so reminder goes to same chat)."""
    _cron_target_chat_id.set(chat_id)


def _get_cron_target_chat_id() -> Optional[int]:
    """Get chat ID for next add_scheduled_task (per-task context)."""
    return _cron_target_chat_id.get()


# Note: LiteLLM is imported lazily inside LiteLLMConnector.call to save RAM on Pi Zero 2W.
LITELLM_AVAILABLE = True # Assume available, will fail at runtime if not


# ============================================================
# SAFETY GUARDS
# ============================================================

# Dangerous bash commands (blocked)
DANGEROUS_COMMANDS = [
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "mkfs",
    "dd if=",
    "> /dev/sd",
    "chmod -R 777 /",
    ":(){ :|:& };:",  # Fork bomb
    "curl | bash",
    "wget | bash",
    "sudo rm -rf",
]

# Protected files (cannot be written/deleted)
PROTECTED_FILES = [
    ".env",
    "gotchi.db",
    "src/drivers/",  # Hardware drivers
    "src/ui/",       # E-Ink UI (critical display stack)
    "src/ui/gotchi_ui.py",
]

# Max file size for write (100KB)
MAX_WRITE_SIZE = 100 * 1024


def _is_dangerous_command(cmd: str) -> bool:
    """Check if command is dangerous."""
    cmd_lower = cmd.lower().strip()
    for danger in DANGEROUS_COMMANDS:
        if danger.lower() in cmd_lower:
            return True
    return False


def _is_protected_path(path: Path) -> bool:
    """Check if path is protected from writes."""
    path_str = str(path)
    for protected in PROTECTED_FILES:
        if protected in path_str:
            return True
    return False


def _sanitize_string(s: str, max_len: int = 10000) -> str:
    """Sanitize and limit string length."""
    if s is None:
        return ""
    return str(s)[:max_len]


# ============================================================
# TOOLS
# ============================================================

def execute_bash(command: str, timeout: int = 120) -> str:
    """Execute a shell command."""
    # Validate
    if not command or not command.strip():
        return "Error: Empty command"
    
    command = _sanitize_string(command, 1000)
    
    # Safety check
    if _is_dangerous_command(command):
        log.warning(f"Blocked dangerous command: {command[:50]}")
        return "Error: Command blocked for safety. Use safer alternatives."
    
    # Limit timeout
    timeout = min(timeout, 300)  # Max 5 minutes
    
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=str(PROJECT_DIR)
        )
        output = ""
        if result.stdout.strip():
            output += result.stdout.strip() + "\n"
        if result.stderr.strip():
            output += f"[stderr] {result.stderr.strip()}\n"
        if not output:
            output = "(no output)"
        return output[:4000]
    except subprocess.TimeoutExpired:
        return f"Timeout after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


def read_file(path: str) -> str:
    """Read a file."""
    if not path or not path.strip():
        return "Error: Empty path"
    
    try:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = PROJECT_DIR / p
        p = p.resolve()
        
        if not p.exists():
            return f"File not found: {path}"
        if p.stat().st_size > 100 * 1024:
            return "File too large (>100KB). Read in chunks or use execute_bash with head/tail."
        
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"Error: {e}"


def write_file(path: str, content: str) -> str:
    """Write to a file (with backup)."""
    if not path or not path.strip():
        return "Error: Empty path"
    if content is None:
        return "Error: Content is None"
    
    # Limit content size
    if len(content) > MAX_WRITE_SIZE:
        return f"Error: Content too large ({len(content)} bytes). Max is {MAX_WRITE_SIZE}."
    
    try:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = PROJECT_DIR / p
        p = p.resolve()
        
        # Safety check
        if _is_protected_path(p):
            return f"Error: Cannot write to protected file: {path}"
        
        p.parent.mkdir(parents=True, exist_ok=True)
        
        # Backup existing file
        if p.exists():
            import shutil
            backup_path = p.with_suffix(p.suffix + ".bak")
            shutil.copy2(p, backup_path)
            log.info(f"Backup created: {backup_path}")
        
        p.write_text(content, encoding="utf-8")
        return f"✓ Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"


def list_directory(path: str = ".") -> str:
    """List directory contents."""
    try:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = PROJECT_DIR / p
        p = p.resolve()
        
        if not p.exists():
            return f"Not found: {path}"
        if not p.is_dir():
            return f"Not a directory: {path}"
        
        items = []
        for item in sorted(p.iterdir()):
            suffix = "/" if item.is_dir() else ""
            items.append(f"  {item.name}{suffix}")
        
        return f"{p}/\n" + "\n".join(items) if items else f"{p}/ (empty)"
    except Exception as e:
        return f"Error: {e}"


def _get_all_moods() -> list[str]:
    """Get all available moods (default + custom)."""
    try:
        from ui.gotchi_ui import _load_all_faces
        faces = _load_all_faces()
        return sorted(faces.keys())
    except Exception:
        # Fallback to hardcoded list if import fails
        return ["happy", "sad", "excited", "thinking", "love", "surprised", 
                "bored", "sleeping", "hacker", "angry", "crying", "proud", 
                "nervous", "confused", "mischievous", "cool", "wink", "dead", 
                "shock", "suspicious", "smug", "cheering", "celebrate"]


def show_face(mood: str, text: str = "") -> str:
    """Display face on E-Ink — delegates to hardware/display.py."""
    if not mood:
        return "Error: mood is required"
    
    mood = mood.lower().strip()
    valid_moods = _get_all_moods()
    
    if mood not in valid_moods:
        return f"Error: Unknown mood '{mood}'. Valid moods: {', '.join(valid_moods[:10])}... (total: {len(valid_moods)})"
    
    # Limit text length
    text = _sanitize_string(text, 60)
    
    try:
        from hardware.display import show_face as _show_face
        _show_face(mood, text, full_refresh=True)
        return f"✓ Displayed: {mood}" + (f" '{text}'" if text else "")
    except Exception as e:
        return f"Error: {e}"


# Standard faces that cannot be overridden/replaced (from gotchi_ui.py)
STANDARD_FACES = [
    "happy", "happy2", "sad", "excited", "thinking", "love", "surprised", "grateful",
    "motivated", "bored", "sleeping", "sleeping_pwn", "awakening", "observing",
    "intense", "cool", "chill", "hype", "hacker", "smart", "broken", "debug",
    "angry", "crying", "proud", "nervous", "confused", "mischievous", "wink",
    "dead", "shock", "suspicious", "smug", "cheering", "celebrate", "dizzy",
    "lonely", "demotivated"
]

def add_custom_face(name: str, kaomoji: str) -> str:
    """
    Add a custom face/mood to the collection. Bot can add its own faces!
    name: mood name (lowercase, no spaces, e.g. "zen", "determined")
    kaomoji: Unicode kaomoji string (e.g. "(◕‿◕)", "(⌐■_■)", "(°▃▃°)")
    """
    if not name or not kaomoji:
        return "Error: name and kaomoji required"
    
    name = name.lower().strip().replace(" ", "_").replace("-", "_")
    
    # Validate kaomoji is reasonable length
    if len(kaomoji) > 20:
        return f"Error: kaomoji too long ({len(kaomoji)} chars). Max 20."
        
    # Check if this name is a standard face
    if name in STANDARD_FACES:
        return f"Error: '{name}' is a standard system face. Please pick a new unique name for your custom face."
    
    try:
        from config import CUSTOM_FACES_PATH, DATA_DIR
        import json
        
        # Ensure data/ exists
        DATA_DIR.mkdir(exist_ok=True)
        
        # Load existing custom faces
        custom_faces = {}
        if CUSTOM_FACES_PATH.exists():
            try:
                custom_faces = json.loads(CUSTOM_FACES_PATH.read_text())
            except Exception:
                pass
        
        # 1. Check if name already exists in custom
        if name in custom_faces:
             current = custom_faces[name]
             if current == kaomoji:
                 return f"Note: Custom face '{name}' already exists with this exact kaomoji {kaomoji}. No changes needed."
             return f"Error: Custom face '{name}' already exists with a different kaomoji: {current}. If you want to change it, first explain why, or use a new name."

        # 2. Check if this exact kaomoji already exists under another name
        for existing_name, existing_kaomoji in custom_faces.items():
            if existing_kaomoji == kaomoji:
                return f"Error: This kaomoji {kaomoji} is already registered as '{existing_name}'. Please use the existing name instead of creating a duplicate."

        # Add new face
        custom_faces[name] = kaomoji
        
        # Save
        CUSTOM_FACES_PATH.write_text(json.dumps(custom_faces, indent=2, ensure_ascii=False))
        
        return f"✓ Added custom face '{name}': {kaomoji}. Now you can use FACE: {name} in your replies."
    except Exception as e:
        return f"Error: {e}"


def remember_fact(category: str, fact: str) -> str:
    """Save to long-term memory — delegates to db/memory.py."""
    if not category or not fact:
        return "Error: Both category and fact are required"
    
    # Sanitize
    category = _sanitize_string(category, 50)
    fact = _sanitize_string(fact, 500)
    
    try:
        from db.memory import add_fact
        add_fact(fact, category)
        return f"✓ Remembered [{category}]: {fact}"
    except Exception as e:
        return f"Error: {e}"


def recall_facts(query: str = "", limit: int = 10) -> str:
    """Search long-term memory — delegates to db/memory.py."""
    try:
        from db.memory import search_facts, get_recent_facts
        
        if query:
            facts = search_facts(query, limit)
        else:
            facts = get_recent_facts(limit)
        
        if not facts:
            return "No facts found"
        
        result = []
        for f in facts:
            date = f['timestamp'].split("T")[0] if f.get('timestamp') else "?"
            result.append(f"[{f['category']}] {f['content']} ({date})")
        return "\n".join(result)
    except Exception as e:
        return f"Error: {e}"


def read_skill(skill_name: str) -> str:
    """Read a skill's SKILL.md (works for both gotchi-skills and openclaw-skills)."""
    from skills.loader import get_skill_content
    return get_skill_content(skill_name)


def search_skills(query: str) -> str:
    """
    Search the skill catalog for capabilities.
    Use this to find skills for tasks you can't do with current tools.
    
    Example queries: "weather", "email", "notes", "music", "calendar"
    """
    from skills.loader import search_skill_catalog
    return search_skill_catalog(query)


def list_skills() -> str:
    """List all available skill names (both active and reference)."""
    from skills.loader import list_all_skill_names, get_eligible_skills
    
    active = get_eligible_skills()
    active_names = {s.name for s in active}
    all_names = list_all_skill_names()
    
    result = ["## Active Skills (loaded in context)"]
    for s in active:
        result.append(f"- {s.emoji} {s.name}: {s.description}")
    
    result.append("\n## Reference Skills (openclaw-skills/ — may need macOS)")
    reference = [n for n in all_names if n not in active_names]
    result.append(f"Total: {len(reference)} skills")
    result.append("Use search_skills('query') to find specific capabilities.")
    result.append("Use read_skill('name') to read full documentation.")
    
    return "\n".join(result)


def restart_self() -> str:
    """Restart the bot service (with 3s delay to send response)."""
    try:
        subprocess.Popen(
            "nohup sh -c 'sleep 3 && sudo systemctl restart gotchi-bot' > /dev/null 2>&1 &",
            shell=True
        )
        return "Restarting in 3s... I'll be back!"
    except Exception as e:
        return f"Error: {e}"


def check_syntax(file_path: str) -> str:
    """Check Python file syntax before restart. ALWAYS use this after modifying code!"""
    try:
        p = Path(file_path).expanduser()
        if not p.is_absolute():
            p = PROJECT_DIR / p
        
        if not p.exists():
            return f"File not found: {file_path}"
        
        if not p.suffix == ".py":
            return f"Not a Python file: {file_path}"
        
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(p)],
            capture_output=True, text=True, timeout=10
        )
        
        if result.returncode == 0:
            return f"✓ Syntax OK: {file_path}"
        else:
            return f"✗ Syntax ERROR in {file_path}:\n{result.stderr}"
    except Exception as e:
        return f"Error: {e}"


def safe_restart() -> str:
    """
    Check all critical files syntax, then restart if OK.
    Use this after code modifications!
    """
    critical_files = [
        "src/main.py",
        "src/bot/handlers.py",
        "src/llm/litellm_connector.py",
        "src/llm/router.py",
    ]
    
    errors = []
    for f in critical_files:
        result = check_syntax(f)
        if "ERROR" in result:
            errors.append(result)
    
    if errors:
        return "❌ Cannot restart — syntax errors:\n\n" + "\n".join(errors)
    
    # All good, restart
    return restart_self()


def write_daily_log(entry: str) -> str:
    """Write to today's daily log — delegates to memory/flush.py."""
    try:
        from memory.flush import write_to_daily_log
        write_to_daily_log(entry)
        return f"Logged to daily log"
    except Exception as e:
        return f"Error: {e}"


def recall_messages(limit: int = 20) -> str:
    """
    Look back at recent conversation messages from the database.
    Use when you need to recall what was discussed recently.
    Returns the last N messages (user + assistant) for the current chat.
    """
    try:
        from db.memory import get_history
        from config import get_admin_id
        
        # Use admin chat as default (most common case)
        chat_id = get_admin_id() or 0
        history = get_history(chat_id, limit=min(limit, 50))
        
        if not history:
            return "No messages found in history."
        
        lines = [f"Last {len(history)} messages:"]
        for msg in history:
            role = "👤 User" if msg["role"] == "user" else "🤖 Bot"
            content = msg["content"][:200]
            lines.append(f"{role}: {content}")
        
        return "\n".join(lines)
    except Exception as e:
        return f"Error reading messages: {e}"


def add_scheduled_task(name: str, interval_minutes: int = 0, run_in_minutes: int = 0, run_in_seconds: int = 0, message: str = "") -> str:
    """Add a scheduled/cron task. Use run_in_seconds for short delays (e.g. 15), run_in_minutes for minutes."""
    try:
        from cron.scheduler import add_cron_job
        target_chat = _get_cron_target_chat_id() or 0
        
        if run_in_seconds > 0:
            job = add_cron_job(
                name=name,
                message=message,
                run_at=f"{run_in_seconds}s",
                delete_after_run=True,
                target_chat_id=target_chat
            )
            return f"One-shot task added: '{name}' in {run_in_seconds}s (ID: {job.id}). To remove: remove_scheduled_task(job_id='{job.id}')"
        if run_in_minutes > 0:
            # One-shot (minutes; supports float e.g. 0.25 = 15 sec)
            job = add_cron_job(
                name=name,
                message=message,
                run_at=f"{run_in_minutes}m",
                delete_after_run=True,
                target_chat_id=target_chat
            )
            return f"One-shot task added: '{name}' in {run_in_minutes}m (ID: {job.id}). To remove: remove_scheduled_task(job_id='{job.id}')"
        elif interval_minutes > 0:
            # Recurring
            job = add_cron_job(
                name=name,
                message=message,
                interval_minutes=interval_minutes
            )
            return f"Recurring task added: '{name}' every {interval_minutes}m (ID: {job.id}). To remove: remove_scheduled_task(job_id='{job.id}')"
        else:
            return "Error: specify run_in_seconds (e.g. 15), run_in_minutes (e.g. 1 or 0.25), or interval_minutes (recurring)"
    except Exception as e:
        return f"Error: {e}"


def list_scheduled_tasks() -> str:
    """List all scheduled tasks. Use job_id or task name with remove_scheduled_task to remove."""
    try:
        from cron.scheduler import list_cron_jobs
        jobs = list_cron_jobs()
        
        if not jobs:
            return "Scheduled tasks (0). No tasks in scheduler. Add with add_scheduled_task(interval_minutes=... or run_in_minutes=...)."
        
        lines = [f"Scheduled tasks ({len(jobs)}):"]
        for job in jobs:
            status = "✓" if job.enabled else "✗"
            if job.interval_minutes:
                schedule = f"every {job.interval_minutes}m"
            elif job.run_at:
                schedule = f"at {job.run_at[:16]}"
            else:
                schedule = "?"
            # job_id first so bot/user can copy; name also works for remove_scheduled_task
            lines.append(f"  job_id='{job.id}' | {status} {job.name} | {schedule} | runs: {job.run_count}")
        lines.append("Remove: remove_scheduled_task(job_id='<id>') or remove_scheduled_task(job_id='<name>').")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def remove_scheduled_task(job_id: str) -> str:
    """Remove a scheduled task by ID."""
    try:
        from cron.scheduler import remove_cron_job
        if remove_cron_job(job_id):
            return f"Removed task: {job_id}"
        return f"Task not found: {job_id}"
    except Exception as e:
        return f"Error: {e}"


def health_check() -> str:
    """
    Run system health check. Use this to diagnose problems!
    Checks: internet, disk, temp, service status, recent errors.
    """
    try:
        result = subprocess.run(
            ["python3", str(PROJECT_DIR / "src" / "utils" / "doctor.py")],
            capture_output=True, text=True, timeout=30
        )
        return result.stdout + (f"\n{result.stderr}" if result.stderr else "")
    except Exception as e:
        return f"Error running health check: {e}"


# Max lines to keep in ERROR_LOG.md so we don't fill disk on Pi
ERROR_LOG_MAX_LINES = 300


def log_error(message: str) -> str:
    """
    Append a critical error to data/ERROR_LOG.md (timestamped).
    Use when: display failed, service down, health_check found problems, restart failed, or user reports something broken.
    Keeps only last ERROR_LOG_MAX_LINES so disk doesn't fill. You can read_file('data/ERROR_LOG.md') to see recent errors.
    """
    if not message or not message.strip():
        return "Error: message required"
    try:
        from datetime import datetime
        from config import DATA_DIR
        log_path = DATA_DIR / "ERROR_LOG.md"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        line = f"[{datetime.now().isoformat()}] ERROR: {message.strip()}\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
        # Trim to last N lines so log doesn't grow unbounded on Pi
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > ERROR_LOG_MAX_LINES:
            with open(log_path, "w", encoding="utf-8") as f:
                f.writelines(lines[-ERROR_LOG_MAX_LINES:])
        return f"Logged to {log_path.name}"
    except Exception as e:
        return f"Error writing log: {e}"


def check_mail() -> str:
    """
    Check unread mail from sibling/brother bot. Use when user asks to check mail or messages from brother.
    Mail is stored in the same DB as the bot (gotchi.db, table bot_mail). Returns list of unread or 'No unread mail'.
    """
    try:
        from bot.heartbeat import get_unread_mail
        mail = get_unread_mail()
        if not mail:
            return "No unread mail from brother."
        lines = [f"From {m['from']} ({m['timestamp']}): {m['message']}" for m in mail]
        return "\n".join(lines)
    except Exception as e:
        return f"Error checking mail: {e}"


def restore_from_backup(file_path: str) -> str:
    """
    Restore a file from its .bak backup.
    Use this if you broke something!
    """
    if not file_path:
        return "Error: file_path required"
    
    try:
        p = Path(file_path).expanduser()
        if not p.is_absolute():
            p = PROJECT_DIR / p
        p = p.resolve()
        
        backup = p.with_suffix(p.suffix + ".bak")
        
        if not backup.exists():
            return f"No backup found: {backup}"
        
        import shutil
        shutil.copy2(backup, p)
        return f"✓ Restored {file_path} from backup"
    except Exception as e:
        return f"Error: {e}"


def log_change(description: str) -> str:
    """
    Log a change to .workspace/CHANGELOG.md.
    Use this EVERY TIME you modify code, config, or workspace files.
    Keeps a running record of self-modifications.
    """
    if not description:
        return "Error: description required"
    
    try:
        from datetime import datetime
        changelog_path = WORKSPACE_DIR / "CHANGELOG.md"
        
        today = datetime.now().strftime("%Y-%m-%d")
        time_str = datetime.now().strftime("%H:%M")
        entry = f"- [{time_str}] {description}"
        
        if changelog_path.exists():
            content = changelog_path.read_text()
            # Check if today's section exists
            if f"## {today}" in content:
                # Append to today's section
                content = content.replace(
                    f"## {today}",
                    f"## {today}\n{entry}",
                    1
                )
            else:
                # Add new day section at top (after header)
                lines = content.split("\n")
                header_end = 0
                for i, line in enumerate(lines):
                    if line.startswith("## "):
                        header_end = i
                        break
                else:
                    header_end = min(3, len(lines))
                
                lines.insert(header_end, f"\n## {today}\n{entry}\n")
                content = "\n".join(lines)
        else:
            content = f"# Changelog\n\nAll notable self-modifications.\n\n## {today}\n{entry}\n"
        
        changelog_path.write_text(content)
        return f"Logged: {description}"
    except Exception as e:
        return f"Error: {e}"


def git_command(command: str) -> str:
    """
    Run a git command in the project repository.
    Use for: status, log, diff, add, commit, branch, stash, etc.
    The repo is at the project root directory.
    
    Examples:
        git_command("status")
        git_command("log --oneline -10")
        git_command("add -A")
        git_command("commit -m 'fix: heartbeat reflection'")
        git_command("diff --stat")
    """
    if not command or not command.strip():
        return "Error: command required (e.g. 'status', 'log --oneline -5')"
    
    command = command.strip()
    
    # Block destructive remote operations
    blocked = ["push --force", "push -f", "reset --hard HEAD~", "clean -fd"]
    for b in blocked:
        if b in command:
            return f"Error: '{b}' is blocked for safety. Ask the owner."
    
    full_cmd = f"git {command}"
    
    try:
        result = subprocess.run(
            full_cmd, shell=True, capture_output=True, text=True,
            timeout=30, cwd=str(PROJECT_DIR)
        )
        output = ""
        if result.stdout.strip():
            output += result.stdout.strip()
        if result.stderr.strip():
            output += f"\n[stderr] {result.stderr.strip()}"
        return (output or "(no output)")[:4000]
    except subprocess.TimeoutExpired:
        return "Error: git command timed out"
    except Exception as e:
        return f"Error: {e}"


def manage_service(service: str, action: str = "status") -> str:
    """
    Manage a systemd service safely. 
    Actions: status, restart, stop, start, logs.
    Default service: gotchi-bot.
    """
    allowed_services = ["gotchi-bot", "ssh", "networking", "cron"]
    allowed_actions = ["status", "restart", "stop", "start", "logs"]
    
    service = service.strip()
    action = action.strip().lower()
    
    if service not in allowed_services:
        return f"Error: Service '{service}' not allowed. Allowed: {', '.join(allowed_services)}"
    
    if action not in allowed_actions:
        return f"Error: Action '{action}' not allowed. Allowed: {', '.join(allowed_actions)}"
    
    try:
        if action == "logs":
            cmd = f"journalctl -u {service} -n 30 --no-pager"
        else:
            cmd = f"sudo systemctl {action} {service}"
        
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=15
        )
        output = (result.stdout + result.stderr).strip()
        return output or f"Service {service}: {action} done"
    except Exception as e:
        return f"Error: {e}"


# Tool definitions
TOOLS = [
    {"type": "function", "function": {
        "name": "execute_bash",
        "description": "Run a shell command",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "integer"}
        }, "required": ["command"]}
    }},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a file",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}
        }, "required": ["path"]}
    }},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Write to a file (creates backup)",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"}
        }, "required": ["path", "content"]}
    }},
    {"type": "function", "function": {
        "name": "list_directory",
        "description": "List directory contents",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}
        }, "required": []}
    }},
    {"type": "function", "function": {
        "name": "remember_fact",
        "description": "Save to long-term memory",
        "parameters": {"type": "object", "properties": {
            "category": {"type": "string"},
            "fact": {"type": "string"}
        }, "required": ["category", "fact"]}
    }},
    {"type": "function", "function": {
        "name": "recall_facts",
        "description": "Search long-term memory",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"}
        }, "required": []}
    }},
    {"type": "function", "function": {
        "name": "recall_messages",
        "description": "Look back at recent chat messages from the database. Use to recall what was discussed recently.",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "Number of messages to retrieve (default 20, max 50)"}
        }, "required": []}
    }},
    {"type": "function", "function": {
        "name": "read_skill",
        "description": "Read skill documentation. Key skills: 'coding' (project map, self-modification), 'display' (E-Ink faces). Also works for openclaw-skills/ reference docs.",
        "parameters": {"type": "object", "properties": {
            "skill_name": {"type": "string", "description": "Skill name: 'coding', 'display', 'weather', 'github', etc."}
        }, "required": ["skill_name"]}
    }},
    {"type": "function", "function": {
        "name": "search_skills",
        "description": "Search the skill catalog for capabilities. Use this to find skills for tasks you can't do yet. Returns matching skills from openclaw-skills/ (may need macOS).",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search term: 'weather', 'email', 'calendar', 'music', etc."}
        }, "required": ["query"]}
    }},
    {"type": "function", "function": {
        "name": "list_skills",
        "description": "List all available skills — both active (in context) and reference (openclaw-skills/).",
        "parameters": {"type": "object", "properties": {}}
    }},
    {"type": "function", "function": {
        "name": "write_daily_log",
        "description": "Add entry to today's log",
        "parameters": {"type": "object", "properties": {
            "entry": {"type": "string"}
        }, "required": ["entry"]}
    }},
    {"type": "function", "function": {
        "name": "restart_self",
        "description": "Restart the bot service (3s delay). Use safe_restart() instead if you modified code!",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }},
    {"type": "function", "function": {
        "name": "check_syntax",
        "description": "Check Python file syntax. ALWAYS use after modifying .py files!",
        "parameters": {"type": "object", "properties": {
            "file_path": {"type": "string", "description": "Path to .py file"}
        }, "required": ["file_path"]}
    }},
    {"type": "function", "function": {
        "name": "safe_restart",
        "description": "Check syntax of critical files, then restart if OK. USE THIS after code changes!",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }},
    {"type": "function", "function": {
        "name": "add_scheduled_task",
        "description": "Add a scheduled task. Use run_in_seconds for short delay (e.g. 15), run_in_minutes for minutes, interval_minutes for recurring.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Task name"},
            "interval_minutes": {"type": "integer", "description": "Run every N minutes (recurring)"},
            "run_in_minutes": {"type": "number", "description": "Run once in N minutes (one-shot). Can use 0.25 for 15 sec."},
            "run_in_seconds": {"type": "integer", "description": "Run once in N seconds (one-shot). Use this for 15, 30, etc."},
            "message": {"type": "string", "description": "What to do when task runs"}
        }, "required": ["name"]}
    }},
    {"type": "function", "function": {
        "name": "list_scheduled_tasks",
        "description": "List all scheduled/cron tasks",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }},
    {"type": "function", "function": {
        "name": "remove_scheduled_task",
        "description": "Remove a scheduled task. Use job_id (first column in list_scheduled_tasks) or the task name (e.g. 'heartbeat-every-5m').",
        "parameters": {"type": "object", "properties": {
            "job_id": {"type": "string", "description": "Task ID (e.g. 'a1b2c3d4') or task name (e.g. 'heartbeat-every-5m') from list_scheduled_tasks"}
        }, "required": ["job_id"]}
    }},
    {"type": "function", "function": {
        "name": "health_check",
        "description": "Run system health check. Use to diagnose problems! Checks internet, disk, temp, service, errors.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }},
    {"type": "function", "function": {
        "name": "log_error",
        "description": "Append a critical error to data/ERROR_LOG.md (timestamped). Use when: display failed, service down, health_check found problems, restart failed, or user reports something broken. Then you can read_file('data/ERROR_LOG.md') later to see what went wrong.",
        "parameters": {"type": "object", "properties": {
            "message": {"type": "string", "description": "Short description of what failed (e.g. 'Display GPIO busy', 'health_check: disk >90%')"}
        }, "required": ["message"]}
    }},
    {"type": "function", "function": {
        "name": "restore_from_backup",
        "description": "Restore a file from .bak backup. Use if you broke something!",
        "parameters": {"type": "object", "properties": {
            "file_path": {"type": "string", "description": "Path to file to restore"}
        }, "required": ["file_path"]}
    }},
    {"type": "function", "function": {
        "name": "check_mail",
        "description": "Check unread mail from sibling/brother bot. Use when user asks to check mail, check mail from brother, or check messages. Mail is in the same DB as the bot (gotchi.db). Do NOT invent paths like probro.db.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }},
    {"type": "function", "function": {
        "name": "add_custom_face",
        "description": "Add a custom face to data/custom_faces.json. After adding, the face becomes available immediately. ALWAYS output FACE: <name> and SAY: <short text> in your FINAL reply to the user so they see the new face on the E-Ink display.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Mood name (lowercase, no spaces, e.g. 'zen', 'determined', 'focused')"},
            "kaomoji": {"type": "string", "description": "Unicode kaomoji string (max 20 chars, e.g. '(◕‿◕)', '(⌐■_■)', '(°▃▃°)')"}
        }, "required": ["name", "kaomoji"]}
    }},
    {"type": "function", "function": {
        "name": "log_change",
        "description": "Log a change to CHANGELOG.md. Use EVERY TIME you modify code, config, or workspace files. Keeps a running record of all self-modifications.",
        "parameters": {"type": "object", "properties": {
            "description": {"type": "string", "description": "What was changed (e.g. 'Added /ping command to handlers.py', 'Updated SOUL.md with new personality trait')"}
        }, "required": ["description"]}
    }},
    {"type": "function", "function": {
        "name": "git_command",
        "description": "Run a git command in the project repo. Use for: status, log, diff, add, commit, branch, stash. Always commit after making code changes.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "Git command without 'git' prefix (e.g. 'status', 'log --oneline -5', 'add -A', 'commit -m \"fix: typo\"')"}
        }, "required": ["command"]}
    }},
    {"type": "function", "function": {
        "name": "manage_service",
        "description": "Manage systemd services (gotchi-bot, ssh, networking, cron). Actions: status, restart, stop, start, logs.",
        "parameters": {"type": "object", "properties": {
            "service": {"type": "string", "description": "Service name (default: gotchi-bot)"},
            "action": {"type": "string", "description": "Action: status, restart, stop, start, logs"}
        }, "required": ["service"]}
    }}
]

TOOL_MAP = {
    "execute_bash": execute_bash,
    "read_file": read_file,
    "write_file": write_file,
    "list_directory": list_directory,
    "remember_fact": remember_fact,
    "recall_facts": recall_facts,
    "recall_messages": recall_messages,
    "add_custom_face": add_custom_face,
    "read_skill": read_skill,
    "search_skills": search_skills,
    "list_skills": list_skills,
    "write_daily_log": write_daily_log,
    "log_change": log_change,
    "git_command": git_command,
    "restart_self": restart_self,
    "check_syntax": check_syntax,
    "safe_restart": safe_restart,
    "manage_service": manage_service,
    "add_scheduled_task": add_scheduled_task,
    "list_scheduled_tasks": list_scheduled_tasks,
    "remove_scheduled_task": remove_scheduled_task,
    "health_check": health_check,
    "log_error": log_error,
    "restore_from_backup": restore_from_backup,
    "check_mail": check_mail,
}


# ============================================================
# TOOL ACTION TRACKING
# ============================================================

# Human-friendly descriptions for tool actions
_TOOL_ICONS = {
    "show_face": "😎",
    "check_mail": "📬",
    "remember_fact": "🧠",
    "recall_facts": "🔍",
    "recall_messages": "💬",
    "execute_bash": "⚙️",
    "read_file": "📄",
    "write_file": "✏️",
    "write_daily_log": "📝",
    "log_change": "📋",
    "git_command": "📦",
    "health_check": "🏥",
    "log_error": "📋",
    "safe_restart": "🔄",
    "manage_service": "🔧",
    "add_custom_face": "🎨",
    "add_scheduled_task": "⏰",
    "list_scheduled_tasks": "📅",
    "search_skills": "🔎",
    "read_skill": "📖",
}


def _format_tool_action(func_name: str, args: dict, result: str) -> str:
    """Format a single tool action for the user summary."""
    icon = _TOOL_ICONS.get(func_name, "🔧")
    
    # Compact human-friendly descriptions
    if func_name == "show_face":
        mood = args.get("mood", "?")
        text = args.get("text", "")
        return f"{icon} face: {mood}" + (f' "{text[:30]}"' if text else "")
    
    elif func_name == "check_mail":
        return f"{icon} checked mail: {result[:60]}"
    
    elif func_name == "remember_fact":
        fact = args.get("content", args.get("fact", ""))[:40]
        return f"{icon} remembered: \"{fact}\""
    
    elif func_name == "recall_facts":
        q = args.get("query", "all")
        return f"{icon} searched memory: \"{q}\""
    
    elif func_name == "recall_messages":
        n = args.get("limit", 20)
        return f"{icon} read last {n} messages"
    
    elif func_name == "execute_bash":
        cmd = args.get("command", "")[:200].replace("`", "'")
        ok = "✓" if "Error" not in result else "✗"
        return f"{icon} bash: {cmd} {ok}"
    
    elif func_name == "read_file":
        path = args.get("path", "?").split("/")[-1]
        return f"{icon} read: {path}"
    
    elif func_name == "write_file":
        path = args.get("path", "?").split("/")[-1]
        ok = "✓" if "Error" not in result else "✗"
        return f"{icon} wrote: {path} {ok}"
    
    elif func_name == "git_command":
        cmd = args.get("command", "?")[:200].replace("`", "'")
        ok = "✓" if "Error" not in result else "✗"
        return f"{icon} git: {cmd} {ok}"
    
    elif func_name == "health_check":
        return f"{icon} health check"

    elif func_name == "log_error":
        msg = (args.get("message") or "?")[:100]
        return f"{icon} error log: {msg}"

    elif func_name == "safe_restart":
        return f"{icon} restart"
    
    else:
        # Generic format
        args_str = ", ".join(f"{k}={str(v)[:100]}" for k, v in list(args.items())[:3])
        ok = "✓" if "Error" not in result else "✗"
        return f"{icon} {func_name}({args_str}) {ok}"


def _build_tool_footer(actions: list[str]) -> str:
    """Build compact tool usage footer inside a code block."""
    # Skip show_face — it's visual, user sees it on the display
    visible = [a for a in actions if not a.startswith("😎 face:")]
    
    if not visible:
        return ""
    
    lines = [f"🔧 Tool usage ({len(visible)}):"]
    for action in visible[:8]:  # Max 8 to keep it compact
        # Ensure no backticks leak into the code block
        safe = (action or "").replace("`", "'")
        lines.append(f"  {safe}")
    if len(visible) > 8:
        lines.append(f"  ... +{len(visible) - 8} more")
    
    return "\n".join(lines)


# ============================================================
# CONNECTOR
# ============================================================

class LiteLLMConnector(LLMConnector):
    """LiteLLM connector with tools."""
    
    name = "litellm"
    
    def __init__(self, model: str = None, api_base: str = None):
        from config import DEFAULT_LITE_PRESET, LLM_PRESETS, GEMINI_API_BASE
        if model is not None:
            self.model = model
            self.api_base = api_base
        else:
            preset = LLM_PRESETS.get(DEFAULT_LITE_PRESET, LLM_PRESETS["glm"])
            self.model = preset["model"]
            self.api_base = preset.get("api_base") or GEMINI_API_BASE or None

    def set_model(self, model: str, api_base: str = None):
        """Dynamically switch model and api_base."""
        self.model = model
        self.api_base = api_base
    
    def is_available(self) -> bool:
        return LITELLM_AVAILABLE
    
    def _load_system_prompt(self, user_message: str = "") -> str:
        """
        Load system prompt — same source as Claude CLI.
        Uses shared prompts.py for consistency.
        """
        from llm.prompts import build_system_context
        return build_system_context(user_message)
    
    async def call(
        self, 
        prompt: str, 
        history: list[dict], 
        system_prompt: Optional[str] = None
    ) -> str:
        """Call LiteLLM with tool support."""
        
        try:
            from litellm import acompletion
        except ImportError:
            raise LLMError("litellm not installed")
        
        # Build messages
        messages = []
        
        # System prompt (includes stats via build_system_context)
        sys_content = system_prompt or self._load_system_prompt(prompt)
        # Inject conversation context: summary + last 5 messages so the model remembers the thread
        from llm.prompts import build_conversation_context
        conv_context = build_conversation_context(history)
        if conv_context:
            sys_content = sys_content + "\n\n---\n" + conv_context
        messages.append({"role": "system", "content": sys_content})
        
        # History
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        
        # Current message
        messages.append({"role": "user", "content": prompt})
        
        # Agent loop with safety limits
        MAX_TURNS = 40
        tool_calls_count = 0
        MAX_TOOL_CALLS = 50  # Safety limit
        
        # Loop detection
        recent_tools = []  # Track last N tool calls
        MAX_REPEAT = 3     # If same tool called 3x in row, summarize
        
        # Tool usage tracking for user transparency
        tool_actions = []
        
        for turn in range(MAX_TURNS):
            try:
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "timeout": 120,
                }
                if ENABLE_LITELLM_TOOLS:
                    kwargs["tools"] = TOOLS
                    kwargs["tool_choice"] = "auto"
                else:
                    kwargs["tool_choice"] = "none"
                
                # Use instance api_base if set, otherwise potentially fall back to env or default
                if self.api_base:
                     kwargs["api_base"] = self.api_base
                
                response = await acompletion(**kwargs)
                
                msg = response.choices[0].message
                messages.append({
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": getattr(msg, "tool_calls", None)
                })
                
                if msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        # Safety: limit total tool calls
                        tool_calls_count += 1
                        if tool_calls_count > MAX_TOOL_CALLS:
                            log.warning(f"[LiteLLM] Tool call limit reached ({MAX_TOOL_CALLS})")
                            return "Error: Too many tool calls. Stopping for safety."
                        
                        func_name = tool_call.function.name
                        
                        # Parse arguments safely
                        try:
                            raw_args = tool_call.function.arguments or "{}"
                            args = json.loads(raw_args)
                            if not isinstance(args, dict):
                                args = {}
                        except json.JSONDecodeError as e:
                            log.warning(f"[LiteLLM] Bad JSON from {func_name}: {e}")
                            args = {}
                        
                        log.info(f"[LiteLLM] Turn {turn+1}: {func_name}({list(args.keys())})")
                        
                        # Loop detection: track recent tools
                        recent_tools.append(func_name)
                        if len(recent_tools) > MAX_REPEAT:
                            recent_tools.pop(0)
                        
                        # Check for repetitive pattern
                        if len(recent_tools) >= MAX_REPEAT and len(set(recent_tools)) == 1:
                            log.warning(f"[LiteLLM] Loop detected: {func_name} called {MAX_REPEAT}x in a row")
                            # Ask model to summarize instead of continuing
                            messages.append({
                                "role": "user",
                                "content": "STOP. You're repeating the same action. Summarize what you've found so far and provide your answer with the information you have."
                            })
                            recent_tools = []  # Reset
                            continue  # Skip tool execution, get summary
                        
                        # Execute tool
                        func = TOOL_MAP.get(func_name)
                        if func:
                            try:
                                result = func(**args)
                            except TypeError as e:
                                # Wrong arguments
                                result = f"Error: Invalid arguments for {func_name}: {e}"
                                log.warning(f"[LiteLLM] {result}")
                            except Exception as e:
                                result = f"Error executing {func_name}: {e}"
                                log.error(f"[LiteLLM] {result}")
                        else:
                            result = f"Unknown tool: {func_name}. Available: {', '.join(TOOL_MAP.keys())}"
                        
                        # Log result preview
                        result_preview = str(result)[:100]
                        log.debug(f"[LiteLLM] {func_name} -> {result_preview}...")
                        
                        # Track for user-visible summary
                        tool_actions.append(_format_tool_action(func_name, args, str(result)[:200]))
                        
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": func_name,
                            "content": str(result)[:4000]
                        })
                else:
                    # No tool calls = final response — clear any rate limit
                    from llm.rate_limits import clear_limit
                    clear_limit("litellm")
                    
                    final = msg.content or "(empty response)"
                    
                    # Build tool usage footer with a distinct separator for handlers.py
                    footer = _build_tool_footer(tool_actions) if tool_actions else ""
                    
                    # Use a distinct long separator that's unlikely to appear in normal text
                    SEPARATOR = "\n\n|--TOOL_LOG--|\n"
                    final_content = final + (SEPARATOR + footer if footer else "")
                    return final_content
                    
            except Exception as e:
                err_str = str(e)
                log.error(f"[LiteLLM] API Error on turn {turn+1}: {err_str[:200]}")
                
                # Handle rate limits smartly
                if "429" in err_str or "RateLimitError" in err_str or "rate" in err_str.lower():
                    from llm.rate_limits import record_rate_limit, should_auto_retry
                    record_rate_limit("litellm", err_str)
                    
                    # Auto-retry if short limit (< 90s)
                    wait = should_auto_retry("litellm")
                    if wait and wait <= 90 and turn == 0:
                        import asyncio
                        log.info(f"[LiteLLM] Short rate limit, auto-retrying in {wait:.0f}s...")
                        await asyncio.sleep(wait + 1)
                        continue  # Retry the same turn
                
                # Don't crash on API errors, return error message
                return f"Error: LLM API failed: {err_str[:200]}"
        
        log.warning(f"[LiteLLM] Max turns ({MAX_TURNS}) reached, {tool_calls_count} tool calls")
        return "I made too many attempts. Please try a simpler request."
