---
name: System Administration
description: Manage Raspberry Pi - power, services, monitoring, backups
metadata:
  {
    "openclaw": {
      "emoji": "🔧",
      "requires": { "os": ["linux"] },
      "always": false
    }
  }
---

# System Administration Skill

Commands for managing your Raspberry Pi Zero 2W.

## Power Management

```bash
# Reboot
sudo reboot

# Shutdown
sudo shutdown -h now

# Scheduled shutdown (in 30 min)
sudo shutdown -h +30

# Cancel scheduled shutdown
sudo shutdown -c
```

## Service Management

```bash
# Bot service
sudo systemctl status gotchi-bot
sudo systemctl restart gotchi-bot
sudo systemctl stop gotchi-bot
journalctl -u gotchi-bot -f  # Live logs
journalctl -u gotchi-bot -n 50  # Last 50 lines

# List all services
systemctl list-units --type=service --state=running
```

## System Monitoring

```bash
# Temperature
vcgencmd measure_temp
# → temp=45.0'C

# Memory
free -h
# → Shows used/free RAM

# Disk space
df -h /
# → Shows root partition usage

# CPU usage
top -bn1 | head -5

# Uptime
uptime -p
# → up 2 days, 5 hours
```

## Network

```bash
# IP address
hostname -I

# Check internet
ping -c 1 8.8.8.8

# WiFi signal
iwconfig wlan0 | grep -i signal

# Network interfaces
ip addr show
```

## Process Management

```bash
# Find heavy processes
ps aux --sort=-%mem | head -10

# Kill by name
pkill -f "process_name"

# Find what's using a port
sudo lsof -i :8080
```

## Backup

```bash
# Backup database
cp gotchi.db gotchi.db.backup.$(date +%Y%m%d)

# Backup workspace
tar -czf workspace_backup_$(date +%Y%m%d).tar.gz .workspace/

# Backup everything important
tar -czf gotchi_backup_$(date +%Y%m%d).tar.gz \
    gotchi.db \
    .workspace/ \
    .env \
    gotchi-skills/
```

## Disk Cleanup

```bash
# Clear old logs
sudo journalctl --vacuum-time=7d

# Clear apt cache
sudo apt clean

# Find large files
du -h --max-depth=2 | sort -h | tail -20

# Remove old backups (keep last 3)
ls -t *.backup.* | tail -n +4 | xargs rm -f
```

## Updates

```bash
# Update system (careful on Pi Zero - slow!)
sudo apt update && sudo apt upgrade -y

# Update Python packages
pip3 install --upgrade python-telegram-bot litellm
```

## Pi-Specific

```bash
# CPU frequency
vcgencmd measure_clock arm

# Voltage
vcgencmd measure_volts

# Throttling status (0 = OK)
vcgencmd get_throttled

# GPU memory split
vcgencmd get_mem gpu

# Config
sudo raspi-config  # Interactive
```

## Quick Health Check

```bash
echo "=== System Health ==="
echo "Temp: $(vcgencmd measure_temp)"
echo "Uptime: $(uptime -p)"
echo "Memory: $(free -h | grep Mem | awk '{print $3 "/" $2}')"
echo "Disk: $(df -h / | tail -1 | awk '{print $3 "/" $2 " (" $5 ")"}')"
echo "Bot: $(systemctl is-active gotchi-bot)"
```

## Safety Rules

1. **Never `rm -rf /`** — use `trash` or move to temp
2. **Backup before updates** — SD cards fail
3. **Check temp regularly** — Pi Zero throttles at 80°C
4. **Free RAM < 50MB** = restart bot soon
5. **Disk > 90%** = cleanup immediately
