"""
Markdown vault helpers for Obsidian-style knowledge capture.

Source of truth: .workspace/knowledge/
No hardcoded taxonomy. The model supplies project/topic/tags as needed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import DEFAULT_LITE_PRESET, LLM_PRESETS, WORKSPACE_DIR

VAULT_DIR = WORKSPACE_DIR / "knowledge"
INBOX_DIR = VAULT_DIR / "inbox"
NOTES_DIR = VAULT_DIR / "notes"
PROJECTS_DIR = VAULT_DIR / "projects"
TOPICS_DIR = VAULT_DIR / "topics"
INDEX_PATH = VAULT_DIR / "INDEX.md"


@dataclass
class VaultResult:
    note_path: Path
    inbox_path: Path
    index_path: Path
    title: str
    note_type: str
    summary: str


@dataclass
class VaultTriage:
    kind: str
    reason: str
    confidence: float = 0.0


def _ensure_vault() -> None:
    for path in (VAULT_DIR, INBOX_DIR, NOTES_DIR, PROJECTS_DIR, TOPICS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def _slugify(text: str, fallback: str = "memo") -> str:
    slug = re.sub(r"[^\w]+", "-", (text or "").strip().lower(), flags=re.UNICODE)
    slug = slug.strip("-")
    return slug[:80] or fallback


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        item = str(item).strip()
        if item and item not in cleaned:
            cleaned.append(item[:300])
    return cleaned


def _yaml_quote(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _yaml_list(key: str, values: list[str]) -> str:
    if not values:
        return f"{key}: []\n"
    lines = [f"{key}:"]
    lines.extend(f"  - {_yaml_quote(value)}" for value in values)
    return "\n".join(lines) + "\n"


def _resolve_within_vault(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = VAULT_DIR / p
    p = p.resolve()
    if VAULT_DIR not in p.parents and p != VAULT_DIR:
        raise ValueError("Path must stay inside .workspace/knowledge")
    return p


def _append_inbox(raw_text: str, source: str, created_at: str) -> Path:
    day = created_at[:10]
    inbox_path = INBOX_DIR / f"{day}.md"
    if not inbox_path.exists():
        inbox_path.write_text(f"# Inbox {day}\n\n", encoding="utf-8")

    with open(inbox_path, "a", encoding="utf-8") as f:
        f.write(
            f"## {created_at[11:16]} [{source}]\n\n"
            f"{raw_text.strip()}\n\n"
        )
    return inbox_path


def _render_note(
    *,
    title: str,
    note_type: str,
    summary: str,
    raw_text: str,
    created_at: str,
    source: str,
    project: str = "",
    topic: str = "",
    tags: Optional[list[str]] = None,
    links: Optional[list[str]] = None,
    body: str = "",
) -> str:
    tags = _as_list(tags)
    links = _as_list(links)
    project_link = f"[[projects/{_slugify(project)}]]" if project else ""
    topic_link = f"[[topics/{_slugify(topic)}]]" if topic else ""
    for link in (project_link, topic_link):
        if link and link not in links:
            links.append(link)

    body_parts = [summary.strip()] if summary.strip() else []
    if body.strip():
        body_parts.append(body.strip())
    if raw_text.strip():
        body_parts.append("## Raw\n" + raw_text.strip())

    rendered_body = "\n\n".join(body_parts) if body_parts else raw_text.strip()
    links_block = "\n".join(f"- {link}" for link in links) if links else "- [[topics/inbox]]"

    return (
        "---\n"
        f"id: {_yaml_quote(created_at.replace(':', '').replace('T', '-'))}\n"
        f"type: {_yaml_quote('vault-note')}\n"
        f"note_type: {_yaml_quote(note_type)}\n"
        f"created: {_yaml_quote(created_at)}\n"
        f"source: {_yaml_quote(source)}\n"
        f"project: {_yaml_quote(project)}\n"
        f"topic: {_yaml_quote(topic)}\n"
        f"status: \"seedling\"\n"
        f"{_yaml_list('tags', tags)}"
        "---\n\n"
        f"# {title}\n\n"
        f"{rendered_body}\n\n"
        f"## Links\n{links_block}\n"
    )


def _touch_collection_page(directory: Path, name: str, note_link: str) -> None:
    if not name:
        return
    directory.mkdir(parents=True, exist_ok=True)
    page_path = directory / f"{_slugify(name)}.md"
    if not page_path.exists():
        page_path.write_text(f"# {name}\n\n## Notes\n\n", encoding="utf-8")
    content = page_path.read_text(encoding="utf-8")
    if note_link not in content:
        if not content.endswith("\n"):
            content += "\n"
        content += f"- {note_link}\n"
        page_path.write_text(content, encoding="utf-8")


def _update_index() -> None:
    notes = sorted(NOTES_DIR.glob("*.md"), reverse=True)[:40]
    lines = [
        "# Knowledge Vault",
        "",
        "Obsidian-compatible knowledge captured from chat.",
        "",
        "## Recent Notes",
        "",
    ]
    if notes:
        for note in notes:
            lines.append(f"- [[notes/{note.stem}|{note.stem}]]")
    else:
        lines.append("_No notes yet._")
    INDEX_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fallback_triage(text: str) -> VaultTriage:
    stripped = (text or "").strip()
    if not stripped:
        return VaultTriage("casual", "empty", 1.0)
    if stripped.startswith("/"):
        return VaultTriage("direct_command", "slash command", 1.0)
    if "?" in stripped:
        return VaultTriage("question", "question mark fallback", 0.4)
    if len(stripped) <= 4 and stripped.islower():
        return VaultTriage("casual", "short lowercase ack", 0.3)
    return VaultTriage("casual", "fallback default", 0.2)


async def classify_message_for_vault(
    text: str,
    context_messages: Optional[list[dict]] = None,
) -> VaultTriage:
    """Classify a message as direct_command, question, memo, or casual."""
    stripped = (text or "").strip()
    if not stripped:
        return _fallback_triage(text)

    context_lines = []
    for msg in (context_messages or [])[-6:]:
        role = msg.get("role", "unknown")
        content = str(msg.get("content", ""))[:240]
        if content:
            context_lines.append(f"{role}: {content}")
    context_block = "\n".join(context_lines) if context_lines else "(none)"

    prompt = f"""Classify the owner's latest message for a project-knowledge Telegram bot.

Return ONLY valid JSON:
{{
  "kind": "direct_command | question | memo | casual",
  "confidence": 0.0,
  "reason": "short reason"
}}

Meanings:
- direct_command: the owner wants the bot to do something now, excluding requests to save/capture something for later.
- question: the owner expects an answer or design discussion.
- memo: project knowledge, content idea, metric, fragment, claim, note, task-to-remember, quote, positioning thought, or an explicit request to save/capture/remember that information.
- casual: acknowledgement or social filler with no project knowledge.

Priority:
1. If it asks the bot to act now, choose direct_command, unless the action is specifically to save/capture/remember the message.
2. If it asks the bot for an answer, choose question.
3. If it looks like a fragment to preserve, choose memo.
4. If uncertain between memo and casual, choose casual.

Recent context:
{context_block}

Latest message:
{stripped}
"""
    try:
        from litellm import acompletion

        preset = LLM_PRESETS.get(DEFAULT_LITE_PRESET, LLM_PRESETS["glm"])
        kwargs = {
            "model": preset["model"],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 180,
            "timeout": 20,
        }
        if preset.get("api_base"):
            kwargs["api_base"] = preset["api_base"]

        response = await acompletion(**kwargs)
        raw = response.choices[0].message.content or ""
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise ValueError("Classifier returned no JSON")
        data = json.loads(match.group(0))
        kind = str(data.get("kind", "")).strip()
        if kind not in {"direct_command", "question", "memo", "casual"}:
            raise ValueError(f"Invalid classification kind: {kind}")
        confidence = float(data.get("confidence", 0.0) or 0.0)
        reason = str(data.get("reason", "")).strip()[:200] or "llm classification"
        return VaultTriage(kind, reason, max(0.0, min(1.0, confidence)))
    except Exception:
        return _fallback_triage(text)


def capture_note(
    *,
    title: str,
    raw_text: str,
    summary: str = "",
    body: str = "",
    source: str = "telegram",
    note_type: str = "memo",
    project: str = "",
    topic: str = "",
    tags: Optional[list[str]] = None,
    links: Optional[list[str]] = None,
) -> VaultResult:
    """Write a note into the vault and keep the index synchronized."""
    _ensure_vault()
    created_at = datetime.now().isoformat(timespec="seconds")
    inbox_path = _append_inbox(raw_text, source, created_at)

    slug = _slugify(title)
    note_path = NOTES_DIR / f"{created_at[:10]}-{created_at[11:19].replace(':', '')}-{slug}.md"
    note_path.write_text(
        _render_note(
            title=title,
            note_type=note_type,
            summary=summary,
            raw_text=raw_text,
            body=body,
            created_at=created_at,
            source=source,
            project=project,
            topic=topic,
            tags=tags,
            links=links,
        ),
        encoding="utf-8",
    )

    note_link = f"[[notes/{note_path.stem}|{title}]]"
    _touch_collection_page(PROJECTS_DIR, project, note_link)
    _touch_collection_page(TOPICS_DIR, topic, note_link)
    _update_index()

    return VaultResult(
        note_path=note_path,
        inbox_path=inbox_path,
        index_path=INDEX_PATH,
        title=title,
        note_type=note_type,
        summary=summary,
    )


def read_vault_file(path: str) -> str:
    """Read a vault file, keeping access scoped to .workspace/knowledge."""
    _ensure_vault()
    try:
        p = _resolve_within_vault(path)
        if not p.exists():
            return f"File not found: {path}"
        if p.stat().st_size > 100 * 1024:
            return "File too large (>100KB)."
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"Error: {e}"


def list_vault(path: str = ".") -> str:
    """List a vault directory."""
    _ensure_vault()
    try:
        p = _resolve_within_vault(path)
        if not p.exists():
            return f"Not found: {path}"
        if not p.is_dir():
            return f"Not a directory: {path}"
        items = []
        for item in sorted(p.iterdir()):
            items.append(f"  {item.name}{'/' if item.is_dir() else ''}")
        return f"{p}/\n" + "\n".join(items) if items else f"{p}/ (empty)"
    except Exception as e:
        return f"Error: {e}"


def search_vault(query: str, limit: int = 10) -> str:
    """Search markdown files in the vault for a query."""
    _ensure_vault()
    query = (query or "").strip()
    if not query:
        return "Error: query required"

    results: list[str] = []
    query_lower = query.lower()
    for path in sorted(VAULT_DIR.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        lower = text.lower()
        idx = lower.find(query_lower)
        if idx < 0:
            continue
        start = max(0, idx - 80)
        end = min(len(text), idx + len(query) + 120)
        snippet = text[start:end].replace("\n", " ").strip()
        results.append(f"- {path.relative_to(VAULT_DIR)}: {snippet}")
        if len(results) >= limit:
            break

    return "\n".join(results) if results else f"No vault matches for: {query}"


def get_vault_stats(limit: int = 5) -> dict:
    """Return lightweight vault stats for UI commands."""
    _ensure_vault()
    notes = sorted(NOTES_DIR.glob("*.md"), reverse=True)
    inbox = sorted(INBOX_DIR.glob("*.md"), reverse=True)
    return {
        "vault_dir": VAULT_DIR,
        "index_path": INDEX_PATH,
        "notes_count": len(notes),
        "inbox_days": len(inbox),
        "recent": notes[:limit],
    }
