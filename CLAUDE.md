# French Transcription Helper

## Workflow Rules
- **Always reference this file** at the start of every task.
- **After every task**, update the README.md and the TODO section below — add new items, clear completed ones.

## Overview
macOS desktop app that captures system audio via BlackHole, transcribes French speech in real time with mlx-whisper, and displays live clickable captions in a floating overlay that works above fullscreen apps. Click any word or drag to select a phrase for instant French→English translation via OPUS-MT. Translations are auto-saved to vocabulary (with Undo). Supports SRT export and Anki vocabulary export.

## Running
```bash
source .venv/bin/activate
python main.py
```

## Building the .app
```bash
chmod +x build_app.sh
./build_app.sh
# Output: dist/French Transcription Helper.app
```

## Architecture
- **Workers** (`workers/`): QThread subclasses for audio capture, transcription, and translation. Communicate via Qt signals.
- **main.py**: Entry point — creates all workers and UI, wires signals/slots, manages system tray.
- **UI** (`ui/`): PyQt6 frameless overlay window with clickable captions (single-word click or drag-to-select phrases via `text_selected` signal), control bar, translation popup with auto-save + undo.
  - `ui/macos_window.py`: ctypes utility to set NSWindow level for fullscreen overlay support.
- **Audio** (`audio/`): sounddevice capture, Silero VAD, ring buffer.
- **Transcription** (`transcription/`): Engine ABC with mlx-whisper backend (Apple Silicon optimized).
- **Translation** (`translation/`): OPUS-MT via HuggingFace transformers, LRU cache.
- **Storage** (`storage/`): SQLite for sessions/segments/vocabulary, SRT export, Anki TSV export.
- **Config** (`config/settings.py`): Settings dataclass with JSON persistence at `~/.transcription_helper/settings.json`.

## Constraints
- **Python 3.9** — use `from __future__ import annotations` in every file for `X | Y` union syntax.
- **macOS only** — Apple Silicon required for mlx-whisper. No CUDA paths.
- **BlackHole 2ch** required for system audio capture.

## Coding Conventions
- PyQt6 signal/slot patterns throughout. Workers are QThread subclasses.
- No global state — `TranscriptionApp` in main.py owns everything.
- Keep UI responsive — all heavy work happens in worker threads.
- Models download on first launch (~1.3 GB total), not bundled with the app.

## TODO
- Multi-language support (Spanish, German) — language selector UI exists with "Coming Soon" placeholders

## Recent Changes
- **Transcription accuracy benchmark**: `test_accuracy.py` — standalone CLI that downloads French YouTube audio+subs, transcribes via MLXWhisperEngine, reports WER per-segment and overall
- **Reduced transcription latency**: `vad_silence_ms` 700→350, `vad_min_speech_ms` 250→200
- **Forced segment breaks**: New `max_speech_seconds` setting (default 3.0s) breaks long continuous speech into chunks
- **Rolling captions**: Caption widget now accumulates and displays last 5 segments instead of replacing each time
