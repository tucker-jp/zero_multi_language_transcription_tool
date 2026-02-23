"""Frameless always-on-top floating overlay window."""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFrame, QApplication
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QRectF
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath

from ui.caption_widget import CaptionWidget
from ui.controls import ControlBar
from ui.translation_popup import TranslationPopup
from ui.macos_window import configure_overlay_window
from ui.styles import OVERLAY_STYLE


class OverlayWindow(QWidget):
    """Floating, draggable, semi-transparent caption overlay."""

    pause_toggled = pyqtSignal(bool)
    export_requested = pyqtSignal()
    save_folder_requested = pyqtSignal()
    text_selected = pyqtSignal(str, str)  # (text, sentence)
    undo_save_requested = pyqtSignal()  # undo last auto-saved word

    def __init__(
        self,
        width: int = 800,
        height: int = 160,
        opacity: float = 0.85,
        font_size: int = 22,
        x: int = -1,
        y: int = -1,
    ):
        super().__init__()
        self._drag_pos: QPoint | None = None
        self._fullscreen_configured = False
        self._setup_window(width, height, opacity, x, y)
        self._setup_ui(font_size)

    def _setup_window(self, width, height, opacity, x, y):
        self.setObjectName("overlay")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(width, height)

        # Position: center-bottom by default
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            if x < 0:
                x = (geo.width() - width) // 2
            if y < 0:
                y = geo.height() - height - 60
        self.move(x, y)

    def _setup_ui(self, font_size):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.caption = CaptionWidget(font_size=font_size)
        self.caption.text_selected.connect(self._on_text_selected)
        layout.addWidget(self.caption, stretch=1)

        # Separator line between caption and controls
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); border: none;")
        layout.addWidget(separator)

        self.controls = ControlBar()
        self.controls.pause_toggled.connect(self.pause_toggled.emit)
        self.controls.export_requested.connect(self.export_requested.emit)
        self.controls.settings_requested.connect(self.save_folder_requested.emit)
        layout.addWidget(self.controls)

        self.popup = TranslationPopup()
        self.popup.undo_save_requested.connect(self.undo_save_requested.emit)

    def _on_text_selected(self, text: str, sentence: str):
        self.text_selected.emit(text, sentence)

    def show_translation(
        self, text: str, text_trans: str, sentence: str, sentence_trans: str
    ):
        is_phrase = " " in text
        popup_width = 450 if is_phrase else 350
        self.popup.setFixedWidth(popup_width)
        # Position popup above the overlay, centered
        pos = self.mapToGlobal(QPoint(self.width() // 2 - popup_width // 2, -220))
        self.popup.show_translation(text, text_trans, sentence, sentence_trans, pos)

    def set_caption(self, text: str, is_final: bool = True):
        self.caption.set_caption(text, is_final=is_final)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Inset by 0.5px for clean stroke
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        radius = 14.0

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        # Fill
        painter.fillPath(path, QBrush(QColor(20, 20, 30, 217)))

        # Subtle 1px border at 6% opacity
        pen = QPen(QColor(255, 255, 255, 15))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.drawPath(path)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._fullscreen_configured:
            configure_overlay_window(self)
            self._fullscreen_configured = True

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
