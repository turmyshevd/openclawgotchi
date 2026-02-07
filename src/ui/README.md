# E-Ink UI

**Display script:** `gotchi_ui.py` (this file) — uses E-Ink driver `epd2in13_V4` from `src/drivers/`.

- **Correct path:** `src/ui/gotchi_ui.py`  
- **Wrong (old):** Any `gotchiui.py` (no underscore) at project root — that one uses `lcddriver` (LCD), not E-Ink. Remove or ignore it.

Manual test on Pi:
```bash
cd /home/probro/openclawgotchi
sudo python3 src/ui/gotchi_ui.py --mood happy --text 'SAY:test' --full
```
