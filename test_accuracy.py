#!/usr/bin/env python3
"""Transcription accuracy benchmark.

Downloads French audio + subtitles from YouTube, feeds the audio through
MLXWhisperEngine, and compares against reference subtitles using Word Error Rate.

Prerequisites (install once):
    brew install yt-dlp ffmpeg

Usage:
    source .venv/bin/activate
    python test_accuracy.py "https://www.youtube.com/watch?v=XXXXX"
    python test_accuracy.py                     # uses a default French video
    python test_accuracy.py --model large       # test with a different model size
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from transcription.engine import create_engine

TEST_DATA_DIR = Path("test_data")

# Short France 24 news clip — clear speech with manual French subtitles (~1 min)
DEFAULT_VIDEO = "https://www.youtube.com/watch?v=u_j2ZGpmCdA"


# ---------------------------------------------------------------------------
# Subtitle parsing
# ---------------------------------------------------------------------------

@dataclass
class SubSegment:
    start: float
    end: float
    text: str


def parse_timestamp(ts: str) -> float:
    """Parse VTT/SRT timestamp to seconds. Handles HH:MM:SS.mmm and MM:SS.mmm."""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(ts)


def parse_subtitle_file(path: Path) -> list[SubSegment]:
    """Parse a VTT or SRT file into timed segments."""
    text = path.read_text(encoding="utf-8", errors="replace")
    segments = []

    # Unified regex: matches "00:00:01.000 --> 00:00:04.000" style lines
    time_re = re.compile(
        r"(\d{1,2}:?\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{1,2}:?\d{2}:\d{2}[.,]\d{3})"
    )

    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = time_re.match(lines[i].strip())
        if m:
            start = parse_timestamp(m.group(1))
            end = parse_timestamp(m.group(2))
            i += 1
            cue_lines = []
            while i < len(lines) and lines[i].strip():
                cue_lines.append(lines[i].strip())
                i += 1
            raw = " ".join(cue_lines)
            # Strip VTT/SRT formatting tags
            clean = re.sub(r"<[^>]+>", "", raw)
            clean = re.sub(r"\{[^}]+\}", "", clean)  # SSA/ASS tags
            clean = clean.strip()
            if clean:
                segments.append(SubSegment(start=start, end=end, text=clean))
        else:
            i += 1

    # Deduplicate consecutive identical segments (common in auto-generated VTT)
    deduped = []
    for seg in segments:
        if deduped and deduped[-1].text == seg.text:
            deduped[-1].end = max(deduped[-1].end, seg.end)
        else:
            deduped.append(seg)

    return deduped


def merge_short_segments(
    segments: list[SubSegment],
    min_duration_s: float = 0.9,
    max_gap_s: float = 0.12,
) -> list[SubSegment]:
    """Merge short/adjacent subtitle cues into evaluation windows.

    YouTube subtitles often contain overlapping micro-cues (10-50ms) that make
    per-cue WER meaningless. This reduces alignment noise.
    """
    if not segments:
        return []

    merged: list[SubSegment] = []
    cur = SubSegment(
        start=segments[0].start,
        end=segments[0].end,
        text=segments[0].text,
    )

    def cur_duration() -> float:
        return max(0.0, cur.end - cur.start)

    for seg in segments[1:]:
        gap = seg.start - cur.end
        should_merge = gap <= max_gap_s or cur_duration() < min_duration_s
        if should_merge:
            cur.end = max(cur.end, seg.end)
            cur.text = f"{cur.text} {seg.text}".strip()
        else:
            merged.append(cur)
            cur = SubSegment(start=seg.start, end=seg.end, text=seg.text)

    merged.append(cur)
    return merged


def choose_subtitle_file(files: list[Path]) -> Path | None:
    """Pick the best subtitle candidate deterministically."""
    if not files:
        return None

    # Prefer human-created FR origin subtitles, then FR VTT, then anything else.
    priority_patterns = [
        ".fr-orig.vtt",
        ".fr.vtt",
        ".fr-FR.vtt",
        ".fr.srt",
        ".vtt",
        ".srt",
    ]

    def score(path: Path) -> tuple[int, int]:
        name = path.name
        prio = len(priority_patterns)
        for i, suffix in enumerate(priority_patterns):
            if name.endswith(suffix):
                prio = i
                break
        # Larger file tends to include fuller subtitle content.
        size = path.stat().st_size if path.exists() else 0
        return (prio, -size)

    return sorted(files, key=score)[0]


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def check_prerequisites():
    """Verify yt-dlp and ffmpeg are installed."""
    # ffmpeg uses -version (single dash), yt-dlp uses --version
    checks = [("yt-dlp", "--version"), ("ffmpeg", "-version")]
    for cmd, flag in checks:
        try:
            subprocess.run(
                [cmd, flag],
                capture_output=True,
                check=True,
            )
        except FileNotFoundError:
            print(f"Error: '{cmd}' not found. Install with: brew install {cmd}")
            sys.exit(1)


def download_audio_and_subs(url: str) -> tuple[Path, Path]:
    """Download audio as 16kHz mono WAV and French subtitles from a YouTube URL."""
    TEST_DATA_DIR.mkdir(exist_ok=True)

    audio_path = TEST_DATA_DIR / "audio.wav"

    # Download subtitles (prefer manual, fall back to auto-generated)
    print("Downloading subtitles...")
    sub_result = subprocess.run(
        [
            "yt-dlp",
            "--write-sub",
            "--write-auto-sub",
            "--sub-lang", "fr,fr-FR,fr-orig",
            "--sub-format", "vtt",
            "--skip-download",
            "--output", str(TEST_DATA_DIR / "subs"),
            url,
        ],
        capture_output=True,
        text=True,
    )

    # Find the subtitle file that was downloaded
    candidates = [f for f in TEST_DATA_DIR.glob("subs*") if f.suffix in (".vtt", ".srt")]
    sub_path = choose_subtitle_file(candidates)

    if sub_path is None:
        print("Error: Could not download French subtitles for this video.")
        print("Try a different video that has French subtitles.")
        print(f"yt-dlp output: {sub_result.stderr}")
        sys.exit(1)

    print(f"  Found subtitles: {sub_path.name}")

    # Download audio and convert to 16kHz mono WAV
    print("Downloading audio...")
    subprocess.run(
        [
            "yt-dlp",
            "--extract-audio",
            "--audio-format", "wav",
            "--postprocessor-args", "ffmpeg:-ar 16000 -ac 1",
            "--output", str(TEST_DATA_DIR / "audio.%(ext)s"),
            url,
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    if not audio_path.exists():
        print("Error: Audio download failed.")
        sys.exit(1)

    print(f"  Audio saved: {audio_path.name}")
    return audio_path, sub_path


# ---------------------------------------------------------------------------
# Audio loading
# ---------------------------------------------------------------------------

def load_audio(path: Path) -> np.ndarray:
    """Load WAV file as float32 numpy array at 16kHz."""
    sr, data = wavfile.read(str(path))

    # Convert to float32
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float32) / 2147483648.0
    elif data.dtype != np.float32:
        data = data.astype(np.float32)

    # Convert stereo to mono
    if data.ndim > 1:
        data = data.mean(axis=1)

    # Resample if needed (simple linear interpolation)
    if sr != 16000:
        print(f"  Resampling from {sr}Hz to 16000Hz...")
        duration = len(data) / sr
        n_samples = int(duration * 16000)
        indices = np.linspace(0, len(data) - 1, n_samples)
        data = np.interp(indices, np.arange(len(data)), data).astype(np.float32)

    return data


# ---------------------------------------------------------------------------
# WER computation
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> list[str]:
    """Normalize text for WER comparison: lowercase, strip punctuation, split words."""
    text = text.lower()
    # Normalize unicode (accented characters stay, but combining forms are unified)
    text = unicodedata.normalize("NFC", text)
    # Remove punctuation but keep accented letters and hyphens within words
    text = re.sub(r"[^\w\s\-]", "", text)
    # Collapse whitespace
    words = text.split()
    return [w for w in words if w]


def repetition_metrics(words: list[str]) -> tuple[float, int]:
    """Return (adjacent_repeat_ratio, max_consecutive_run)."""
    if len(words) < 2:
        return 0.0, 1 if words else 0

    repeated_edges = 0
    max_run = 1
    cur_run = 1
    for i in range(1, len(words)):
        if words[i] == words[i - 1]:
            repeated_edges += 1
            cur_run += 1
            max_run = max(max_run, cur_run)
        else:
            cur_run = 1
    return repeated_edges / (len(words) - 1), max_run


def word_error_rate(reference: list[str], hypothesis: list[str]) -> tuple[float, int, int, int]:
    """Compute WER using Levenshtein edit distance on word sequences.

    Returns (wer, substitutions, deletions, insertions).
    """
    r = reference
    h = hypothesis
    n = len(r)
    m = len(h)

    # DP table
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if r[i - 1] == h[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                d[i][j] = 1 + min(
                    d[i - 1][j],      # deletion
                    d[i][j - 1],      # insertion
                    d[i - 1][j - 1],  # substitution
                )

    # Backtrack to count S, D, I
    subs = dels = ins = 0
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and r[i - 1] == h[j - 1]:
            i -= 1
            j -= 1
        elif i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + 1:
            subs += 1
            i -= 1
            j -= 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            dels += 1
            i -= 1
        else:
            ins += 1
            j -= 1

    wer = d[n][m] / max(n, 1)
    return wer, subs, dels, ins


# ---------------------------------------------------------------------------
# Main benchmark
# ---------------------------------------------------------------------------

def run_benchmark(
    audio_path: Path,
    sub_path: Path,
    backend: str = "mlx",
    model: str = "small",
    compute_type: str = "int8_float16",
    merge_short_ms: int = 900,
    merge_gap_ms: int = 120,
):
    """Run the transcription benchmark and print results."""

    # Parse subtitles
    print("\nParsing subtitles...")
    raw_ref_segments = parse_subtitle_file(sub_path)
    print(f"  Raw subtitle segments: {len(raw_ref_segments)}")

    ref_segments = merge_short_segments(
        raw_ref_segments,
        min_duration_s=merge_short_ms / 1000.0,
        max_gap_s=merge_gap_ms / 1000.0,
    )
    print(
        f"  Merged evaluation windows: {len(ref_segments)} "
        f"(min={merge_short_ms}ms, gap={merge_gap_ms}ms)"
    )

    if not ref_segments:
        print("Error: No subtitle segments parsed.")
        sys.exit(1)

    # Load audio
    print("Loading audio...")
    audio = load_audio(audio_path)
    duration = len(audio) / 16000
    print(f"  Duration: {duration:.1f}s ({len(audio)} samples)")

    # Create and load engine
    print(f"\nLoading transcription engine (backend={backend}, model={model})...")
    engine_kwargs = {"model": model, "language": "fr", "word_timestamps": True}
    if backend == "faster_whisper":
        engine_kwargs["compute_type"] = compute_type
    engine = create_engine(backend=backend, **engine_kwargs)
    engine.load_model()
    print("  Model loaded.")

    # --- Full-file transcription ---
    print("\n" + "=" * 70)
    print("FULL-FILE TRANSCRIPTION")
    print("=" * 70)

    full_result = engine.transcribe(audio)
    if full_result:
        print(f"\nTranscribed text:\n  {full_result.text}\n")

        # Build full reference text
        full_ref_text = " ".join(seg.text for seg in ref_segments)
        ref_words = normalize_text(full_ref_text)
        hyp_words = normalize_text(full_result.text)

        wer, subs, dels, ins = word_error_rate(ref_words, hyp_words)
        print(f"Overall WER: {wer:.1%}")
        print(f"  Reference words: {len(ref_words)}")
        print(f"  Hypothesis words: {len(hyp_words)}")
        print(f"  Substitutions: {subs}, Deletions: {dels}, Insertions: {ins}")
        rep_ratio, max_run = repetition_metrics(hyp_words)
        print(
            f"  Adjacent repetition: {rep_ratio:.1%} "
            f"(max consecutive run={max_run})"
        )

        # Word confidence stats
        if full_result.words:
            probs = [w.probability for w in full_result.words]
            print(f"\nWord confidence: mean={np.mean(probs):.3f}, "
                  f"min={np.min(probs):.3f}, max={np.max(probs):.3f}")
            low_conf = [w for w in full_result.words if w.probability < 0.5]
            if low_conf:
                print(f"  Low-confidence words (<0.5): "
                      + ", ".join(f'"{w.word}" ({w.probability:.2f})' for w in low_conf[:10]))
    else:
        print("  No transcription produced for full file.")

    # --- Segment-by-segment comparison ---
    print("\n" + "=" * 70)
    print("SEGMENT-BY-SEGMENT COMPARISON")
    print("=" * 70)

    segment_wers = []
    repetition_alerts = 0
    for i, ref_seg in enumerate(ref_segments):
        # Extract audio for this segment
        start_sample = int(ref_seg.start * 16000)
        end_sample = int(ref_seg.end * 16000)

        # Clamp to audio bounds
        start_sample = max(0, start_sample)
        end_sample = min(len(audio), end_sample)

        if end_sample - start_sample < 1600:  # less than 0.1s
            continue

        seg_audio = audio[start_sample:end_sample]
        result = engine.transcribe(seg_audio)

        hyp_text = result.text if result else ""
        ref_words_seg = normalize_text(ref_seg.text)
        hyp_words_seg = normalize_text(hyp_text)

        if ref_words_seg:
            seg_wer, _, _, _ = word_error_rate(ref_words_seg, hyp_words_seg)
            segment_wers.append(seg_wer)
        else:
            seg_wer = 0.0

        # Color-code: green for good, yellow for ok, red for bad
        if seg_wer <= 0.1:
            indicator = "OK"
        elif seg_wer <= 0.3:
            indicator = ".."
        else:
            indicator = "XX"

        time_str = f"[{ref_seg.start:6.1f}s - {ref_seg.end:6.1f}s]"
        print(f"\n  {indicator} Segment {i + 1:3d} {time_str}  WER: {seg_wer:.0%}")
        print(f"     REF: {ref_seg.text}")
        print(f"     HYP: {hyp_text}")
        rep_ratio, max_run = repetition_metrics(hyp_words_seg)
        if rep_ratio >= 0.20 or max_run >= 4:
            repetition_alerts += 1
            print(
                f"     REP: ratio={rep_ratio:.1%}, max-run={max_run} "
                "(possible hallucination loop)"
            )

        # Show per-word confidence for this segment
        if result and result.words:
            low = [w for w in result.words if w.probability < 0.5]
            if low:
                print(f"     LOW: " + ", ".join(
                    f'"{w.word}" ({w.probability:.2f})' for w in low
                ))

    # Summary
    if segment_wers:
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"  Segments evaluated: {len(segment_wers)}")
        print(f"  Mean segment WER:   {np.mean(segment_wers):.1%}")
        print(f"  Median segment WER: {np.median(segment_wers):.1%}")
        print(f"  Best segment WER:   {np.min(segment_wers):.1%}")
        print(f"  Worst segment WER:  {np.max(segment_wers):.1%}")
        good = sum(1 for w in segment_wers if w <= 0.1)
        ok = sum(1 for w in segment_wers if 0.1 < w <= 0.3)
        bad = sum(1 for w in segment_wers if w > 0.3)
        print(f"  Good (<=10%): {good}  |  OK (<=30%): {ok}  |  Poor (>30%): {bad}")
        print(f"  Repetition-alert segments: {repetition_alerts}")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark transcription accuracy against YouTube subtitles"
    )
    parser.add_argument(
        "url",
        nargs="?",
        default=DEFAULT_VIDEO,
        help="YouTube URL with French audio and subtitles (default: a French news clip)",
    )
    parser.add_argument(
        "--model",
        default="small",
        help="Whisper model size: tiny, base, small, medium, large (default: small)",
    )
    parser.add_argument(
        "--backend",
        default="mlx",
        choices=["mlx", "faster_whisper"],
        help="Transcription backend to benchmark (default: mlx).",
    )
    parser.add_argument(
        "--compute-type",
        default="int8_float16",
        help="faster-whisper compute type (default: int8_float16).",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip download and use existing files in test_data/",
    )
    parser.add_argument(
        "--subtitle",
        default="",
        help="Optional subtitle file path to use instead of auto-discovery.",
    )
    parser.add_argument(
        "--merge-short-ms",
        type=int,
        default=900,
        help="Merge reference subtitle windows shorter than this (default: 900).",
    )
    parser.add_argument(
        "--merge-gap-ms",
        type=int,
        default=120,
        help="Merge adjacent subtitle windows if gap <= this (default: 120).",
    )
    args = parser.parse_args()

    if not args.skip_download:
        check_prerequisites()
        audio_path, sub_path = download_audio_and_subs(args.url)
    else:
        audio_path = TEST_DATA_DIR / "audio.wav"
        if args.subtitle:
            sub_path = Path(args.subtitle)
        else:
            candidates = [
                f for f in TEST_DATA_DIR.glob("subs*") if f.suffix in (".vtt", ".srt")
            ]
            sub_path = choose_subtitle_file(candidates)
        if not audio_path.exists() or sub_path is None:
            print("Error: No existing test data found. Run without --skip-download first.")
            sys.exit(1)
        if not sub_path.exists():
            print(f"Error: Subtitle file not found: {sub_path}")
            sys.exit(1)

    run_benchmark(
        audio_path,
        sub_path,
        backend=args.backend,
        model=args.model,
        compute_type=args.compute_type,
        merge_short_ms=max(0, args.merge_short_ms),
        merge_gap_ms=max(0, args.merge_gap_ms),
    )


if __name__ == "__main__":
    main()
