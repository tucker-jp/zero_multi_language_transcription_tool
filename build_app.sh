#!/usr/bin/env bash
# Build macOS .app bundle using py2app.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment
if [ ! -d ".venv" ]; then
    echo "ERROR: .venv not found. Run 'python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt' first."
    exit 1
fi
source .venv/bin/activate

# Install py2app if missing
if ! python -c "import py2app" 2>/dev/null; then
    echo "Installing py2app..."
    pip install py2app
fi

# Clean previous builds
rm -rf build dist

# Build the .app
echo "Building .app bundle..."
python setup.py py2app

echo ""
echo "Done! App bundle at:"
echo "  dist/French Transcription Helper.app"
