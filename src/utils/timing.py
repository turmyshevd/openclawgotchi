"""
Time-awareness helpers.

The bot is configured to operate in a single timezone (default
``Europe/Berlin``) and never reasons about UTC vs local internally —
``timedatectl`` is set once at install time and every ``datetime.now()``
returns the right wall-clock value. Two responsibilities live here:

  1. ``now_ts()`` — produce the canonical timestamp string used for
     message/log/vault entries. Format ``dd_mm_yyyy-hh_mm_ss`` (DE
     convention with underscore separators), e.g. ``09_05_2026-17_15_42``.
     Easier to grep and sort lexicographically per-day than the more
     common ISO form, and lossless to parse back via ``parse_ts()``.

  2. Quiet schedule — a tiny JSON file (``data/quiet_schedule.json``,
     gitignored, backed up by scripts/auto_update.sh) that tells the
     bot which 24h spans are silent / quiet / normal / chatty. The
     heartbeat scheduler checks ``current_verbosity()`` before firing
     so the bot doesn't ping the owner at 03:00 unless explicitly
     allowed. Spans are simple ``{from, to, verbosity}`` triples; gaps
     fall back to ``default_verbosity``.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

TS_FORMAT = "%d_%m_%Y-%H_%M_%S"

# Verbosity levels the schedule maps onto. Higher = more proactive.
SILENT = 0     # heartbeat skipped, no autonomous output
QUIET = 1      # heartbeat allowed but reflections shorter
NORMAL = 2     # default
CHATTY = 3     # heartbeat may speak more freely

DEFAULT_SCHEDULE = {
    "default_verbosity": NORMAL,
    "spans": [
        {"from": "00:00", "to": "07:00", "verbosity": SILENT},
        {"from": "07:00", "to": "22:00", "verbosity": NORMAL},
        {"from": "22:00", "to": "24:00", "verbosity": QUIET},
    ],
}


# ---- timestamp helpers ---------------------------------------------------


def now_ts() -> str:
    """Canonical timestamp string for this project. Local wall clock."""
    return datetime.now().strftime(TS_FORMAT)


def parse_ts(s: str) -> Optional[datetime]:
    """Inverse of ``now_ts``. Returns None on parse failure."""
    try:
        return datetime.strptime(s, TS_FORMAT)
    except (TypeError, ValueError):
        return None


# ---- quiet-schedule helpers ----------------------------------------------


def _schedule_path() -> Path:
    from config import DATA_DIR
    return DATA_DIR / "quiet_schedule.json"


def _parse_hhmm(s: str) -> Optional[time]:
    """Accept '07:00', '7:00', '0700', '24:00' (sentinel = end-of-day)."""
    if not s:
        return None
    s = s.strip()
    # Allow '24:00' as the sentinel meaning end-of-day.
    if s == "24:00":
        return time(23, 59, 59)
    m = re.match(r"^(\d{1,2}):?(\d{2})$", s)
    if not m:
        return None
    try:
        h, mn = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mn <= 59:
            return time(h, mn)
    except ValueError:
        pass
    return None


def _t_to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute + (1 if t.second else 0)  # 23:59:59 → 1440


def load_schedule() -> dict:
    """Load schedule from disk, falling back to (and persisting) the default."""
    p = _schedule_path()
    if p.exists():
        try:
            data = json.loads(p.read_text())
            if isinstance(data, dict) and isinstance(data.get("spans"), list):
                return data
        except Exception as e:
            log.warning(f"quiet_schedule.json unreadable: {e} — using default")
    save_schedule(DEFAULT_SCHEDULE)
    return DEFAULT_SCHEDULE


def save_schedule(schedule: dict) -> None:
    p = _schedule_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(schedule, indent=2))


def reset_schedule() -> dict:
    save_schedule(DEFAULT_SCHEDULE)
    return DEFAULT_SCHEDULE


def add_span(start: str, end: str, verbosity: int) -> tuple[bool, str]:
    """Add or replace a span. Returns (ok, message).

    Overlapping existing spans are trimmed away — the new span wins.
    Spans that get fully covered are dropped.
    """
    if verbosity not in (SILENT, QUIET, NORMAL, CHATTY):
        return False, f"verbosity must be 0..3, got {verbosity}"
    s = _parse_hhmm(start)
    e = _parse_hhmm(end)
    if s is None or e is None:
        return False, "times must look like HH:MM (24h)"
    s_min = _t_to_minutes(s)
    e_min = _t_to_minutes(e)
    if e_min <= s_min:
        return False, "end must be after start (no wrap-around — split across midnight)"

    schedule = load_schedule()
    new_spans = []
    for span in schedule.get("spans", []):
        sp_s = _parse_hhmm(span.get("from", ""))
        sp_e = _parse_hhmm(span.get("to", ""))
        if sp_s is None or sp_e is None:
            continue
        sp_s_min, sp_e_min = _t_to_minutes(sp_s), _t_to_minutes(sp_e)
        # Fully covered → drop.
        if sp_s_min >= s_min and sp_e_min <= e_min:
            continue
        # Overlap from left → trim right edge.
        if sp_s_min < s_min < sp_e_min <= e_min:
            new_spans.append({**span, "to": _minutes_to_hhmm(s_min)})
            continue
        # Overlap from right → trim left edge.
        if s_min <= sp_s_min < e_min < sp_e_min:
            new_spans.append({**span, "from": _minutes_to_hhmm(e_min)})
            continue
        # Splits an existing span → split into two.
        if sp_s_min < s_min and sp_e_min > e_min:
            new_spans.append({**span, "to": _minutes_to_hhmm(s_min)})
            new_spans.append({**span, "from": _minutes_to_hhmm(e_min)})
            continue
        # No overlap.
        new_spans.append(span)

    new_spans.append({"from": _minutes_to_hhmm(s_min), "to": _minutes_to_hhmm(e_min), "verbosity": verbosity})
    new_spans.sort(key=lambda x: _t_to_minutes(_parse_hhmm(x["from"])))
    schedule["spans"] = new_spans
    save_schedule(schedule)
    return True, f"saved span {start}-{end} verbosity={verbosity}"


def _minutes_to_hhmm(m: int) -> str:
    if m >= 1440:
        return "24:00"
    return f"{m // 60:02d}:{m % 60:02d}"


def current_verbosity(at: Optional[datetime] = None) -> int:
    """Return the verbosity level for ``at`` (or now). Defaults when no span hits."""
    schedule = load_schedule()
    now = (at or datetime.now()).time()
    now_min = _t_to_minutes(now)
    for span in schedule.get("spans", []):
        s = _parse_hhmm(span.get("from", ""))
        e = _parse_hhmm(span.get("to", ""))
        if s is None or e is None:
            continue
        if _t_to_minutes(s) <= now_min < _t_to_minutes(e):
            try:
                return int(span.get("verbosity", schedule.get("default_verbosity", NORMAL)))
            except (TypeError, ValueError):
                return NORMAL
    return int(schedule.get("default_verbosity", NORMAL))


def render_schedule(schedule: Optional[dict] = None) -> str:
    """Pretty-print the schedule plus a 24-segment ASCII bar."""
    sched = schedule or load_schedule()
    spans = sched.get("spans", [])
    if not spans:
        return "_(empty schedule, all hours fall back to default)_"

    glyph = {SILENT: "·", QUIET: "▁", NORMAL: "▄", CHATTY: "█"}
    label = {SILENT: "silent", QUIET: "quiet", NORMAL: "normal", CHATTY: "chatty"}

    bar = []
    for hour in range(24):
        h_min = hour * 60
        v = sched.get("default_verbosity", NORMAL)
        for span in spans:
            s = _parse_hhmm(span["from"])
            e = _parse_hhmm(span["to"])
            if s is None or e is None:
                continue
            if _t_to_minutes(s) <= h_min < _t_to_minutes(e):
                v = int(span.get("verbosity", v))
                break
        bar.append(glyph.get(v, "?"))

    lines = ["".join(bar), "0   3   6   9   12  15  18  21"]
    for span in spans:
        v = int(span.get("verbosity", NORMAL))
        lines.append(f"  {span['from']}–{span['to']}  {glyph.get(v, '?')} {label.get(v, '?')}")
    return "\n".join(lines)
