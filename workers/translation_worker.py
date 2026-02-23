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
        maxsize = max(1, int(settings.translation_queue_maxsize))
        self._queue: queue.Queue[tuple[str, str] | None] = queue.Queue(maxsize=maxsize)
        self._running = False
        self._dropped_count = 0

    def request_translation(self, text: str, sentence: str):
        item = (text, sentence)
        try:
            self._queue.put_nowait(item)
            return
        except queue.Full:
            pass

        try:
            self._queue.get_nowait()
        except queue.Empty:
            pass

        try:
            self._queue.put_nowait(item)
        except queue.Full:
            return

        self._dropped_count += 1
        if self._dropped_count % 25 == 0:
            self.status.emit(
                f"Translation queue overloaded; dropped {self._dropped_count} requests."
            )

    def run(self):
        self._running = True
        translator = None

        try:
            self.status.emit("Loading translation model...")
            translator = OpusMTTranslator(
                model_name=self._settings.translation_model,
                cache_size=self._settings.translation_cache_size,
            )
            translator.load_model()
            self.status.emit("Translation model loaded.")
        except Exception as e:
            self.error.emit(f"Failed to load translation model: {e}")
            return

        try:
            while self._running:
                try:
                    item = self._queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                if item is None:
                    break

                try:
                    text, sentence = item
                except Exception:
                    self.error.emit("Translation worker received malformed queue item.")
                    continue

                try:
                    context = self._prepare_sentence_context(text, sentence)
                    text_trans = translator.translate(text)
                    sentence_trans = translator.translate(context) if context else ""
                    self.translation_ready.emit(text, text_trans, context, sentence_trans)
                except Exception as e:
                    self.error.emit(f"Translation error: {e}")
        except Exception as e:
            self.error.emit(f"Translation worker crashed: {e}")

    def stop(self):
        self._running = False
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass

    def _prepare_sentence_context(self, text: str, sentence: str) -> str:
        """Trim context aggressively to reduce click-to-translation latency."""
        if not bool(self._settings.translation_include_sentence_context):
            return ""

        sentence = " ".join((sentence or "").split())
        if not sentence:
            return ""

        is_single_word = " " not in text.strip()
        if is_single_word and not bool(
            self._settings.translation_include_sentence_for_single_word
        ):
            return ""

        max_chars = int(self._settings.translation_sentence_max_chars)
        if len(sentence) <= max_chars:
            return sentence

        # Keep the selected text near the center of the context window when possible.
        needle = text.strip().lower()
        haystack = sentence.lower()
        idx = haystack.find(needle) if needle else -1

        if idx < 0:
            return sentence[:max_chars].rstrip() + "..."

        center = idx + max(1, len(needle) // 2)
        half = max_chars // 2
        start = max(0, center - half)
        end = min(len(sentence), start + max_chars)
        start = max(0, end - max_chars)

        # Nudge to word boundaries.
        if start > 0:
            next_space = sentence.find(" ", start)
            if next_space != -1 and next_space + 1 < len(sentence):
                start = next_space + 1
        if end < len(sentence):
            prev_space = sentence.rfind(" ", start, end)
            if prev_space > start:
                end = prev_space

        clipped = sentence[start:end].strip()
        if start > 0:
            clipped = "..." + clipped
        if end < len(sentence):
            clipped = clipped + "..."
        return clipped
