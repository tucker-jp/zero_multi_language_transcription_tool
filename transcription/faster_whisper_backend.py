"""faster-whisper transcription backend."""

from __future__ import annotations

import numpy as np

from transcription.engine import TranscriptionEngine
from transcription.result import TranscriptionSegment, WordInfo


class FasterWhisperEngine(TranscriptionEngine):
    """Transcription engine powered by faster-whisper (CTranslate2)."""

    def __init__(
        self,
        model: str = "small",
        language: str = "fr",
        word_timestamps: bool = False,
        compute_type: str = "int8",
    ):
        self._model_name = model
        self._language = language
        self._word_timestamps = bool(word_timestamps)
        self._compute_type = compute_type
        self._loaded = False
        self._model = None

    def load_model(self):
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise ImportError(
                "faster-whisper is not installed. Install with: "
                "pip install faster-whisper"
            ) from e

        # On Apple Silicon, CPU + mixed int8/float16 is often the best throughput
        # choice for live captions without the memory overhead of larger dtypes.
        self._model = WhisperModel(
            self._model_name,
            device="cpu",
            compute_type=self._compute_type,
        )
        self._loaded = True

    def is_loaded(self) -> bool:
        return self._loaded and self._model is not None

    def transcribe(
        self, audio: np.ndarray, session_offset: float = 0.0
    ) -> TranscriptionSegment | None:
        if not self.is_loaded():
            raise RuntimeError("Model not loaded. Call load_model() first.")

        audio = audio.astype(np.float32)
        segments_iter, _info = self._model.transcribe(
            audio,
            language=self._language,
            word_timestamps=self._word_timestamps,
            vad_filter=True,
            beam_size=1,
            best_of=1,
            temperature=0.0,
        )
        segments = list(segments_iter)
        if not segments:
            return None

        full_text = " ".join(seg.text.strip() for seg in segments).strip()
        if not full_text:
            return None

        words: list[WordInfo] = []
        if self._word_timestamps:
            for seg in segments:
                for w in seg.words or []:
                    token = (w.word or "").strip()
                    if not token:
                        continue
                    words.append(
                        WordInfo(
                            word=token,
                            start=float(w.start),
                            end=float(w.end),
                            probability=float(getattr(w, "probability", 1.0)),
                        )
                    )

        return TranscriptionSegment(
            text=full_text,
            start_time=session_offset + float(segments[0].start),
            end_time=session_offset + float(segments[-1].end),
            words=words,
            language=self._language,
        )
