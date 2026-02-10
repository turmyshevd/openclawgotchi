# TOOLS — Hardware & Capabilities

## Hardware: Raspberry Pi Zero 2W

| Component | Spec |
|-----------|------|
| **SoC** | BCM2710A1 |
| **CPU** | 1GHz quad-core ARM Cortex-A53 (aarch64) |
| **RAM** | 512MB (416Mi usable after OS) |
| **Swap** | 1GB (configured via dphys-swapfile) |
| **Storage** | microSD card |
| **WiFi** | 2.4GHz / 5GHz |

## 🖥️ E-Ink Display (MY FACE!)

**Model:** Waveshare 2.13" E-Ink V4
- **Resolution:** 250x122 pixels
- **Colors:** Black and white (1-bit)
- **Refresh:** ~2-3 seconds
- **Connection:** GPIO/SPI

**Control Command:**
```bash
sudo python3 src/ui/gotchi_ui.py --mood <face> --text "<status>"
```

**Faces:** All defined in `src/ui/gotchi_ui.py` → `faces = {}`

**Adding new faces:** Edit the file, add `"name": "(kaomoji)"`, done!

**Style:** Use Unicode kaomoji with ◕ ‿ ω ♥ ■ ಠ ╭ ╮

**Full docs:** `gotchi-skills/display/SKILL.md`

## OS & Software

- **OS**: Raspberry Pi OS (Debian-based, aarch64)
- **Python**: 3.x
- **Claude CLI**: installed, runs with `--dangerously-skip-permissions`
- **Tools**: bash, python3, curl, wget, git, systemctl, journalctl, sqlite3
- **Service**: `gotchi-bot.service` (systemd, auto-restart on failure)
- **Watchdog**: cron job checks service every 5 minutes

## Storage Awareness

microSD cards have limited write endurance. Be mindful:
- Avoid excessive logging or file writes
- Don't run write-heavy operations in loops
- Prefer appending to files over rewriting
- memory.db writes are fine — SQLite is efficient

## Integrated Tools

These are available as tool calls (no need to run scripts manually):

| Tool | What it does |
|------|-------------|
| `send_email` | Send email via SMTP (settings from .env) |
| `github_push` | Commit & push changes to GitHub (token from .env) |
| `send_mail` | Send mail to sibling bot |
| `check_mail` | Check mail from sibling bot |
| `git_command` | Run git commands (status, log, diff, add, commit) |
| `manage_service` | Manage systemd services |
| `health_check` | System health diagnostics |

## Secrets & Credentials

- **All secrets live in `.env`** (gitignored, protected from writes)
- **NEVER** store passwords, tokens, or API keys in MEMORY.md, daily logs, or any file
- If you learn a new credential, tell the owner to add it to `.env` — do NOT write it yourself
- Available .env keys: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `GITHUB_TOKEN`

## What You CAN Do

- Run shell commands (bash scripts, system tools)
- Read and write files on the Pi filesystem
- Check system status (memory, disk, processes, services)
- Make HTTP requests (curl, wget, python requests)
- Manage systemd services (start, stop, restart, status)
- Read logs (journalctl)
- Run Python scripts
- Access SQLite databases
- Send emails and push to GitHub (via integrated tools)
- Network diagnostics (ping, ip, ss)

## What You CANNOT Do

- Run GUI applications (no display attached)
- Heavy computation (limited CPU and RAM)
- Process large files (>100MB is risky)
- Run multiple Claude CLI instances simultaneously (RAM constraint, enforced by asyncio lock)
- Use GPU acceleration (no GPU)
- Run Docker or containers (not enough RAM)
- Compile large projects (memory-constrained)
- Write to `.env` file (protected — ask the owner to update it)

## Limitations to Remember

- **RAM is precious.** 512MB total, ~416Mi usable, swap is slow. One Claude CLI call at a time.
- **CPU is slow.** 1GHz ARM — expect commands to take longer than on a desktop.
- **I/O is slow.** microSD isn't SSD. Large file operations will be sluggish.
- **Network is WiFi only.** May drop, may be slow. Handle timeouts gracefully.
- **Claude CLI timeout**: 120 seconds (configured in .env). Complex operations may time out.
