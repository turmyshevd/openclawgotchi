---
name: obsidian-pro
description: Advanced Obsidian knowledge management using callouts, properties, and wikilinks. Inspired by kepano/obsidian-skills.
metadata:
  {
    "version": "1.0.0",
    "author": "kepano & openclawgotchi",
    "capabilities": ["callouts", "properties", "wikilinks", "canvas"],
    "openclaw": {
      "emoji": "💎",
      "always": false
    }
  }
---

# Obsidian Pro Guide

Use these rules to make notes "Obsidian-native", visual, and interconnected.

Use this skill together with the vault tools:

- `vault_write(path, content)` to create or update markdown notes and `.canvas` files
- `vault_read(path)` to inspect an existing note before editing it
- `vault_list(path)` to explore folders such as `projects/`, `topics/`, and `mocs/`
- `vault_search(query)` to find related notes, duplicates, and backlink targets

Before creating a new note, search the vault first so you link into what already exists.

## 1. Visual Structure (Callouts)

Don't just write text. Use callouts for semantic meaning:

- `> [!abstract] Summary`: For the executive summary or TL;DR.
- `> [!quote] Raw Input`: For the original message or data source.
- `> [!info] Details`: For additional context or technical specs.
- `> [!todo] Actions`: For follow-up tasks.
- `> [!danger] Warning`: For critical errors or blockers.

## 2. Note Properties (YAML)

Every new markdown note should start with a YAML block. Use these standard keys:

```yaml
---
id: YYYY-MM-DD-HHMMSS
type: vault-note
created: YYYY-MM-DDTHH:MM:SS
project: "Project Name"
topic: "Topic Name"
status: "inbox | seedling | evergreen"
tags:
  - tag1
  - tag2
---
```

Keep `id` stable after creation. Prefer ISO timestamps for `created`.

## 3. Interconnection (Wikilinks)

- Use `[[Note Name]]` to link to other notes.
- If referencing a project, use `[[projects/Project Name|Project Name]]`.
- If referencing a topic, use `[[topics/Topic Name|Topic Name]]`.
- Always try to link the current note to at least one "Map of Content" (MOC) or existing index.

Suggested vault layout:

- `projects/<Project Name>.md`
- `topics/<Topic Name>.md`
- `mocs/<Area Name> MOC.md`
- `inbox/<YYYY-MM-DD Note Title>.md`

## 4. Canvas Generation

When asked to "map out" or "visualize" connections, generate an `.canvas` file (JSON).
Structure nodes with `x`, `y`, `width`, `height`.

Example Node:
```json
{
  "id": "node1",
  "type": "text",
  "text": "# Concept",
  "x": 0, "y": 0, "width": 200, "height": 100
}
```

Write canvas files with `vault_write("maps/<name>.canvas", "<json>")`.

## 5. Cleaning and Refactoring

- Use `vault_search` to find orphans or duplicates.
- When renaming notes, ensure you update all `[[wikilinks]]` in the vault.
- Do not create duplicate notes when a topic already exists; extend and relink instead.
