#!/usr/bin/env python3
"""
Display arbitrary text on E-Ink screen
Usage: ./display_text.py "Line 1" "Line 2" "Line 3"
"""

import sys
from PIL import Image, ImageDraw, ImageFont

try:
    import epd2in13_V4 as epd_driver
except ImportError as e:
    print(f"Error: {e}")
    sys.exit(1)

def display_text(lines, title=""):
    """Display multiple lines of text on screen."""
    epd = epd_driver.EPD()
    
    try:
        epd.init()
        
        # Create image
        image = Image.new('1', (250, 122), 255)
        draw = ImageDraw.Draw(image)
        
        # Load fonts
        try:
            font_title = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 16)
            font_text = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 12)
        except:
            font_title = ImageFont.load_default()
            font_text = ImageFont.load_default()
        
        y = 5
        
        # Draw title if provided
        if title:
            draw.text((5, y), title, font=font_title, fill=0)
            y += 20
            draw.line((5, y, 245, y), fill=0)  # Separator line
            y += 5
        
        # Draw text lines
        for line in lines:
            if y > 115:
                break  # Out of space
            draw.text((5, y), line[:40], font=font_text, fill=0)  # Max 40 chars
            y += 15
        
        print(f"Displaying {len(lines)} lines...")
        epd.display(epd.getbuffer(image))
        epd.sleep()
        print("Done.")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: display_text.py 'Line 1' 'Line 2' ...")
        sys.exit(1)
    
    lines = sys.argv[1:]
    display_text(lines)
