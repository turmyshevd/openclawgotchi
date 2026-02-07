#!/usr/bin/env python3
"""
OpenClawGotchi UI - Advanced E-Ink Display System
Inspired by Pwnagotchi UI
"""

import sys
import os
import subprocess
import time
import json
from PIL import Image, ImageDraw, ImageFont
import datetime
from pathlib import Path

# XP Stats import
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

# Bot name from config (with fallback)
try:
    from config import BOT_NAME
except ImportError:
    BOT_NAME = os.environ.get("BOT_NAME", "Gotchi")

try:
    from db.stats import get_level_progress
except ImportError:
    def get_level_progress():
        return {"level": 1, "title": "Bot", "xp": 0, "xp_in_level": 0, "xp_needed_this_level": 100, "max_level": 20}


# --- Configuration ---
# Calculate paths relative to this script: src/ui/gotchi_ui.py
UI_DIR = Path(__file__).parent.resolve()
SRC_DIR = UI_DIR.parent
PROJECT_DIR = SRC_DIR.parent
FONT_DIR = PROJECT_DIR / "resources/fonts"

# Add drivers to path
sys.path.append(str(SRC_DIR / "drivers"))

try:
    import epd2in13_V4 as epd_driver
except ImportError:
    print("Error: EPD driver not found")
    sys.exit(1)

def get_system_stats():
    """Gather system metrics."""
    stats = {}
    try:
        # Load
        stats['load'] = os.getloadavg()[0]
        
        # Temp
        temp = subprocess.check_output(["vcgencmd", "measure_temp"], text=True).strip()
        stats['temp'] = temp.replace("temp=", "").replace("'C", "")
        
        # Memory
        mem_out = subprocess.check_output(["free", "-m"], text=True).splitlines()[1].split()
        stats['mem_avail'] = mem_out[6] 
        stats['mem_total'] = mem_out[1]
        
        # Uptime (short)
        up = subprocess.check_output(["uptime", "-p"], text=True).strip()
        stats['uptime'] = up.replace("up ", "").replace("hours", "h").replace("minutes", "m").split(",")[0]
        
    except Exception as e:
        print(f"Stats error: {e}")
        return {'load': 0, 'temp': '?', 'mem_avail': '?', 'mem_total': '?', 'uptime': '?'}
        
    return stats


def _load_all_faces() -> dict:
    """
    Load all faces: default + custom (from data/custom_faces.json).
    Custom faces override defaults if name matches.
    """
    # Default faces (THE SINGLE SOURCE OF TRUTH)
    default_faces = {
        # === BASIC EMOTIONS ===
        "happy":        "(◕‿◕)",
        "happy2":       "(•‿‿•)",
        "sad":          "(╥☁╥ )",
        "excited":      "(ᵔ◡◡ᵔ)",
        "thinking":     "(￣ω￣)",
        "love":         "(♥‿‿♥)",
        "surprised":    "(◉_◉)",
        "grateful":     "(^‿‿^)",
        "motivated":    "(☼‿‿☼)",
        
        # === STATES ===
        "bored":        "(-__-)",
        "sleeping":     "( -_-)zZ",
        "sleeping_pwn": "(⇀‿‿↼)", # Pwnagotchi style
        "awakening":    "(≖‿‿≖)",
        "observing":    "( ⚆⚆)",
        "intense":      "(°▃▃°)",
        "cool":         "(⌐■_■)",
        "chill":        "(▰˘◡˘▰)",
        "hype":         "(╯°□°）╯",
        "hacker":       "[■_■]",
        "smart":        "(✜‿‿✜)",
        "broken":       "(☓‿‿☓)",
        "debug":        "(#__#)",
        
        # === EXTENDED ===
        "angry":        "(╬ಠ益ಠ)",
        "crying":       "(ಥ﹏ಥ)",
        "proud":        "(๑•̀ᴗ•́)و",
        "nervous":      "(°△°;)",
        "confused":     "(◎_◎;)",
        "mischievous":  "(◕‿↼)",
        "wink":         "(◕‿◕✿)",
        "dead":         "(✖_✖)",
        "shock":        "(◯△◯)",
        "suspicious":   "(¬_¬)",
        "smug":         "(￣ω￣)",
        "cheering":     "\\(◕◡◕)/",
        "celebrate":    "★(◕‿◕)★",
        "dizzy":        "(@_@)",
        "lonely":       "(ب__ب)",
        "demotivated":  "(≖__≖)",
    }
    
    # Load custom faces from JSON
    custom_faces = {}
    try:
        from config import CUSTOM_FACES_PATH
        if CUSTOM_FACES_PATH.exists():
            custom_faces = json.loads(CUSTOM_FACES_PATH.read_text())
    except Exception:
        pass  # If file doesn't exist or invalid, just use defaults
    
    # Merge: custom override defaults
    faces = {**default_faces, **custom_faces}
    return faces


def render_ui(mood="happy", status_text="", fast_mode=True):
    """Render the UI."""
    stats = get_system_stats()
    
    # Init Display
    import epdconfig
    epd = epd_driver.EPD()
    gpio_released = False
    try:
        if fast_mode:
            epd.init()
        else:
            epd.init()
            epd.Clear(0xFF)
            
        # Canvas (V4: 122x250 native, logic Horizontal 250x122)
        WIDTH, HEIGHT = 250, 122
        image = Image.new('1', (WIDTH, HEIGHT), 255)
        draw = ImageDraw.Draw(image)
        
        # --- FONTS ---
        try:
            # UI Font: DejaVuSansMono (Terminal style, small & crisp)
            # Size 10 is the sweet spot for Full Refresh
            font_ui_path = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'
            if not os.path.exists(font_ui_path):
                font_ui_path = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'
            
            font_ui = ImageFont.truetype(font_ui_path, 10)
            
            # Bubble Font: Try Unifont first (Aesthetic), then Noto
            font_bubble_path = '/usr/share/fonts/opentype/unifont/unifont.otf'
            if not os.path.exists(font_bubble_path):
                 font_bubble_path = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
            
            if "noto" in font_bubble_path.lower():
                font_bubble = ImageFont.truetype(font_bubble_path, 16, index=0)
            else:
                font_bubble = ImageFont.truetype(font_bubble_path, 16)

            # Face Font: Use Unifont specifically for kaomoji
            font_face_path = '/usr/share/fonts/opentype/unifont/unifont.otf'
            if not os.path.exists(font_face_path):
                 font_face_path = font_bubble_path
            font_face = ImageFont.truetype(font_face_path, 32)
            
            # Emoji Fallback Font: Symbola
            font_emoji_path = '/usr/share/fonts/truetype/ancient-scripts/Symbola_hint.ttf'
            font_emoji_bubble = None
            font_emoji_face = None
            if os.path.exists(font_emoji_path):
                font_emoji_bubble = ImageFont.truetype(font_emoji_path, 16)
                font_emoji_face = ImageFont.truetype(font_emoji_path, 32)
            
            print(f"Loaded fonts: Mono (UI), {os.path.basename(font_bubble_path)} (Bubble), {os.path.basename(font_face_path)} (Face) & Symbola (Emoji)")
            
            def get_char_font(char, primary_font, fallback_font):
                """Determine which font to use for a character."""
                if not fallback_font:
                    return primary_font
                code = ord(char)
                # Force fallback for known emoji/symbol ranges
                if code > 0xFFFF or (0x2300 <= code <= 0x27BF) or (0x2B00 <= code <= 0x2BFF):
                    return fallback_font
                try:
                    if primary_font.getmask(char).getbbox() is None:
                        return fallback_font
                except:
                    return fallback_font
                return primary_font

            def get_text_width(text, font, fallback_font):
                """Calculate total width of text using fallback logic."""
                total_w = 0
                for char in text:
                    if char in ' \t\r\n':
                        total_w += draw.textlength(char, font=font)
                        continue
                    target_font = get_char_font(char, font, fallback_font)
                    total_w += draw.textlength(char, font=target_font)
                return total_w

            def draw_text_with_fallback(draw, xy, text, font, fallback_font, fill=0):
                """Draw text character by character, switching to fallback if needed."""
                curr_x, curr_y = xy
                for char in text:
                    if char in ' \t\r\n':
                        curr_x += draw.textlength(char, font=font)
                        continue
                    target_font = get_char_font(char, font, fallback_font)
                    draw.text((curr_x, curr_y), char, font=target_font, fill=fill)
                    curr_x += draw.textlength(char, font=target_font)
            
        except Exception as e:
            print(f"Font fatal error: {e}")
            font_ui = ImageFont.load_default()
            font_bubble = ImageFont.load_default()
            font_face = ImageFont.load_default()

        # --- LAYOUT CONSTANTS ---
        HEADER_H = 14
        FOOTER_H = 14

        # 1. Header (Compact Stats)
        now = datetime.datetime.now().strftime("%H:%M")
        
        # Left: Name + Mode
        mode_label = ""
        # Check an environment variable or flag for mode
        # Since we're in a separate process, we'll try to detect it from the status_text 
        # but better to pass it or use a shared state. 
        # For now, let's look for | MODE: ... in status_text if we want it dynamic, 
        # or just parse it from the incoming text.
        
        display_name = BOT_NAME
        if "MODE: L" in status_text:
            display_name = f"{BOT_NAME} [L]"
        elif "MODE: P" in status_text:
            display_name = f"{BOT_NAME} [P]"
            
        draw.text((2, 1), display_name, font=font_ui, fill=0)
        
        # Right: Stats (Formatted clearly)
        # e.g. T:45C | Free:120M | 14:00
        txt_stats = f"T:{stats['temp']}°C | Free:{stats['mem_avail']}MB | {now}"
        bbox = draw.textbbox((0, 0), txt_stats, font=font_ui)
        w = bbox[2] - bbox[0]
        draw.text((WIDTH - w - 2, 1), txt_stats, font=font_ui, fill=0)
        
        # Line
        draw.line((0, HEADER_H, WIDTH, HEADER_H), fill=0)
        
        # 2. Footer (Status)
        draw.line((0, HEIGHT - FOOTER_H, WIDTH, HEIGHT - FOOTER_H), fill=0)
        
        # 3. Speech Bubble Check
        speech_text = None
        
        # Support "SAY: ... | STATUS: ..." format
        if "SAY:" in status_text:
            # Check for explicit status separator
            if "| STATUS:" in status_text:
                parts = status_text.split("| STATUS:")
                raw_say = parts[0]
                status_text = parts[1].strip()
            # Or just STATUS:
            elif "STATUS:" in status_text:
                 parts = status_text.split("STATUS:")
                 raw_say = parts[0]
                 status_text = parts[1].strip()
            else:
                raw_say = status_text
                status_text = "Speaking..."
            
            speech_text = raw_say.replace("SAY:", "").strip() 
        
        if not status_text:
            status_text = "Idle."
        
        # Get XP for footer (RPG progress: current/needed or MAX)
        try:
            prog = get_level_progress()
            if prog["level"] >= prog["max_level"]:
                xp_str = f"Lv{prog['level']} MAX"
            else:
                xp_str = f"Lv{prog['level']} {prog['xp_in_level']}/{prog['xp_needed_this_level']}"
        except Exception:
            xp_str = ""
        
        # Draw status on left, XP on right
        draw.text((4, HEIGHT - FOOTER_H + 1), status_text[:35], font=font_ui, fill=0)
        if xp_str:
            bbox_xp = draw.textbbox((0, 0), xp_str, font=font_ui)
            xp_w = bbox_xp[2] - bbox_xp[0]
            draw.text((WIDTH - xp_w - 4, HEIGHT - FOOTER_H + 1), xp_str, font=font_ui, fill=0)

        # 4. Main Content (Face + Bubble)
        
        # Face selection — THE SINGLE SOURCE OF TRUTH!
        # All faces are defined here. Other files just reference this.
        # Style: Use Unicode kaomoji with ◕ ‿ ω ♥ ■ ಠ etc.
        # Load custom faces from JSON (bot can add its own!)
        faces = _load_all_faces()
        face_str = faces.get(mood, faces.get('happy', "(◕‿◕)"))
        
        # Measure Face (Fallback aware for complex symbols)
        fw = get_text_width(face_str, font_face, font_emoji_face)
        fh = 32 # Height is fixed for faces
        
        # Dynamic Positioning
        # Center coordinates (Default)
        cy = (HEIGHT - FOOTER_H + HEADER_H) // 2 
        
        if speech_text:
            # Shift Face LEFT to make room for bubble
            # Place face center at 20% of width (Extreme left)
            cx = int(WIDTH * 0.20)
            # Ensure face doesn't touch left border
            if cx - fw // 2 < 2: cx = fw // 2 + 2
            
            # Move face down slightly
            face_y = cy - fh // 2 + 8
        else:
            # Center Face (Standard)
            cx = WIDTH // 2
            face_y = cy - fh // 2

        # Draw Face
        draw_text_with_fallback(draw, (cx - fw // 2, face_y - 4), face_str, font=font_face, fallback_font=font_emoji_face, fill=0)
        
        # Draw Bubble if needed
        if speech_text:
            # Helper for text wrapping
            def get_wrapped_text(text, font, fallback_font, max_w):
                lines = []
                words = text.split(' ')
                curr_line = ""
                
                for word in words:
                    test_line = (curr_line + " " + word).strip()
                    w = get_text_width(test_line, font, fallback_font)
                    
                    if w <= max_w:
                        curr_line = test_line
                    else:
                        if curr_line:
                            lines.append(curr_line)
                            curr_line = word
                        else:
                            # Splitting long words
                            temp_line = ""
                            for c in list(word):
                                test_c = temp_line + c
                                if get_text_width(test_c, font, fallback_font) <= max_w:
                                    temp_line = test_c
                                else:
                                    lines.append(temp_line)
                                    temp_line = c
                            curr_line = temp_line
                if curr_line: lines.append(curr_line)
                return lines
            
            # 1. Calculate available width
            start_x = cx + fw // 2 + 5
            max_bubble_width = WIDTH - start_x - 8
            
            # Wrap text with fallback awareness
            lines = get_wrapped_text(speech_text, font_bubble, font_emoji_bubble, max_bubble_width)
            
            # Calculate Bubble Size with fallback awareness
            max_line_w = 0
            for line in lines:
                w = get_text_width(line, font_bubble, font_emoji_bubble)
                if w > max_line_w: max_line_w = w
            
            line_height = 18
            text_block_h = len(lines) * line_height
            
            bw = max_line_w + 12
            bh = text_block_h + 10
            
            # HARD CAP: Bubble cannot be wider than screen
            if bw > WIDTH - 4: bw = WIDTH - 4
            
            bx = start_x
            
            # If bubble extends beyond right edge, shift it left
            if bx + bw > WIDTH - 2:
                bx = WIDTH - bw - 2
            
            # Vertical Align
            bubble_cy = face_y + 10 
            by = bubble_cy - bh // 2
            
            # 1. Check Header collision (Top)
            if by < HEADER_H + 2: 
                by = HEADER_H + 2
                
            # 2. Check Footer collision (Bottom)
            max_y = HEIGHT - FOOTER_H - 2
            if by + bh > max_y:
                by = max_y - bh 
                # Double check Top
                if by < HEADER_H + 2:
                     by = HEADER_H + 2 
            
            # Draw Box
            draw.rectangle((bx, by, bx+bw, by+bh), outline=0, fill=255)
            
            # Tail (Side style)
            p_tip = (cx + fw//2 + 2, face_y + 10) # Face cheek
            
            # Base logic
            tail_y = by + bh // 2
            if tail_y > by + bh - 5: tail_y = by + bh - 5
            if tail_y < by + 5: tail_y = by + 5
            
            p_top = (bx, tail_y - 5)
            p_bot = (bx, tail_y + 5)
            
            draw.polygon([p_tip, p_top, p_bot], outline=0, fill=255)
            draw.line((bx, p_top[1] + 1, bx, p_bot[1] - 1), fill=255) 

            # Draw Text Lines
            curr_y = by + 5
            for line in lines:
                draw_text_with_fallback(draw, (bx + 6, curr_y), line, font=font_bubble, fallback_font=font_emoji_bubble, fill=0)
                curr_y += line_height

        # Rotate 180 degrees if needed
        # image = image.rotate(180) # Uncomment if you want to test rotation
        rotated_image = image.rotate(180)
        
        # Update Display (Standard Full only)
        # Using displayPartBaseImage for fast_mode is safer than display_fast if contrast is issue
        if fast_mode:
            epd.displayPartBaseImage(epd.getbuffer(rotated_image))
        else:
            epd.display(epd.getbuffer(rotated_image))

        epd.sleep()
        gpio_released = True
        global _display_gpio_released
        _display_gpio_released = True

    except Exception as e:
        print(f"Render Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if not gpio_released:
            try:
                epdconfig.module_exit(cleanup=True)
            except Exception:
                pass

# Set to True when render_ui() successfully called epd.sleep() (GPIO already released)
_display_gpio_released = False


# Keep only last N lines so we don't fill disk on Pi
_DISPLAY_ERROR_LOG_MAX_LINES = 200


def _log_display_error(msg: str):
    """Write error to data/display_error.log so we can see why E-Ink failed. Trims to last N lines."""
    try:
        log_dir = PROJECT_DIR / "data"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "display_error.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat()} {msg}\n")
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > _DISPLAY_ERROR_LOG_MAX_LINES:
            with open(log_file, "w", encoding="utf-8") as f:
                f.writelines(lines[-_DISPLAY_ERROR_LOG_MAX_LINES:])
    except Exception:
        pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mood", default="happy", help="Face emotion")
    parser.add_argument("--text", default="", help="Status text line")
    parser.add_argument("--full", action="store_true", help="Force full refresh")
    args = parser.parse_args()

    try:
        render_ui(mood=args.mood, status_text=args.text, fast_mode=not args.full)
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        print(f"Display error: {e}", file=sys.stderr)
        traceback.print_exc()
        _log_display_error(f"FAIL: {e}\n{err}")
        sys.exit(1)
    finally:
        # If we crashed before/during render_ui, GPIO was claimed at import; release it.
        if not _display_gpio_released:
            try:
                import epdconfig
                epdconfig.module_exit(cleanup=True)
            except Exception:
                pass
