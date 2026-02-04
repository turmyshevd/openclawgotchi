#!/bin/bash
set -e
echo "=== Hardening Pi for persistent bot operation ==="

# 1. Increase swap permanently (survives reboot)
echo "[1/4] Setting swap to 1024MB..."
sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
sudo systemctl restart dphys-swapfile
echo "  Swap configured: $(/sbin/swapon --show | tail -1)"

# 2. Ensure bot service is enabled
echo "[2/4] Ensuring gotchi-bot starts on boot..."
sudo systemctl enable gotchi-bot.service
sudo systemctl restart gotchi-bot.service

# 3. Add watchdog cron — restart bot if it dies and systemd somehow misses it
echo "[3/4] Adding watchdog cron..."
CRON_LINE="*/5 * * * * systemctl is-active gotchi-bot.service || systemctl restart gotchi-bot.service"
(sudo crontab -l 2>/dev/null | grep -v "gotchi-bot" ; echo "$CRON_LINE") | sudo crontab -
echo "  Watchdog cron added (checks every 5 min)"

# 4. Disable unnecessary services to free RAM on boot
echo "[4/4] Disabling unnecessary services..."

# Desktop/Printing/Network/Mobile services
# Masking avahi-daemon saves RAM and removes unnecessary network broadcasts
echo "  Masking desktop/printing/mobile/network services..."
SERVICES_TO_MASK="wayvnc wayvnc-control cups cups-browsed cups.path cups.socket packagekit.service ModemManager.service avahi-daemon"

# Audio services (saves ~30-40MB RAM)
echo "  Masking audio services (Pipewire/Pulse)..."
SERVICES_TO_MASK="$SERVICES_TO_MASK pipewire pipewire-pulse wireplumber"

for svc in $SERVICES_TO_MASK; do
    sudo systemctl mask $svc 2>/dev/null || true
    sudo systemctl stop $svc 2>/dev/null || true
done

# User-level audio services (often run as user 'probro' on Pi OS)
echo "  Masking user-level audio services..."
USER_SERVICES="pipewire pipewire-pulse wireplumber pipewire.socket pipewire-pulse.socket"
for usvc in $USER_SERVICES; do
    systemctl --user mask $usvc 2>/dev/null || true
    systemctl --user stop $usvc 2>/dev/null || true
done

echo ""
echo "=== Done! ==="
echo "Swap: $(free -h | grep Swap)"
echo "Bot: $(systemctl is-active gotchi-bot)"
echo "Bot enabled: $(systemctl is-enabled gotchi-bot)"
echo ""
echo "Reboot to verify: sudo reboot"
