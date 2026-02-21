"""Plain-text transcript writer."""

from __future__ import annotations

from pathlib import Path


def _format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def export_txt(
    segments: list[dict],
    output_path: str | Path,
    include_timestamps: bool = True,
) -> Path:
    """Export transcript segments to readable plain text."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    for seg in segments:
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        if include_timestamps:
            ts = _format_timestamp(float(seg.get("start_time", 0.0)))
            lines.append(f"[{ts}] {text}")
        else:
            lines.append(text)

    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return output_path
