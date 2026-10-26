#!/bin/bash

# Always run from the backend folder, no matter where the script is called from
cd "$(dirname "$0")" || exit 1

# Setup check: Python environment
if [ ! -f venv/bin/activate ]; then
    echo "Python-Umgebung (venv) fehlt, wird erstellt..."
    if ! python3 -m venv venv; then
        rm -rf venv
        echo "venv konnte nicht erstellt werden. Auf dem Pi hilft: sudo apt install python3-venv"
        exit 1
    fi
fi

source venv/bin/activate

# Setup check: install dependencies when requirements.txt is new or has changed
STAMP=venv/.requirements.sha256
CURRENT=$(sha256sum requirements.txt | cut -d' ' -f1)
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$CURRENT" ] || ! command -v uvicorn > /dev/null; then
    echo "Installiere Python-Pakete..."
    pip install -r requirements.txt || exit 1
    echo "$CURRENT" > "$STAMP"
fi

# Setup check: Tailscale Funnel (only a hint, does not stop the start)
if ! command -v tailscale > /dev/null; then
    echo "Hinweis: Tailscale ist nicht installiert."
elif ! tailscale funnel status 2> /dev/null | grep -q 1919; then
    echo "Hinweis: Tailscale Funnel scheint nicht für Port 1919 eingerichtet zu sein (sudo tailscale funnel --bg 1919)."
fi

# Secrets (APP_PASSWORD, SECRET_KEY) come from backend/.env, which is not in git. See .env.example.
if [ ! -f .env ]; then
    echo "backend/.env fehlt. Kopiere .env.example nach .env und trage Passwort und SECRET_KEY ein."
    exit 1
fi
set -a
source .env
set +a
if [ -z "$APP_PASSWORD" ] || [ -z "$SECRET_KEY" ]; then
    echo "APP_PASSWORD oder SECRET_KEY fehlt in backend/.env."
    exit 1
fi

# Daily backup of the database into <repo>/logs, the 7 newest backups are kept
BACKUP_DIR="$(cd .. && pwd)/logs"

backup_db() {
    [ -f furniture.db ] || return 0
    mkdir -p "$BACKUP_DIR"
    local target="$BACKUP_DIR/furniture-$(date +%F).db"
    [ -f "$target" ] && return 0
    # sqlite backup API: consistent copy even while the server is writing
    python - "$target.tmp" <<'PY'
import sqlite3, sys
src = sqlite3.connect("furniture.db")
dst = sqlite3.connect(sys.argv[1])
src.backup(dst)
dst.close()
src.close()
PY
    mv "$target.tmp" "$target"
    ls -1t "$BACKUP_DIR"/furniture-*.db | tail -n +8 | xargs -r rm --
}

# Checks hourly, so a backup is made about once a day while the server runs
( while true; do backup_db; sleep 3600; done ) &
BACKUP_PID=$!
trap 'kill $BACKUP_PID 2> /dev/null' EXIT

uvicorn app.main:app --reload --port 1919 --host 127.0.0.1

