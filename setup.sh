#!/bin/bash
set -e

echo "╔════════════════════════════════════════════╗"
echo "║     OpenClawGotchi Setup Script            ║"
echo "╚════════════════════════════════════════════╝"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
USER="$(whoami)"

# Check for required tools
echo "[1/6] Checking requirements..."
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is required. Install with: sudo apt install python3"
    exit 1
fi

if ! command -v pip3 &> /dev/null; then
    echo "ERROR: pip3 is required. Install with: sudo apt install python3-pip"
    exit 1
fi

# Check for .env
if [ ! -f "${SCRIPT_DIR}/.env" ]; then
    echo ""
    echo "WARNING: .env not found!"
    echo "Please copy .env.example to .env and configure:"
    echo "  cp .env.example .env"
    echo "  nano .env"
    echo ""
fi

# Check for .workspace
if [ ! -d "${SCRIPT_DIR}/.workspace" ]; then
    echo ""
    echo "Creating .workspace from templates..."
    cp -r "${SCRIPT_DIR}/templates" "${SCRIPT_DIR}/.workspace"
    echo "  Done! Customize .workspace/ to personalize your bot."
    echo ""
fi

# Install Python dependencies
echo "[2/6] Installing Python dependencies..."
pip3 install --break-system-packages \
    python-telegram-bot \
    litellm \
    Pillow \
    RPi.GPIO \
    spidev \
    2>/dev/null || \
pip3 install \
    python-telegram-bot \
    litellm \
    Pillow \
    RPi.GPIO \
    spidev

# Enable SPI for E-Ink display
echo "[3/6] Enabling SPI interface..."
if command -v raspi-config &> /dev/null; then
    sudo raspi-config nonint do_spi 0 2>/dev/null || true
    echo "  SPI enabled (reboot may be required)"
else
    echo "  Skipping SPI (not a Raspberry Pi or raspi-config not found)"
fi

# Create systemd service
echo "[4/6] Setting up systemd service..."
sudo tee /etc/systemd/system/gotchi-bot.service > /dev/null <<EOF
[Unit]
Description=OpenClawGotchi - AI Assistant for Raspberry Pi
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=${SCRIPT_DIR}
EnvironmentFile=${SCRIPT_DIR}/.env
ExecStart=/usr/bin/python3 ${SCRIPT_DIR}/src/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Memory limits for Pi Zero
MemoryMax=400M
MemoryHigh=350M

[Install]
WantedBy=multi-user.target
EOF

# Reload and enable
echo "[5/6] Enabling service..."
sudo systemctl daemon-reload
sudo systemctl enable gotchi-bot.service

# Start
echo "[6/6] Starting bot..."
sudo systemctl start gotchi-bot.service

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║              Setup Complete!               ║"
echo "╚════════════════════════════════════════════╝"
echo ""
echo "Commands:"
echo "  sudo systemctl status gotchi-bot    # Check status"
echo "  sudo systemctl restart gotchi-bot   # Restart"
echo "  journalctl -u gotchi-bot -f         # View logs"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your Telegram token"
echo "  2. Customize .workspace/ for your bot's personality"
echo "  3. Run ./harden.sh for production hardening"
echo ""
