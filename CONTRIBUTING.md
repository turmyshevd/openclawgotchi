# Contributing to OpenClawGotchi

Thank you for your interest in contributing! 🤖

## Getting Started

1. Fork the repository
2. Clone your fork
3. Create a branch for your feature

```bash
git clone https://github.com/yourusername/openclawgotchi
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

### Check Memory Usage

```bash
free -h
# Bot should use < 100MB
```

## Questions?

Open an issue on GitHub!

---

**Thank you for making OpenClawGotchi better!** 💙
