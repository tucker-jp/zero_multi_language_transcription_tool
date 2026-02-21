"""Anki-compatible tab-separated vocabulary export."""

from __future__ import annotations

from pathlib import Path


def export_anki(
    vocabulary: list[dict],
    output_path: str | Path,
    tag: str = "french",
) -> None:
    """Write vocabulary as a tab-separated file for Anki import.

    Format per line: french_word<TAB>english_translation<TAB>tag
    """
    output_path = Path(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in vocabulary:
            word = entry.get("word", "").replace("\t", " ")
            translation = entry.get("translation", "").replace("\t", " ")
            f.write(f"{word}\t{translation}\t{tag}\n")
