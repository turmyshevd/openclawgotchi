#!/bin/bash
SERVICE_FILE="$HOME/.config/systemd/user/openclaw-gateway.service"
ZAI_URL="https://api.z.ai/api/anthropic"
ZAI_KEY="62e38cb58a8d44c583f6400576095ffb.L8PryvFRNqlkoQfO"

echo "🔧 Fixing OpenClaw Gateway for Z.ai..."

if [ ! -f "$SERVICE_FILE" ]; then
    echo "❌ Service file not found!"
    exit 1
fi

# 1. Update API KEY
sed -i "s|^Environment=ANTHROPIC_API_KEY=.*|Environment=ANTHROPIC_API_KEY=$ZAI_KEY|" "$SERVICE_FILE"

# 2. Update/Add Base URL
if grep -q "Environment=ANTHROPIC_BASE_URL=" "$SERVICE_FILE"; then
    sed -i "s|^Environment=ANTHROPIC_BASE_URL=.*|Environment=ANTHROPIC_BASE_URL=$ZAI_URL|" "$SERVICE_FILE"
else
    # Insert after API Key
    sed -i "/^Environment=ANTHROPIC_API_KEY=/a Environment=ANTHROPIC_BASE_URL=$ZAI_URL" "$SERVICE_FILE"
fi

echo "📄 Updated config:"
grep "ANTHROPIC_" "$SERVICE_FILE"

# 3. Restart
systemctl --user daemon-reload
systemctl --user restart openclaw-gateway
echo "✅ Restarted service!"
