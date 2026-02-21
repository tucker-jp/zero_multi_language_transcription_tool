"""QThread worker: stream audio to OpenAI Realtime transcription and emit live captions."""

from __future__ import annotations

import base64
import json
import os
import queue
import time
from dataclasses import dataclass

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from config.settings import Settings
from transcription.result import TranscriptionSegment


TARGET_SAMPLE_RATE = 24000
MINI_TRANSCRIBE_USD_PER_MIN = 0.003


@dataclass
class _ChunkItem:
    audio: np.ndarray
    chunk_start_s: float
    chunk_end_s: float
    enqueued_mono: float


class OpenAIRealtimeWorker(QThread):
    """Streams raw PCM chunks to OpenAI Realtime and emits partial/final transcripts."""

    transcription_ready = pyqtSignal(TranscriptionSegment)
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        # Realtime ingest needs a deeper queue than segment-based transcription.
        maxsize = max(128, int(settings.transcription_queue_maxsize) * 32)
        self._queue: queue.Queue[_ChunkItem | None] = queue.Queue(maxsize=maxsize)
        self._running = False
        self._dropped_count = 0

        self._commit_order: list[str] = []
        self._next_emit_index = 0
        self._completed: dict[str, dict] = {}
        self._partial_text: dict[str, str] = {}
        self._speech_bounds_ms: dict[str, tuple[float | None, float | None]] = {}
        self._active_speech_start_ms: float | None = None
        self._audio_origin_mono: float | None = None
        self._server_audio_offset_s = 0.0
        self._audio_seconds_sent = 0.0
        self._last_cost_status_mins = 0

    def enqueue_audio_chunk(self, audio: np.ndarray, chunk_start_s: float, chunk_end_s: float):
        item = _ChunkItem(
            audio=audio,
            chunk_start_s=float(chunk_start_s),
            chunk_end_s=float(chunk_end_s),
            enqueued_mono=time.monotonic(),
        )

        try:
            self._queue.put_nowait(item)
            return
        except queue.Full:
            pass

        try:
            self._queue.get_nowait()
        except queue.Empty:
            pass

        try:
            self._queue.put_nowait(item)
        except queue.Full:
            return

        self._dropped_count += 1
        if self._dropped_count % 200 == 0:
            self.status.emit(
                f"Realtime audio queue overloaded; dropped {self._dropped_count} chunks."
            )

    def _resample_to_target(self, audio: np.ndarray, source_rate: int) -> np.ndarray:
        if source_rate == TARGET_SAMPLE_RATE:
            return audio.astype(np.float32, copy=False)

        src_len = len(audio)
        if src_len == 0:
            return np.zeros(0, dtype=np.float32)

        dst_len = max(1, int(round(src_len * TARGET_SAMPLE_RATE / source_rate)))
        src_x = np.linspace(0.0, 1.0, num=src_len, endpoint=False)
        dst_x = np.linspace(0.0, 1.0, num=dst_len, endpoint=False)
        out = np.interp(dst_x, src_x, audio)
        return out.astype(np.float32, copy=False)

    def _audio_to_base64_pcm16(self, audio: np.ndarray) -> str:
        audio = np.clip(audio, -1.0, 1.0)
        pcm16 = (audio * 32767.0).astype(np.int16)
        return base64.b64encode(pcm16.tobytes()).decode("ascii")

    def _build_session_update_event(self) -> dict:
        session: dict = {
            "type": "transcription",
            "audio": {
                "input": {
                    "format": {
                        "type": "audio/pcm",
                        "rate": TARGET_SAMPLE_RATE,
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": float(self._settings.openai_realtime_vad_threshold),
                        "prefix_padding_ms": int(
                            self._settings.openai_realtime_vad_prefix_padding_ms
                        ),
                        "silence_duration_ms": int(
                            self._settings.openai_realtime_vad_silence_ms
                        ),
                    },
                    "transcription": {
                        "model": self._settings.openai_realtime_model,
                        "language": self._settings.language,
                    },
                }
            },
        }

        prompt = ""
        if isinstance(getattr(self._settings, "openai_realtime_prompt", ""), str):
            prompt = self._settings.openai_realtime_prompt.strip()
        if prompt:
            session["audio"]["input"]["transcription"]["prompt"] = prompt

        noise_reduction = str(self._settings.openai_realtime_noise_reduction or "").strip()
        if noise_reduction and noise_reduction.lower() != "none":
            session["audio"]["input"]["noise_reduction"] = {"type": noise_reduction}

        if bool(self._settings.openai_realtime_include_logprobs):
            session["include"] = ["item.input_audio_transcription.logprobs"]

        return {"type": "session.update", "session": session}

    def _parse_avg_logprob(self, event: dict) -> float | None:
        raw = event.get("logprobs")
        if not isinstance(raw, list) or not raw:
            return None

        values: list[float] = []
        for tok in raw:
            if not isinstance(tok, dict):
                continue
            lp = tok.get("logprob")
            if isinstance(lp, (int, float)):
                values.append(float(lp))

        if not values:
            return None
        return sum(values) / len(values)

    def _emit_final_ready(self):
        while self._next_emit_index < len(self._commit_order):
            item_id = self._commit_order[self._next_emit_index]
            payload = self._completed.get(item_id)
            if payload is None:
                return

            text = payload.get("text", "").strip()
            if text:
                start_time, end_time, end_to_caption_ms = self._derive_timing(item_id)
                self.transcription_ready.emit(
                    TranscriptionSegment(
                        text=text,
                        start_time=start_time,
                        end_time=end_time,
                        words=[],
                        language=self._settings.language,
                        end_to_caption_ms=end_to_caption_ms,
                        is_final=True,
                        source="openai_realtime",
                        avg_logprob=payload.get("avg_logprob"),
                    )
                )

            self._next_emit_index += 1

    def _derive_timing(self, item_id: str) -> tuple[float, float, float | None]:
        bounds = self._speech_bounds_ms.get(item_id)
        if bounds is not None:
            start_ms, end_ms = bounds
            if isinstance(start_ms, (int, float)) and isinstance(end_ms, (int, float)):
                start_s = self._server_audio_offset_s + (float(start_ms) / 1000.0)
                end_s = self._server_audio_offset_s + (float(end_ms) / 1000.0)
                if end_s < start_s:
                    end_s = start_s

                end_to_caption_ms = None
                if self._audio_origin_mono is not None:
                    audio_end_mono = self._audio_origin_mono + end_s
                    end_to_caption_ms = max(0.0, (time.monotonic() - audio_end_mono) * 1000.0)
                return start_s, end_s, end_to_caption_ms

        # Fallback if server bounds are unavailable.
        fallback_end = max(self._server_audio_offset_s, self._audio_seconds_sent)
        fallback_start = max(0.0, fallback_end - 1.2)
        return fallback_start, fallback_end, None

    def _handle_server_event(self, event: dict):
        event_type = str(event.get("type", ""))
        if not event_type:
            return

        if event_type == "error":
            err = event.get("error")
            if isinstance(err, dict):
                message = err.get("message") or err.get("type") or str(err)
            else:
                message = str(event)
            self.error.emit(f"OpenAI Realtime error: {message}")
            return

        if event_type in {"session.created", "session.updated"}:
            model = self._settings.openai_realtime_model
            self.status.emit(f"OpenAI Realtime session ready (model={model}).")
            return

        if event_type == "input_audio_buffer.speech_started":
            self._active_speech_start_ms = event.get("audio_start_ms")
            return

        if event_type == "input_audio_buffer.speech_stopped":
            item_id = event.get("item_id")
            end_ms = event.get("audio_end_ms")
            start_ms = event.get("audio_start_ms", self._active_speech_start_ms)
            if isinstance(item_id, str):
                self._speech_bounds_ms[item_id] = (start_ms, end_ms)
            self._active_speech_start_ms = None
            return

        if event_type == "input_audio_buffer.committed":
            item_id = event.get("item_id")
            if isinstance(item_id, str) and item_id not in self._commit_order:
                self._commit_order.append(item_id)
                self._emit_final_ready()
            return

        if event_type == "conversation.item.input_audio_transcription.delta":
            item_id = event.get("item_id")
            delta = event.get("delta", "")
            if not isinstance(item_id, str) or not isinstance(delta, str):
                return

            current = self._partial_text.get(item_id, "")
            current += delta
            self._partial_text[item_id] = current

            partial = current.strip()
            if partial:
                self.transcription_ready.emit(
                    TranscriptionSegment(
                        text=partial,
                        start_time=0.0,
                        end_time=0.0,
                        words=[],
                        language=self._settings.language,
                        is_final=False,
                        source="openai_realtime",
                    )
                )
            return

        if event_type == "conversation.item.input_audio_transcription.completed":
            item_id = event.get("item_id")
            transcript = event.get("transcript", "")
            if not isinstance(item_id, str) or not isinstance(transcript, str):
                return

            self._completed[item_id] = {
                "text": transcript,
                "avg_logprob": self._parse_avg_logprob(event),
            }
            self._partial_text.pop(item_id, None)
            self._emit_final_ready()
            return

    def run(self):
        self._running = True

        api_key = (self._settings.openai_api_key or "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            self.error.emit(
                "OpenAI API key missing. Set OPENAI_API_KEY env var or openai_api_key in settings."
            )
            return

        try:
            import websocket
        except ImportError:
            self.error.emit(
                "Missing dependency 'websocket-client'. Install with: pip install websocket-client"
            )
            return

        ws = None
        try:
            self.status.emit("Connecting to OpenAI Realtime transcription...")
            ws = websocket.create_connection(
                self._settings.openai_realtime_url,
                header=[
                    f"Authorization: Bearer {api_key}",
                    "OpenAI-Beta: realtime=v1",
                ],
                timeout=5,
            )
            ws.settimeout(0.05)
            ws.send(json.dumps(self._build_session_update_event()))

            while self._running:
                sent_any = False
                while True:
                    try:
                        item = self._queue.get_nowait()
                    except queue.Empty:
                        break

                    if item is None:
                        self._running = False
                        break

                    if self._audio_origin_mono is None:
                        self._audio_origin_mono = item.enqueued_mono - item.chunk_end_s
                        self._server_audio_offset_s = max(0.0, item.chunk_start_s)

                    audio_24k = self._resample_to_target(item.audio, self._settings.sample_rate)
                    self._audio_seconds_sent += len(audio_24k) / TARGET_SAMPLE_RATE
                    payload = self._audio_to_base64_pcm16(audio_24k)
                    ws.send(
                        json.dumps(
                            {
                                "type": "input_audio_buffer.append",
                                "audio": payload,
                            }
                        )
                    )
                    sent_any = True

                # Periodic spend visibility at runtime.
                sent_minutes = int(self._audio_seconds_sent // 60)
                if sent_minutes >= self._last_cost_status_mins + 3:
                    self._last_cost_status_mins = sent_minutes
                    estimated_cost = (self._audio_seconds_sent / 60.0) * MINI_TRANSCRIBE_USD_PER_MIN
                    self.status.emit(
                        f"OpenAI streamed {self._audio_seconds_sent/60.0:.1f} min "
                        f"(~${estimated_cost:.2f} at $0.003/min)."
                    )

                while self._running:
                    try:
                        raw = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        break
                    except websocket.WebSocketConnectionClosedException:
                        self.error.emit("OpenAI Realtime connection closed.")
                        self._running = False
                        break

                    if not raw:
                        break

                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    self._handle_server_event(event)

                if not sent_any:
                    self.msleep(8)

            # Try to commit any trailing audio before close.
            if ws is not None:
                try:
                    ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                    deadline = time.monotonic() + 0.6
                    while time.monotonic() < deadline:
                        try:
                            raw = ws.recv()
                        except websocket.WebSocketTimeoutException:
                            continue
                        if not raw:
                            break
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        self._handle_server_event(event)
                except Exception:
                    pass

        except Exception as e:
            self.error.emit(f"OpenAI Realtime worker failed: {e}")
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass

    def stop(self):
        self._running = False
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass
