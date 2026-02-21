"""Data classes for transcription results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WordInfo:
    word: str
    start: float  # seconds relative to segment start
    end: float
    probability: float = 1.0


@dataclass
class TranscriptionSegment:
    text: str
    start_time: float  # seconds relative to session start
    end_time: float
    words: list[WordInfo]
    language: str = "fr"
    queue_wait_ms: float | None = None
    inference_ms: float | None = None
    end_to_caption_ms: float | None = None
