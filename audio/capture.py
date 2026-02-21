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


def resolve_input_device(device_spec: str | int | None) -> int | None:
    """Resolve a configured device name/index to a concrete sounddevice input index."""
    if device_spec is None:
        return None

    devices = sd.query_devices()

    def _is_valid_input_index(index: int) -> bool:
        return 0 <= index < len(devices) and devices[index]["max_input_channels"] >= 1

    if isinstance(device_spec, int):
        if _is_valid_input_index(device_spec):
            return device_spec
        raise ValueError(f"Configured audio_device index {device_spec} is not a valid input device.")

    spec = str(device_spec).strip()
    if not spec:
        return None

    # Support numeric strings like "2" in settings files.
    try:
        index = int(spec)
    except ValueError:
        index = None

    if index is not None:
        if _is_valid_input_index(index):
            return index
        raise ValueError(f"Configured audio_device index {index} is not a valid input device.")

    spec_lower = spec.lower()

    # Prefer exact name match first.
    for i, d in enumerate(devices):
        if d["max_input_channels"] >= 1 and d["name"].lower() == spec_lower:
            return i

    # Then allow substring match.
    for i, d in enumerate(devices):
        if d["max_input_channels"] >= 1 and spec_lower in d["name"].lower():
            return i

    available = ", ".join(d["name"] for d in devices if d["max_input_channels"] >= 1)
    raise ValueError(
        f'Configured audio_device "{spec}" not found. Available input devices: {available}'
    )


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
