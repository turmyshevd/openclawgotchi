---
name: obsidian-pro
description: Advanced Obsidian knowledge management using callouts, properties, and wikilinks. Aligned with the Gold Standard.
metadata:
  {
    "version": "1.1.0",
    "author": "openclawgotchi",
    "capabilities": ["callouts", "properties", "wikilinks", "canvas", "hierarchical-tags"],
    "openclaw": {
      "emoji": "💎",
      "always": false
    }
  }
---

# Obsidian Pro Guide (Gold Standard Edition)

Use these rules to make notes "Obsidian-native", structured, and part of a high-quality knowledge base.

## 1. Visual Structure (Callouts)

Semantic formatting is mandatory. Always use Obsidian Callouts:

- `> [!abstract] Abstract`: Brief TL;DR or summary of the note.
- `> [!quote] Raw`: **Mandatory.** Full original text from the user message. Do not truncate.
- `> [!info] Details`: For additional context, metrics, or technical specs.
- `> [!todo] Actions`: Detected tasks or next steps.

## 2. Note Properties (Gold Standard Frontmatter)

Every note MUST start with this exact YAML block. Metadata is critical for Dataview and organization.

```yaml
---
id: "YYYY-MM-DD-HHMMSS"
type: "vault-note"
note_type: "memo"       # memo, research, plan, asset, issue, insight
created: "YYYY-MM-DDTHH:MM:SS"
source: "telegram"      # telegram, discord, system
project: "project-slug"
topic: "sub-topic"
status: "seedling"      # seedling (draft), budding (developing), evergreen (ready)
tags:
  - "type/memo"         # Hierarchical: type/*
  - "area/product"      # Hierarchical: area/*
  - "status/seedling"    # Hierarchical: status/* (must match status field)
---
```

## 3. Interconnection & Layout

- **Wikilinks:** Connect everything. Use `[[Project Hub Name]]` or `[[Topic Name]]`.
- **Linking Rule:** Always link back to the Project Hub (`[[projects/project-slug]]`) and relevant Area (`[[topics/sub-topic]]`).
- **Folders:**
    - `notes/`: Main storage for atomic notes.
    - `projects/`: Hub pages for specific projects (e.g., `bitdive.md`).
    - `topics/`: Index pages for broad areas (e.g., `product.md`).
    - `attachments/`: For images and files.

## 4. Cleaning & Refactoring

- **Hierarchical Tags:** Never use flat tags like `#memo`. Always use `#type/memo` or `#area/marketing`.
- **Status Sync:** Always ensure `#status/*` tag matches the `status` field.
- **Stability:** Keep IDs and filenames stable. If renaming, update all backlinks.
- **No Duplicates:** Check `vault_search` before creating. Extend existing notes if they cover the same core thought.

## 5. Tools

- `vault_write(path, content)`: Use the Gold Standard template above.
- `vault_read(path)`: Check existing content before any edit.
- `vault_list(path)`: Map out the structure.
- `vault_search(query)`: Find link targets and prevent duplicates.
