"""
LiteLLM connector — full-featured fallback with tools.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

from config import PROJECT_DIR, GEMINI_MODEL
from llm.base import LLMConnector, LLMError

log = logging.getLogger(__name__)

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


def show_face(mood: str, text: str = "") -> str:
    """Display face on E-Ink — delegates to hardware/display.py."""
    # Validate mood
    VALID_MOODS = ["happy", "sad", "excited", "thinking", "love", "surprised", 
                   "bored", "sleeping", "hacker", "disappointed", "angry", 
                   "crying", "proud", "nervous", "confused", "mischievous", 
                   "cool", "wink", "dead", "shock", "suspicious", "smug", 
                   "cheering", "celebrate"]
    
    if not mood:
        return "Error: mood is required"
    
    mood = mood.lower().strip()
    if mood not in VALID_MOODS:
        return f"Error: Unknown mood '{mood}'. Valid: {', '.join(VALID_MOODS[:5])}..."
    
    # Limit text length
    text = _sanitize_string(text, 60)
    
    try:
        from hardware.display import show_face as _show_face
        _show_face(mood, text, full_refresh=True)
        return f"✓ Displayed: {mood}" + (f" '{text}'" if text else "")
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
    """Read a skill's SKILL.md."""
    for skills_dir in ["gotchi-skills", "openclaw-skills"]:
        skill_path = PROJECT_DIR / skills_dir / skill_name / "SKILL.md"
        if skill_path.exists():
            return skill_path.read_text()
    
    available = []
    for skills_dir in ["gotchi-skills", "openclaw-skills"]:
        sd = PROJECT_DIR / skills_dir
        if sd.exists():
            for item in sd.iterdir():
                if item.is_dir() and (item / "SKILL.md").exists():
                    available.append(f"{skills_dir}/{item.name}")
    
    return f"Skill '{skill_name}' not found.\n\nAvailable:\n" + "\n".join(available)


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


def add_scheduled_task(name: str, interval_minutes: int = 0, run_in_minutes: int = 0, message: str = "") -> str:
    """Add a scheduled/cron task."""
    try:
        from cron.scheduler import add_cron_job
        
        if run_in_minutes > 0:
            # One-shot
            job = add_cron_job(
                name=name,
                message=message,
                run_at=f"{run_in_minutes}m",
                delete_after_run=True
            )
            return f"One-shot task added: '{name}' in {run_in_minutes}m (ID: {job.id})"
        elif interval_minutes > 0:
            # Recurring
            job = add_cron_job(
                name=name,
                message=message,
                interval_minutes=interval_minutes
            )
            return f"Recurring task added: '{name}' every {interval_minutes}m (ID: {job.id})"
        else:
            return "Error: specify interval_minutes (recurring) or run_in_minutes (one-shot)"
    except Exception as e:
        return f"Error: {e}"


def list_scheduled_tasks() -> str:
    """List all scheduled tasks."""
    try:
        from cron.scheduler import list_cron_jobs
        jobs = list_cron_jobs()
        
        if not jobs:
            return "No scheduled tasks."
        
        lines = []
        for job in jobs:
            status = "✓" if job.enabled else "✗"
            if job.interval_minutes:
                schedule = f"every {job.interval_minutes}m"
            elif job.run_at:
                schedule = f"at {job.run_at[:16]}"
            else:
                schedule = "?"
            lines.append(f"{status} {job.name} ({job.id}) — {schedule}, runs: {job.run_count}")
        
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
        "name": "read_skill",
        "description": "Read skill documentation. Key skills: 'coding' (project map, self-modification), 'display' (E-Ink faces). Use this to learn how to modify yourself!",
        "parameters": {"type": "object", "properties": {
            "skill_name": {"type": "string", "description": "Skill name: 'coding', 'display', etc."}
        }, "required": ["skill_name"]}
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
        "description": "Add a scheduled task (cron). Use interval_minutes for recurring, run_in_minutes for one-shot.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Task name"},
            "interval_minutes": {"type": "integer", "description": "Run every N minutes (recurring)"},
            "run_in_minutes": {"type": "integer", "description": "Run once in N minutes (one-shot)"},
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
        "description": "Remove a scheduled task by ID",
        "parameters": {"type": "object", "properties": {
            "job_id": {"type": "string", "description": "Task ID to remove"}
        }, "required": ["job_id"]}
    }},
    {"type": "function", "function": {
        "name": "health_check",
        "description": "Run system health check. Use to diagnose problems! Checks internet, disk, temp, service, errors.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }},
    {"type": "function", "function": {
        "name": "restore_from_backup",
        "description": "Restore a file from .bak backup. Use if you broke something!",
        "parameters": {"type": "object", "properties": {
            "file_path": {"type": "string", "description": "Path to file to restore"}
        }, "required": ["file_path"]}
    }}
]

TOOL_MAP = {
    "execute_bash": execute_bash,
    "read_file": read_file,
    "write_file": write_file,
    "list_directory": list_directory,
    "remember_fact": remember_fact,
    "recall_facts": recall_facts,
    "read_skill": read_skill,
    "write_daily_log": write_daily_log,
    "restart_self": restart_self,
    "check_syntax": check_syntax,
    "safe_restart": safe_restart,
    "add_scheduled_task": add_scheduled_task,
    "list_scheduled_tasks": list_scheduled_tasks,
    "remove_scheduled_task": remove_scheduled_task,
    "health_check": health_check,
    "restore_from_backup": restore_from_backup,
}


# ============================================================
# CONNECTOR
# ============================================================

class LiteLLMConnector(LLMConnector):
    """LiteLLM connector with tools."""
    
    name = "litellm"
    
    def __init__(self, model: str = GEMINI_MODEL):
        self.model = model
        # Initialize api_base from env (for existing default) 
        # but allow overriding it later
        from config import GEMINI_API_BASE
        self.api_base = GEMINI_API_BASE if GEMINI_API_BASE else None

    def set_model(self, model: str, api_base: str = None):
        """Dynamically switch model and api_base."""
        self.model = model
        self.api_base = api_base
    
    def is_available(self) -> bool:
        return LITELLM_AVAILABLE
    
    def _load_system_prompt(self) -> str:
        """
        Load system prompt — same source as Claude CLI.
        Uses shared prompts.py for consistency.
        """
        from llm.prompts import build_system_context
        return build_system_context()
    
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
        sys_content = system_prompt or self._load_system_prompt()
        messages.append({"role": "system", "content": sys_content})
        
        # History
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        
        # Current message
        messages.append({"role": "user", "content": prompt})
        
        # Agent loop with safety limits
        MAX_TURNS = 25
        tool_calls_count = 0
        MAX_TOOL_CALLS = 50  # Safety limit
        
        for turn in range(MAX_TURNS):
            try:
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "tools": TOOLS,
                    "tool_choice": "auto",
                    "timeout": 120,
                }
                
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
                        
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": func_name,
                            "content": str(result)[:4000]
                        })
                else:
                    # No tool calls = final response
                    return msg.content or "(empty response)"
                    
            except Exception as e:
                log.error(f"[LiteLLM] API Error on turn {turn+1}: {e}")
                # Don't crash on API errors, return error message
                return f"Error: LLM API failed: {str(e)[:200]}"
        
        log.warning(f"[LiteLLM] Max turns ({MAX_TURNS}) reached, {tool_calls_count} tool calls")
        return "I made too many attempts. Please try a simpler request."
