#!/bin/bash
set -e

echo ""
echo "╔═══════════════════════════════════════════════════╗"
echo "║       🤖 OpenClawGotchi — Setup Wizard            ║"
echo "╚═══════════════════════════════════════════════════╝"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
USER="$(whoami)"
ENV_FILE="${SCRIPT_DIR}/.env"

# Helper: ensure system timezone is correct and NTP sync is on. The bot
# stamps every persisted message and respects a quiet schedule based on
# local wall-clock time, so getting this right at install time avoids
# 4-hour-off heartbeats on a freshly-flashed Pi. Defaults to Europe/Berlin
# (matches the project's German developer base); set ``OCG_TIMEZONE`` in
# the environment before running setup to override.
configure_time() {
    local tz="${OCG_TIMEZONE:-Europe/Berlin}"
    local current
    current=$(timedatectl show --property=Timezone --value 2>/dev/null || echo "")
    if [ "$current" = "$tz" ]; then
        echo "  ✅ Timezone already $tz"
    else
        echo "  🕒 Setting timezone to $tz"
        sudo timedatectl set-timezone "$tz" 2>/dev/null || \
            echo "  ⚠️  Could not set timezone (run 'sudo timedatectl set-timezone $tz' manually)"
    fi
    sudo timedatectl set-ntp true 2>/dev/null || true
    if timedatectl show --property=NTPSynchronized --value 2>/dev/null | grep -q "yes"; then
        echo "  ✅ NTP synchronized"
    else
        echo "  ℹ️  NTP not synchronized yet (DietPi sync mechanism may take a minute)"
    fi
}


# Helper: ensure OLLAMA_API_BASE in $ENV_FILE points at the user's actual
# Ollama host (or is left empty / commented). The repo ships a placeholder
# default in src/config.py so the import never crashes — but on a real
# device that placeholder produces "could not reach ollama-server:11434"
# the moment anything touches Ollama. Prompt the user once during setup
# and write the resolved value to .env (gitignored, never committed).
configure_ollama_base() {
    local current
    current=$(grep -E "^OLLAMA_API_BASE=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)
    # Skip if already set to a real-looking value (anything but the placeholder).
    if [ -n "$current" ] && [ "$current" != "http://ollama-server:11434" ]; then
        echo "  ✅ Ollama base already set: $current"
        return 0
    fi
    echo ""
    echo "  🦙 Optional: local/LAN Ollama server for tool-capable open models"
    echo "     Leave blank to skip — you can still use gemini / glm only."
    read -p "  Ollama API base [skip] (e.g. http://192.168.1.42:11434): " OLLAMA_BASE
    if [ -z "$OLLAMA_BASE" ]; then
        echo "  ℹ️  No Ollama host configured. /model → ollama will report 'unreachable' until you set OLLAMA_API_BASE in .env."
        return 0
    fi
    # Normalize: prepend http:// if user typed bare host:port
    case "$OLLAMA_BASE" in
        http://*|https://*) ;;
        *) OLLAMA_BASE="http://${OLLAMA_BASE}" ;;
    esac
    if grep -qE "^OLLAMA_API_BASE=" "$ENV_FILE"; then
        sed -i "s|^OLLAMA_API_BASE=.*|OLLAMA_API_BASE=${OLLAMA_BASE}|" "$ENV_FILE"
    else
        echo "OLLAMA_API_BASE=${OLLAMA_BASE}" >> "$ENV_FILE"
    fi
    echo "  ✅ Ollama base saved to .env"
}

# ============================================
# STEP 1: Check Python
# ============================================
echo "[1/5] Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo "  ❌ Python 3 not found!"
    echo "  Run: sudo apt update && sudo apt install -y python3 python3-pip"
    exit 1
fi
echo "  ✅ Python $(python3 --version | cut -d' ' -f2)"

# ============================================
# STEP 2: Configure .env (interactive)
# ============================================
echo ""
echo "[2/5] Configuration..."

if [ -f "$ENV_FILE" ]; then
    echo "  Found existing .env"
    # Check if token is set
    if grep -q "TELEGRAM_BOT_TOKEN=your_bot_token_here" "$ENV_FILE" || ! grep -q "TELEGRAM_BOT_TOKEN=." "$ENV_FILE"; then
        echo "  ⚠️  TELEGRAM_BOT_TOKEN not configured!"
        read -p "  Enter your Telegram Bot Token: " BOT_TOKEN
        if [ -n "$BOT_TOKEN" ]; then
            sed -i "s|TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=${BOT_TOKEN}|" "$ENV_FILE"
            echo "  ✅ Token saved"
        fi
    else
        echo "  ✅ Token already configured"
    fi
    # Always offer to fix the Ollama base if it's still on the placeholder —
    # missing or default value only, otherwise quiet.
    configure_time
    configure_ollama_base
else
    echo "  Creating .env from template..."
    cp "${SCRIPT_DIR}/.env.example" "$ENV_FILE"
    
    echo ""
    echo "  ┌─────────────────────────────────────────────┐"
    echo "  │  Let's configure your bot!                  │"
    echo "  └─────────────────────────────────────────────┘"
    echo ""
    
    # Bot Token (REQUIRED)
    echo "  📱 Get a token from @BotFather on Telegram"
    read -p "  Enter Telegram Bot Token: " BOT_TOKEN
    if [ -z "$BOT_TOKEN" ]; then
        echo "  ❌ Token is required! Run setup.sh again after getting a token."
        exit 1
    fi
    sed -i "s|TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=${BOT_TOKEN}|" "$ENV_FILE"
    
    # User ID (REQUIRED)
    echo ""
    echo "  👤 Get your ID from @userinfobot on Telegram"
    read -p "  Enter your Telegram User ID: " USER_ID
    if [ -n "$USER_ID" ]; then
        sed -i "s|ALLOWED_USERS=.*|ALLOWED_USERS=${USER_ID}|" "$ENV_FILE"
    fi
    
    # Bot Name (optional)
    echo ""
    read -p "  What should your bot be called? [Gotchi]: " BOT_NAME
    BOT_NAME=${BOT_NAME:-Gotchi}
    sed -i "s|BOT_NAME=.*|BOT_NAME=${BOT_NAME}|" "$ENV_FILE"
    
    # Owner Name (optional)
    read -p "  What's your name? [Owner]: " OWNER_NAME
    OWNER_NAME=${OWNER_NAME:-Owner}
    sed -i "s|OWNER_NAME=.*|OWNER_NAME=${OWNER_NAME}|" "$ENV_FILE"
    
    # Gemini API (optional)
    echo ""
    echo "  🔑 Optional: Gemini API for fallback (get at aistudio.google.com)"
    read -p "  Gemini API Key [skip]: " GEMINI_KEY
    if [ -n "$GEMINI_KEY" ]; then
        sed -i "s|GEMINI_API_KEY=.*|GEMINI_API_KEY=${GEMINI_KEY}|" "$ENV_FILE"
        sed -i "s|DEFAULT_LITE_PRESET=.*|DEFAULT_LITE_PRESET=gemini|" "$ENV_FILE"
        echo "  ✅ Lite preset set to gemini"
    else
        echo "  ℹ️  No Gemini key provided. The default Lite preset remains glm, which requires its own provider key in .env."
    fi

    # Ollama base (optional, but ask up-front so /model → ollama doesn't
    # silently fail with the http://ollama-server:11434 placeholder).
    configure_time
    configure_ollama_base

    echo ""
    echo "  ✅ Configuration saved to .env"
fi

# ============================================
# STEP 3: Create .workspace
# ============================================
echo ""
echo "[3/5] Setting up workspace..."
if [ ! -d "${SCRIPT_DIR}/.workspace" ]; then
    cp -r "${SCRIPT_DIR}/templates" "${SCRIPT_DIR}/.workspace"
    echo "  ✅ Created .workspace/ from templates"
else
    echo "  ✅ .workspace/ already exists"
fi

# ============================================
# STEP 4: Install dependencies
# ============================================
echo ""
echo "[4/6] Installing system dependencies & Python packages..."
echo "  (This may take a few minutes on Pi Zero)"

# Install system fonts and GPIO tools
sudo apt-get update -qq
sudo apt-get install -y -qq fonts-unifont fonts-dejavu-core fonts-symbola python3-lgpio lsof 2>/dev/null

# Add user to hardware groups
sudo usermod -aG gpio,spi,i2c "${USER}" 2>/dev/null || true

# Create venv with system-site-packages so it can see system lgpio
if [ ! -d "${SCRIPT_DIR}/venv" ]; then
    python3 -m venv --system-site-packages "${SCRIPT_DIR}/venv"
fi

# Install python packages in venv
"${SCRIPT_DIR}/venv/bin/pip" install --quiet \
    "python-telegram-bot[job-queue]" \
    litellm \
    Pillow \
    RPi.GPIO \
    spidev \
    gpiozero \
    2>/dev/null

echo "  ✅ Dependencies installed"

# Enable SPI for E-Ink display (Pi only)
if command -v raspi-config &> /dev/null; then
    echo "  Enabling SPI for E-Ink display..."
    sudo raspi-config nonint do_spi 0 2>/dev/null || true
fi

# ============================================
# STEP 5: Create systemd service
# ============================================
echo ""
echo "[5/6] Setting up systemd service..."

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
ExecStart=${SCRIPT_DIR}/venv/bin/python3 ${SCRIPT_DIR}/src/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Memory limits for Pi Zero (512MB)
MemoryMax=400M
MemoryHigh=350M

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable gotchi-bot.service
echo "  ✅ Service created and enabled"

# ============================================
# STEP 6: E-Ink Permissions (Passwordless sudo)
# ============================================
echo ""
echo "[6/6] Configuring E-Ink permissions..."
# Create a sudoers entry so the bot can run the UI script without a password
SUDOERS_FILE="/etc/sudoers.d/gotchi-display"
UI_SCRIPT_PATH="${SCRIPT_DIR}/src/ui/gotchi_ui.py"
PYTHON_VENV_PATH="${SCRIPT_DIR}/venv/bin/python3"
echo "${USER} ALL=(ALL) NOPASSWD: ${PYTHON_VENV_PATH} ${UI_SCRIPT_PATH}" | sudo tee "$SUDOERS_FILE" > /dev/null
sudo chmod 0440 "$SUDOERS_FILE"
echo "  ✅ Display permissions configured (passwordless sudo)"

# Allow the bot user to restart its own service (used by /update + auto_update.sh)
UPDATE_SUDOERS_FILE="/etc/sudoers.d/gotchi-update"
echo "${USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart gotchi-bot.service, /usr/bin/systemctl restart gotchi-bot.service" | sudo tee "$UPDATE_SUDOERS_FILE" > /dev/null
sudo chmod 0440 "$UPDATE_SUDOERS_FILE"
echo "  ✅ /update permissions configured (passwordless service restart)"

# ============================================
# OPTIONAL: HARDENING (recommended for Pi Zero)
# ============================================
echo ""
echo "  ┌─────────────────────────────────────────────┐"
echo "  │  🔧 Hardening (recommended for Pi Zero)     │"
echo "  │  • Creates 1GB swap file                    │"
echo "  │  • Disables audio/bluetooth (saves ~80MB)   │"
echo "  │  • Hardware watchdog (reboot on freeze)     │"
echo "  │  • Service watchdog (restart bot if dead)   │"
echo "  └─────────────────────────────────────────────┘"
read -p "  Run hardening script? [Y/n]: " RUN_HARDEN
RUN_HARDEN=${RUN_HARDEN:-Y}

if [[ "$RUN_HARDEN" =~ ^[Yy]$ ]]; then
    echo ""
    echo "  Running harden.sh..."
    bash "${SCRIPT_DIR}/harden.sh"
fi

# ============================================
# START THE BOT
# ============================================
echo ""
read -p "Start the bot now? [Y/n]: " START_NOW
START_NOW=${START_NOW:-Y}

if [[ "$START_NOW" =~ ^[Yy]$ ]]; then
    echo ""
    echo "Starting bot..."
    sudo systemctl start gotchi-bot.service
    sleep 2
    
    if systemctl is-active --quiet gotchi-bot.service; then
        echo ""
        echo "╔═══════════════════════════════════════════════════╗"
        echo "║           ✅ Setup Complete!                      ║"
        echo "╚═══════════════════════════════════════════════════╝"
        echo ""
        echo "  Your bot is running! Send it a message on Telegram."
        echo ""
        echo "  On first message, the bot will introduce itself"
        echo "  and ask about its personality (onboarding)."
        echo ""
    else
        echo ""
        echo "  ⚠️  Bot failed to start. Check logs:"
        echo "  journalctl -u gotchi-bot -n 20"
    fi
else
    echo ""
    echo "╔═══════════════════════════════════════════════════╗"
    echo "║           ✅ Setup Complete!                      ║"
    echo "╚═══════════════════════════════════════════════════╝"
fi

echo ""
echo "  📖 Commands:"
echo "     sudo systemctl status gotchi-bot   # Status"
echo "     sudo systemctl restart gotchi-bot  # Restart"
echo "     journalctl -u gotchi-bot -f        # Live logs"
echo ""
echo "  🔧 Customize:"
echo "     nano .env                          # Edit config"
echo "     nano .workspace/SOUL.md            # Edit personality"
echo ""
