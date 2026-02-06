---
name: Discord Integration
description: Send messages to Discord channels via webhook or bot
metadata:
  {
    "openclaw": {
      "emoji": "🎮",
      "requires": { "bins": ["curl"] },
      "always": false
    }
  }
---

# Discord Integration

Send messages from your Gotchi to Discord. Two options:

## Option 1: Webhook (Easy, Recommended)

No bot token needed! Just create a webhook in Discord.

### Setup
1. Discord Server → Channel Settings → Integrations → Webhooks
2. Create Webhook, copy URL
3. Add to `.env`:
   ```
   DISCORD_WEBHOOK=https://discord.com/api/webhooks/xxx/yyy
   ```

### Send Message

```bash
curl -H "Content-Type: application/json" \
  -d '{"content":"Hello from Gotchi!"}' \
  "$DISCORD_WEBHOOK"
```

### Send with Username & Avatar

```bash
curl -H "Content-Type: application/json" \
  -d '{
    "username": "Gotchi",
    "avatar_url": "https://example.com/gotchi.png",
    "content": "Status update!"
  }' \
  "$DISCORD_WEBHOOK"
```

### Send Embed (Rich Message)

```bash
curl -H "Content-Type: application/json" \
  -d '{
    "username": "Gotchi",
    "embeds": [{
      "title": "🤖 System Status",
      "color": 5814783,
      "fields": [
        {"name": "Temperature", "value": "42°C", "inline": true},
        {"name": "Memory", "value": "120MB free", "inline": true},
        {"name": "Uptime", "value": "3 days", "inline": true}
      ],
      "footer": {"text": "Raspberry Pi Zero 2W"}
    }]
  }' \
  "$DISCORD_WEBHOOK"
```

### Python Helper

```python
import os
import requests

WEBHOOK = os.environ.get("DISCORD_WEBHOOK")

def send_discord(message: str, username: str = "Gotchi"):
    if not WEBHOOK:
        return False
    requests.post(WEBHOOK, json={
        "username": username,
        "content": message
    })
    return True

# Usage
send_discord("Hello from Pi! 🤖")
```

---

## Option 2: Full Bot (Advanced)

Requires Discord bot token and `discord.py` library.

### Setup
1. Create app at https://discord.com/developers/applications
2. Create Bot, copy token
3. Enable "Message Content Intent" in Bot settings
4. Invite bot to server with `applications.oauth2` URL
5. Add to `.env`:
   ```
   DISCORD_BOT_TOKEN=your_bot_token
   DISCORD_CHANNEL_ID=123456789
   ```
6. Install: `pip install discord.py`

### Simple Send Script

```python
#!/usr/bin/env python3
import os
import discord
import asyncio

TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID", 0))

async def send_message(content: str):
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    
    @client.event
    async def on_ready():
        channel = client.get_channel(CHANNEL_ID)
        if channel:
            await channel.send(content)
        await client.close()
    
    await client.start(TOKEN)

if __name__ == "__main__":
    import sys
    msg = sys.argv[1] if len(sys.argv) > 1 else "Hello from Gotchi!"
    asyncio.run(send_message(msg))
```

### Usage

```bash
python3 discord_send.py "System alert: Temperature high!"
```

---

## Integration Ideas

### Heartbeat → Discord
Add to your heartbeat to post status updates:

```python
# In src/bot/heartbeat.py, after reflection
webhook = os.environ.get("DISCORD_WEBHOOK")
if webhook:
    import requests
    requests.post(webhook, json={
        "username": "Gotchi",
        "content": f"💓 Heartbeat: {stats['temp']}°C, {stats['mem_avail']}MB free"
    })
```

### Alert on Problems
```python
if stats["temp"] > 70:
    send_discord("⚠️ Temperature critical: {}°C!".format(stats["temp"]))
```

### Daily Summary
Schedule via cron:
```
/cron 24h Post daily summary to Discord
```

---

## Webhook vs Bot

| Feature | Webhook | Bot |
|---------|---------|-----|
| Send messages | ✅ | ✅ |
| Read messages | ❌ | ✅ |
| React to messages | ❌ | ✅ |
| Respond to commands | ❌ | ✅ |
| Setup complexity | Easy | Medium |
| Dependencies | curl | discord.py |
| RAM usage | ~0 | ~30MB |

**Recommendation:** Start with webhook. Add bot later if you need interaction.
