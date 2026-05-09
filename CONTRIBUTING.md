# Contributing to OpenClawGotchi

Thank you for your interest in contributing! 🤖

## Getting Started

1. Fork the repository
2. Clone your fork
3. Create a branch for your feature

```bash
git clone https://github.com/<your-username>/openclawgotchi
cd openclawgotchi
git checkout -b feature/my-feature
```

## Development Setup

### On Mac/Linux (without Pi hardware)

```bash
# Setup
cp -r templates/ .workspace/
cp .env.example .env
# Edit .env with test values

# Run (E-Ink will be skipped)
python3 src/main.py
```

### On Raspberry Pi

```bash
./setup.sh
```

## Project Structure

- **src/** — Python source code
- **templates/** — Default personality templates
- **gotchi-skills/** — Pi-specific skills
- **.workspace/** — Live bot personality (gitignored)

## Guidelines

### Code Style

- Python 3.9+ compatible
- Keep memory usage low (512MB Pi)
- Use asyncio for non-blocking operations
- One Claude CLI call at a time

### Commits

- Use clear, descriptive commit messages
- Group related changes
- Reference issues if applicable

### Pull Requests

1. Test your changes
2. Update documentation if needed
3. Describe what you changed and why
4. Keep PRs focused on one thing

#### Scope

OpenClawGotchi has a few highly-coupled files, especially:

- `src/bot/handlers.py`
- `src/main.py`
- `src/config.py`
- `setup.sh`
- `requirements.txt`
- `README.md`
- `templates/BOT_INSTRUCTIONS.md`

Because of that, contributors should prefer **small, isolated PRs**.

Good PRs:

- one feature or one fix
- one hardware topic at a time
- one transport topic at a time (Telegram or Discord)
- docs that describe behavior implemented in the same PR

Avoid:

- large "sync my whole branch" PRs
- mixing unrelated features in one PR
- docs/changelog updates for features that are not actually merged
- stale branches that accidentally revert recent `main` work

#### Before Opening a PR

1. Rebase or merge the latest `main`
2. Make sure your branch does not undo recent work in core files
3. Run syntax checks for touched Python files
4. If you changed setup, env vars, commands, media flows, or hardware support, update:
   - `.env.example`
   - `README.md`
   - `setup.sh` if install/runtime behavior changed

#### Maintainer Outcomes

Maintainers may choose one of four outcomes:

- **Merge as-is**: for small, clean, isolated PRs
- **Request changes**: if the implementation is close but not ready
- **Manual integration**: if the idea is good but the branch is stale or conflicts with current release work
- **Close**: if the change is already integrated another way, duplicated, or out of scope

Manual integration is normal in this repo. It means the maintainer accepted the idea/code but had to transplant it safely onto the current `main`.

#### Hardware and Transport Notes

- Hardware features must degrade gracefully when the hardware is absent
- Optional dependencies should be explicit
- Telegram is the primary control plane
- Discord is optional and should not break Telegram behavior
- If a PR changes onboarding, auth, media handling, or setup, say clearly whether it affects Telegram, Discord, or both

## What to Contribute

### Good First Issues

- Add new E-Ink faces to `src/ui/gotchi_ui.py`
- Improve documentation
- Add Pi-compatible skills to `gotchi-skills/`
- Fix bugs

### Ideas

- New personality templates
- Better error handling
- Performance optimizations
- New bot commands

## Testing

### Manual Testing

```bash
# Test display (on Pi)
sudo python3 src/ui/gotchi_ui.py --mood happy --text "Test"

# Test bot
python3 src/main.py
# Send messages via Telegram
```

If relevant, also test:

- Discord inbound startup when `DISCORD_BOT_TOKEN` is set
- voice transcription when `OPENAI_API_KEY` is set
- image/photo handling when Vision is enabled
- setup flow if you changed `setup.sh`

### Check Memory Usage

```bash
free -h
# Bot should use < 100MB
```

## Questions?

Open an issue on GitHub!

---

**Thank you for making OpenClawGotchi better!** 💙
