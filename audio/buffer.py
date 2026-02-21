"""Ring buffer for accumulating audio samples."""

import numpy as np


class RingBuffer:
    """Fixed-size ring buffer for float32 audio samples at a given sample rate."""

    def __init__(self, max_seconds: float, sample_rate: int = 16000):
        self._capacity = int(max_seconds * sample_rate)
        self._buf = np.zeros(self._capacity, dtype=np.float32)
        self._write_pos = 0
        self._total_written = 0

    @property
    def total_written(self) -> int:
        return self._total_written

    def write(self, data: np.ndarray):
        """Append samples to the ring buffer."""
        data = data.flatten().astype(np.float32)
        n = len(data)
        if n >= self._capacity:
            # Data larger than buffer — keep only the last _capacity samples
            self._buf[:] = data[-self._capacity :]
            self._write_pos = 0
            self._total_written += n
            return

        end = self._write_pos + n
        if end <= self._capacity:
            self._buf[self._write_pos : end] = data
        else:
            first = self._capacity - self._write_pos
            self._buf[self._write_pos :] = data[:first]
            self._buf[: n - first] = data[first:]

        self._write_pos = end % self._capacity
        self._total_written += n

    def read_last(self, num_samples: int) -> np.ndarray:
        """Read the last num_samples from the buffer."""
        num_samples = min(num_samples, self._capacity, self._total_written)
        start = (self._write_pos - num_samples) % self._capacity
        if start + num_samples <= self._capacity:
            return self._buf[start : start + num_samples].copy()
        first = self._capacity - start
        return np.concatenate([self._buf[start:], self._buf[: num_samples - first]])

    def clear(self):
        self._buf[:] = 0
        self._write_pos = 0
        self._total_written = 0
