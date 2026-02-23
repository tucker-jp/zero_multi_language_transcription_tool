"""French Transcription Helper — main entry point.

Captures system audio via BlackHole, transcribes French speech with mlx-whisper,
displays live clickable captions in a floating overlay, and provides
click-to-translate via OPUS-MT with vocabulary saving and TXT export.
"""

from __future__ import annotations

import sys
import signal
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QFileDialog
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor

from config.settings import Settings
from audio.capture import find_blackhole_device
from workers.audio_worker import AudioWorker
from workers.transcription_worker import TranscriptionWorker
from workers.openai_realtime_worker import OpenAIRealtimeWorker
from workers.translation_worker import TranslationWorker
from transcription.result import TranscriptionSegment
from storage.database import Database
from storage.anki_export import export_anki
from storage.txt_export import export_txt
from ui.overlay import OverlayWindow


class TranscriptionApp:
    """Wires together all workers, UI, and storage."""

    def __init__(self):
        self._settings = Settings.load()
        self._db = Database(self._settings.db_path)
        self._db.connect()
        self._session_id: int | None = None
        self._pending_db_segments: list[TranscriptionSegment] = []
        self._db_flush_timer: QTimer | None = None
        self._last_vocab_id: int | None = None
        self._latency_samples_ms: list[float] = []

        # Workers
        self._audio_worker: AudioWorker | None = None
        self._transcription_worker: TranscriptionWorker | None = None
        self._openai_realtime_worker: OpenAIRealtimeWorker | None = None
        self._translation_worker: TranslationWorker | None = None

        # UI
        self._overlay: OverlayWindow | None = None
        self._tray: QSystemTrayIcon | None = None
        self._manage_window = None

    def start(self):
        self._check_blackhole()
        self._session_id = self._db.start_session(
            title=f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

        self._create_overlay()
        self._create_workers()
        self._connect_signals()
        self._start_db_flush_timer()
        self._start_workers()
        self._create_tray()
        self._overlay.show()

    def _check_blackhole(self):
        if not self._settings.audio_device and find_blackhole_device() is None:
            print(
                "ERROR: BlackHole audio device not found.\n"
                "Please install BlackHole 2ch and set up a Multi-Output Device.\n"
                "See setup_audio.md for instructions."
            )
            sys.exit(1)

    def _create_overlay(self):
        s = self._settings
        self._overlay = OverlayWindow(
            width=s.overlay_width,
            height=s.overlay_height,
            opacity=s.overlay_opacity,
            font_size=s.font_size,
            x=s.overlay_x,
            y=s.overlay_y,
        )

    def _create_workers(self):
        self._audio_worker = AudioWorker(self._settings)
        if self._settings.stt_provider == "openai_realtime":
            self._openai_realtime_worker = OpenAIRealtimeWorker(self._settings)
            self._transcription_worker = None
        else:
            self._transcription_worker = TranscriptionWorker(self._settings)
            self._openai_realtime_worker = None
        self._translation_worker = TranslationWorker(self._settings)

    def _connect_signals(self):
        aw = self._audio_worker
        tw = self._transcription_worker
        ow = self._openai_realtime_worker
        tl = self._translation_worker
        ov = self._overlay

        # Audio → Transcription pipeline
        if tw is not None:
            aw.speech_segment.connect(tw.enqueue)
            tw.transcription_ready.connect(self._on_transcription)
            tw.error.connect(self._on_error)
            tw.status.connect(self._on_status)
        elif ow is not None:
            aw.audio_chunk.connect(ow.enqueue_audio_chunk)
            ow.transcription_ready.connect(self._on_transcription)
            ow.error.connect(self._on_error)
            ow.status.connect(self._on_status)

        aw.error.connect(self._on_error)
        aw.status.connect(self._on_status)

        # Translation → auto-save + UI
        tl.translation_ready.connect(self._on_translation_ready)
        tl.error.connect(self._on_error)
        tl.status.connect(self._on_status)

        # UI → Workers
        ov.pause_toggled.connect(self._on_pause_toggled)
        ov.export_requested.connect(self._on_export)
        ov.save_folder_requested.connect(self._on_choose_save_folder)
        ov.text_selected.connect(tl.request_translation)
        ov.undo_save_requested.connect(self._on_undo_save)

    def _start_workers(self):
        if self._transcription_worker:
            self._transcription_worker.start()
        if self._openai_realtime_worker:
            self._openai_realtime_worker.start()
        self._translation_worker.start()
        self._audio_worker.start()

    def _start_db_flush_timer(self):
        self._db_flush_timer = QTimer()
        self._db_flush_timer.setInterval(500)
        self._db_flush_timer.timeout.connect(self._flush_segment_batch)
        self._db_flush_timer.start()

    def _create_tray(self):
        # Create a simple colored circle as tray icon
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(100, 181, 246))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, 4, 24, 24)
        painter.end()

        icon = QIcon(pixmap)
        self._tray = QSystemTrayIcon(icon)

        menu = QMenu()
        self._pause_action = menu.addAction("Pause Listening")
        self._pause_action.triggered.connect(self._on_tray_pause)
        menu.addSeparator()
        show_action = menu.addAction("Show Overlay")
        show_action.triggered.connect(self._overlay.show)
        hide_action = menu.addAction("Hide Overlay")
        hide_action.triggered.connect(self._overlay.hide)
        menu.addSeparator()
        manage_action = menu.addAction("Manage...")
        manage_action.triggered.connect(self._on_manage)
        menu.addSeparator()
        export_action = menu.addAction("Export Session TXT...")
        export_action.triggered.connect(self._on_export)
        anki_action = menu.addAction("Export Anki Vocabulary...")
        anki_action.triggered.connect(self._on_export_anki)
        save_dir_action = menu.addAction("Set Default Save Folder...")
        save_dir_action.triggered.connect(self._on_choose_save_folder)
        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._on_quit)

        self._tray.setContextMenu(menu)
        self._tray.setToolTip("French Transcription Helper")
        self._tray.show()

    def _on_transcription(self, segment: TranscriptionSegment):
        self._overlay.set_caption(segment.text, is_final=segment.is_final)
        if not segment.is_final:
            return
        if segment.source == "openai_realtime_repair":
            self._on_status("Applied high-accuracy repair pass on latest segment.")
        if self._session_id is not None:
            self._pending_db_segments.append(segment)
            if len(self._pending_db_segments) >= 10:
                self._flush_segment_batch()

        if segment.end_to_caption_ms is not None:
            self._record_latency(segment.end_to_caption_ms)

    def _record_latency(self, latency_ms: float):
        self._latency_samples_ms.append(latency_ms)
        if len(self._latency_samples_ms) > 100:
            self._latency_samples_ms = self._latency_samples_ms[-100:]

        log_every = max(1, int(self._settings.latency_log_every_n_segments))
        if len(self._latency_samples_ms) % log_every != 0:
            return

        recent = self._latency_samples_ms[-log_every:]
        avg_ms = sum(recent) / len(recent)
        p95_ms = sorted(recent)[int(0.95 * (len(recent) - 1))]
        target = int(self._settings.live_latency_target_ms)
        self._on_status(
            f"Latency avg={avg_ms:.0f}ms p95={p95_ms:.0f}ms target<={target}ms ({len(self._latency_samples_ms)} seg)"
        )

    def _flush_segment_batch(self):
        if self._session_id is None or not self._pending_db_segments:
            return
        self._db.add_segments(self._session_id, self._pending_db_segments)
        self._pending_db_segments.clear()

    def _get_current_session_segments(self) -> list[dict]:
        self._flush_segment_batch()
        if self._session_id is None:
            return []
        return self._db.get_segments(self._session_id)

    def _on_pause_toggled(self, paused: bool):
        if paused:
            self._audio_worker.pause()
        else:
            self._audio_worker.resume()
        self._pause_action.setText(
            "Resume Listening" if paused else "Pause Listening"
        )

    def _on_tray_pause(self):
        paused = not self._overlay.controls.is_paused
        if paused:
            self._audio_worker.pause()
        else:
            self._audio_worker.resume()
        self._overlay.controls.set_paused(paused)
        self._pause_action.setText(
            "Resume Listening" if paused else "Pause Listening"
        )

    def _on_manage(self):
        # Lazy import to keep startup fast
        from ui.manage_window import ManageWindow

        if self._manage_window is None:
            self._manage_window = ManageWindow(self._db, self._settings)
        self._manage_window.refresh()
        self._manage_window.show()
        self._manage_window.raise_()
        self._manage_window.activateWindow()

    def _on_export(self):
        segments = self._get_current_session_segments()
        if not segments:
            return
        default_name = f"transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        export_dir = self._default_transcript_dir()
        export_dir.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self._overlay,
            "Export Transcript",
            str(export_dir / default_name),
            "Text Files (*.txt)",
        )
        if path:
            export_txt(segments, path, include_timestamps=True)
            self._on_status(f"Exported TXT to {path}")

    def _on_translation_ready(
        self, word: str, word_trans: str, sentence: str, sentence_trans: str
    ):
        # Auto-save to vocabulary
        self._last_vocab_id = self._db.save_word(
            word, word_trans, sentence, self._session_id
        )
        # Then show popup
        self._overlay.show_translation(word, word_trans, sentence, sentence_trans)

    def _on_undo_save(self):
        if self._last_vocab_id is not None:
            self._db.delete_word(self._last_vocab_id)
            self._last_vocab_id = None

    def _on_export_anki(self):
        vocab = self._db.get_vocabulary()
        if not vocab:
            self._on_status("No vocabulary to export")
            return
        default_name = f"anki_{self._settings.language}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        export_dir = self._default_anki_dir()
        export_dir.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self._overlay,
            "Export Anki Vocabulary",
            str(export_dir / default_name),
            "Text Files (*.txt)",
        )
        if path:
            export_anki(vocab, path, tag=self._settings.language)
            self._on_status(f"Exported {len(vocab)} words to {path}")

    def _save_root(self) -> Path:
        configured = str(self._settings.default_save_dir or "").strip()
        root = Path(configured).expanduser() if configured else Path.home()
        return root

    def _default_transcript_dir(self) -> Path:
        return self._save_root() / "transcripts" / self._settings.language

    def _default_anki_dir(self) -> Path:
        return self._save_root() / "anki" / self._settings.language

    def _on_choose_save_folder(self, _checked: bool = False):
        current = self._save_root()
        folder = QFileDialog.getExistingDirectory(
            self._overlay,
            "Select Default Save Folder",
            str(current),
        )
        if not folder:
            return
        chosen = Path(folder).expanduser().resolve()
        self._settings.default_save_dir = str(chosen)
        self._settings.save()
        self._on_status(f"Default save folder set to {chosen}")

    def _on_error(self, msg: str):
        print(f"[ERROR] {msg}")

    def _on_status(self, msg: str):
        print(f"[STATUS] {msg}")

    def _on_quit(self):
        self._flush_segment_batch()
        if self._db_flush_timer is not None:
            self._db_flush_timer.stop()

        self._stop_workers()
        if self._session_id is not None:
            self._db.end_session(self._session_id)
            # Auto-save plain-text transcript
            segments = self._get_current_session_segments()
            if segments:
                txt_dir = self._default_transcript_dir()
                txt_dir.mkdir(parents=True, exist_ok=True)
                filename = f"session_{self._session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                export_txt(segments, txt_dir / filename, include_timestamps=True)
                print(f"[STATUS] Auto-saved transcript to {txt_dir / filename}")
        self._db.close()
        QApplication.quit()

    def _stop_workers(self):
        if self._audio_worker:
            self._audio_worker.stop()
            self._audio_worker.wait(3000)
        if self._transcription_worker:
            self._transcription_worker.stop()
            self._transcription_worker.wait(3000)
        if self._openai_realtime_worker:
            self._openai_realtime_worker.stop()
            self._openai_realtime_worker.wait(3000)
        if self._translation_worker:
            self._translation_worker.stop()
            self._translation_worker.wait(3000)


def main():
    # Allow Ctrl+C to work
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setApplicationName("French Transcription Helper")
    app.setQuitOnLastWindowClosed(False)

    transcription_app = TranscriptionApp()
    transcription_app.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
