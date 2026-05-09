"""
Minimal MCP-over-SSE client for openclawgotchi.

Why hand-rolled instead of `mcp[cli]`?
  The official PyPI `mcp` package pulls in `cryptography` (~4.7 MB),
  `pydantic-settings`, `starlette`, `uvicorn`, `pyjwt`, `httpx-sse`,
  `sse-starlette`, `python-multipart` — non-trivial RAM hit on the
  Pi Zero 2W (512 MB total, ~50 MB headroom in practice). This module
  speaks just enough of the MCP spec to do `initialize` + `tools/list`
  + `tools/call` against an SSE-transport server, using only `requests`
  (already in the venv via litellm) plus a small SSE-line parser.

Wire protocol it speaks:
  GET  {base_url}/sse                   — long-poll SSE stream
       first event: ``event: endpoint\\ndata: /messages?session_id=…``
                    (relative to base_url)
       further events: ``event: message\\ndata: <JSON-RPC response>``
  POST {endpoint_url}                   — send JSON-RPC requests
       body: {"jsonrpc":"2.0","id":<n>,"method":<m>,"params":<p>}

Public surface:
  client = MCPSSEClient(base_url, api_key=None)
  client.connect()        # opens SSE, waits for endpoint
  client.initialize()     # MCP handshake
  tools = client.list_tools()
  result = client.call_tool(name, {arg: value, ...})
  client.close()

All synchronous — designed to slot into the bot's existing sync
TOOL_MAP dispatcher in litellm_connector.py without async plumbing.

Activation is gated by env var ``RAG_MCP_URL`` — set it to the
MCP-SSE base URL (e.g. ``http://your-rag-host:8766``). REST and MCP
transports run side-by-side: configure ``RAG_REST_URL`` for the REST
endpoint and ``RAG_MCP_URL`` for the MCP gateway, both can be active
at once. Legacy single-URL deployments using ``RAG_API_URL`` +
``RAG_TRANSPORT=mcp`` still work via the compat shim in ``config.py``.
When the MCP server is unreachable, callers fall back to None / empty
results so the bot stays alive.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Optional

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 15.0
DEFAULT_PROTOCOL_VERSION = "2024-11-05"


def _resolve_mcp_url() -> str:
    """Return the configured MCP-SSE base URL, honouring the legacy alias.

    Priority:
      1. ``RAG_MCP_URL`` (the canonical, post-split env var).
      2. ``RAG_API_URL`` when ``RAG_TRANSPORT=mcp`` (legacy deployments
         from before the split — kept working without config edits).
    """
    url = os.environ.get("RAG_MCP_URL", "").strip().rstrip("/")
    if url:
        return url
    legacy = os.environ.get("RAG_API_URL", "").strip().rstrip("/")
    if legacy and os.environ.get("RAG_TRANSPORT", "rest").strip().lower() == "mcp":
        return legacy
    return ""


def is_enabled() -> bool:
    """True when an MCP-SSE base URL is configured (new var or legacy)."""
    return bool(_resolve_mcp_url())


class MCPSSEClient:
    """Thread-safe synchronous MCP client over SSE.

    A single background thread reads the SSE stream and routes
    JSON-RPC responses back to whichever caller invoked the matching
    request id. Notifications are silently dropped — we don't act on
    server-pushed events today.
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_S,
        client_name: str = "openclawgotchi",
        client_version: str = "0.1",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.client_name = client_name
        self.client_version = client_version

        # Lazy import — keeps module-import cheap even if the bot never
        # actually opens an MCP connection.
        import requests
        self._requests = requests
        self._session = requests.Session()

        self._endpoint_url: Optional[str] = None
        self._endpoint_event = threading.Event()
        self._responses: dict[int, dict] = {}
        self._response_events: dict[int, threading.Event] = {}
        self._next_id = 1
        self._id_lock = threading.Lock()
        self._stop = threading.Event()
        self._sse_thread: Optional[threading.Thread] = None
        self._initialized = False
        self._init_lock = threading.Lock()

    # ---- internals -------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json, text/event-stream"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _next_request_id(self) -> int:
        with self._id_lock:
            i = self._next_id
            self._next_id += 1
            return i

    def _sse_loop(self) -> None:
        """Read the SSE stream forever (until close()) and dispatch messages."""
        url = f"{self.base_url}/sse"
        try:
            r = self._session.get(
                url,
                headers=self._headers(),
                stream=True,
                timeout=(self.timeout, None),  # connect timeout, then no read timeout
            )
            r.raise_for_status()
            event_type: Optional[str] = None
            data_buf: list[str] = []
            for raw_line in r.iter_lines(decode_unicode=True):
                if self._stop.is_set():
                    break
                if raw_line is None:
                    continue
                line = raw_line.rstrip("\r")
                if line == "":
                    # Dispatch the buffered event.
                    if event_type and data_buf:
                        self._dispatch(event_type, "\n".join(data_buf))
                    event_type = None
                    data_buf = []
                    continue
                if line.startswith(":"):
                    # Comment / heartbeat.
                    continue
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    data_buf.append(line[5:].lstrip(" "))
        except Exception as e:
            log.warning(f"MCP SSE stream closed: {e}")
        finally:
            # Wake any pending callers so they don't hang forever.
            for evt in self._response_events.values():
                evt.set()

    def _dispatch(self, event_type: str, data: str) -> None:
        if event_type == "endpoint":
            # Server tells us where to POST messages. Path may be relative.
            ep = data if data.startswith(("http://", "https://")) else f"{self.base_url}{data}"
            self._endpoint_url = ep
            self._endpoint_event.set()
            log.debug(f"MCP endpoint: {ep}")
            return
        if event_type == "message":
            try:
                msg = json.loads(data)
            except Exception as e:
                log.warning(f"MCP non-JSON message: {e}")
                return
            msg_id = msg.get("id")
            if msg_id is None:
                # Notification. Today we ignore these.
                return
            if msg_id in self._response_events:
                self._responses[msg_id] = msg
                self._response_events[msg_id].set()

    def _request(self, method: str, params: Optional[dict] = None) -> Any:
        if self._endpoint_url is None:
            raise RuntimeError("MCP client not connected (call .connect() first)")
        req_id = self._next_request_id()
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            body["params"] = params

        evt = threading.Event()
        self._response_events[req_id] = evt
        try:
            r = self._session.post(
                self._endpoint_url,
                json=body,
                headers=self._headers(),
                timeout=self.timeout,
            )
            if r.status_code >= 400:
                raise RuntimeError(f"MCP {method} HTTP {r.status_code}: {r.text[:200]}")
            if not evt.wait(timeout=self.timeout):
                raise TimeoutError(f"MCP {method}: no response within {self.timeout}s")
            resp = self._responses.pop(req_id, None)
            if resp is None:
                raise RuntimeError(f"MCP {method}: stream closed before response")
            if "error" in resp:
                raise RuntimeError(f"MCP {method} error: {resp['error']}")
            return resp.get("result")
        finally:
            self._response_events.pop(req_id, None)

    def _notify(self, method: str, params: Optional[dict] = None) -> None:
        if self._endpoint_url is None:
            raise RuntimeError("MCP client not connected")
        body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        try:
            self._session.post(
                self._endpoint_url,
                json=body,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except Exception as e:
            log.warning(f"MCP notification {method} failed: {e}")

    # ---- public API ------------------------------------------------------

    def connect(self) -> None:
        """Open the SSE stream and wait for the server's endpoint event."""
        if self._sse_thread is not None and self._sse_thread.is_alive():
            return
        self._stop.clear()
        self._endpoint_event.clear()
        self._sse_thread = threading.Thread(
            target=self._sse_loop,
            daemon=True,
            name="mcp-sse-reader",
        )
        self._sse_thread.start()
        if not self._endpoint_event.wait(timeout=self.timeout):
            self.close()
            raise TimeoutError(f"MCP {self.base_url}/sse: no endpoint event within {self.timeout}s")

    def initialize(self) -> dict:
        """Run the MCP `initialize` handshake. Idempotent."""
        with self._init_lock:
            if self._initialized:
                return {"already": True}
            result = self._request("initialize", {
                "protocolVersion": DEFAULT_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": self.client_name, "version": self.client_version},
            })
            # Required notification per MCP spec.
            self._notify("notifications/initialized")
            self._initialized = True
            return result

    def list_tools(self) -> list[dict]:
        """Return list of tools the server advertises."""
        if not self._initialized:
            self.initialize()
        result = self._request("tools/list")
        return list(result.get("tools", [])) if isinstance(result, dict) else []

    def call_tool(self, name: str, arguments: Optional[dict] = None) -> dict:
        """Call a tool by name. Returns the raw MCP `tools/call` result dict."""
        if not self._initialized:
            self.initialize()
        return self._request("tools/call", {
            "name": name,
            "arguments": arguments or {},
        })

    def close(self) -> None:
        """Stop the SSE reader and clean up. Safe to call multiple times."""
        self._stop.set()
        try:
            self._session.close()
        except Exception:
            pass
        self._endpoint_url = None
        self._initialized = False


# ---- module-level convenience: a singleton client lazily reused ---------

_singleton: Optional[MCPSSEClient] = None
_singleton_lock = threading.Lock()


def get_client() -> Optional[MCPSSEClient]:
    """Return a connected, initialized MCPSSEClient, or None when disabled.

    On first call (per process) this opens the SSE stream and runs
    `initialize`. Subsequent calls reuse the same client. If the
    server is unreachable, returns None (callers fall back).
    """
    base = _resolve_mcp_url()
    if not base:
        return None
    api_key = os.environ.get("RAG_API_KEY", "") or None

    global _singleton
    with _singleton_lock:
        if _singleton is None:
            try:
                client = MCPSSEClient(base, api_key=api_key)
                client.connect()
                client.initialize()
                _singleton = client
            except Exception as e:
                log.warning(f"MCP client setup failed ({base}): {e}")
                return None
        return _singleton


def extract_text_content(call_result: dict) -> str:
    """Pull a printable string out of an MCP `tools/call` result.

    MCP results have a `content` array of typed parts. We concatenate
    text parts; non-text parts are summarised by their type.
    """
    if not isinstance(call_result, dict):
        return str(call_result)
    parts = call_result.get("content")
    if not isinstance(parts, list):
        return json.dumps(call_result)[:2000]
    out: list[str] = []
    for p in parts:
        if not isinstance(p, dict):
            continue
        t = p.get("type")
        if t == "text":
            out.append(str(p.get("text", "")))
        else:
            out.append(f"[{t}]")
    return "\n".join(out).strip()
