# BOOT.md — Startup Behavior

_What happens when the bot service starts._

## Current Startup Sequence (automatic)

1. **Database init** — creates tables if missing
2. **Skills loaded** — gotchi-skills + openclaw-skills catalog
3. **Hooks loaded** — event automation
4. **E-Ink boot screen** — shows sleeping face + "Zzz..."
5. **Startup hook fired** — logs to audit trail
6. **Mail check** — processes pending command mail from brother
7. **E-Ink online** — shows sleeping face + "Online (Zzz...)"
8. **After 60s** — switches to cool face + "Chilling..."
9. **First heartbeat** — after 1 minute, then every 4 hours

## Onboarding (first run only)

If `.workspace/BOOTSTRAP.md` exists:
- First message triggers onboarding mode
- Bot asks about identity, personality, preferences
- Updates IDENTITY.md, USER.md, SOUL.md
- Deletes BOOTSTRAP.md when done

## Notes

- Bot won't start without `.env` (token required)
- `.workspace/` is auto-created from `templates/` on first run
- setup.sh handles .env creation, dependencies, systemd service
