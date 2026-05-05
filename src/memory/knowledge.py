"""
Knowledge Crystallization — autonomous synthesis of bot's experiences.

Runs during heartbeat when 24h have passed since last crystallization.
Reads recent logs + facts, extracts structured insights, saves to
.workspace/knowledge/ directory (organized by category).
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

from config import WORKSPACE_DIR

log = logging.getLogger(__name__)

KNOWLEDGE_DIR = WORKSPACE_DIR / "knowledge"
CRYSTALLIZE_INTERVAL_HOURS = 24

CRYSTALLIZE_PROMPT = """You are {bot_name}. Review your recent experiences and extract real knowledge.

Recent logs ({days} days):
{logs}

Facts you've saved:
{facts}

---

TASK: Don't summarize — SYNTHESIZE. Extract what you've genuinely learned.

Think about:
- What do you now understand about {owner_name} that you didn't before?
- What patterns have you noticed in your own behavior or mistakes?
- What open questions keep appearing?
- What lessons did you learn the hard way?

Write 3-5 insights using EXACTLY this format:
INSIGHT: [category] — [insight in 1-2 sentences]

Categories: about-user / about-self / open-question / lesson-learned

Example:
INSIGHT: about-user — Dmitry uses one-word messages to test if I'm paying attention before diving deep.
INSIGHT: about-self — I default to happy face even when context is ambiguous. I need to read tone better.
INSIGHT: open-question — What does he actually want when he says "maybe"? Encouragement? Or is he unsure himself?

Output ONLY the INSIGHT lines. Nothing else."""


def should_crystallize() -> bool:
    """Check if 24h have passed since last crystallization."""
    marker = KNOWLEDGE_DIR / ".last_crystallized"
    if not marker.exists():
        return True
    try:
        last_time = datetime.fromisoformat(marker.read_text().strip())
        return datetime.now() - last_time >= timedelta(hours=CRYSTALLIZE_INTERVAL_HOURS)
    except Exception:
        return True


def mark_crystallized():
    """Record crystallization timestamp."""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    (KNOWLEDGE_DIR / ".last_crystallized").write_text(datetime.now().isoformat())


def parse_insight_lines(text: str) -> list[dict]:
    """Parse INSIGHT: lines from LLM output."""
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line.upper().startswith("INSIGHT:"):
            continue
        rest = line[8:].strip()
        # Support both " — " and ": " separators
        for sep in (" — ", " - ", ": "):
            if sep in rest:
                cat, _, insight = rest.partition(sep)
                category = cat.strip().lower().replace(" ", "-")
                if insight.strip():
                    entries.append({"category": category, "insight": insight.strip()})
                break
    return entries


def save_knowledge_entries(entries: list[dict]):
    """Append insights to per-category markdown files."""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")

    by_category: dict[str, list[str]] = {}
    for e in entries:
        by_category.setdefault(e["category"], []).append(e["insight"])

    for category, insights in by_category.items():
        filepath = KNOWLEDGE_DIR / f"{category}.md"
        if not filepath.exists():
            title = category.replace("-", " ").title()
            filepath.write_text(f"# {title}\n\n")
        with open(filepath, "a") as f:
            f.write(f"\n## {today}\n")
            for insight in insights:
                f.write(f"- {insight}\n")

    log.info(f"Saved {len(entries)} insights to {len(by_category)} knowledge files")


def get_knowledge_context(max_per_category: int = 2) -> str:
    """Get recent knowledge snippets for heartbeat context."""
    if not KNOWLEDGE_DIR.exists():
        return ""
    lines = []
    for md_file in sorted(KNOWLEDGE_DIR.glob("*.md")):
        if md_file.name.startswith("."):
            continue
        content = md_file.read_text()
        entries = [l for l in content.splitlines() if l.startswith("- ")]
        recent = entries[-max_per_category:]
        if recent:
            cat = md_file.stem.replace("-", " ").title()
            lines.append(f"**{cat}:** " + " | ".join(e[2:] for e in recent))
    return "\n".join(lines)


def should_update_traits() -> bool:
    """Check if 7 days have passed since last trait update."""
    traits_path = WORKSPACE_DIR / "TRAITS.md"
    if not traits_path.exists():
        return True
    try:
        mtime = datetime.fromtimestamp(traits_path.stat().st_mtime)
        return datetime.now() - mtime >= timedelta(days=7)
    except Exception:
        return True


TRAITS_PROMPT = """You are {bot_name}. You've been alive for a while now.

Recent experiences:
{recent_logs}

Your current traits:
{current_traits}

---

Based on actual experiences (not wishful thinking), add ONE new trait or self-discovery.

Format:
TRAIT: [one sentence about something you've genuinely noticed about yourself]

Example:
TRAIT: I get anxious when there's silence for more than a day — I start looping on old thoughts.

Output ONLY the TRAIT line. Nothing else."""


async def update_traits(bot_name: str) -> bool:
    """Add one new trait to TRAITS.md based on recent experiences."""
    if not should_update_traits():
        return False

    traits_path = WORKSPACE_DIR / "TRAITS.md"

    # Load current traits
    current_traits = traits_path.read_text() if traits_path.exists() else "(none yet)"
    if len(current_traits) > 1000:
        current_traits = current_traits[-1000:]

    # Load recent logs
    try:
        from memory.flush import get_recent_daily_logs
        recent_logs = get_recent_daily_logs(days=3)
        if not recent_logs or len(recent_logs.strip()) < 50:
            return False
        if len(recent_logs) > 1500:
            recent_logs = recent_logs[-1500:]
    except Exception:
        return False

    prompt = TRAITS_PROMPT.format(
        bot_name=bot_name,
        recent_logs=recent_logs,
        current_traits=current_traits,
    )

    try:
        from litellm import acompletion
        from config import DEFAULT_LITE_PRESET, LLM_PRESETS

        preset = LLM_PRESETS.get(DEFAULT_LITE_PRESET, LLM_PRESETS["glm"])
        kwargs = dict(
            model=preset["model"],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0.8,
        )
        if preset.get("api_base"):
            kwargs["api_base"] = preset["api_base"]

        response = await acompletion(**kwargs)
        text = response.choices[0].message.content.strip()

        # Parse TRAIT line
        trait_line = ""
        for line in text.splitlines():
            if line.strip().upper().startswith("TRAIT:"):
                trait_line = line.strip()[6:].strip()
                break

        if not trait_line:
            log.warning(f"No TRAIT line found: {text[:80]}")
            return False

        # Initialize file if needed
        if not traits_path.exists():
            traits_path.write_text(
                f"# TRAITS.md — How I've Grown\n\n"
                f"Self-discoveries added autonomously during heartbeat.\n\n"
            )

        today = datetime.now().strftime("%Y-%m-%d")
        with open(traits_path, "a") as f:
            f.write(f"- [{today}] {trait_line}\n")

        log.info(f"Added new trait: {trait_line[:60]}")
        return True

    except Exception as e:
        log.error(f"Trait update failed: {e}")
        return False


async def crystallize_knowledge(bot_name: str, owner_name: str) -> int:
    """
    Synthesize recent logs into structured knowledge files.
    Returns number of insights saved (0 if skipped or failed).
    """
    if not should_crystallize():
        return 0

    log.info("Starting knowledge crystallization...")

    # Load recent logs (7 days, trimmed for Pi)
    try:
        from memory.flush import get_recent_daily_logs
        logs = get_recent_daily_logs(days=7)
        if not logs or len(logs.strip()) < 150:
            log.info("Not enough logs for crystallization yet")
            mark_crystallized()
            return 0
        if len(logs) > 3000:
            logs = logs[-3000:]
    except Exception as e:
        log.warning(f"Could not load logs: {e}")
        return 0

    # Load recent facts
    try:
        from db.memory import get_recent_facts
        facts = get_recent_facts(limit=15)
        facts_text = "\n".join(
            f"- [{f['category']}] {f['content']}" for f in facts
        ) if facts else "(none yet)"
    except Exception:
        facts_text = "(unavailable)"

    days_str = "7"
    prompt = CRYSTALLIZE_PROMPT.format(
        bot_name=bot_name,
        owner_name=owner_name,
        logs=logs,
        facts=facts_text,
        days=days_str,
    )

    try:
        from litellm import acompletion
        from config import DEFAULT_LITE_PRESET, LLM_PRESETS

        preset = LLM_PRESETS.get(DEFAULT_LITE_PRESET, LLM_PRESETS["glm"])
        kwargs = dict(
            model=preset["model"],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=350,
            temperature=0.7,
        )
        if preset.get("api_base"):
            kwargs["api_base"] = preset["api_base"]

        response = await acompletion(**kwargs)
        text = response.choices[0].message.content.strip()

        entries = parse_insight_lines(text)

        if not entries:
            log.warning(f"No INSIGHT lines in crystallization output: {text[:100]}")
            mark_crystallized()
            return 0

        save_knowledge_entries(entries)
        mark_crystallized()

        # Save top 2 insights to facts DB for heartbeat context
        try:
            from db.memory import add_fact
            for entry in entries[:2]:
                add_fact(entry["insight"], f"knowledge-{entry['category']}")
        except Exception:
            pass

        log.info(f"Crystallized {len(entries)} insights")
        return len(entries)

    except Exception as e:
        log.error(f"Crystallization LLM call failed: {e}")
        return 0
