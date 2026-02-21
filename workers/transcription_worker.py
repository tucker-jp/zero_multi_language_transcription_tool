"""QThread worker: Whisper inference queue → emits transcription results."""

from __future__ import annotations

import queue

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from config.settings import Settings
from transcription.engine import create_engine
from transcription.result import TranscriptionSegment


class TranscriptionWorker(QThread):
    """Processes speech segments through Whisper and emits transcriptions."""

    transcription_ready = pyqtSignal(TranscriptionSegment)
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._queue: queue.Queue[tuple[np.ndarray, float] | None] = queue.Queue()
        self._running = False

    def enqueue(self, audio: np.ndarray, session_offset: float):
        self._queue.put((audio, session_offset))

    def run(self):
        self._running = True
        self.status.emit("Loading Whisper model...")

        try:
            engine = create_engine(
                backend="mlx",
                model=self._settings.whisper_model,
                language=self._settings.language,
            )
            engine.load_model()
            self.status.emit("Whisper model loaded.")
        except Exception as e:
            self.error.emit(f"Failed to load Whisper: {e}")
            return

        while self._running:
            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if item is None:
                break

            audio, offset = item
            try:
                segment = engine.transcribe(audio, session_offset=offset)
                if segment:
                    self.transcription_ready.emit(segment)
            except Exception as e:
                self.error.emit(f"Transcription error: {e}")

    def stop(self):
        self._running = False
        self._queue.put(None)  # Unblock the queue
