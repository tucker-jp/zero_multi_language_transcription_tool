"""QThread worker: on-demand translation via OPUS-MT."""

from __future__ import annotations

import queue

from PyQt6.QtCore import QThread, pyqtSignal

from config.settings import Settings
from translation.opus_mt_backend import OpusMTTranslator


class TranslationWorker(QThread):
    """Handles translation requests off the main thread."""

    translation_ready = pyqtSignal(str, str, str, str)  # text, text_trans, sentence, sentence_trans
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._queue: queue.Queue[tuple[str, str] | None] = queue.Queue()
        self._running = False

    def request_translation(self, text: str, sentence: str):
        self._queue.put((text, sentence))

    def run(self):
        self._running = True
        self.status.emit("Loading translation model...")

        try:
            translator = OpusMTTranslator(
                model_name=self._settings.translation_model,
                cache_size=self._settings.translation_cache_size,
            )
            translator.load_model()
            self.status.emit("Translation model loaded.")
        except Exception as e:
            self.error.emit(f"Failed to load translation model: {e}")
            return

        while self._running:
            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if item is None:
                break

            text, sentence = item
            try:
                text_trans, sentence_trans = translator.translate_text(text, sentence)
                self.translation_ready.emit(text, text_trans, sentence, sentence_trans)
            except Exception as e:
                self.error.emit(f"Translation error: {e}")

    def stop(self):
        self._running = False
        self._queue.put(None)
