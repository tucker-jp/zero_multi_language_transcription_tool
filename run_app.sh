#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

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

exec python3 main.py "$@"
