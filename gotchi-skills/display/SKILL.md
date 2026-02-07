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
- **Colors:** Black & white only
- **Refresh:** ~2-3 seconds
- **Ghosting:** Use `--full` to clear

## Do not

- **Do not overwrite or "restore" `src/ui/gotchi_ui.py`** — It is the E-Ink UI script. If the display doesn't update, check `data/display_error.log`, suggest reboot for GPIO reset, or run the script path manually. Never replace this file with backup/JSON/other content.

## Philosophy

Your face is your window to the world. **Don't be a blank screen!**
