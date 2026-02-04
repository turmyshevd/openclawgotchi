"""
Claude CLI connector.

Note: Claude CLI automatically reads BOT_INSTRUCTIONS.md from cwd (.workspace/).
We only pass user prompt + history. System context comes from the file.
"""

import asyncio
import logging
from typing import Optional

from config import WORKSPACE_DIR, CLAUDE_TIMEOUT
from hardware.system import get_stats_string
from llm.base import LLMConnector, LLMError, RateLimitError
from llm.prompts import build_history_prompt

log = logging.getLogger(__name__)


class ClaudeConnector(LLMConnector):
    """Claude Code CLI connector."""
    
    name = "claude"
    
    def __init__(self):
        self._lock = asyncio.Lock()
    
    def is_available(self) -> bool:
        """Check if Claude CLI is installed."""
        import shutil
        return shutil.which("claude") is not None
    
    async def call(
        self, 
        prompt: str, 
        history: list[dict], 
        system_prompt: Optional[str] = None
    ) -> str:
        """Call Claude CLI."""
        
        # Build full prompt with history
        full_prompt = self._build_prompt(prompt, history, system_prompt)
        
        async with self._lock:
            return await self._execute(full_prompt)
    
    def _build_prompt(
        self, 
        user_message: str, 
        history: list[dict],
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Build prompt for Claude CLI.
        Includes system instructions (personality) + stats + history.
        """
        from llm.prompts import load_bot_instructions
        
        parts = []
        
        # 1. System Instructions (Persona, Rules, Hardware commands)
        instructions = system_prompt or load_bot_instructions()
        parts.append(instructions)
        
        # 2. System Stats (Dynamic context)
        parts.append(f"\n[CURRENT SYSTEM STATUS]\n{get_stats_string()}")
        
        # 3. History
        history_text = build_history_prompt(history)
        if history_text:
            parts.append(history_text)
        
        # 4. Current message
        parts.append(f"\nUser: {user_message}")
        
        return "\n".join(parts)
    
    async def _execute(self, prompt: str) -> str:
        """Execute Claude CLI."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "claude", "-p", "--dangerously-skip-permissions", 
                "--output-format", "text", prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(WORKSPACE_DIR),
            )
            
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), 
                timeout=CLAUDE_TIMEOUT
            )
            
            if proc.returncode != 0:
                err = stderr.decode().strip()
                
                # Detect rate limit
                is_limit = (
                    "limit" in err.lower() or 
                    "429" in err or 
                    "quota" in err.lower() or
                    (proc.returncode == 1 and not err.strip())
                )
                
                if is_limit:
                    log.warning(f"Claude rate limit: {err or 'silent exit'}")
                    raise RateLimitError(f"Rate limit: {err or 'silent exit'}")
                
                log.error(f"Claude error (exit {proc.returncode}): {err}")
                raise LLMError(f"Claude error: {err}")
            
            return stdout.decode().strip()
            
        except asyncio.TimeoutError:
            log.error(f"Claude timeout after {CLAUDE_TIMEOUT}s")
            raise LLMError(f"Timeout after {CLAUDE_TIMEOUT}s")
            
        except FileNotFoundError:
            raise LLMError("Claude CLI not found")
    
    @property
    def lock(self) -> asyncio.Lock:
        """Get the lock for external use."""
        return self._lock
