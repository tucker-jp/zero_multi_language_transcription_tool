"""Clickable caption display with word/phrase selection via mouse events."""

from __future__ import annotations

import html
import re

from PyQt6.QtWidgets import QTextBrowser
from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QTextCursor, QTextCharFormat, QColor, QCursor

from ui.styles import CAPTION_STYLE


class CaptionWidget(QTextBrowser):
    """Displays transcribed text with click-to-select words or drag-to-select phrases."""

    text_selected = pyqtSignal(str, str)  # (selected_text, sentence)

    def __init__(self, font_size: int = 22, max_segments: int = 5, parent=None):
        super().__init__(parent)
        self._font_size = font_size
        self._max_segments = max_segments
        self._segments: list[str] = []
        self._current_sentence = ""
        self._word_spans: list[tuple[int, int]] = []  # (start, end) char positions
        self._press_word_idx: int | None = None
        self._current_end_idx: int | None = None
        self._is_dragging = False
        self._press_pos = None
        self._setup()

    def _setup(self):
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setReadOnly(True)
        self.setMouseTracking(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        style = CAPTION_STYLE.replace("{font_size}", str(self._font_size))
        self.setStyleSheet(style)

    def set_caption(self, text: str):
        """Append a segment and display the last N segments as rolling captions."""
        text = text.strip()
        if not text:
            return
        self._segments.append(text)
        if len(self._segments) > self._max_segments:
            self._segments = self._segments[-self._max_segments:]
        self._current_sentence = " ".join(self._segments)
        self._render_segments()

    def _render_segments(self):
        """Render all visible segments as styled HTML."""
        all_words = self._current_sentence.split()
        html_parts = []
        for w in all_words:
            html_parts.append(
                f'<span style="cursor: pointer;">{html.escape(w)}</span>'
            )
        html = " ".join(html_parts)
        self.setHtml(
            f'<div style="text-align: center; line-height: 1.5;">{html}</div>'
        )
        self._build_word_spans()
        # Auto-scroll to bottom to show latest captions
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _build_word_spans(self):
        """Build character position ranges for each word from plain text."""
        self._word_spans = []
        plain = self.toPlainText()
        for match in re.finditer(r'\S+', plain):
            self._word_spans.append((match.start(), match.end()))

    def _word_index_at(self, pos) -> int | None:
        """Map a widget position to a word index, or None if not on a word."""
        cursor = self.cursorForPosition(pos)
        char_pos = cursor.position()
        for i, (start, end) in enumerate(self._word_spans):
            if start <= char_pos < end:
                return i
        return None

    def _highlight_range(self, start_idx: int, end_idx: int):
        """Highlight words from start_idx to end_idx (inclusive) with blue background."""
        if not self._word_spans:
            return
        lo = min(start_idx, end_idx)
        hi = max(start_idx, end_idx)

        # First clear all highlights
        self._clear_highlights()

        # Apply highlight to the range
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(100, 181, 246, 77))  # ~30% opacity

        cursor = self.textCursor()
        char_start = self._word_spans[lo][0]
        char_end = self._word_spans[hi][1]
        cursor.setPosition(char_start)
        cursor.setPosition(char_end, QTextCursor.MoveMode.KeepAnchor)
        cursor.mergeCharFormat(fmt)

    def _clear_highlights(self):
        """Remove all highlights from text."""
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(0, 0, 0, 0))
        cursor.mergeCharFormat(fmt)

    def _get_word_text(self, idx: int) -> str:
        """Get the plain text of the word at index."""
        if 0 <= idx < len(self._word_spans):
            plain = self.toPlainText()
            start, end = self._word_spans[idx]
            return plain[start:end]
        return ""

    def _clean_word(self, word: str) -> str:
        """Strip punctuation from a word for translation."""
        return word.strip(".,!?;:\"'()[]{}«»—-…")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.pos()
            self._press_word_idx = self._word_index_at(event.pos())
            self._current_end_idx = self._press_word_idx
            self._is_dragging = False
            if self._press_word_idx is not None:
                self._highlight_range(self._press_word_idx, self._press_word_idx)
        # Don't call super() — prevents QTextBrowser's default selection/anchor behavior

    def mouseMoveEvent(self, event):
        if self._press_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            # Check drag distance
            delta = event.pos() - self._press_pos
            if delta.manhattanLength() > 4:
                self._is_dragging = True

            if self._is_dragging and self._press_word_idx is not None:
                end_idx = self._word_index_at(event.pos())
                if end_idx is not None and end_idx != self._current_end_idx:
                    self._current_end_idx = end_idx
                    self._highlight_range(self._press_word_idx, end_idx)
        else:
            # Hover cursor: pointing hand over words, arrow elsewhere
            idx = self._word_index_at(event.pos())
            if idx is not None:
                self.viewport().setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            else:
                self.viewport().setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        # Don't call super()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._press_word_idx is not None:
            if self._is_dragging and self._current_end_idx is not None:
                # Drag-select: emit phrase
                lo = min(self._press_word_idx, self._current_end_idx)
                hi = max(self._press_word_idx, self._current_end_idx)
                words = [self._get_word_text(i) for i in range(lo, hi + 1)]
                phrase = " ".join(words)
                cleaned = " ".join(self._clean_word(w) for w in words)
                if cleaned.strip():
                    self.text_selected.emit(cleaned, self._current_sentence)
            else:
                # Single click: emit word
                word = self._get_word_text(self._press_word_idx)
                cleaned = self._clean_word(word)
                if cleaned:
                    self.text_selected.emit(cleaned, self._current_sentence)

            # Clear highlights after brief delay
            QTimer.singleShot(150, self._clear_highlights)

        self._press_word_idx = None
        self._current_end_idx = None
        self._is_dragging = False
        self._press_pos = None
        # Don't call super()

    def clear_caption(self):
        self._segments = []
        self._current_sentence = ""
        self._word_spans = []
        self.clear()
