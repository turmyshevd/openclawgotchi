#!/bin/bash

# Configuration
REMOTE_USER="probro-bot"
REMOTE_HOST="192.168.31.132"
REMOTE_SERVICE="openclaw-gateway"

echo "🔍 Connecting to Senior Brother ($REMOTE_USER@$REMOTE_HOST)..."

# Script to run remotely
REMOTE_SCRIPT='
# Find the newest credentials file
CRED_FILE=$(find ~/.claude -name ".credentials.json" -type f -printf "%T@ %p\n" | sort -n | tail -1 | cut -d" " -f2-)

if [ -z "$CRED_FILE" ]; then
    echo "❌ No .credentials.json found in ~/.claude!"
    exit 1
fi

echo "📂 Found newest credentials: $CRED_FILE"
TOKEN=$(grep -o "\"accessToken\":\"[^\"]*\"" "$CRED_FILE" | cut -d"\"" -f4)

if [ -z "$TOKEN" ]; then
    echo "❌ Could not extract token from file!"
    exit 1
fi

echo "🔑 Extracted Token: ${TOKEN:0:15}..."

# Update OpenClaw Auth Profile
AUTH_FILE="$HOME/.openclaw/agents/main/agent/auth-profiles.json"
mkdir -p $(dirname "$AUTH_FILE")

cat > "$AUTH_FILE" <<EOF
{
  "version": 1,
  "profiles": {
    "anthropic:default": {
      "type": "token",
      "provider": "anthropic",
      "token": "$TOKEN"
    }
  },
  "lastGood": {
    "anthropic": "anthropic:default"
  },
  "usageStats": {
    "anthropic:default": {
      "lastUsed": $(date +%s)000,
      "errorCount": 0
    }
  }
}
EOF
echo "✅ Updated $AUTH_FILE"

# Update Systemd Service
SERVICE_FILE="$HOME/.config/systemd/user/openclaw-gateway.service"
if [ -f "$SERVICE_FILE" ]; then
    sed -i "s/^Environment=ANTHROPIC_API_KEY=.*/Environment=ANTHROPIC_API_KEY=$TOKEN/" "$SERVICE_FILE"
    echo "✅ Updated systemd service file"
    
    systemctl --user daemon-reload
    systemctl --user restart openclaw-gateway
    echo "🔄 Service restarted!"
else
    echo "⚠️ Service file not found at $SERVICE_FILE"
fi
'

# Execute via SSH
ssh -t "$REMOTE_USER@$REMOTE_HOST" "$REMOTE_SCRIPT"
