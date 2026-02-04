# TOOLS.md — Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

- Device names and locations
- SSH hosts and aliases
- Network addresses
- Hardware peripherals
- Environment-specific notes

## Hardware

| Component | Value |
|-----------|-------|
| **Device** | Raspberry Pi Zero 2W |
| **RAM** | 512MB |
| **LAN IP** | *(your IP)* |
| **SSH User** | *(your user)* |
| **Display** | *(if any)* |

## Peripherals

*(List your connected hardware)*

```markdown
### Display
- Type: E-Ink / OLED / None
- Driver: (if applicable)

### Sensors
- (list any)
```

## SSH Hosts

```markdown
- pi-local → 192.168.x.x, user: probro
- (add more as needed)
```

## Limitations to Remember

- **RAM is precious.** 512MB total. One LLM call at a time.
- **CPU is slow.** 1GHz ARM. Commands take longer than desktop.
- **Storage is microSD.** Avoid excessive writes.
- **Network is WiFi.** May drop. Handle timeouts.

## What You CAN Do

- Shell commands, Python scripts
- Read/write files, SQLite
- System status, logs, services
- Network diagnostics

## What You CANNOT Do

- GUI applications
- Heavy computation (>100MB files)
- Docker/containers
- Multiple simultaneous LLM calls

---

_Add whatever helps you do your job. This is your cheat sheet._
