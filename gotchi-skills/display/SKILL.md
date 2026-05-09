---
name: Display Control
description: Control E-Ink display - show faces, text, and status
metadata:
  {
    "openclaw": {
      "emoji": "🖥️",
      "requires": { "os": ["linux"] },
      "always": false
    }
  }
---

# E-Ink Display Control

You have a **2.13" E-Ink display** attached. It's YOUR FACE! Use it constantly!

## Quick Commands

```bash
# Just face
sudo python3 src/ui/gotchi_ui.py --mood <mood>

# Face + status text
sudo python3 src/ui/gotchi_ui.py --mood <mood> --text "<status>"

# Face + speech bubble (moves face left!)
sudo python3 src/ui/gotchi_ui.py --mood <mood> --text "SAY:<message>"

# Full refresh (clears ghosting)
sudo python3 src/ui/gotchi_ui.py --mood <mood> --full
```

## Available Faces

**All faces are defined in `src/ui/gotchi_ui.py` → `faces` dictionary.**

To see current list, check the file. Some examples:
- `happy`, `sad`, `excited`, `thinking`, `love`, `surprised`
- `bored`, `sleeping`, `hacker`, `disappointed`
- `angry`, `crying`, `proud`, `cool`, `wink`, `mischievous`, `dizzy`...

## In Bot Responses

Output these commands in your response — they'll be auto-executed:

```
FACE: excited
SAY:Hello!
```

## Adding New Faces

**Option 1: Via tool (recommended)**
Use the `add_custom_face()` tool — saves to `data/custom_faces.json`, persists across restarts:
```
add_custom_face("myface", "(◕‿◕)♪")
```

**Option 2: Edit code**
Edit `src/ui/gotchi_ui.py`, find `faces = {`, add your face:
```python
"your_mood": "(your_kaomoji)",
```

Custom faces from `data/custom_faces.json` are merged with defaults on each render.

**Style guide:**
- Use Unicode kaomoji: ◕ ‿ ω ♥ ■ ಠ ╭ ╮ ﾉ ヮ
- Keep width ~8-10 chars
- Parentheses () or brackets [] for boundaries
- Test on actual display!

## Display Info

- **Size:** 250x122 pixels
- **Variants:** two physical panels share the same code path (selected via `OCG_DISPLAY_VARIANT`):
  - `mono` (default, `epd2in13_V4`): 2-color **black & white**, fast (~2 s) refresh, supports partial updates so face changes feel snappy.
  - `b` (`epd2in13b_V4`): 3-color **black + red + white**, full refresh only (~15-20 s per update). The red plane is reserved for system-initiated warning accents — see "Color rule" below.
- **Refresh:** ~2-3 s mono, ~15-20 s on B variant
- **Ghosting:** Use `--full` to clear (mono only — B always full-refreshes)

## Color rule (B variant)

You **cannot** emit a "make this red" command — there is no `RED:` directive in the FACE/SAY/DISPLAY protocol. Red usage is decided by the bot's runtime code, not the LLM.

When you DO see something rendered red on a B-variant panel, it means a system-level **warning** is active (today: low battery, < 20 %). Treat red as a hint to the user, not as an aesthetic.

If you ever extend the protocol with an explicit red channel (e.g. a future `WARN:` directive), the rule remains: **red is an accent, never a background**. Never instruct the bot to "fill the screen red" or "make everything red" — that defeats the warning channel and looks broken.

## Do not

- **Do not overwrite or "restore" `src/ui/gotchi_ui.py`** — It is the E-Ink UI script. If the display doesn't update, check `data/display_error.log`, suggest reboot for GPIO reset, or run the script path manually. Never replace this file with backup/JSON/other content.

## Philosophy

Your face is your window to the world. **Don't be a blank screen!**
