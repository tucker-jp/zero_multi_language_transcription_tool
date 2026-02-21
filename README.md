# French Transcription Helper

A macOS desktop app that captures system audio, transcribes French speech in real time with pluggable Whisper backends (`mlx-whisper` by default, optional `faster-whisper`), and displays live clickable captions in a floating overlay — even above fullscreen apps. Click any word or drag to select a phrase for instant French-to-English translation via OPUS-MT. Translations are auto-saved to vocabulary (with one-click Undo). Supports readable plain-text transcript export and Anki-compatible vocabulary export.

## Prerequisites

- **macOS** on Apple Silicon (M1/M2/M3/M4)
- **Python 3.9+**
- **BlackHole 2ch** virtual audio driver for system audio capture

See [setup_audio.md](setup_audio.md) for BlackHole installation and Multi-Output Device configuration.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Models are downloaded automatically on first run (~1 GB for Whisper small, ~300 MB for OPUS-MT). They are **not** bundled with the .app — the first launch will download them.

Optional backend for local A/B testing:
```bash
pip install faster-whisper
```

## Building the .app Bundle

To package as a standalone macOS application:

```bash
source .venv/bin/activate
chmod +x build_app.sh
./build_app.sh
```

This produces `dist/French Transcription Helper.app` which you can drag to `/Applications` or run directly from Finder.

## Usage

### Starting

```bash
source .venv/bin/activate
python main.py
```

A floating overlay appears at the bottom of your screen and a system tray icon (blue circle) is added.

### Using the overlay

- **Live captions** appear as French audio is detected
- **Click any word** to see its English translation in a popup (labeled "WORD") — automatically saved to vocabulary
- **Drag across words** to select a phrase for translation (labeled "PHRASE") — selected words highlight in blue during the drag, also auto-saved
- **Undo Save** button in the popup removes the last auto-saved word/phrase from vocabulary
- **Pause/Resume** button on the overlay toggles audio capture
- **Export Session TXT** button opens a save dialog for plain-text transcript export
- **Fullscreen support** — overlay stays visible above fullscreen apps and on all Spaces

### System tray menu

- **Pause/Resume Listening** — toggle audio capture (syncs with overlay button)
- **Show/Hide Overlay** — toggle overlay visibility
- **Manage...** — opens the management window to browse sessions, manage vocabulary with select/delete, and export filtered vocabulary to Anki. Includes a language selector (French active; Spanish and German coming soon).
- **Export Session TXT...** — manually export transcript text
- **Export Anki Vocabulary...** — export all saved vocabulary as a tab-separated `.txt` file (front=French, back=English) ready for Anki import
- **Quit** — stop all workers and exit

### Stopping

Quit via the tray menu or press **Ctrl+C** in the terminal. On exit the app automatically:

1. Stops workers (audio, then transcription, then translation)
2. Ends the database session
3. Auto-exports a TXT transcript to `~/.transcription_helper/transcripts/`
4. Closes the database

## Configuration

Settings are stored at `~/.transcription_helper/settings.json`. Edit this file to change defaults (the app must be restarted for changes to take effect).

| Setting | Default | Description |
|---|---|---|
| `performance_profile` | `"live"` | Runtime tuning profile (`live`, `balanced`, `accurate`) |
| `live_latency_target_ms` | `900` | Target end-to-caption latency in milliseconds |
| `latency_log_every_n_segments` | `10` | Print rolling latency stats every N segments |
| `audio_device` | `null` | Audio input device name or index. `null` = auto-detect BlackHole |
| `sample_rate` | `16000` | Audio sample rate in Hz |
| `channels` | `1` | Number of audio channels |
| `chunk_duration_ms` | `30` | Duration of each VAD chunk in ms |
| `vad_threshold` | `0.5` | Voice activity detection confidence threshold (0-1) |
| `vad_silence_ms` | `350` | Silence duration (ms) to trigger end-of-speech |
| `vad_min_speech_ms` | `200` | Ignore speech segments shorter than this (ms) |
| `max_speech_seconds` | `3.0` | Force a segment break during long continuous speech (seconds) |
| `transcription_backend` | `"mlx"` | STT backend (`mlx` or `faster_whisper`) |
| `whisper_model` | `"small"` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large`) |
| `language` | `"fr"` | Source language code |
| `max_segment_seconds` | `15.0` | Maximum transcription segment length |
| `segment_overlap_seconds` | `1.0` | Overlap between consecutive segments |
| `word_timestamps` | `false` | Enable per-word timestamps (slower when `true`) |
| `faster_whisper_compute_type` | `"int8_float16"` | Compute type when using `faster_whisper` |
| `translation_model` | `"Helsinki-NLP/opus-mt-fr-en"` | HuggingFace translation model |
| `translation_cache_size` | `1000` | Number of cached translations (LRU) |
| `transcription_queue_maxsize` | `8` | Max pending audio segments before dropping oldest |
| `translation_queue_maxsize` | `32` | Max pending translation requests before dropping oldest |
| `overlay_opacity` | `0.85` | Overlay window opacity (0-1) |
| `font_size` | `22` | Caption text size in points |
| `overlay_width` | `800` | Overlay width in pixels |
| `overlay_height` | `160` | Overlay height in pixels |
| `overlay_x` | `-1` | Overlay X position. `-1` = centered |
| `overlay_y` | `-1` | Overlay Y position. `-1` = bottom of screen |
| `data_dir` | `"~/.transcription_helper"` | Directory for database and exports |
| `db_path` | `"~/.transcription_helper/transcripts.db"` | SQLite database path |

## Architecture

```
                    +-----------+
  System Audio ---> | BlackHole | ---> sounddevice
                    +-----------+
                         |
                   AudioWorker (QThread)
                    capture + VAD
                         |
                   speech segments
                         |
               TranscriptionWorker (QThread)
            mlx-whisper / faster-whisper
                         |
                  transcribed text
                    /         \
        OverlayWindow        Database (SQLite)
        (PyQt6 UI)           segments + sessions
              |
     click word / drag phrase
              |
        TranslationWorker (QThread)
           OPUS-MT
              |
        translation popup
```

| Module | Purpose |
|---|---|
| `main.py` | Entry point, wires signals/slots between workers and UI |
| `config/settings.py` | Settings dataclass with JSON persistence |
| `audio/capture.py` | sounddevice input stream (BlackHole) |
| `audio/vad.py` | Silero VAD for speech detection |
| `audio/buffer.py` | Ring buffer for audio chunks |
| `transcription/engine.py` | Transcription engine ABC |
| `transcription/mlx_backend.py` | mlx-whisper backend (Apple Silicon) |
| `transcription/faster_whisper_backend.py` | faster-whisper backend (CTranslate2) |
| `transcription/result.py` | TranscriptionSegment dataclass |
| `translation/opus_mt_backend.py` | OPUS-MT translation via HuggingFace transformers |
| `translation/cache.py` | LRU translation cache |
| `workers/audio_worker.py` | QThread for audio capture + VAD |
| `workers/transcription_worker.py` | QThread for Whisper transcription |
| `workers/translation_worker.py` | QThread for text translation (words and phrases) |
| `ui/overlay.py` | Frameless floating overlay window (fullscreen-aware) |
| `ui/caption_widget.py` | Clickable caption text display |
| `ui/controls.py` | Pause/Export control buttons |
| `ui/translation_popup.py` | Translation popup with auto-save + undo |
| `ui/macos_window.py` | macOS native window level utility (ctypes/ObjC) |
| `ui/styles.py` | Qt stylesheets (overlay) |
| `ui/manage_styles.py` | Qt stylesheets (management window) |
| `ui/manage_window.py` | Management window for sessions and vocabulary |
| `storage/database.py` | SQLite database for sessions, segments, vocabulary |
| `storage/txt_export.py` | Plain-text transcript export |
| `storage/anki_export.py` | Anki-compatible tab-separated vocabulary export |

## Transcription Accuracy Testing

A standalone benchmark script compares transcription output against reference subtitles from YouTube videos.

**Prerequisites:**
```bash
brew install yt-dlp ffmpeg
```

**Usage:**
```bash
source .venv/bin/activate
python test_accuracy.py "https://www.youtube.com/watch?v=XXXXX"  # specific video
python test_accuracy.py                                           # default French clip
python test_accuracy.py --model large                             # test different model
python test_accuracy.py --backend faster_whisper --model small
python test_accuracy.py --skip-download                           # reuse cached audio
python test_accuracy.py --skip-download --subtitle test_data/subs.fr-orig.vtt
python test_accuracy.py --skip-download --merge-short-ms 900 --merge-gap-ms 120
```

The script downloads audio + French subtitles, transcribes the audio through the configured test engine, and reports Word Error Rate (WER) overall plus merged-window comparisons with side-by-side output. It also flags likely repetition-loop hallucinations.

## Troubleshooting

**"BlackHole audio device not found"**
Install BlackHole 2ch and configure a Multi-Output Device in Audio MIDI Setup. See [setup_audio.md](setup_audio.md).

**No captions appearing**
- Check that audio is playing through the Multi-Output Device (not just regular speakers)
- Try lowering `vad_threshold` in settings (e.g. `0.3`)
- Ensure the source audio is in French

**High memory usage**
- Switch to a smaller Whisper model (`"tiny"` or `"base"`) in settings
- Reduce `translation_cache_size`

**Slow transcription**
- Use a smaller Whisper model
- Close other heavy applications to free Apple Silicon GPU/Neural Engine resources
