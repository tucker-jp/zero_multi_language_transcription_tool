"""System audio capture via sounddevice (expects BlackHole virtual device)."""

from __future__ import annotations

import sys

import sounddevice as sd
import numpy as np


def find_blackhole_device() -> int | None:
    """Find the BlackHole 2ch input device index."""
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if "blackhole" in d["name"].lower() and d["max_input_channels"] >= 1:
            return i
    return None


def list_input_devices() -> list[dict]:
    """Return list of input devices with index and name."""
    devices = sd.query_devices()
    result = []
    for i, d in enumerate(devices):
        if d["max_input_channels"] >= 1:
            result.append({"index": i, "name": d["name"]})
    return result


class AudioCapture:
    """Captures audio from a sounddevice input (typically BlackHole)."""

    def __init__(
        self,
        device: int | None = None,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_duration_ms: int = 30,
        callback=None,
    ):
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_samples = int(sample_rate * chunk_duration_ms / 1000)
        self._callback = callback
        self._stream: sd.InputStream | None = None

    def _audio_callback(self, indata: np.ndarray, frames, time_info, status):
        if status:
            print(f"[audio] {status}", file=sys.stderr)
        if self._callback:
            # Convert to mono float32
            audio = indata[:, 0].copy() if indata.ndim > 1 else indata.flatten().copy()
            self._callback(audio)

    def start(self):
        if self._stream is not None:
            return
        self._stream = sd.InputStream(
            device=self.device,
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            blocksize=self.chunk_samples,
            callback=self._audio_callback,
        )
        self._stream.start()

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    @property
    def is_active(self) -> bool:
        return self._stream is not None and self._stream.active
