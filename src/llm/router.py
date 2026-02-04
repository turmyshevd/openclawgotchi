"""
LLM Router — auto-fallback between Claude and LiteLLM.
"""

import logging
from typing import Optional

from llm.base import LLMConnector, LLMError, RateLimitError
from llm.claude import ClaudeConnector
from llm.litellm_connector import LiteLLMConnector

log = logging.getLogger(__name__)


class LLMRouter:
    """
    Routes requests to available LLM.
    - Lite mode (default): LiteLLM/Gemini only
    - Pro mode: Claude only, no fallback (rate limits bubble up)
    """
    
    def __init__(self):
        self.claude = ClaudeConnector()
        self.litellm = LiteLLMConnector()
        self.force_lite = True  # Default: Lite mode (Gemini)
    
    async def call(
        self, 
        prompt: str, 
        history: list[dict],
        system_prompt: Optional[str] = None
    ) -> tuple[str, str]:
        """
        Call LLM based on current mode.
        
        Returns:
            tuple: (response_text, connector_name)
        """
        
        # LITE MODE: LiteLLM only
        if self.force_lite:
            if not self.litellm.is_available():
                raise LLMError("LiteLLM not available")
            response = await self.litellm.call(prompt, history, system_prompt)
            return response, "litellm"
        
        # PRO MODE: Claude only, no fallback
        if not self.claude.is_available():
            raise LLMError("Claude CLI not found. Install it or use /pro for Lite mode.")
        
        # Claude call - let RateLimitError bubble up for queueing
        response = await self.claude.call(prompt, history, system_prompt)
        return response, "claude"
    
    def toggle_lite_mode(self) -> bool:
        """Toggle between Lite and Pro mode. Returns new state (True=Lite)."""
        self.force_lite = not self.force_lite
        log.info(f"Mode switched to: {'Lite' if self.force_lite else 'Pro'}")
        return self.force_lite
    
    @property
    def lock(self):
        """Get Claude's lock for exclusive access."""
        return self.claude.lock


# Global instance
_router: Optional[LLMRouter] = None


def get_router() -> LLMRouter:
    """Get or create the global router instance."""
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router


# Convenience alias
def get_llm() -> LLMRouter:
    """Alias for get_router()."""
    return get_router()
