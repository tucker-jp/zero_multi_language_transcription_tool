"""QThread worker: audio capture + VAD → emits speech segments."""

from __future__ import annotations

import time

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from audio.capture import AudioCapture, find_blackhole_device
from audio.vad import SileroVAD
from audio.buffer import RingBuffer
from config.settings import Settings


class AudioWorker(QThread):
    """Captures audio from BlackHole, runs VAD, emits speech segments."""

    speech_segment = pyqtSignal(np.ndarray, float)  # (audio, session_offset)
    error = pyqtSignal(str)
    status = pyqtSignal(str)  # status messages

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._running = False
        self._paused = False

    def run(self):
        self._running = True
        settings = self._settings

        # Find audio device
        device = None
        if settings.audio_device:
            device = int(settings.audio_device)
        else:
            device = find_blackhole_device()
            if device is None:
                self.error.emit(
                    "BlackHole device not found. Please install BlackHole 2ch "
                    "and set up a Multi-Output Device."
                )
                return

        self.status.emit("Loading VAD model...")
        try:
            vad = SileroVAD(
                threshold=settings.vad_threshold,
                sample_rate=settings.sample_rate,
                silence_ms=settings.vad_silence_ms,
                min_speech_ms=settings.vad_min_speech_ms,
            )
        except Exception as e:
            self.error.emit(f"Failed to load VAD: {e}")
            return

        # Ring buffer holds enough audio for max segment + silence padding
        buf = RingBuffer(
            max_seconds=settings.max_segment_seconds + 5.0,
            sample_rate=settings.sample_rate,
        )

        session_start = time.monotonic()
        speech_start_time: float | None = None
        max_speech_samples = int(settings.max_speech_seconds * settings.sample_rate)

        def on_audio(audio: np.ndarray):
            nonlocal speech_start_time
            if self._paused or not self._running:
                return

            buf.write(audio)
            result = vad.process_chunk(audio)

            if result["is_speech"] and speech_start_time is None:
                speech_start_time = time.monotonic() - session_start

            if result["speech_end"]:
                duration_samples = result["speech_duration_samples"]
                # Add some padding
                padding = int(settings.sample_rate * 0.3)
                total_samples = min(
                    duration_samples + padding,
                    int(settings.max_segment_seconds * settings.sample_rate),
                )
                segment_audio = buf.read_last(total_samples)
                offset = speech_start_time if speech_start_time is not None else 0.0
                self.speech_segment.emit(segment_audio, offset)
                speech_start_time = None
            elif (
                result["is_speech"]
                and result["speech_duration_samples"] > max_speech_samples
            ):
                # Force a segment break during long continuous speech
                duration_samples = vad.force_end_segment()
                padding = int(settings.sample_rate * 0.3)
                total_samples = min(
                    duration_samples + padding,
                    int(settings.max_segment_seconds * settings.sample_rate),
                )
                segment_audio = buf.read_last(total_samples)
                offset = speech_start_time if speech_start_time is not None else 0.0
                self.speech_segment.emit(segment_audio, offset)
                speech_start_time = time.monotonic() - session_start

        self.status.emit("Starting audio capture...")
        try:
            capture = AudioCapture(
                device=device,
                sample_rate=settings.sample_rate,
                channels=settings.channels,
                chunk_duration_ms=settings.chunk_duration_ms,
                callback=on_audio,
            )
            capture.start()
            self.status.emit("Listening...")
        except Exception as e:
            self.error.emit(f"Failed to start audio capture: {e}")
            return

        # Keep thread alive while running
        while self._running:
            self.msleep(100)

        capture.stop()

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        self._running = False
