"""Management window for browsing sessions and managing vocabulary."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QComboBox,
    QLabel,
    QSplitter,
    QListWidget,
    QListWidgetItem,
    QTextBrowser,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHeaderView,
    QFileDialog,
    QMessageBox,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt

from config.settings import Settings
from storage.database import Database
from storage.anki_export import export_anki
from ui.manage_styles import (
    MANAGE_WINDOW_STYLE,
    MANAGE_TAB_STYLE,
    MANAGE_TABLE_STYLE,
    MANAGE_LIST_STYLE,
    MANAGE_BUTTON_STYLE,
    MANAGE_COMBO_STYLE,
    MANAGE_TEXTBROWSER_STYLE,
)


class SessionsTab(QWidget):
    """Tab for browsing transcription sessions and their segments."""

    def __init__(self, db: Database):
        super().__init__()
        self._db = db
        self._current_session_id: int | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: session list
        self._session_list = QListWidget()
        self._session_list.setStyleSheet(MANAGE_LIST_STYLE)
        self._session_list.currentItemChanged.connect(self._on_session_selected)
        splitter.addWidget(self._session_list)

        # Right: segment viewer
        self._segment_viewer = QTextBrowser()
        self._segment_viewer.setStyleSheet(MANAGE_TEXTBROWSER_STYLE)
        self._segment_viewer.setOpenExternalLinks(False)
        self._segment_viewer.setPlaceholderText("Select a session to view segments")
        splitter.addWidget(self._segment_viewer)

        splitter.setStretchFactor(0, 35)
        splitter.setStretchFactor(1, 65)

        layout.addWidget(splitter)

    def refresh(self):
        self._session_list.clear()
        self._segment_viewer.clear()
        self._current_session_id = None

        sessions = self._db.get_sessions()
        for session in sessions:
            started = session.get("started_at", "")
            ended = session.get("ended_at", "")
            title = session.get("title", "Untitled")

            # Format date range
            try:
                start_dt = datetime.fromisoformat(started)
                date_str = start_dt.strftime("%b %d, %Y  %H:%M")
            except (ValueError, TypeError):
                date_str = started

            if ended:
                try:
                    end_dt = datetime.fromisoformat(ended)
                    date_str += f" - {end_dt.strftime('%H:%M')}"
                except (ValueError, TypeError):
                    pass

            item = QListWidgetItem(f"{title}\n{date_str}")
            item.setData(Qt.ItemDataRole.UserRole, session["id"])
            self._session_list.addItem(item)

    def _on_session_selected(self, current: QListWidgetItem | None, _previous):
        if current is None:
            self._segment_viewer.clear()
            self._current_session_id = None
            return

        session_id = current.data(Qt.ItemDataRole.UserRole)
        self._current_session_id = session_id
        segments = self._db.get_segments(session_id)

        if not segments:
            self._segment_viewer.setHtml(
                '<p style="color: rgba(255,255,255,0.4);">No segments in this session.</p>'
            )
            return

        lines = []
        for seg in segments:
            start = seg.get("start_time", 0.0)
            minutes = int(start) // 60
            seconds = int(start) % 60
            text = seg.get("text", "")
            lines.append(
                f'<p><span style="color: #64B5F6; font-weight: 600;">'
                f'[{minutes:02d}:{seconds:02d}]</span> {text}</p>'
            )

        self._segment_viewer.setHtml("".join(lines))


class VocabularyTab(QWidget):
    """Tab for managing saved vocabulary with checkboxes and export."""

    def __init__(self, db: Database, language: str):
        super().__init__()
        self._db = db
        self._language = language
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._select_all_btn = QPushButton("Select All")
        self._select_all_btn.setStyleSheet(MANAGE_BUTTON_STYLE)
        self._select_all_btn.clicked.connect(self._select_all)
        toolbar.addWidget(self._select_all_btn)

        self._deselect_all_btn = QPushButton("Deselect All")
        self._deselect_all_btn.setStyleSheet(MANAGE_BUTTON_STYLE)
        self._deselect_all_btn.clicked.connect(self._deselect_all)
        toolbar.addWidget(self._deselect_all_btn)

        self._count_label = QLabel("0 of 0 selected")
        self._count_label.setStyleSheet(
            "color: rgba(255, 255, 255, 0.5); font-size: 13px; padding: 0 8px;"
        )
        toolbar.addWidget(self._count_label)

        toolbar.addStretch()

        self._delete_btn = QPushButton("Delete Selected")
        self._delete_btn.setObjectName("deleteBtn")
        self._delete_btn.setStyleSheet(MANAGE_BUTTON_STYLE)
        self._delete_btn.clicked.connect(self._delete_selected)
        toolbar.addWidget(self._delete_btn)

        self._export_btn = QPushButton("Export to Anki...")
        self._export_btn.setObjectName("exportBtn")
        self._export_btn.setStyleSheet(MANAGE_BUTTON_STYLE)
        self._export_btn.clicked.connect(self._export_selected)
        toolbar.addWidget(self._export_btn)

        layout.addLayout(toolbar)

        # Table
        self._table = QTableWidget()
        self._table.setStyleSheet(MANAGE_TABLE_STYLE)
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["", "Word", "Translation", "Context Sentence", "Date Added"]
        )
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.itemChanged.connect(self._update_count)

        # Column sizing
        header = self._table.horizontalHeader()
        header.resizeSection(0, 40)
        header.resizeSection(1, 120)
        header.resizeSection(2, 120)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.resizeSection(4, 110)

        layout.addWidget(self._table)

    def refresh(self):
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        vocab = self._db.get_vocabulary(language=self._language)

        self._table.setRowCount(len(vocab))
        for row, entry in enumerate(vocab):
            # Checkbox
            check_item = QTableWidgetItem()
            check_item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
            check_item.setCheckState(Qt.CheckState.Checked)
            check_item.setData(Qt.ItemDataRole.UserRole, entry["id"])
            self._table.setItem(row, 0, check_item)

            # Word
            self._table.setItem(row, 1, QTableWidgetItem(entry.get("word", "")))

            # Translation
            self._table.setItem(
                row, 2, QTableWidgetItem(entry.get("translation", ""))
            )

            # Context sentence
            self._table.setItem(
                row, 3, QTableWidgetItem(entry.get("sentence", "") or "")
            )

            # Date added
            added_at = entry.get("added_at", "")
            try:
                dt = datetime.fromisoformat(added_at)
                date_str = dt.strftime("%b %d, %Y")
            except (ValueError, TypeError):
                date_str = added_at
            self._table.setItem(row, 4, QTableWidgetItem(date_str))

        self._table.blockSignals(False)
        self._update_count()

    def _update_count(self):
        total = self._table.rowCount()
        checked = 0
        for row in range(total):
            item = self._table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                checked += 1
        self._count_label.setText(f"{checked} of {total} selected")

    def _select_all(self):
        self._table.blockSignals(True)
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked)
        self._table.blockSignals(False)
        self._update_count()

    def _deselect_all(self):
        self._table.blockSignals(True)
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)
        self._table.blockSignals(False)
        self._update_count()

    def _get_checked_rows(self) -> list[int]:
        checked = []
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                checked.append(row)
        return checked

    def _delete_selected(self):
        checked = self._get_checked_rows()
        if not checked:
            return

        reply = QMessageBox.question(
            self,
            "Delete Vocabulary",
            f"Delete {len(checked)} selected word(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for row in checked:
            item = self._table.item(row, 0)
            if item:
                word_id = item.data(Qt.ItemDataRole.UserRole)
                self._db.delete_word(word_id)

        self.refresh()

    def _export_selected(self):
        checked = self._get_checked_rows()
        if not checked:
            return

        filtered = []
        for row in checked:
            word = self._table.item(row, 1)
            translation = self._table.item(row, 2)
            if word and translation:
                filtered.append(
                    {
                        "word": word.text(),
                        "translation": translation.text(),
                    }
                )

        if not filtered:
            return

        default_name = (
            f"anki_{self._language}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Anki Vocabulary",
            str(Path.home() / default_name),
            "Text Files (*.txt)",
        )
        if path:
            export_anki(filtered, path, tag=self._language)


class ManageWindow(QWidget):
    """Main management window for sessions and vocabulary."""

    def __init__(self, db: Database, settings: Settings):
        super().__init__()
        self._db = db
        self._settings = settings
        self._setup_ui()

    def _setup_ui(self):
        self.setObjectName("manageWindow")
        self.setWindowTitle("French Transcription Helper")
        self.setFixedSize(780, 550)
        self.setStyleSheet(MANAGE_WINDOW_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header bar
        header = QHBoxLayout()
        title = QLabel("Manage")
        title.setStyleSheet(
            "color: #FFFFFF; font-size: 20px; font-weight: 700; "
            'font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;'
        )
        header.addWidget(title)
        header.addStretch()

        # Language selector
        lang_label = QLabel("Language:")
        lang_label.setStyleSheet(
            "color: rgba(255, 255, 255, 0.6); font-size: 13px;"
        )
        header.addWidget(lang_label)

        self._lang_combo = QComboBox()
        self._lang_combo.setStyleSheet(MANAGE_COMBO_STYLE)
        self._lang_combo.addItem("French")
        self._lang_combo.addItem("Spanish (Coming Soon)")
        self._lang_combo.addItem("German (Coming Soon)")

        # Disable Spanish and German
        model = self._lang_combo.model()
        for i in (1, 2):
            item = model.item(i)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)

        header.addWidget(self._lang_combo)

        layout.addLayout(header)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(MANAGE_TAB_STYLE)

        self._sessions_tab = SessionsTab(self._db)
        self._vocabulary_tab = VocabularyTab(self._db, self._settings.language)

        self._tabs.addTab(self._sessions_tab, "Sessions")
        self._tabs.addTab(self._vocabulary_tab, "Vocabulary")

        layout.addWidget(self._tabs)

    def refresh(self):
        self._sessions_tab.refresh()
        self._vocabulary_tab.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        # Center on screen
        screen = self.screen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            self.move(x, y)
