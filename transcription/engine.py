"""Abstract transcription engine and factory."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from transcription.result import TranscriptionSegment


class TranscriptionEngine(ABC):
    @abstractmethod
    def load_model(self):
        """Load the model into memory."""

    @abstractmethod
    def transcribe(
        self, audio: np.ndarray, session_offset: float = 0.0
    ) -> TranscriptionSegment | None:
        """Transcribe audio array and return a segment, or None if no speech."""

    @abstractmethod
    def is_loaded(self) -> bool:
        """Whether the model is loaded and ready."""


def create_engine(backend: str = "mlx", **kwargs) -> TranscriptionEngine:
    if backend == "mlx":
        from transcription.mlx_backend import MLXWhisperEngine

        return MLXWhisperEngine(**kwargs)
    raise ValueError(f"Unknown transcription backend: {backend}")
