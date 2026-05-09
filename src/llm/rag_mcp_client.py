"""
Skeleton for future MCP-client integration with an external RAG service.

Today the bot talks to a RAG service via plain REST (`rag_client.py`) which
is small, sync and dependency-light — fits the Pi Zero 2W's RAM budget.
A future Option B would talk to the RAG service's MCP-SSE endpoint instead,
which gives access to whatever tools that server exposes (`rag_search`,
`rag_persist`, `rag_status`, …) dynamically rather than the curated REST
surface this module wraps.

Why it isn't wired in yet:

  - the official `mcp` Python package pulls in `httpx[http2]`, `pydantic`,
    `anyio`, etc. — non-trivial RAM hit on a 512 MB device
  - SSE keeps a long-lived connection open per client, which doesn't play
    nicely with the bot's "spawn-and-die" subprocess pattern for display
    updates and other side jobs
  - REST gets us 90 % of the value (search + persist) at 10 % of the cost

When this gets activated:
  1. add `mcp[cli]>=1.x` to requirements.txt
  2. flesh out `RagMcpClient` below: `__aenter__`, `list_tools`,
     `call_tool(name, args)`, retry/reconnect on SSE drops
  3. extend `litellm_connector.TOOL_MAP` with a generic `rag_mcp_tool`
     dispatcher OR auto-register every advertised MCP tool at startup
  4. honour the same env vars as `rag_client.py` (`RAG_API_URL` /
     `RAG_API_KEY`) but route to the MCP-SSE port (typically 8766)

Until then this module is intentionally a placeholder so `import` doesn't
break and the architectural shape is visible in the source.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Conventional SSE port for RAG-style MCP servers. Kept here so any future
# activator only has to flip a flag rather than hunt constants. Override
# via env or constructor when the actual server uses something else.
DEFAULT_MCP_SSE_PORT = 8766


def is_enabled() -> bool:
    """Always False today — flips on in the future Option B PR."""
    return False


class RagMcpClient:
    """Placeholder. Construct + call methods are stubs that raise."""

    def __init__(self, base_url: str, api_key: str | None = None):
        self.base_url = base_url
        self.api_key = api_key

    async def __aenter__(self):
        raise NotImplementedError("RagMcpClient is a roadmap stub — see module docstring")

    async def __aexit__(self, *exc):
        return False

    async def list_tools(self) -> list[dict]:
        raise NotImplementedError("RagMcpClient is a roadmap stub")

    async def call_tool(self, name: str, args: dict) -> dict:
        raise NotImplementedError("RagMcpClient is a roadmap stub")
