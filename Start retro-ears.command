#!/bin/bash
# Double-click to start retro-ears on macOS.
cd "$(dirname "$0")" || exit 1
APP_DIR="$(pwd)"

wait_for_key() {
  [ -n "$RETRO_NO_PAUSE" ] && return
  read -r -p "Press Return to close this window…" _
}

case "$(uname -m)" in
  arm64) BUNDLED_UV="$APP_DIR/bin/uv-arm64" ;;
  *) BUNDLED_UV="$APP_DIR/bin/uv-x86_64" ;;
esac

if [ -x "$BUNDLED_UV" ]; then
  UV="$BUNDLED_UV"
elif command -v uv >/dev/null 2>&1; then
  UV="$(command -v uv)"
else
  echo "Download retro-ears from https://github.com/kandooswill/retro-ears/releases"
  wait_for_key
  exit 1
fi

export UV_PYTHON_INSTALL_DIR="$APP_DIR/.runtime/python"
export UV_CACHE_DIR="$APP_DIR/.runtime/cache"
export UV_PROJECT_ENVIRONMENT="$APP_DIR/.runtime/venv"
export UV_PYTHON_PREFERENCE=only-managed
export RETRO_UV="$UV"

VERSION="$(tr -d '[:space:]' < VERSION)"
if [ "$(cat .runtime/installed-version 2>/dev/null)" != "$VERSION" ]; then
  echo "Setting up retro-ears — the first run takes 1–2 minutes…"
  if ! "$UV" sync --frozen --no-dev; then
    echo "Setup failed — check your internet connection and try again"
    wait_for_key
    exit 1
  fi
  mkdir -p .runtime
  printf '%s' "$VERSION" > .runtime/installed-version
fi

while true; do
  "$UV" run --no-sync python app.py "$@"
  code=$?
  if [ "$code" -eq 42 ]; then
    echo "Restarting…"
    continue
  fi
  break
done

echo "retro-ears stopped. You can close this window."
wait_for_key
exit "$code"
