#!/usr/bin/env bash
# Start retro-ears on macOS. Usage: ./run.sh [--update] [--no-browser]
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "retro-ears needs Python 3.10 or newer: https://www.python.org/downloads/"
  exit 1
fi
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "retro-ears needs Python 3.10 or newer (found $("$PYTHON" --version 2>&1))."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "First run: setting up (this takes a minute)…"
  "$PYTHON" -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
fi

APP_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --update) .venv/bin/python -m pip install --upgrade "yt-dlp[default]" ytmusicapi ;;
    *) APP_ARGS+=("$arg") ;;
  esac
done

.venv/bin/python -m pip install --quiet -r requirements.txt
exec .venv/bin/python app.py "${APP_ARGS[@]+"${APP_ARGS[@]}"}"
