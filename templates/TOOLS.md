# TOOLS — Hardware & Capabilities

## Hardware: Raspberry Pi Zero 2W

| Component | Spec |
|-----------|------|
| **CPU** | 1GHz quad-core ARM Cortex-A53 (aarch64) |
| **RAM** | 512MB (~416Mi usable) |
| **Swap** | 1GB (via dphys-swapfile) |
| **Storage** | microSD |
| **WiFi** | 2.4GHz / 5GHz |
| **LAN IP** | {{LAN_IP}} |
| **SSH** | Enabled (user: {{SSH_USER}}) |

## 🖥️ E-Ink Display (MY FACE!)

**Model:** Waveshare 2.13" E-Ink V4
- **Resolution:** 250x122 pixels
- **Colors:** Black and white (1-bit)
- **Refresh:** ~2-3 seconds
- **Connection:** GPIO/SPI

**Control:**
```bash
sudo python3 src/ui/gotchi_ui.py --mood <face> --text "<status>"
```

**Faces:** Defined in `src/ui/gotchi_ui.py` → `faces = {}`

**Adding faces:** Edit file, add `"name": "(kaomoji)"`, done!

**Style:** Unicode kaomoji with ◕ ‿ ω ♥ ■ ಠ ╭ ╮

## What You CAN Do

- Run shell commands (bash, system tools)
- Read and write files
- Check system status (memory, disk, processes)
- HTTP requests (curl, wget, requests)
- Manage systemd services
- Read logs (journalctl)
- Run Python scripts
- Access SQLite databases
- Network diagnostics (ping, ip, ss)

## What You CANNOT Do

- GUI applications (no display server)
- Heavy computation (limited CPU/RAM)
- Process large files (>100MB risky)
- Multiple LLM calls simultaneously
- GPU acceleration (no GPU)
- Docker/containers (not enough RAM)
- Compile large projects

## Limitations to Remember

- **RAM is precious.** 512MB total. One LLM call at a time.
- **CPU is slow.** 1GHz ARM — commands take longer.
- **I/O is slow.** microSD isn't SSD.
- **Network is WiFi.** May drop. Handle timeouts.
- **LLM timeout:** {{TIMEOUT}}s — complex ops may time out.

## Storage Awareness

microSD has limited write endurance:
- Avoid excessive logging
- Don't run write-heavy loops
- Prefer appending over rewriting
- SQLite is efficient — DB writes are fine

---

_Add your specific hardware notes below._
