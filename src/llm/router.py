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
    Falls back from Claude to LiteLLM on rate limits.
    """
    
    def __init__(self):
        self.claude = ClaudeConnector()
        self.litellm = LiteLLMConnector()
        self.force_lite = True  # Manual lite mode toggle (Default: ON)
    
    async def call(
        self, 
        prompt: str, 
        history: list[dict],
        system_prompt: Optional[str] = None
    ) -> tuple[str, str]:
        """
        Call LLM with automatic fallback.
        
        Returns:
            tuple: (response_text, connector_name)
        """
        
        # Force lite mode
        if self.force_lite:
            if not self.litellm.is_available():
                raise LLMError("LiteLLM not available")
            response = await self.litellm.call(prompt, history, system_prompt)
            return response, "litellm"
        
        # Try Claude first
        if self.claude.is_available():
            try:
                response = await self.claude.call(prompt, history, system_prompt)
                return response, "claude"
            except RateLimitError:
                log.warning("Claude rate limited, falling back to LiteLLM")
        
        # Fallback to LiteLLM
        if self.litellm.is_available():
            response = await self.litellm.call(prompt, history, system_prompt)
            return response, "litellm"
        
        raise LLMError("No LLM available")
    
    def toggle_lite_mode(self) -> bool:
        """Toggle force lite mode. Returns new state."""
        self.force_lite = not self.force_lite
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
