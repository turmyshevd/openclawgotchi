#!/usr/bin/env bash
#
# OpenClawGotchi auto-update
#
# Fetches the configured upstream branch, fast-forwards if there are new
# commits, refreshes the venv's Python deps, and restarts the systemd
# service. Idempotent and safe to run repeatedly (no-op when up-to-date).
#
# Usage:
#   bash scripts/auto_update.sh           # update from origin/main
#   bash scripts/auto_update.sh --check   # exit 0 if updates available, 1 if not
#
# Cron suggestion (weekly, Sunday 04:00):
#   0 4 * * 0  cd /home/dietpi/openclawgotchi && bash scripts/auto_update.sh >> logs/update.log 2>&1
#
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${PROJECT_DIR}"

REMOTE="${OCG_UPDATE_REMOTE:-origin}"
BRANCH="${OCG_UPDATE_BRANCH:-main}"
SERVICE="${OCG_SERVICE:-gotchi-bot.service}"
VENV_PIP="${PROJECT_DIR}/venv/bin/pip"

log() { echo "[$(date -Iseconds)] $*"; }

# Refuse to run with uncommitted local changes — would be lost on pull
if [ -n "$(git status --porcelain)" ]; then
    log "ERROR: uncommitted changes in working tree. Commit/stash first."
    git status --short
    exit 2
fi

log "Fetching ${REMOTE}/${BRANCH}…"
git fetch --quiet "${REMOTE}" "${BRANCH}"

LOCAL_HEAD="$(git rev-parse HEAD)"
REMOTE_HEAD="$(git rev-parse "${REMOTE}/${BRANCH}")"
AHEAD_BY="$(git rev-list --count "HEAD..${REMOTE}/${BRANCH}")"

if [ "${LOCAL_HEAD}" = "${REMOTE_HEAD}" ]; then
    log "Already up-to-date (HEAD = ${LOCAL_HEAD:0:8})."
    [ "${1:-}" = "--check" ] && exit 1 || exit 0
fi

log "${AHEAD_BY} new commit(s) on ${REMOTE}/${BRANCH}:"
git --no-pager log --oneline "HEAD..${REMOTE}/${BRANCH}" | head -20

if [ "${1:-}" = "--check" ]; then
    exit 0
fi

# Track whether requirements.txt changed so we know whether to reinstall deps
REQS_CHANGED="$(git diff --name-only "HEAD..${REMOTE}/${BRANCH}" -- requirements.txt | head -1)"

log "Pulling ${REMOTE}/${BRANCH} (fast-forward only)…"
git pull --ff-only --quiet "${REMOTE}" "${BRANCH}"

if [ -n "${REQS_CHANGED}" ] && [ -x "${VENV_PIP}" ]; then
    log "requirements.txt changed — refreshing venv dependencies…"
    "${VENV_PIP}" install --quiet --upgrade -r requirements.txt
fi

log "Restarting ${SERVICE}…"
if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl restart "${SERVICE}"
    sleep 3
    if systemctl is-active --quiet "${SERVICE}"; then
        log "OK — ${SERVICE} is active. Now at $(git rev-parse --short HEAD)."
    else
        log "ERROR — ${SERVICE} failed to come back up. Check journalctl -u ${SERVICE}."
        exit 3
    fi
else
    log "systemctl not available, skipping service restart. Now at $(git rev-parse --short HEAD)."
fi
