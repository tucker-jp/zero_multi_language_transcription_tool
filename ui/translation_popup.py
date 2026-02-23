"""Popup showing word/phrase and sentence translation."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import (
    pyqtSignal,
    Qt,
    QTimer,
    QPoint,
    QRectF,
    QPropertyAnimation,
    QEasingCurve,
)
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen

from ui.styles import POPUP_STYLE
from ui.macos_window import configure_overlay_window


class TranslationPopup(QFrame):
    """Floating popup that shows word/phrase + sentence translations."""

    undo_save_requested = pyqtSignal()  # emitted when user clicks Undo

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("translationPopup")
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._word = ""
        self._translation = ""
        self._sentence = ""
        self._fade_anim: QPropertyAnimation | None = None
        self._setup()

    def _setup(self):
        self.setStyleSheet(POPUP_STYLE)
        self.setFixedWidth(350)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)

        self._type_label = QLabel()
        self._type_label.setObjectName("typeLabel")
        header.addWidget(self._type_label)
        header.addStretch()

        self._close_btn = QPushButton("X")
        self._close_btn.setObjectName("closeBtn")
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setToolTip("Close")
        self._close_btn.clicked.connect(self.hide)
        header.addWidget(self._close_btn)

        layout.addLayout(header)

        self._word_label = QLabel()
        self._word_label.setObjectName("wordLabel")
        self._word_label.setWordWrap(True)
        layout.addWidget(self._word_label)

        self._translation_label = QLabel()
        self._translation_label.setObjectName("translationLabel")
        self._translation_label.setWordWrap(True)
        layout.addWidget(self._translation_label)

        self._sentence_label = QLabel()
        self._sentence_label.setObjectName("sentenceLabel")
        self._sentence_label.setWordWrap(True)
        layout.addWidget(self._sentence_label)

        self._sentence_trans_label = QLabel()
        self._sentence_trans_label.setObjectName("sentenceTransLabel")
        self._sentence_trans_label.setWordWrap(True)
        layout.addWidget(self._sentence_trans_label)

        self._undo_btn = QPushButton("Undo Save")
        self._undo_btn.setObjectName("undoBtn")
        self._undo_btn.clicked.connect(self._on_undo)
        layout.addWidget(self._undo_btn)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        radius = 12.0

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        # Solid dark blue fill
        painter.fillPath(path, QBrush(QColor(10, 55, 130, 255)))

        # Blue border
        pen = QPen(QColor(100, 181, 246, 200))
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.drawPath(path)

        painter.end()

    def show_translation(
        self,
        word: str,
        word_translation: str,
        sentence: str,
        sentence_translation: str,
        pos: QPoint | None = None,
    ):
        self._word = word
        self._translation = word_translation
        self._sentence = sentence

        is_phrase = " " in word
        self._type_label.setText("PHRASE" if is_phrase else "WORD")
        self._word_label.setText(word)
        self._translation_label.setText(word_translation)
        self._sentence_label.setText(f"FR: {sentence}")
        self._sentence_trans_label.setText(f"EN: {sentence_translation}")

        if pos:
            self.move(pos)

        self.adjustSize()

        # Fade-in animation
        self._undo_btn.setEnabled(True)
        self._undo_btn.setText("Undo Save")

        self.setWindowOpacity(0.0)
        self.show()
        configure_overlay_window(self)

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(150)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.start()

    def _on_undo(self):
        self.undo_save_requested.emit()
        self._undo_btn.setText("Removed!")
        self._undo_btn.setEnabled(False)
