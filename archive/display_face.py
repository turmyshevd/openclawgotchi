#!/usr/bin/env python3
"""
E-Ink Display Test Script
Displays a face on Waveshare 2.13" v3 E-Paper HAT
"""

import sys
import os
from pathlib import Path

# Add project lib path if needed
PROJECT_DIR = Path(__file__).parent.resolve()

try:
    from PIL import Image, ImageDraw, ImageFont
    import epd2in13_V4 as epd_driver
except ImportError as e:
    print(f"Error: Missing library - {e}")
    print("Install: pip3 install pillow spidev RPi.GPIO")
    sys.exit(1)

def draw_face(mood="happy", fast=True):
    """Draw a Pwnagotchi-style face.
    
    Args:
        mood: Emotion to display
        fast: Use partial update (less flashing) vs full update (cleaner)
    """
    # Initialize display
    epd = epd_driver.EPD()
    
    try:
        print("Initializing E-Ink display...")
        if fast:
            epd.init()  # Fast mode (partial update)
            print("Using fast mode (minimal flashing)")
        else:
            epd.init()
            epd.Clear(0xFF)
            print("Using full update (clean, but flashes)")
        
        # Create image - V4 uses (height, width) = (250, 122)
        image = Image.new('1', (250, 122), 255)  # 1-bit, white background
        draw = ImageDraw.Draw(image)
        
        # Load font (or use default)
        try:
            font_large = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 40)
            font_small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 14)
        except:
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        # Draw face based on mood
        if mood == "happy":
            face = "(◕‿◕)"
        elif mood == "bored":
            face = "(⌐■_■)"
        elif mood == "sad":
            face = "(✖╭╮✖)"
        elif mood == "excited":
            face = "(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧"
        elif mood == "thinking":
            face = "(￣ω￣)"
        elif mood == "love":
            face = "(♥ω♥)"
        else:
            face = "(◕‿◕)"
        
        # Center face
        bbox = draw.textbbox((0, 0), face, font=font_large)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (250 - text_width) // 2
        y = (122 - text_height) // 2 - 10
        
        draw.text((x, y), face, font=font_large, fill=0)
        
        # Add status text
        status = "ProBro Zero"
        bbox_status = draw.textbbox((0, 0), status, font=font_small)
        status_width = bbox_status[2] - bbox_status[0]
        draw.text(((250 - status_width) // 2, 100), status, font=font_small, fill=0)
        
        print(f"Displaying: {face}")
        
        # Display image
        epd.display(epd.getbuffer(image))
        
        # Sleep mode to reduce power
        epd.sleep()
        print("Display updated. E-Ink in sleep mode.")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    mood = sys.argv[1] if len(sys.argv) > 1 else "happy"
    fast = sys.argv[2] != "full" if len(sys.argv) > 2 else True
    draw_face(mood, fast)
