#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

LOCK_DIR="${HOME}/.transcription_helper/.run_lock"
PID_FILE="${LOCK_DIR}/pid"
mkdir -p "${HOME}/.transcription_helper"

if [[ -d "$LOCK_DIR" ]]; then
  if [[ -f "$PID_FILE" ]]; then
    existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$existing_pid" ]] && ps -p "$existing_pid" >/dev/null 2>&1; then
      echo "ERROR: Transcription Helper is already running (PID ${existing_pid})."
      echo "Quit it from the tray first, then run this command again."
      exit 1
    fi
  fi
  rm -rf "$LOCK_DIR"
fi

mkdir "$LOCK_DIR"
echo "$$" > "$PID_FILE"
cleanup() {
  rm -rf "$LOCK_DIR"
}
trap cleanup EXIT INT TERM

if [[ ! -d ".venv" ]]; then
  echo "ERROR: .venv not found. Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

source ".venv/bin/activate"

if [[ -f ".env" ]]; then
  set -a
  source ".env"
  set +a
fi

python3 main.py "$@"
