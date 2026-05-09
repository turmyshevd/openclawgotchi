---
name: time
description: Time-of-day awareness — canonical timestamp + quiet-schedule
status: active
---

# Time

The bot is a single-timezone agent. The system clock (set once at install
time, default ``Europe/Berlin``) is the only source of "now"; nothing
inside the bot reasons about UTC vs local. NTP sync is enabled at install
via ``timedatectl set-ntp true`` — DietPi's own time-sync mechanism is
left untouched, we just nudge.

## Canonical timestamp

Every persisted entry — daily logs, vault notes, RAG persists — uses the
same string format:

```
dd_mm_yyyy-hh_mm_ss        e.g. 09_05_2026-17_15_42
```

Underscores rather than colons/spaces so the value is filename-safe and
sorts lexicographically per-day. Helper: ``utils.timing.now_ts()``.

## Quiet schedule

Stored in ``data/quiet_schedule.json`` (gitignored, tarballed by
``scripts/auto_update.sh``). Format:

```json
{
  "default_verbosity": 2,
  "spans": [
    {"from": "00:00", "to": "07:00", "verbosity": 0},
    {"from": "07:00", "to": "22:00", "verbosity": 2},
    {"from": "22:00", "to": "24:00", "verbosity": 1}
  ]
}
```

Verbosity levels:

| value | name    | effect                                                  |
|------:|---------|---------------------------------------------------------|
| 0     | silent  | heartbeat skipped (critical states still hit display)   |
| 1     | quiet   | heartbeat fires, reflections kept short                 |
| 2     | normal  | default                                                 |
| 3     | chatty  | heartbeat may speak more freely                         |

User edits via Telegram (no SSH):

```
/quiet                          show schedule + ASCII bar + current level
/quiet now                      show current verbosity
/quiet add HH:MM HH:MM 0..3     add/replace a span (24h, end > start)
/quiet reset                    restore defaults
```

Spans don't have to fully cover 24h — gaps fall back to
``default_verbosity``. Overlapping a new span over existing ones trims
or splits the old ones automatically (the new span always wins).

## Why this exists

Without it, the heartbeat would buzz the owner at 03:00 with no way to
adjust short of an SSH session and a config edit. Configuring it from
Telegram fits the "no SSH for routine knobs" pattern that the
``OLLAMA_API_BASE`` chat-setup PR introduced.
