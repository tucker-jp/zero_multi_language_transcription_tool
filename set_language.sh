#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [[ $# -ne 1 ]]; then
  echo "Usage: ./set_language.sh fr|es"
  exit 1
fi

LANG_CODE="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
case "$LANG_CODE" in
  fr)
    TRANS_MODEL="Helsinki-NLP/opus-mt-fr-en"
    ;;
  es)
    TRANS_MODEL="Helsinki-NLP/opus-mt-es-en"
    ;;
  *)
    echo "Unsupported language '$1'. Use 'fr' or 'es'."
    exit 1
    ;;
esac

python3 - <<'PY' "$LANG_CODE" "$TRANS_MODEL"
import json
import sys
from pathlib import Path

lang = sys.argv[1]
translation_model = sys.argv[2]

settings_path = Path.home() / ".transcription_helper" / "settings.json"
settings_path.parent.mkdir(parents=True, exist_ok=True)

data = {}
if settings_path.exists():
    try:
        data = json.loads(settings_path.read_text())
    except Exception:
        data = {}

data["language"] = lang
data["translation_model"] = translation_model

settings_path.write_text(json.dumps(data, indent=2))
print(f"Updated {settings_path}")
print(f"language={lang}")
print(f"translation_model={translation_model}")
PY
