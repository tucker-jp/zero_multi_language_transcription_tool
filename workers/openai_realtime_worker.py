"""QThread worker: stream audio to OpenAI Realtime transcription and emit live captions."""

from __future__ import annotations

import base64
import io
import json
import os
import queue
import time
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from config.settings import Settings
from transcription.result import TranscriptionSegment


TARGET_SAMPLE_RATE = 24000
MINI_TRANSCRIBE_USD_PER_MIN = 0.003
TRANSCRIBE_USD_PER_MIN = 0.006
MAX_AUDIO_TIMELINE_SECONDS = 120.0


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

        self._audio_timeline: list[tuple[float, float, np.ndarray]] = []

        self._api_key = ""
        self._repair_enabled = bool(self._settings.openai_repair_enabled)
        self._repair_hour_marks: list[float] = []
        self._budget_warned_70 = False
        self._budget_warned_90 = False
        self._budget_hard_blocked = False

        self._usage_path = Path(self._settings.openai_usage_path)
        self._usage_month = datetime.now().strftime("%Y-%m")
        self._usage_realtime_seconds = 0.0
        self._usage_repair_seconds = 0.0
        self._load_usage()

    # ------------------------------------------------------------------
    # Usage / budget tracking
    # ------------------------------------------------------------------

    def _load_usage(self):
        if not self._usage_path.exists():
            return
        try:
            data = json.loads(self._usage_path.read_text())
        except (json.JSONDecodeError, OSError, ValueError):
            return

        month = str(data.get("month", ""))
        if month != self._usage_month:
            return

        self._usage_realtime_seconds = max(0.0, float(data.get("realtime_seconds", 0.0)))
        self._usage_repair_seconds = max(0.0, float(data.get("repair_seconds", 0.0)))

    def _save_usage(self):
        payload = {
            "month": self._usage_month,
            "realtime_seconds": self._usage_realtime_seconds,
            "repair_seconds": self._usage_repair_seconds,
            "updated_at": datetime.now().isoformat(),
        }
        self._usage_path.parent.mkdir(parents=True, exist_ok=True)
        self._usage_path.write_text(json.dumps(payload, indent=2))

    def _projected_spend_usd(
        self,
        add_realtime_seconds: float = 0.0,
        add_repair_seconds: float = 0.0,
    ) -> tuple[float, float, float]:
        realtime_seconds = self._usage_realtime_seconds + max(0.0, add_realtime_seconds)
        repair_seconds = self._usage_repair_seconds + max(0.0, add_repair_seconds)
        realtime_usd = (realtime_seconds / 60.0) * MINI_TRANSCRIBE_USD_PER_MIN
        repair_usd = (repair_seconds / 60.0) * TRANSCRIBE_USD_PER_MIN
        return realtime_usd, repair_usd, realtime_usd + repair_usd

    def _current_spend_usd(self) -> tuple[float, float, float]:
        return self._projected_spend_usd(0.0, 0.0)

    def _emit_budget_progress(self):
        budget = float(self._settings.openai_monthly_budget_usd)
        if budget <= 0.0:
            return
        _r, _p, total = self._current_spend_usd()
        ratio = total / budget

        if ratio >= 0.90 and not self._budget_warned_90:
            self._budget_warned_90 = True
            self.status.emit(
                f"OpenAI spend is at {ratio * 100:.0f}% of ${budget:.2f} monthly budget."
            )
        elif ratio >= 0.70 and not self._budget_warned_70:
            self._budget_warned_70 = True
            self.status.emit(
                f"OpenAI spend is at {ratio * 100:.0f}% of ${budget:.2f} monthly budget."
            )

    def _apply_realtime_spend(self, seconds: float):
        seconds = max(0.0, float(seconds))
        if seconds <= 0.0:
            return
        self._usage_realtime_seconds += seconds
        self._audio_seconds_sent += seconds
        self._emit_budget_progress()

    def _apply_repair_spend(self, seconds: float):
        seconds = max(0.0, float(seconds))
        if seconds <= 0.0:
            return
        self._usage_repair_seconds += seconds
        self._emit_budget_progress()

    def _allow_realtime_spend(self, add_seconds: float) -> bool:
        budget = float(self._settings.openai_monthly_budget_usd)
        if budget <= 0.0:
            return True

        _r, _p, projected = self._projected_spend_usd(add_realtime_seconds=add_seconds)
        if projected <= budget:
            return True

        # First sacrifice repair to keep baseline realtime running as long as possible.
        if self._repair_enabled:
            self._repair_enabled = False
            self.status.emit(
                "Repair pass disabled to stay within monthly budget."
            )

        if not bool(self._settings.openai_budget_hard_cap_enabled):
            return True

        if not self._budget_hard_blocked:
            self._budget_hard_blocked = True
            self.error.emit(
                "OpenAI monthly budget cap reached. Stopping cloud transcription "
                "to prevent overspend."
            )
        self._running = False
        return False

    def _allow_repair_spend(self, add_seconds: float) -> bool:
        if not self._repair_enabled:
            return False

        max_extra = float(self._settings.openai_repair_max_extra_monthly_usd)
        _r, projected_repair, projected_total = self._projected_spend_usd(
            add_repair_seconds=add_seconds
        )

        if max_extra >= 0.0 and projected_repair > max_extra:
            self._repair_enabled = False
            self.status.emit(
                "Repair pass disabled after reaching configured repair budget cap."
            )
            return False

        budget = float(self._settings.openai_monthly_budget_usd)
        if budget > 0.0 and projected_total > budget:
            self._repair_enabled = False
            self.status.emit(
                "Repair pass skipped to avoid exceeding monthly budget."
            )
            return False

        return True

    # ------------------------------------------------------------------
    # Audio helpers
    # ------------------------------------------------------------------

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

    def _audio_to_wav_bytes(self, audio: np.ndarray, sample_rate: int) -> bytes:
        pcm16 = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
        out = io.BytesIO()
        with wave.open(out, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm16.tobytes())
        return out.getvalue()

    def _append_audio_timeline(self, chunk_start_s: float, chunk_end_s: float, audio: np.ndarray):
        self._audio_timeline.append((chunk_start_s, chunk_end_s, audio.astype(np.float32, copy=True)))

        cutoff = chunk_end_s - MAX_AUDIO_TIMELINE_SECONDS
        if cutoff <= 0.0:
            return

        drop_until = 0
        for i, (_s, e, _a) in enumerate(self._audio_timeline):
            if e >= cutoff:
                break
            drop_until = i + 1

        if drop_until > 0:
            self._audio_timeline = self._audio_timeline[drop_until:]

    def _extract_audio_window(
        self,
        start_s: float,
        end_s: float,
        pad_s: float = 0.18,
    ) -> np.ndarray | None:
        sample_rate = int(self._settings.sample_rate)
        if sample_rate <= 0:
            return None

        window_start = max(0.0, start_s - pad_s)
        window_end = max(window_start, end_s + pad_s)
        duration = window_end - window_start
        if duration <= 0.0:
            return None

        max_duration = float(self._settings.openai_repair_max_segment_seconds)
        if duration > max_duration:
            return None

        pieces: list[np.ndarray] = []
        for chunk_start, chunk_end, chunk_audio in self._audio_timeline:
            overlap_start = max(window_start, chunk_start)
            overlap_end = min(window_end, chunk_end)
            if overlap_end <= overlap_start:
                continue

            start_i = int(round((overlap_start - chunk_start) * sample_rate))
            end_i = int(round((overlap_end - chunk_start) * sample_rate))
            start_i = max(0, min(len(chunk_audio), start_i))
            end_i = max(start_i, min(len(chunk_audio), end_i))
            if end_i > start_i:
                pieces.append(chunk_audio[start_i:end_i])

        if not pieces:
            return None

        audio = np.concatenate(pieces).astype(np.float32, copy=False)
        if len(audio) == 0:
            return None
        return audio

    # ------------------------------------------------------------------
    # Realtime / repair API payloads
    # ------------------------------------------------------------------

    def _build_session_update_event(self) -> dict:
        session: dict = {
            "input_audio_format": "pcm16",
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
            "input_audio_transcription": {
                "model": self._settings.openai_realtime_model,
                "language": self._settings.language,
            },
        }

        prompt = ""
        if isinstance(getattr(self._settings, "openai_realtime_prompt", ""), str):
            prompt = self._settings.openai_realtime_prompt.strip()
        if prompt:
            session["input_audio_transcription"]["prompt"] = prompt

        noise_reduction = str(self._settings.openai_realtime_noise_reduction or "").strip()
        if noise_reduction and noise_reduction.lower() != "none":
            session["input_audio_noise_reduction"] = {"type": noise_reduction}

        if bool(self._settings.openai_realtime_include_logprobs):
            session["include"] = ["item.input_audio_transcription.logprobs"]

        return {"type": "transcription_session.update", "session": session}

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

    def _maybe_repair_text(
        self,
        text: str,
        start_time: float,
        end_time: float,
        avg_logprob: float | None,
    ) -> tuple[str, str]:
        if not self._repair_enabled:
            return text, "openai_realtime"

        if avg_logprob is None:
            return text, "openai_realtime"

        threshold = float(self._settings.openai_repair_avg_logprob_threshold)
        if avg_logprob >= threshold:
            return text, "openai_realtime"

        now_mono = time.monotonic()
        cutoff = now_mono - 3600.0
        self._repair_hour_marks = [t for t in self._repair_hour_marks if t >= cutoff]
        hour_limit = int(self._settings.openai_repair_max_segments_per_hour)
        if hour_limit > 0 and len(self._repair_hour_marks) >= hour_limit:
            return text, "openai_realtime"

        source_audio = self._extract_audio_window(start_time, end_time)
        if source_audio is None:
            return text, "openai_realtime"

        segment_seconds = len(source_audio) / max(1, int(self._settings.sample_rate))
        if segment_seconds <= 0.0:
            return text, "openai_realtime"

        if not self._allow_repair_spend(segment_seconds):
            return text, "openai_realtime"

        repaired = self._run_repair_transcription(source_audio)
        self._apply_repair_spend(segment_seconds)
        self._repair_hour_marks.append(now_mono)

        if not repaired:
            return text, "openai_realtime"

        cleaned = repaired.strip()
        if not cleaned:
            return text, "openai_realtime"

        if cleaned == text.strip():
            return text, "openai_realtime"

        self.status.emit(
            f"Applied repair pass (avg_logprob={avg_logprob:.2f}) on low-confidence segment."
        )
        return cleaned, "openai_realtime_repair"

    def _run_repair_transcription(self, audio: np.ndarray) -> str:
        try:
            import requests
        except ImportError:
            self.error.emit(
                "Repair pass needs 'requests'. Install with: pip install requests"
            )
            self._repair_enabled = False
            return ""

        wav_bytes = self._audio_to_wav_bytes(audio, int(self._settings.sample_rate))
        files = {
            "file": ("segment.wav", wav_bytes, "audio/wav"),
        }
        data = {
            "model": self._settings.openai_repair_model,
            "language": self._settings.language,
        }

        prompt = str(self._settings.openai_realtime_prompt or "").strip()
        if prompt:
            data["prompt"] = prompt

        timeout_s = float(self._settings.openai_repair_timeout_s)

        try:
            response = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                data=data,
                files=files,
                timeout=timeout_s,
            )
        except Exception as e:
            self.error.emit(f"Repair pass request failed: {e}")
            return ""

        if response.status_code >= 400:
            self.error.emit(
                "Repair pass request failed "
                f"({response.status_code}): {response.text[:240]}"
            )
            return ""

        try:
            payload = response.json()
        except ValueError:
            self.error.emit("Repair pass returned non-JSON response.")
            return ""

        text = payload.get("text", "")
        if not isinstance(text, str):
            return ""
        return text

    # ------------------------------------------------------------------
    # Event handling / emission
    # ------------------------------------------------------------------

    def _emit_final_ready(self):
        while self._next_emit_index < len(self._commit_order):
            item_id = self._commit_order[self._next_emit_index]
            payload = self._completed.get(item_id)
            if payload is None:
                return

            text = payload.get("text", "").strip()
            if text:
                start_time, end_time, end_to_caption_ms = self._derive_timing(item_id)
                final_text, source = self._maybe_repair_text(
                    text,
                    start_time,
                    end_time,
                    payload.get("avg_logprob"),
                )
                self.transcription_ready.emit(
                    TranscriptionSegment(
                        text=final_text,
                        start_time=start_time,
                        end_time=end_time,
                        words=[],
                        language=self._settings.language,
                        end_to_caption_ms=end_to_caption_ms,
                        is_final=True,
                        source=source,
                        avg_logprob=payload.get("avg_logprob"),
                    )
                )

            self._completed.pop(item_id, None)
            self._speech_bounds_ms.pop(item_id, None)
            self._partial_text.pop(item_id, None)
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
                if err.get("code") == "input_audio_buffer_commit_empty":
                    # Benign during shutdown when no trailing speech remains.
                    return
                message = err.get("message") or err.get("type") or str(err)
            else:
                message = str(event)
            self.error.emit(f"OpenAI Realtime error: {message}")
            return

        if event_type in {
            "session.created",
            "session.updated",
            "transcription_session.created",
            "transcription_session.updated",
        }:
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

    # ------------------------------------------------------------------
    # Public worker API
    # ------------------------------------------------------------------

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

    def run(self):
        self._running = True

        self._api_key = (self._settings.openai_api_key or "").strip() or os.getenv(
            "OPENAI_API_KEY", ""
        ).strip()
        if not self._api_key:
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
                    f"Authorization: Bearer {self._api_key}",
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

                    self._append_audio_timeline(item.chunk_start_s, item.chunk_end_s, item.audio)

                    audio_24k = self._resample_to_target(item.audio, self._settings.sample_rate)
                    chunk_seconds = len(audio_24k) / TARGET_SAMPLE_RATE
                    if not self._allow_realtime_spend(chunk_seconds):
                        break

                    self._apply_realtime_spend(chunk_seconds)
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
                    realtime_usd, repair_usd, total_usd = self._current_spend_usd()
                    self.status.emit(
                        f"OpenAI usage this month: {self._audio_seconds_sent/60.0:.1f} live min, "
                        f"${total_usd:.2f} total (${realtime_usd:.2f} live + ${repair_usd:.2f} repair)."
                    )
                    self._save_usage()

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
            self._save_usage()
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
