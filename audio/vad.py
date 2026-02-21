"""Silero VAD wrapper for speech detection."""

import numpy as np
import torch


class SileroVAD:
    """Wraps Silero VAD model for streaming speech detection."""

    def __init__(
        self,
        threshold: float = 0.5,
        sample_rate: int = 16000,
        silence_ms: int = 700,
        min_speech_ms: int = 250,
    ):
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.silence_samples = int(sample_rate * silence_ms / 1000)
        self.min_speech_samples = int(sample_rate * min_speech_ms / 1000)

        # Load Silero VAD
        self._model, self._utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
        )
        self._model.eval()

        # State tracking
        self._is_speaking = False
        self._speech_samples = 0
        self._silence_samples_count = 0

    def reset(self):
        self._model.reset_states()
        self._is_speaking = False
        self._speech_samples = 0
        self._silence_samples_count = 0

    def force_end_segment(self) -> int:
        """Force a segment break during long continuous speech.

        Returns the number of speech samples accumulated so far.
        Resets counters but keeps _is_speaking = True so VAD continues.
        """
        duration = self._speech_samples
        self._speech_samples = 0
        self._silence_samples_count = 0
        # Keep _is_speaking = True — speech continues, we just checkpointed
        return duration

    def process_chunk(self, audio: np.ndarray) -> dict:
        """Process a chunk of audio and return VAD state.

        Returns dict with:
            - is_speech: bool, whether current chunk contains speech
            - speech_end: bool, whether a speech segment just ended
            - speech_duration_samples: int, how many samples in current speech segment
        """
        tensor = torch.from_numpy(audio).float()
        # Silero VAD expects 512-sample chunks at 16kHz
        # Process in 512-sample sub-chunks if needed
        speech_prob = 0.0
        chunk_size = 512
        for i in range(0, len(tensor), chunk_size):
            sub = tensor[i : i + chunk_size]
            if len(sub) < chunk_size:
                sub = torch.nn.functional.pad(sub, (0, chunk_size - len(sub)))
            speech_prob = self._model(sub, self.sample_rate).item()

        is_speech = speech_prob >= self.threshold
        speech_end = False

        if is_speech:
            self._silence_samples_count = 0
            self._speech_samples += len(audio)
            if not self._is_speaking:
                self._is_speaking = True
        elif self._is_speaking:
            self._silence_samples_count += len(audio)
            if self._silence_samples_count >= self.silence_samples:
                # Speech segment ended
                if self._speech_samples >= self.min_speech_samples:
                    speech_end = True
                self._is_speaking = False
                duration = self._speech_samples
                self._speech_samples = 0
                self._silence_samples_count = 0
                return {
                    "is_speech": False,
                    "speech_end": speech_end,
                    "speech_duration_samples": duration,
                }

        return {
            "is_speech": is_speech,
            "speech_end": False,
            "speech_duration_samples": self._speech_samples,
        }
