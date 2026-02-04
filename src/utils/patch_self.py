#!/usr/bin/env python3
"""
Self-Improvement Tool.
Usage: ./patch_self.py <file_relative_path> <new_content_string_or_stdin>
"""

import sys
import os
import shutil
import subprocess
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    if len(sys.argv) < 2:
        print("Usage: ./patch_self.py <file> [content]")
        print("If content is not provided, reads from stdin.")
        sys.exit(1)

    target_file = sys.argv[1]
    
    # Allow absolute paths or project-relative
    if os.path.isabs(target_file):
        full_path = target_file
    else:
        full_path = os.path.abspath(os.path.join(PROJECT_DIR, target_file))

    # Get content
    if len(sys.argv) > 2:
        new_content = sys.argv[2]
    else:
        new_content = sys.stdin.read()

    if not new_content:
        print("Error: Empty content")
        sys.exit(1)

    # 1. Backup (if exists)
    if os.path.exists(full_path):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{full_path}.{ts}.bak"
        try:
            shutil.copy2(full_path, backup_path)
            print(f"[Backup] Saved to {os.path.basename(backup_path)}")
        except PermissionError:
             # Try sudo backup
             subprocess.run(["sudo", "cp", full_path, backup_path], check=False)
             print(f"[Backup] Saved to {os.path.basename(backup_path)} (via sudo)")

    # 2. Write
    try:
        with open(full_path, "w") as f:
            f.write(new_content)
        print(f"[Success] Updated {target_file}")
    except PermissionError:
        print(f"[Info] Permission denied. Trying sudo...")
        try:
            # Using sudo tee to write protected files
            p = subprocess.run(
                ["sudo", "tee", full_path],
                input=new_content,
                text=True,
                stdout=subprocess.DEVNULL
            )
            if p.returncode != 0:
                raise Exception("Sudo write failed")
            print(f"[Success] Updated {target_file} (via sudo)")
        except Exception as e:
            print(f"[Error] Failed to write: {e}")
            sys.exit(1)
    except Exception as e:
        print(f"[Error] File error: {e}")
        sys.exit(1)
    
    # 3. Check syntax (if python)
    if target_file.endswith(".py"):
        import py_compile
        try:
            py_compile.compile(full_path, doraise=True)
            print("[Check] Syntax OK")
        except Exception as e:
            print(f"[Error] Syntax Invalid! Restoring backup...")
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, full_path)
            sys.exit(1)

if __name__ == "__main__":
    main()
