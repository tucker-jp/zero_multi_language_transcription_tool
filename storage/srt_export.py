"""SRT subtitle file writer."""

from __future__ import annotations

from pathlib import Path


def _format_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format HH:MM:SS,mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def export_srt(segments: list[dict], output_path: str | Path) -> Path:
    """Export segments to an SRT file.

    Args:
        segments: list of dicts with 'start_time', 'end_time', 'text' keys
        output_path: where to write the SRT file

    Returns:
        Path to the written file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    for i, seg in enumerate(segments, start=1):
        start = _format_timestamp(seg["start_time"])
        end = _format_timestamp(seg["end_time"])
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(seg["text"])
        lines.append("")  # blank line separator

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
