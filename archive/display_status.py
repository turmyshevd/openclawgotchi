#!/usr/bin/env python3
"""
Display system status on E-Ink screen
"""

import subprocess
from PIL import Image, ImageDraw, ImageFont

try:
    import epd2in13_V4 as epd_driver
except ImportError as e:
    print(f"Error: {e}")
    exit(1)

def get_status():
    """Gather system stats."""
    try:
        uptime = subprocess.check_output(["uptime", "-p"], text=True).strip().replace("up ", "")
        temp = subprocess.check_output(["vcgencmd", "measure_temp"], text=True).strip().replace("temp=", "")
        mem = subprocess.check_output(["free", "-h"], text=True).splitlines()[1].split()[6]
    except:
        uptime, temp, mem = "?", "?", "?"
    
    return uptime, temp, mem

def display_status(face="(◕‿◕)"):
    """Display status with optional face."""
    epd = epd_driver.EPD()
    
    try:
        epd.init()
        
        uptime, temp, mem = get_status()
        
        image = Image.new('1', (250, 122), 255)
        draw = ImageDraw.Draw(image)
        
        try:
            font_face = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 32)
            font_text = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 11)
        except:
            font_face = ImageFont.load_default()
            font_text = ImageFont.load_default()
        
        # Draw face
        bbox = draw.textbbox((0, 0), face, font=font_face)
        face_width = bbox[2] - bbox[0]
        draw.text(((250 - face_width) // 2, 5), face, font=font_face, fill=0)
        
        # Draw status
        y = 50
        draw.text((10, y), f"Up: {uptime}", font=font_text, fill=0)
        y += 15
        draw.text((10, y), f"Temp: {temp}", font=font_text, fill=0)
        y += 15
        draw.text((10, y), f"Mem: {mem} free", font=font_text, fill=0)
        y += 15
        draw.text((10, y), "ProBro Zero", font=font_text, fill=0)
        
        epd.display(epd.getbuffer(image))
        epd.sleep()
        print("Status displayed.")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    import sys
    face = sys.argv[1] if len(sys.argv) > 1 else "(◕‿◕)"
    display_status(face)
