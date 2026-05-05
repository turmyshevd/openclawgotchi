# VAULT.md — Knowledge Capture

Source of truth: `.workspace/knowledge/`.

## Core Rule
If a message is not a direct command and not an explicit question, treat it as memo-worthy project knowledge by default.

## Capture Behavior (Obsidian Pro)
- **Formatting:** Use Obsidian Callouts for structure. 
    - Wrap summary in `> [!abstract]`.
    - Wrap raw input in `> [!quote]`.
    - Use `> [!todo]` for any detected tasks.
- **Linking:** Always attempt to connect notes using `[[Wikilinks]]`. 
- **Metadata:** Ensure YAML frontmatter includes `status: "seedling"` for new notes.
- **Organization:** Infer project/topic/tags. Avoid fixed categories.
- **Clarification:** If essential fields are unclear, ask one short clarification before writing.

## Advanced Reference
For advanced formatting and canvas generation, use `read_skill("obsidian-pro")`.

## Tools
- `vault_write` to create/update a note.
- `vault_read` to inspect an existing vault file.
- `vault_list` to inspect vault structure.
- `vault_search` to look for related notes before creating a new one.

## Output Rule
After capture, respond briefly with what was saved and include tool usage when available.

