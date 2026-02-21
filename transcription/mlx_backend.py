"""mlx-whisper transcription backend for Apple Silicon."""

from __future__ import annotations

import numpy as np
import mlx_whisper

from transcription.engine import TranscriptionEngine
from transcription.result import TranscriptionSegment, WordInfo


class MLXWhisperEngine(TranscriptionEngine):
    def __init__(self, model: str = "small", language: str = "fr"):
        # mlx-whisper uses HuggingFace model paths
        if "/" not in model:
            model = f"mlx-community/whisper-{model}-mlx"
        self._model_path = model
        self._language = language
        self._loaded = False

    def load_model(self):
        """Trigger model download/load by running a dummy transcription."""
        dummy = np.zeros(16000, dtype=np.float32)
        mlx_whisper.transcribe(
            dummy,
            path_or_hf_repo=self._model_path,
            language=self._language,
            word_timestamps=True,
        )
        self._loaded = True

    def is_loaded(self) -> bool:
        return self._loaded

    def transcribe(
        self, audio: np.ndarray, session_offset: float = 0.0
    ) -> TranscriptionSegment | None:
        """Transcribe audio using mlx-whisper.

        Args:
            audio: float32 array at 16kHz
            session_offset: time offset in seconds for absolute timing
        """
        audio = audio.astype(np.float32)
        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=self._model_path,
            language=self._language,
            word_timestamps=True,
        )

        if not result or not result.get("segments"):
            return None

        # Combine all segments into one TranscriptionSegment
        full_text = result["text"].strip()
        if not full_text:
            return None

        words = []
        for seg in result["segments"]:
            for w in seg.get("words", []):
                words.append(
                    WordInfo(
                        word=w["word"].strip(),
                        start=w["start"],
                        end=w["end"],
                        probability=w.get("probability", 1.0),
                    )
                )

        first_seg = result["segments"][0]
        last_seg = result["segments"][-1]

        self._loaded = True

        return TranscriptionSegment(
            text=full_text,
            start_time=session_offset + first_seg["start"],
            end_time=session_offset + last_seg["end"],
            words=words,
            language=self._language,
        )
