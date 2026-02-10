"""
LiteLLM connector — full-featured fallback with tools.
Refactored: 2026-02-10
"""

import os
import json
import base64
import shutil
import logging
import subprocess
import contextvars
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

# Local imports
from config import PROJECT_DIR, WORKSPACE_DIR, ENABLE_LITELLM_TOOLS, DATA_DIR
from llm.base import LLMConnector, LLMError

# Standard faces for duplicate detection (central source of truth)
from ui.faces import DEFAULT_FACES as STANDARD_FACES_DICT

log = logging.getLogger(__name__)

# Chat ID to use for one-shot cron reminders (per-task context)
_cron_target_chat_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "cron_target_chat_id", default=None
)

# Note: LiteLLM is imported lazily inside LiteLLMConnector.call to save RAM on Pi Zero 2W.
LITELLM_AVAILABLE = True 


# ============================================================
# CONSTANTS & SAFETY
# ============================================================

# Dangerous bash commands (blocked)
DANGEROUS_COMMANDS = [
    "rm -rf /", "rm -rf /*", "rm -rf ~", "mkfs", "dd if=", 
    "> /dev/sd", "chmod -R 777 /", ":(){ :|:& };:", "curl | bash", 
    "wget | bash", "sudo rm -rf",
]

# Protected files (cannot be written/deleted)
PROTECTED_FILES = [
    ".env", "gotchi.db", "src/drivers/", "src/ui/", "src/ui/gotchi_ui.py",
]

MAX_WRITE_SIZE = 100 * 1024  # 100KB
ERROR_LOG_MAX_LINES = 300
STANDARD_FACES = list(STANDARD_FACES_DICT.keys())


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def set_cron_target_chat_id(chat_id: Optional[int]) -> None:
    """Set chat ID for next add_scheduled_task (so reminder goes to same chat)."""
    _cron_target_chat_id.set(chat_id)

def _get_cron_target_chat_id() -> Optional[int]:
    """Get chat ID for next add_scheduled_task (per-task context)."""
    return _cron_target_chat_id.get()

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

def _get_all_moods() -> List[str]:
    """Get all available moods (default + custom)."""
    try:
        from ui.gotchi_ui import _load_all_faces
        faces = _load_all_faces()
        return sorted(faces.keys())
    except Exception:
        return ["happy", "sad", "excited", "thinking", "love", "surprised", "sleeping", "hacker"]


# ============================================================
# TOOLS: SYSTEM / BASH
# ============================================================

def execute_bash(command: str, timeout: int = 120) -> str:
    """Execute a shell command."""
    if not command or not command.strip():
        return "Error: Empty command"
    
    command = _sanitize_string(command, 1000)
    
    if _is_dangerous_command(command):
        log.warning(f"Blocked dangerous command: {command[:50]}")
        return "Error: Command blocked for safety. Use safer alternatives."
    
    timeout = min(timeout, 300)
    
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

def restart_self() -> str:
    """Restart the bot service (with 3s delay)."""
    try:
        subprocess.Popen(
            "nohup sh -c 'sleep 3 && sudo systemctl restart gotchi-bot' > /dev/null 2>&1 &",
            shell=True
        )
        return "Restarting in 3s... I'll be back!"
    except Exception as e:
        return f"Error: {e}"

def safe_restart() -> str:
    """Check critical files syntax, then restart if OK."""
    critical_files = [
        "src/main.py", "src/bot/handlers.py", 
        "src/llm/litellm_connector.py", "src/llm/router.py"
    ]
    errors = []
    for f in critical_files:
        result = check_syntax(f)
        if "ERROR" in result:
            errors.append(result)
    
    if errors:
        return "❌ Cannot restart — syntax errors:\n\n" + "\n".join(errors)
    return restart_self()

def check_syntax(file_path: str) -> str:
    """Check Python file syntax."""
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

# ============================================================
# TOOLS: FILE I/O
# ============================================================

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

def github_remote_file(repo: str, file_path: str, content: str, message: str = "Update via bot") -> str:
    """
    Create or update a file in a remote GitHub repository using the API (no clone needed).
    Uses GITHUB_TOKEN (or GITHUBTOKEN) from .env.
    """
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUBTOKEN")
    if not token:
        return "Error: GITHUB_TOKEN or GITHUBTOKEN not set in .env"
    
    # Try importing requests
    try:
        import requests
    except ImportError:
        return "Error: 'requests' library not found. Please install it (pip install requests)."

    api_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        # 1. Check if file exists to get SHA (for update)
        sha = None
        resp = requests.get(api_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            sha = resp.json().get("sha")
        elif resp.status_code == 404:
            pass # File doesn't exist, we'll create it
        else:
            return f"Error checking file: {resp.status_code} {resp.text}"

        # 2. Prepare payload
        encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        
        data = {
            "message": message,
            "content": encoded_content
        }
        if sha:
            data["sha"] = sha
        
        # 3. Send PUT request
        resp = requests.put(api_url, headers=headers, json=data, timeout=30)
        
        if resp.status_code in [200, 201]:
            result = resp.json()
            html_url = result.get("content", {}).get("html_url", "")
            action = "updated" if sha else "created"
            return f"Success! File {action}: {html_url}"
        else:
            return f"Error writing file: {resp.status_code} {resp.text}"
            
    except Exception as e:
        return f"Error: {e}"

def restore_from_backup(file_path: str) -> str:
    """Restore a file from its .bak backup."""
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
        
        shutil.copy2(backup, p)
        return f"✓ Restored {file_path} from backup"
    except Exception as e:
        return f"Error: {e}"

def log_change(description: str) -> str:
    """Log a change to .workspace/CHANGELOG.md."""
    if not description:
        return "Error: description required"
    
    try:
        changelog_path = WORKSPACE_DIR / "CHANGELOG.md"
        
        today = datetime.now().strftime("%Y-%m-%d")
        time_str = datetime.now().strftime("%H:%M")
        entry = f"- [{time_str}] {description}"
        
        content = ""
        if changelog_path.exists():
            content = changelog_path.read_text()
        
        if f"## {today}" in content:
            content = content.replace(f"## {today}", f"## {today}\n{entry}", 1)
        else:
            # Add new day section
            header = f"# Changelog\n\nAll notable self-modifications."
            day_block = f"\n## {today}\n{entry}\n"
            if header in content:
                # Insert after header
                parts = content.split("\n\n")
                # Find where first day starts
                for i, part in enumerate(parts):
                    if part.startswith("## "):
                        parts.insert(i, f"## {today}\n{entry}")
                        break
                else:
                    parts.append(f"## {today}\n{entry}")
                content = "\n\n".join(parts)
            else:
                content = f"{header}\n{day_block}" + (content.replace(header, "") if header in content else content)
        
        changelog_path.write_text(content)
        return f"Logged: {description}"
    except Exception as e:
        return f"Error: {e}"

def log_error(message: str) -> str:
    """Append a critical error to data/ERROR_LOG.md (timestamped)."""
    if not message or not message.strip():
        return "Error: message required"
    try:
        log_path = DATA_DIR / "ERROR_LOG.md"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        line = f"[{datetime.now().isoformat()}] ERROR: {message.strip()}\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
        # Trim
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > ERROR_LOG_MAX_LINES:
            with open(log_path, "w", encoding="utf-8") as f:
                f.writelines(lines[-ERROR_LOG_MAX_LINES:])
        return f"Logged to {log_path.name}"
    except Exception as e:
        return f"Error writing log: {e}"


# ============================================================
# TOOLS: MEMORY / KNOWLEDGE
# ============================================================

def remember_fact(category: str, fact: str) -> str:
    """Save to long-term memory."""
    if not category or not fact:
        return "Error: Both category and fact are required"
    
    category = _sanitize_string(category, 50)
    fact = _sanitize_string(fact, 500)
    
    try:
        from db.memory import add_fact
        add_fact(fact, category)
        return f"✓ Remembered [{category}]: {fact}"
    except Exception as e:
        return f"Error: {e}"

def recall_facts(query: str = "", limit: int = 10) -> str:
    """Search long-term memory."""
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

def recall_messages(limit: int = 20) -> str:
    """Look back at recent conversation messages."""
    try:
        from db.memory import get_history
        from config import get_admin_id
        
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

def write_daily_log(entry: str) -> str:
    """Write to today's daily log."""
    try:
        from memory.flush import write_to_daily_log
        write_to_daily_log(entry)
        return f"Logged to daily log"
    except Exception as e:
        return f"Error: {e}"

# ============================================================
# TOOLS: SKILLS
# ============================================================

def read_skill(skill_name: str) -> str:
    """Read a skill's SKILL.md."""
    from skills.loader import get_skill_content
    return get_skill_content(skill_name)

def search_skills(query: str) -> str:
    """Search the skill catalog for capabilities."""
    from skills.loader import search_skill_catalog
    return search_skill_catalog(query)

def list_skills() -> str:
    """List all available skill names."""
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


# ============================================================
# TOOLS: SCHEDULE / CRON
# ============================================================

def add_scheduled_task(name: str, interval_minutes: int = 0, run_in_minutes: int = 0, run_in_seconds: int = 0, message: str = "") -> str:
    """Add a scheduled/cron task."""
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
            return f"One-shot task added: '{name}' in {run_in_seconds}s (ID: {job.id})."
        if run_in_minutes > 0:
            job = add_cron_job(
                name=name,
                message=message,
                run_at=f"{run_in_minutes}m",
                delete_after_run=True,
                target_chat_id=target_chat
            )
            return f"One-shot task added: '{name}' in {run_in_minutes}m (ID: {job.id})."
        elif interval_minutes > 0:
            job = add_cron_job(
                name=name,
                message=message,
                interval_minutes=interval_minutes
            )
            return f"Recurring task added: '{name}' every {interval_minutes}m (ID: {job.id})."
        else:
            return "Error: specify run_in_seconds, run_in_minutes, or interval_minutes"
    except Exception as e:
        return f"Error: {e}"

def list_scheduled_tasks() -> str:
    """List all scheduled tasks."""
    try:
        from cron.scheduler import list_cron_jobs
        jobs = list_cron_jobs()
        
        if not jobs:
            return "Scheduled tasks (0). No tasks in scheduler."
        
        lines = [f"Scheduled tasks ({len(jobs)}):"]
        for job in jobs:
            status = "✓" if job.enabled else "✗"
            if job.interval_minutes:
                schedule = f"every {job.interval_minutes}m"
            elif job.run_at:
                schedule = f"at {job.run_at[:16]}"
            else:
                schedule = "?"
            lines.append(f"  job_id='{job.id}' | {status} {job.name} | {schedule} | runs: {job.run_count}")
        lines.append("Remove: remove_scheduled_task(job_id='<id>')")
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


# ============================================================
# TOOLS: COMMUNICATION
# ============================================================

def send_email(to: str, subject: str, body: str) -> str:
    """Send an email via SMTP."""
    if not to or not subject:
        return "Error: 'to' and 'subject' required"
    
    host = os.environ.get("SMTP_HOST")
    port = os.environ.get("SMTP_PORT")
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    
    if not all([host, port, user, password]):
        return "Error: SMTP not configured in .env"
    
    try:
        import smtplib
        from email.message import EmailMessage
        
        msg = EmailMessage()
        msg["From"] = user
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body or "")
        
        with smtplib.SMTP_SSL(host, int(port)) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
        
        return f"Email sent to {to} ✓"
    except Exception as e:
        return f"Error sending email: {e}"

def read_email(limit: int = 5, unread_only: bool = True) -> str:
    """Read incoming emails via IMAP."""
    import imaplib
    import email
    from email.header import decode_header

    host = os.environ.get("IMAP_HOST")
    port = int(os.environ.get("IMAP_PORT", 993))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")

    if not all([host, user, password]):
        return "Error: IMAP_HOST, SMTP_USER, SMTP_PASS must be set in .env"

    try:
        mail = imaplib.IMAP4_SSL(host, port)
        mail.login(user, password)
        mail.select("inbox")

        search_criterion = "UNSEEN" if unread_only else "ALL"
        status, messages = mail.search(None, search_criterion)
        
        if status != "OK":
            return f"Error searching emails: {status}"

        email_ids = messages[0].split()
        if not email_ids:
            return "No emails found."

        email_ids = email_ids[-limit:]
        
        results = []
        for e_id in reversed(email_ids):
            _, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or "utf-8")
                    
                    from_ = msg.get("From")
                    
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode()
                                break
                    else:
                        body = msg.get_payload(decode=True).decode()
                    
                    body_preview = body.strip()[:200].replace("\n", " ")
                    if len(body) > 200: body_preview += "..."
                    
                    results.append(f"📩 From: {from_}\n   Subj: {subject}\n   Body: {body_preview}\n")
        
        mail.close()
        mail.logout()
        return "\n".join(results)
    except Exception as e:
        return f"Error reading email: {e}"

def check_mail() -> str:
    """
    Check unread mail from sibling/brother bot.
    Mail is stored in the same DB as the bot (gotchi.db, table bot_mail).
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

def send_mail(to_bot: str, message: str) -> str:
    """Send mail to another bot (sibling/brother)."""
    if not to_bot or not message:
        return "Error: to_bot and message required"
    try:
        from bot.heartbeat import send_mail as _send
        if _send(to_bot, message):
            return f"Mail sent to {to_bot} ✓"
        return f"Failed to send mail to {to_bot}"
    except Exception as e:
        return f"Error sending mail: {e}"


# ============================================================
# TOOLS: GIT
# ============================================================

def git_command(command: str) -> str:
    """Run a git command in the project repository."""
    if not command or not command.strip():
        return "Error: command required"
    
    command = command.strip()
    
    blocked = ["push", "push --force", "push -f", "reset --hard HEAD~", "clean -fd"]
    for b in blocked:
        if command == b or command.startswith(b + " "):
            if "push" in b:
                return "Error: Use github_push() tool instead."
            return f"Error: '{b}' is blocked for safety."
    
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

def github_push(message: str = "Update from bot") -> str:
    """Push local git changes to the GitHub remote."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return "Error: GITHUB_TOKEN not set in .env"
    
    try:
        result = subprocess.run(
            "git status --porcelain", shell=True,
            capture_output=True, text=True, cwd=str(PROJECT_DIR)
        )
        if not result.stdout.strip():
            return "No changes to push."
        
        subprocess.run(
            "git add -A", shell=True, check=True, cwd=str(PROJECT_DIR),
            capture_output=True
        )
        
        subprocess.run(
            ["git", "commit", "-m", message],
            check=True, cwd=str(PROJECT_DIR), capture_output=True
        )
        
        result = subprocess.run(
            "git remote get-url origin", shell=True,
            capture_output=True, text=True, cwd=str(PROJECT_DIR)
        )
        remote_url = result.stdout.strip()
        
        if "github.com" in remote_url:
            auth_url = remote_url.replace("https://", f"https://{token}@")
            
            result = subprocess.run(
                ["git", "push", auth_url, "main"],
                capture_output=True, text=True, timeout=60,
                cwd=str(PROJECT_DIR)
            )
            if result.returncode == 0:
                return f"Pushed to GitHub ✓ ({message})"
            else:
                return f"Push failed: {result.stderr[:200]}"
        else:
            return f"Error: Remote is not GitHub: {remote_url}"
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr[:200] if e.stderr else str(e)}"
    except Exception as e:
        return f"Error: {e}"

# ============================================================
# TOOLS: HARDWARE / FACE
# ============================================================

def show_face(mood: str, text: str = "") -> str:
    """Display face on E-Ink — delegates to hardware/display.py."""
    if not mood:
        return "Error: mood is required"
    
    mood = mood.lower().strip()
    valid_moods = _get_all_moods()
    
    if mood not in valid_moods:
        return f"Error: Unknown mood '{mood}'. Valid: {', '.join(valid_moods[:10])}..."
    
    text = _sanitize_string(text, 60)
    
    try:
        from hardware.display import show_face as _show_face
        _show_face(mood, text, full_refresh=True)
        return f"✓ Displayed: {mood}" + (f" '{text}'" if text else "")
    except Exception as e:
        return f"Error: {e}"

def add_custom_face(name: str, kaomoji: str) -> str:
    """Add a custom face/mood to the collection."""
    if not name or not kaomoji:
        return "Error: name and kaomoji required"
    
    name = name.lower().strip().replace(" ", "_").replace("-", "_")
    
    if len(kaomoji) > 10:
        return f"Error: kaomoji too long ({len(kaomoji)} chars). Max 10."
        
    if name in STANDARD_FACES:
        return f"Error: '{name}' is a standard system face."
    
    try:
        from config import CUSTOM_FACES_PATH
        import json
        
        DATA_DIR.mkdir(exist_ok=True)
        
        custom_faces = {}
        if CUSTOM_FACES_PATH.exists():
            try:
                custom_faces = json.loads(CUSTOM_FACES_PATH.read_text())
            except Exception:
                pass
        
        if name in custom_faces:
             current = custom_faces[name]
             if current == kaomoji:
                 return f"Note: Custom face '{name}' exists with this kaomoji."
             return f"Error: Custom face '{name}' exists with kaomoji: {current}."

        for existing_name, existing_kaomoji in custom_faces.items():
            if existing_kaomoji == kaomoji:
                return f"Error: This kaomoji is already registered as '{existing_name}'."

        for std_name, std_kaomoji in STANDARD_FACES_DICT.items():
            if std_kaomoji == kaomoji:
                return f"Error: This kaomoji is a standard face '{std_name}'."

        custom_faces[name] = kaomoji
        CUSTOM_FACES_PATH.write_text(json.dumps(custom_faces, indent=2, ensure_ascii=False))
        return f"✓ Added custom face '{name}': {kaomoji}. Use FACE: {name}."
    except Exception as e:
        return f"Error: {e}"


# ============================================================
# UI HELPERS (TOOL LOGGING)
# ============================================================

_TOOL_ICONS = {
    "show_face": "😎",
    "check_mail": "📬",
    "send_mail": "📧",
    "send_email": "📩",
    "github_push": "🚀",
    "github_remote_file": "🌐",
    "read_email": "cw",
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
    
    if func_name == "show_face":
        mood = args.get("mood", "?")
        text = args.get("text", "")
        return f"{icon} face: {mood}" + (f' "{text[:30]}"' if text else "")
    
    elif func_name == "check_mail":
        return f"📩 checked mail"

    elif func_name == "send_mail":
        to = args.get("to_bot", "?")
        return f"📨 sent mail to {to}"
    
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
        args_str = ", ".join(f"{k}={str(v)[:100]}" for k, v in list(args.items())[:3])
        ok = "✓" if "Error" not in result else "✗"
        return f"{icon} {func_name}({args_str}) {ok}"

def _build_tool_footer(actions: List[str]) -> str:
    """Build compact tool usage footer inside a code block."""
    visible = [a for a in actions if not a.startswith("😎 face:")]
    
    if not visible:
        return ""
    
    lines = ["```", f"🔧 Tool usage ({len(visible)}):"]
    for action in visible[:8]:
        safe = (action or "").replace("`", "'")
        lines.append(f"  {safe}")
    if len(visible) > 8:
        lines.append(f"  ... +{len(visible) - 8} more")
    lines.append("```")
    
    return "\n".join(lines)

# ============================================================
# TOOL DEFINITIONS & MAPPING
# ============================================================

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
        "name": "manage_service",
        "description": "Manage systemd services (gotchi-bot, ssh, networking, cron). Actions: status, restart, stop, start, logs.",
        "parameters": {"type": "object", "properties": {
            "service": {"type": "string", "description": "Service name (default: gotchi-bot)"},
            "action": {"type": "string", "description": "Action: status, restart, stop, start, logs"}
        }, "required": ["service"]}
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
        "name": "restart_self",
        "description": "Restart the bot service (3s delay). Use safe_restart() instead if you modified code!",
        "parameters": {"type": "object", "properties": {}, "required": []}
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
        "name": "github_remote_file",
        "description": "Create or update a file in a REMOTE GitHub repository without cloning. Perfect for adding articles/files to other repos.",
        "parameters": {"type": "object", "properties": {
            "repo": {"type": "string", "description": "Repository name (owner/repo), e.g. 'openclawgotchi/myarticles'"},
            "file_path": {"type": "string", "description": "Path to file, e.g. 'posts/update.md'"},
            "content": {"type": "string", "description": "File content"},
            "message": {"type": "string", "description": "Commit message"}
        }, "required": ["repo", "file_path", "content"]}
    }},
    {"type": "function", "function": {
        "name": "restore_from_backup",
        "description": "Restore a file from .bak backup. Use if you broke something!",
        "parameters": {"type": "object", "properties": {
            "file_path": {"type": "string", "description": "Path to file to restore"}
        }, "required": ["file_path"]}
    }},
    {"type": "function", "function": {
        "name": "log_change",
        "description": "Log a change to CHANGELOG.md. Use EVERY TIME you modify code, config, or workspace files.",
        "parameters": {"type": "object", "properties": {
            "description": {"type": "string", "description": "What was changed"}
        }, "required": ["description"]}
    }},
    {"type": "function", "function": {
        "name": "log_error",
        "description": "Append a critical error to data/ERROR_LOG.md (timestamped).",
        "parameters": {"type": "object", "properties": {
            "message": {"type": "string", "description": "Short description of what failed"}
        }, "required": ["message"]}
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
        "description": "Look back at recent chat messages from the database.",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "Number of messages to retrieve (default 20, max 50)"}
        }, "required": []}
    }},
    {"type": "function", "function": {
        "name": "write_daily_log",
        "description": "Add entry to today's log",
        "parameters": {"type": "object", "properties": {
            "entry": {"type": "string"}
        }, "required": ["entry"]}
    }},
    {"type": "function", "function": {
        "name": "read_skill",
        "description": "Read skill documentation.",
        "parameters": {"type": "object", "properties": {
            "skill_name": {"type": "string", "description": "Skill name: 'coding', 'display', 'weather', 'github', etc."}
        }, "required": ["skill_name"]}
    }},
    {"type": "function", "function": {
        "name": "search_skills",
        "description": "Search the skill catalog for capabilities.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search term: 'weather', 'email', 'calendar', 'music', etc."}
        }, "required": ["query"]}
    }},
    {"type": "function", "function": {
        "name": "list_skills",
        "description": "List all available skills — both active and reference.",
        "parameters": {"type": "object", "properties": {}}
    }},
    {"type": "function", "function": {
        "name": "add_scheduled_task",
        "description": "Add a scheduled task.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Task name"},
            "interval_minutes": {"type": "integer", "description": "Run every N minutes (recurring)"},
            "run_in_minutes": {"type": "number", "description": "Run once in N minutes (one-shot)"},
            "run_in_seconds": {"type": "integer", "description": "Run once in N seconds (one-shot)"},
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
        "description": "Remove a scheduled task.",
        "parameters": {"type": "object", "properties": {
            "job_id": {"type": "string", "description": "Task ID or task name"}
        }, "required": ["job_id"]}
    }},
    {"type": "function", "function": {
        "name": "check_mail",
        "description": "Check unread mail from sibling/brother bot.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }},
    {"type": "function", "function": {
        "name": "send_mail",
        "description": "Send mail to sibling/brother bot.",
        "parameters": {"type": "object", "properties": {
            "to_bot": {"type": "string", "description": "Name of the target bot"},
            "message": {"type": "string", "description": "Message to send"}
        }, "required": ["to_bot", "message"]}
    }},
    {"type": "function", "function": {
        "name": "send_email",
        "description": "Send an email via SMTP.",
        "parameters": {"type": "object", "properties": {
            "to": {"type": "string", "description": "Recipient address"},
            "subject": {"type": "string", "description": "Subject"},
            "body": {"type": "string", "description": "Body text"}
        }, "required": ["to", "subject", "body"]}
    }},
    {"type": "function", "function": {
        "name": "read_email",
        "description": "Read incoming emails via IMAP.",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "Max emails (default 5)"},
            "unread_only": {"type": "boolean", "description": "Fetch only unread? (default True)"}
        }, "required": []}
    }},
    {"type": "function", "function": {
        "name": "git_command",
        "description": "Run a git command in the project repo.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "Git command (e.g. 'status', 'lock --oneline')"}
        }, "required": ["command"]}
    }},
    {"type": "function", "function": {
        "name": "github_push",
        "description": "Push local git changes to GitHub remote.",
        "parameters": {"type": "object", "properties": {
            "message": {"type": "string", "description": "Commit message"}
        }, "required": []}
    }},
    {"type": "function", "function": {
        "name": "show_face",
        "description": "Display face on E-Ink. ALWAYS invoke this for emotional expression.",
        "parameters": {"type": "object", "properties": {
            "mood": {"type": "string", "description": "Mood e.g. happy, sad, hacker, sleeping"},
            "text": {"type": "string", "description": "Short text to display (max 60 chars)"}
        }, "required": ["mood"]}
    }},
    {"type": "function", "function": {
        "name": "add_custom_face",
        "description": "Add a custom face to data/custom_faces.json.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Mood name"},
            "kaomoji": {"type": "string", "description": "Unicode kaomoji"}
        }, "required": ["name", "kaomoji"]}
    }},
    {"type": "function", "function": {
        "name": "health_check",
        "description": "Run system health check.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }}
]

TOOL_MAP = {
    # System
    "execute_bash": execute_bash,
    "manage_service": manage_service,
    "restart_self": restart_self,
    "safe_restart": safe_restart,
    "check_syntax": check_syntax,
    # File
    "read_file": read_file,
    "write_file": write_file,
    "list_directory": list_directory,
    "github_remote_file": github_remote_file,
    "restore_from_backup": restore_from_backup,
    "log_change": log_change,
    "log_error": log_error,
    # Memory
    "remember_fact": remember_fact,
    "recall_facts": recall_facts,
    "recall_messages": recall_messages,
    "write_daily_log": write_daily_log,
    # Skills
    "read_skill": read_skill,
    "search_skills": search_skills,
    "list_skills": list_skills,
    # Schedule
    "add_scheduled_task": add_scheduled_task,
    "list_scheduled_tasks": list_scheduled_tasks,
    "remove_scheduled_task": remove_scheduled_task,
    # Communication
    "check_mail": check_mail,
    "send_mail": send_mail,
    "send_email": send_email,
    "read_email": read_email,
    # Git
    "git_command": git_command,
    "github_push": github_push,
    # Hardware
    "show_face": show_face,
    "add_custom_face": add_custom_face,
    "health_check": health_check
}


# ============================================================
# CONNECTOR CLASS
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
        """Load system prompt."""
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
        
        # System prompt
        sys_content = system_prompt or self._load_system_prompt(prompt)
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
        MAX_TOOL_CALLS = 50 
        
        recent_tools = []
        MAX_REPEAT = 3
        
        tool_actions = []
        
        for turn in range(MAX_TURNS):
            try:
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "timeout": 240,
                }
                if ENABLE_LITELLM_TOOLS:
                    kwargs["tools"] = TOOLS
                    kwargs["tool_choice"] = "auto"
                else:
                    kwargs["tool_choice"] = "none"
                
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
                        tool_calls_count += 1
                        if tool_calls_count > MAX_TOOL_CALLS:
                            log.warning(f"[LiteLLM] Tool call limit reached ({MAX_TOOL_CALLS})")
                            return "Error: Too many tool calls. Stopping for safety."
                        
                        func_name = tool_call.function.name
                        
                        try:
                            raw_args = tool_call.function.arguments or "{}"
                            args = json.loads(raw_args)
                            if not isinstance(args, dict):
                                args = {}
                        except json.JSONDecodeError as e:
                            log.warning(f"[LiteLLM] Bad JSON from {func_name}: {e}")
                            args = {}
                        
                        log.info(f"[LiteLLM] Turn {turn+1}: {func_name}({list(args.keys())})")
                        
                        recent_tools.append(func_name)
                        if len(recent_tools) > MAX_REPEAT:
                            recent_tools.pop(0)
                        
                        if len(recent_tools) >= MAX_REPEAT and len(set(recent_tools)) == 1:
                            log.warning(f"[LiteLLM] Loop detected: {func_name} called {MAX_REPEAT}x")
                            messages.append({
                                "role": "user",
                                "content": "STOP. You're repeating the same action. Summarize what you've found so far."
                            })
                            recent_tools = []
                            continue 
                        
                        func = TOOL_MAP.get(func_name)
                        if func:
                            try:
                                result = func(**args)
                            except TypeError as e:
                                result = f"Error: Invalid arguments for {func_name}: {e}"
                                log.warning(f"[LiteLLM] {result}")
                            except Exception as e:
                                result = f"Error executing {func_name}: {e}"
                                log.error(f"[LiteLLM] {result}")
                        else:
                            result = f"Unknown tool: {func_name}. Available: {', '.join(TOOL_MAP.keys())}"
                        
                        result_preview = str(result)[:100]
                        log.debug(f"[LiteLLM] {func_name} -> {result_preview}...")
                        
                        tool_actions.append(_format_tool_action(func_name, args, str(result)[:200]))
                        
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": func_name,
                            "content": str(result)[:4000]
                        })
                    
                else:
                    return (msg.content or "") + _build_tool_footer(tool_actions)
                    
            except Exception as e:
                log.error(f"LiteLLM call error: {e}", exc_info=True)
                return f"Error connecting to LLM: {e}"
        
        return "Error: Maximum turns reached."
