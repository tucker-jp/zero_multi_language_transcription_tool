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
    chunk_duration_ms: int = 20  # ms per VAD chunk

    # VAD
    vad_threshold: float = 0.5
    vad_silence_ms: int = 350  # ms of silence to trigger end-of-speech
    vad_min_speech_ms: int = 200  # ignore segments shorter than this
    max_speech_seconds: float = 3.0  # force segment break during long speech

    # Transcription
    stt_provider: str = "local"  # local, openai_realtime
    transcription_backend: str = "mlx"  # mlx, faster_whisper
    whisper_model: str = "small"
    language: str = "fr"
    max_segment_seconds: float = 15.0
    segment_overlap_seconds: float = 1.0
    word_timestamps: bool = False
    faster_whisper_compute_type: str = "int8"
    openai_api_key: str = ""
    openai_realtime_model: str = "gpt-4o-mini-transcribe"
    openai_realtime_prompt: str = ""
    openai_realtime_url: str = "wss://api.openai.com/v1/realtime?intent=transcription"
    openai_realtime_noise_reduction: str = "near_field"
    openai_realtime_include_logprobs: bool = True
    openai_realtime_vad_threshold: float = 0.5
    openai_realtime_vad_prefix_padding_ms: int = 180
    openai_realtime_vad_silence_ms: int = 260
    openai_monthly_budget_usd: float = 10.0
    openai_budget_hard_cap_enabled: bool = True
    openai_usage_path: str = field(
        default_factory=lambda: str(DEFAULT_DATA_DIR / "openai_usage.json")
    )
    openai_repair_enabled: bool = False
    openai_repair_model: str = "gpt-4o-transcribe"
    openai_repair_avg_logprob_threshold: float = -0.9
    openai_repair_max_segment_seconds: float = 8.0
    openai_repair_timeout_s: float = 8.0
    openai_repair_max_segments_per_hour: int = 30
    openai_repair_max_extra_monthly_usd: float = 3.0

    # Translation
    translation_model: str = "Helsinki-NLP/opus-mt-fr-en"
    translation_cache_size: int = 1000
    translation_include_sentence_context: bool = True
    translation_include_sentence_for_single_word: bool = False
    translation_sentence_max_chars: int = 180
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
    default_save_dir: str = field(default_factory=lambda: str(Path.home() / "Documents"))

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
            if settings.stt_provider not in {"local", "openai_realtime"}:
                settings.stt_provider = "local"
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
            settings.openai_realtime_vad_threshold = min(
                0.99, max(0.0, float(settings.openai_realtime_vad_threshold))
            )
            settings.openai_realtime_vad_prefix_padding_ms = max(
                0, int(settings.openai_realtime_vad_prefix_padding_ms)
            )
            settings.openai_realtime_vad_silence_ms = max(
                100, int(settings.openai_realtime_vad_silence_ms)
            )
            settings.openai_monthly_budget_usd = max(
                0.5, float(settings.openai_monthly_budget_usd)
            )
            settings.openai_repair_avg_logprob_threshold = float(
                settings.openai_repair_avg_logprob_threshold
            )
            settings.openai_repair_max_segment_seconds = min(
                30.0, max(1.0, float(settings.openai_repair_max_segment_seconds))
            )
            settings.openai_repair_timeout_s = min(
                60.0, max(2.0, float(settings.openai_repair_timeout_s))
            )
            settings.openai_repair_max_segments_per_hour = max(
                0, int(settings.openai_repair_max_segments_per_hour)
            )
            settings.openai_repair_max_extra_monthly_usd = max(
                0.0, float(settings.openai_repair_max_extra_monthly_usd)
            )
            settings.translation_sentence_max_chars = min(
                600, max(40, int(settings.translation_sentence_max_chars))
            )
            settings.default_save_dir = str(
                settings.default_save_dir or str(Path.home() / "Documents")
            )
            return settings
        return cls()
