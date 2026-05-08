#!/usr/bin/env bash
#
# OpenClawGotchi auto-update
#
# Fetches the configured upstream branch, fast-forwards if there are new
# commits, refreshes the venv's Python deps, restarts the systemd service,
# and rolls back automatically if the service fails to come back up.
#
# Idempotent and safe to run repeatedly (no-op when up-to-date).
#
# User state (.env, data/, .workspace/) is in .gitignore and never touched
# by `git pull`. As an extra safety net, gotchi.db + data/ + .env are
# tarballed to backups/ before each update; the last 3 are kept.
#
# Usage:
#   bash scripts/auto_update.sh           # update from origin/main
#   bash scripts/auto_update.sh --check   # exit 0 if updates available, 1 if not
#
# Env overrides:
#   OCG_UPDATE_REMOTE  (default: origin)
#   OCG_UPDATE_BRANCH  (default: main)
#   OCG_SERVICE        (default: gotchi-bot.service)
#   OCG_BACKUP_KEEP    (default: 3)  — number of backups to retain
#   OCG_NO_BACKUP=1                   — skip the pre-update backup
#   OCG_NO_ROLLBACK=1                 — skip auto-rollback on service failure
#
# Cron suggestion (weekly, Sunday 04:00):
#   0 4 * * 0  /bin/bash /full/path/openclawgotchi/scripts/auto_update.sh \
#              >> /full/path/openclawgotchi/logs/update.log 2>&1
#
# Exit codes:
#   0  success (updated or already up-to-date)
#   1  --check mode and no updates available
#   2  uncommitted changes block the update
#   3  service failed to start AND rollback was skipped/failed
#   4  service failed to start, rollback succeeded — manual review wanted
#
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${PROJECT_DIR}"

REMOTE="${OCG_UPDATE_REMOTE:-origin}"
BRANCH="${OCG_UPDATE_BRANCH:-main}"
SERVICE="${OCG_SERVICE:-gotchi-bot.service}"
VENV_PIP="${PROJECT_DIR}/venv/bin/pip"
BACKUP_DIR="${PROJECT_DIR}/backups"
BACKUP_KEEP="${OCG_BACKUP_KEEP:-3}"

log() { echo "[$(date -Iseconds)] $*"; }

# --- Pre-flight: refuse if tracked files are modified (untracked is fine) ---
DIRTY_TRACKED="$(git status --porcelain | grep -v '^??' || true)"
if [ -n "${DIRTY_TRACKED}" ]; then
    log "ERROR: tracked files have uncommitted changes. Commit/stash first."
    echo "${DIRTY_TRACKED}"
    exit 2
fi

log "Fetching ${REMOTE}/${BRANCH}…"
git fetch --quiet "${REMOTE}" "${BRANCH}"

LOCAL_HEAD="$(git rev-parse HEAD)"
REMOTE_HEAD="$(git rev-parse "${REMOTE}/${BRANCH}")"
AHEAD_BY="$(git rev-list --count "HEAD..${REMOTE}/${BRANCH}")"

if [ "${AHEAD_BY}" = "0" ]; then
    log "Up-to-date with ${REMOTE}/${BRANCH} (no new commits behind)."
    [ "${1:-}" = "--check" ] && exit 1 || exit 0
fi

log "${AHEAD_BY} new commit(s) on ${REMOTE}/${BRANCH}:"
git --no-pager log --oneline "HEAD..${REMOTE}/${BRANCH}" | head -20

if [ "${1:-}" = "--check" ]; then
    exit 0
fi

# --- Backup user state (DB + small JSON state + .env) before pulling ---
BACKUP_FILE=""
if [ "${OCG_NO_BACKUP:-0}" != "1" ]; then
    mkdir -p "${BACKUP_DIR}"
    TS="$(date +%Y%m%d-%H%M%S)"
    BACKUP_FILE="${BACKUP_DIR}/pre-update-${TS}-${LOCAL_HEAD:0:8}.tar.gz"
    # Build list of things to back up that actually exist (no errors on first runs).
    BACKUP_PATHS=()
    [ -f gotchi.db ]          && BACKUP_PATHS+=(gotchi.db)
    [ -f .env ]               && BACKUP_PATHS+=(.env)
    [ -d data ]               && BACKUP_PATHS+=(data)
    if [ "${#BACKUP_PATHS[@]}" -gt 0 ]; then
        log "Backing up user state to $(basename "${BACKUP_FILE}")…"
        tar -czf "${BACKUP_FILE}" "${BACKUP_PATHS[@]}" 2>/dev/null
        # Rolling retention — keep newest N
        ls -1t "${BACKUP_DIR}"/pre-update-*.tar.gz 2>/dev/null \
            | tail -n +"$((BACKUP_KEEP + 1))" \
            | xargs -r rm -f
    else
        log "No user state to back up yet (skipping)."
        BACKUP_FILE=""
    fi
fi

# --- Track previous HEAD so we can roll back if the service fails ---
PREVIOUS_HEAD="${LOCAL_HEAD}"
REQS_CHANGED="$(git diff --name-only "HEAD..${REMOTE}/${BRANCH}" -- requirements.txt | head -1)"

log "Pulling ${REMOTE}/${BRANCH} (fast-forward only)…"
git pull --ff-only --quiet "${REMOTE}" "${BRANCH}"

if [ -n "${REQS_CHANGED}" ] && [ -x "${VENV_PIP}" ]; then
    log "requirements.txt changed — refreshing venv dependencies…"
    "${VENV_PIP}" install --quiet --upgrade -r requirements.txt
fi

# --- Restart and verify ---
restart_service() {
    sudo systemctl restart "${SERVICE}"
    sleep 4
    systemctl is-active --quiet "${SERVICE}"
}

if ! command -v systemctl >/dev/null 2>&1; then
    log "systemctl not available, skipping service restart. Now at $(git rev-parse --short HEAD)."
    exit 0
fi

log "Restarting ${SERVICE}…"
if restart_service; then
    log "OK — ${SERVICE} is active. Now at $(git rev-parse --short HEAD)."
    [ -n "${BACKUP_FILE}" ] && log "Pre-update backup: $(basename "${BACKUP_FILE}")"
    exit 0
fi

# --- Auto-rollback path ---
log "ERROR — ${SERVICE} failed to come back up after update."
journalctl -u "${SERVICE}" -n 20 --no-pager 2>&1 | sed 's/^/  | /' || true

if [ "${OCG_NO_ROLLBACK:-0}" = "1" ]; then
    log "OCG_NO_ROLLBACK=1 — skipping rollback. Manual intervention needed."
    exit 3
fi

log "Rolling back to ${PREVIOUS_HEAD:0:8}…"
git reset --hard --quiet "${PREVIOUS_HEAD}"

if [ -n "${REQS_CHANGED}" ] && [ -x "${VENV_PIP}" ]; then
    log "Reinstalling old requirements.txt…"
    "${VENV_PIP}" install --quiet --upgrade -r requirements.txt
fi

if restart_service; then
    log "Rollback succeeded — ${SERVICE} active at ${PREVIOUS_HEAD:0:8}."
    log "The new version did not boot. Inspect with: journalctl -u ${SERVICE} -e"
    exit 4
else
    log "FATAL — rollback also failed to start the service. Manual intervention required."
    log "Last 20 service log lines:"
    journalctl -u "${SERVICE}" -n 20 --no-pager 2>&1 | sed 's/^/  | /' || true
    exit 3
fi
