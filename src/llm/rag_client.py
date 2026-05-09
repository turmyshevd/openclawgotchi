"""
Thin REST client for an external RAG (Retrieval-Augmented Generation) service.

The bot itself stays small (Pi Zero 2W) — heavy retrieval / embedding /
reranking lives on a separate host that exposes a HTTP API. This module
is the bot-side glue.

Expected API contract (kept deliberately small so any compatible server
can be swapped in by setting RAG_API_URL):

    POST {RAG_API_URL}/rag/query
        body: {"query": str, "collections": [str], "top_k": int,
               "rerank": bool|null}
        200 → {"query": str, "hits": [{"id", "score", "collection",
                                       "payload": {"chunk_text", "source_path",
                                                   …}}],
               "duration_ms": float, "reranked": bool, …}

    POST {RAG_API_URL}/rag/ingest-text
        body: {"text": str, "title": str, "collection": str,
               "tags": [str], "source_origin": str}
        202 → {"accepted": int, "queued": int, "completed": [...]}

    GET  {RAG_API_URL}/health
        200 → {"status": "ok", "version": str,
               "components": [{"name", "healthy", "latency_ms"}]}

When RAG_API_URL is empty (default) the client is fully disabled and every
public function returns ``None`` / ``"…not configured"`` instead of raising,
so installs without a RAG backend are unaffected. When RAG_API_KEY is set
it's sent as a `Authorization: Bearer …` header on every request.

For an MCP-based (rather than REST) integration, see ``rag_mcp_client.py``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from config import RAG_API_URL, RAG_API_KEY, RAG_DEFAULT_COLLECTIONS

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 8.0


def is_configured() -> bool:
    """True when RAG_API_URL is set in the environment."""
    return bool(RAG_API_URL)


def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if RAG_API_KEY:
        h["Authorization"] = f"Bearer {RAG_API_KEY}"
    return h


def _post(path: str, body: dict, timeout: float = DEFAULT_TIMEOUT_S) -> Optional[dict]:
    """POST JSON, return parsed JSON or None on any failure."""
    if not is_configured():
        return None
    import requests  # already pulled in by litellm

    url = f"{RAG_API_URL}{path}"
    try:
        r = requests.post(url, json=body, headers=_headers(), timeout=timeout)
        if r.status_code >= 400:
            log.warning(f"RAG {path} → HTTP {r.status_code}: {r.text[:200]}")
            return None
        return r.json()
    except Exception as e:
        log.warning(f"RAG {path} unreachable: {e}")
        return None


def query(
    text: str,
    top_k: int = 5,
    collections: Optional[list[str]] = None,
    rerank: Optional[bool] = None,
) -> Optional[dict]:
    """Retrieve top-k snippets relevant to `text`.

    Returns the raw QueryResponse dict (with `hits`, `duration_ms`, …) or
    None if disabled / unreachable. Callers usually format with
    ``format_hits()`` for human / LLM presentation.
    """
    if not text or not text.strip():
        return None
    body = {
        "query": text.strip()[:8192],
        "collections": collections or RAG_DEFAULT_COLLECTIONS,
        "top_k": max(1, min(int(top_k), 50)),
    }
    if rerank is not None:
        body["rerank"] = bool(rerank)
    return _post("/rag/query", body)


def persist(text: str, title: Optional[str] = None, tags: Optional[list[str]] = None,
            collection: Optional[str] = None) -> Optional[dict]:
    """Ingest a single markdown-ish text into the vault. Best-effort persistence.

    Used for agent reflections, captured notes, etc. Returns the ingest
    response dict or None on failure.
    """
    if not text or not text.strip():
        return None
    body: dict[str, Any] = {"text": text.strip()[:50000]}
    if title:
        body["title"] = title.strip()[:200]
    if tags:
        body["tags"] = [t.strip() for t in tags if t and t.strip()][:20]
    if collection:
        body["collection"] = collection
    elif RAG_DEFAULT_COLLECTIONS:
        body["collection"] = RAG_DEFAULT_COLLECTIONS[0]
    return _post("/rag/ingest-text", body, timeout=20.0)


def format_hits(response: dict, max_chars: int = 2000) -> str:
    """Render a QueryResponse for human / LLM consumption.

    Pulls ``payload.chunk_text`` (or ``payload.text``) plus source path
    and score. Truncated to ``max_chars`` so it fits the bot's Telegram +
    LLM message budget.
    """
    if not response or not response.get("hits"):
        return "(no relevant snippets)"

    parts: list[str] = []
    for i, hit in enumerate(response["hits"], start=1):
        payload = hit.get("payload") or {}
        chunk = (payload.get("chunk_text") or payload.get("text") or "").strip()
        source = payload.get("source_path") or payload.get("origin_file_name") or "?"
        score = hit.get("score") or hit.get("rerank_score") or hit.get("rrf_score") or 0.0
        # Compact source: just the file name, no full path
        src_short = str(source).rsplit("/", 1)[-1]
        parts.append(f"#{i} [{src_short}] (score={score:.3f})\n{chunk[:600]}")

    out = "\n\n".join(parts)
    if len(out) > max_chars:
        out = out[: max_chars - 1] + "…"
    return out


def health() -> Optional[dict]:
    """Probe ``/health`` — returns parsed body or None when unreachable."""
    if not is_configured():
        return None
    import requests
    try:
        r = requests.get(f"{RAG_API_URL}/health", headers=_headers(), timeout=4.0)
        if r.ok:
            return r.json()
    except Exception as e:
        log.debug(f"RAG /health unreachable: {e}")
    return None
