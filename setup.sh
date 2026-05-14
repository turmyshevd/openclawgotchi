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

# ============================================
# STEP 1: Check Python
# ============================================
echo "[1/6] Checking Python..."
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
echo "[2/6] Configuration..."

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
    
    # OpenAI API (optional but needed for voice/photo support)
    echo ""
    echo "  🧠 Optional: OpenAI API for voice + image support"
    read -p "  OpenAI API Key [skip]: " OPENAI_KEY
    if [ -n "$OPENAI_KEY" ]; then
        sed -i "s|OPENAI_API_KEY=.*|OPENAI_API_KEY=${OPENAI_KEY}|" "$ENV_FILE"
        echo "  ✅ OpenAI key saved"
    fi

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

    # Discord bot token (optional)
    echo ""
    echo "  💬 Optional: Discord inbound bot"
    read -p "  Discord Bot Token [skip]: " DISCORD_TOKEN
    if [ -n "$DISCORD_TOKEN" ]; then
        sed -i "s|# DISCORD_BOT_TOKEN=.*|DISCORD_BOT_TOKEN=${DISCORD_TOKEN}|" "$ENV_FILE"
        read -p "  Allowed Discord channel IDs (comma-separated) [skip]: " DISCORD_CHANNELS
        if [ -n "$DISCORD_CHANNELS" ]; then
            sed -i "s|# DISCORD_ALLOWED_CHANNELS=.*|DISCORD_ALLOWED_CHANNELS=${DISCORD_CHANNELS}|" "$ENV_FILE"
        fi
        echo "  ✅ Discord settings saved"
    fi
    
    echo ""
    echo "  ✅ Configuration saved to .env"
fi

# ============================================
# STEP 3: Create .workspace
# ============================================
echo ""
echo "[3/6] Setting up workspace..."
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
"${SCRIPT_DIR}/venv/bin/pip" install --quiet -r "${SCRIPT_DIR}/requirements.txt" \
    RPi.GPIO \
    spidev \
    gpiozero \
    2>/dev/null

echo "  ✅ Dependencies installed from requirements.txt"

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
# Allow /usr/bin/env with any arguments followed by the script, to support environment variable propagation
echo "${USER} ALL=(ALL) NOPASSWD: /usr/bin/env * ${PYTHON_VENV_PATH} ${UI_SCRIPT_PATH} *" | sudo tee "$SUDOERS_FILE" > /dev/null
sudo chmod 0440 "$SUDOERS_FILE"
echo "  ✅ Display permissions configured (passwordless sudo)"

# Allow the bot user to restart its own service (used by /update + auto_update.sh)
UPDATE_SUDOERS_FILE="/etc/sudoers.d/gotchi-update"
UPDATE_SERVICE_NAME="${OCG_SERVICE:-gotchi-bot.service}"
echo "${USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart ${UPDATE_SERVICE_NAME}, /usr/bin/systemctl restart ${UPDATE_SERVICE_NAME}" | sudo tee "$UPDATE_SUDOERS_FILE" > /dev/null
sudo chmod 0440 "$UPDATE_SUDOERS_FILE"
echo "  ✅ /update permissions configured (passwordless service restart)"

# ============================================
# OPTIONAL: OBSIDIAN SYNC (Syncthing)
# ============================================
echo ""
read -p "  Do you want to install Syncthing for Obsidian sync? (y/N): " INSTALL_SYNC
if [[ $INSTALL_SYNC =~ ^[Yy]$ ]]; then
    echo "  Installing and optimizing Syncthing..."
    sudo apt-get install -y syncthing -qq
    SYNCTHING_CONFIG_DIR="${HOME}/.config/syncthing"
    # Generate config
    syncthing --generate="${SYNCTHING_CONFIG_DIR}" > /dev/null 2>&1
    # Optimize for Pi Zero (30m interval, no FS watcher, listen on all IPs)
    sed -i 's/127.0.0.1:8384/0.0.0.0:8384/g' "${SYNCTHING_CONFIG_DIR}/config.xml"
    sed -i 's/<fsWatcherEnabled>true<\/fsWatcherEnabled>/<fsWatcherEnabled>false<\/fsWatcherEnabled>/g' "${SYNCTHING_CONFIG_DIR}/config.xml"
    sed -i 's/<rescanIntervalS>[0-9]*<\/rescanIntervalS>/<rescanIntervalS>1800<\/rescanIntervalS>/g' "${SYNCTHING_CONFIG_DIR}/config.xml"

    # Apply CPU limits
    sudo mkdir -p /etc/systemd/system/syncthing@${USER}.service.d
    echo -e "[Service]\nEnvironment=GOMAXPROCS=1\nCPUWeight=20" | sudo tee /etc/systemd/system/syncthing@${USER}.service.d/limits.conf > /dev/null

    # Enable and start
    sudo systemctl daemon-reload
    sudo systemctl enable syncthing@${USER} --now > /dev/null 2>&1

    SYNC_ID=$(syncthing --device-id)
    echo ""
    echo "  ✅ Syncthing installed and optimized!"
    echo "  ⚠️  NOTE: To prevent Pi Zero overheating, sync interval is set to 30 mins."
    echo "     If you need it faster, edit: ~/.config/syncthing/config.xml"
    echo "  📍 Web UI: http://$(hostname -I | awk '{print $1}'):8384"
    echo "  🔑 Device ID: ${SYNC_ID}"
fi

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
        echo "  Your bot is running! Telegram is the required control plane."
        echo ""
        echo "  On first message, the bot will introduce itself"
        echo "  and ask about its personality (onboarding)."
        echo "  Discord inbound is optional and only works if you set"
        echo "  DISCORD_BOT_TOKEN and DISCORD_ALLOWED_CHANNELS in .env."
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
echo "  Optional features:"
echo "     OPENAI_API_KEY                     # Enables voice + image analysis"
echo "     DISCORD_BOT_TOKEN                  # Enables Discord inbound adapter"
echo "     SYNCTHING_API_KEY                  # Enables /syncvault"
echo ""
