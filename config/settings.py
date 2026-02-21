"""Application settings with JSON persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

DEFAULT_DATA_DIR = Path.home() / ".transcription_helper"
DEFAULT_CONFIG_PATH = DEFAULT_DATA_DIR / "settings.json"


@dataclass
class Settings:
    # Runtime profile
    performance_profile: str = "live"  # live, balanced, accurate
    live_latency_target_ms: int = 900
    latency_log_every_n_segments: int = 10

    # Audio
    audio_device: str | int | None = None  # name or index; None = BlackHole auto-detect
    sample_rate: int = 16000
    channels: int = 1
    chunk_duration_ms: int = 30  # ms per VAD chunk

    # VAD
    vad_threshold: float = 0.5
    vad_silence_ms: int = 350  # ms of silence to trigger end-of-speech
    vad_min_speech_ms: int = 200  # ignore segments shorter than this
    max_speech_seconds: float = 3.0  # force segment break during long speech

    # Transcription
    transcription_backend: str = "mlx"  # mlx, faster_whisper
    whisper_model: str = "small"
    language: str = "fr"
    max_segment_seconds: float = 15.0
    segment_overlap_seconds: float = 1.0
    word_timestamps: bool = False
    faster_whisper_compute_type: str = "int8_float16"

    # Translation
    translation_model: str = "Helsinki-NLP/opus-mt-fr-en"
    translation_cache_size: int = 1000
    transcription_queue_maxsize: int = 8
    translation_queue_maxsize: int = 32

    # UI
    overlay_opacity: float = 0.85
    font_size: int = 22
    overlay_width: int = 800
    overlay_height: int = 160
    overlay_x: int = -1  # -1 = center
    overlay_y: int = -1  # -1 = bottom

    # Storage
    data_dir: str = field(default_factory=lambda: str(DEFAULT_DATA_DIR))
    db_path: str = field(
        default_factory=lambda: str(DEFAULT_DATA_DIR / "transcripts.db")
    )

    def save(self, path: Path | None = None):
        path = Path(path or DEFAULT_CONFIG_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = Path(path or DEFAULT_CONFIG_PATH)
        if path.exists():
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, ValueError) as e:
                print(f"Warning: corrupted settings file {path}, using defaults: {e}")
                return cls()
            # Only use keys that exist in the dataclass
            valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
            filtered = {k: v for k, v in data.items() if k in valid_keys}
            settings = cls(**filtered)
            if settings.performance_profile not in {"live", "balanced", "accurate"}:
                settings.performance_profile = "live"
            if settings.transcription_backend not in {"mlx", "faster_whisper"}:
                settings.transcription_backend = "mlx"
            settings.transcription_queue_maxsize = max(
                1, int(settings.transcription_queue_maxsize)
            )
            settings.translation_queue_maxsize = max(
                1, int(settings.translation_queue_maxsize)
            )
            settings.live_latency_target_ms = max(300, int(settings.live_latency_target_ms))
            settings.latency_log_every_n_segments = max(
                1, int(settings.latency_log_every_n_segments)
            )
            return settings
        return cls()
