# VAULT.md — Knowledge Capture (Gold Standard)

Source of truth: `.workspace/knowledge/`.

## Core Rule
If a message contains project knowledge, strategic insights, or technical facts, capture it immediately using the Gold Standard template.

## Gold Standard Template (Strict Compliance)

```markdown
---
id: "YYYY-MM-DD-HHMMSS"
type: "vault-note"
note_type: "memo"       # memo, research, plan, asset, issue, insight
created: "YYYY-MM-DDTHH:MM:SS"
source: "telegram"
project: "project-slug"
topic: "sub-topic"
status: "seedling"      # seedling (draft), budding (developing), evergreen (ready)
tags:
  - "type/memo"         # Hierarchical: type/*
  - "area/product"      # Hierarchical: area/*
  - "status/seedling"    # Hierarchical: status/* (must match status field)
---

# Title (H1)

[Brief Abstract / TL;DR]

## Key Points
- Point 1
- Point 2

> [!quote] Raw
> Full original text from user message. DO NOT TRUNCATE OR SUMMARIZE HERE.

## Links
- [[projects/project-slug]]
- [[topics/sub-topic]]
```

## Capture Rules
1. **Frontmatter Metadata:** Never skip or simplify YAML. Always use hierarchical tags (`type/*`, `area/*`).
2. **Language Consistency:** Always write the Title, Abstract, and Key Points in the **Bot's Primary Language (based on BOT_LANGUAGE setting)**, even if the source message or document is in another language.
3. **Preserve Raw:** Always include the full original message in a `> [!quote] Raw` block. Keep the Raw text in its original language.
4. **Internal Links:** Always link back to the Project Hub (`[[projects/...]]`) and relevant Topic (`[[topics/...]]`).


## Tools
- `vault_write`: Create/update note using the template.
- `vault_read`: Check existing content to avoid duplicates.
- `vault_list`: See current structure.
- `vault_search`: Find related notes for linking.
