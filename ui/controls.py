"""Control buttons for the overlay (pause, export, settings)."""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PyQt6.QtCore import pyqtSignal

from ui.styles import CONTROLS_STYLE


class ControlBar(QWidget):
    """Horizontal bar with pause/resume, export, and settings buttons."""

    pause_toggled = pyqtSignal(bool)  # True = paused
    export_requested = pyqtSignal()
    settings_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paused = False
        self._setup()

    def _setup(self):
        self.setStyleSheet(CONTROLS_STYLE)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self._pause_btn = QPushButton("Pause")
        self._pause_btn.setObjectName("pauseBtn")
        self._pause_btn.clicked.connect(self._toggle_pause)
        layout.addWidget(self._pause_btn)

        self._export_btn = QPushButton("Export Session TXT")
        self._export_btn.clicked.connect(self.export_requested.emit)
        layout.addWidget(self._export_btn)

        layout.addStretch()

    def _toggle_pause(self):
        self._paused = not self._paused
        self._pause_btn.setText("Resume" if self._paused else "Pause")
        self._pause_btn.setProperty("paused", self._paused)
        self._pause_btn.style().unpolish(self._pause_btn)
        self._pause_btn.style().polish(self._pause_btn)
        self.pause_toggled.emit(self._paused)

    def set_paused(self, paused: bool):
        """Set pause state without emitting the signal (for external sync)."""
        self._paused = paused
        self._pause_btn.setText("Resume" if self._paused else "Pause")
        self._pause_btn.setProperty("paused", self._paused)
        self._pause_btn.style().unpolish(self._pause_btn)
        self._pause_btn.style().polish(self._pause_btn)

    @property
    def is_paused(self) -> bool:
        return self._paused
