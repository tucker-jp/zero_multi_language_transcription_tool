"""QSS themes for the management window."""

from __future__ import annotations

MANAGE_WINDOW_STYLE = """
QWidget#manageWindow {
    background-color: #1a1a2e;
    color: #E0E0E0;
    font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
}
"""

MANAGE_TAB_STYLE = """
QTabWidget::pane {
    border: none;
    background-color: #1a1a2e;
}
QTabBar::tab {
    background-color: transparent;
    color: rgba(255, 255, 255, 0.5);
    font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: 14px;
    font-weight: 600;
    padding: 10px 24px;
    border: none;
    border-bottom: 3px solid transparent;
    min-width: 100px;
}
QTabBar::tab:selected {
    color: #64B5F6;
    border-bottom: 3px solid #64B5F6;
}
QTabBar::tab:hover:!selected {
    color: rgba(255, 255, 255, 0.8);
}
"""

MANAGE_TABLE_STYLE = """
QTableWidget {
    background-color: #16213e;
    alternate-background-color: #1a2744;
    color: #E0E0E0;
    font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    border: 1px solid rgba(100, 181, 246, 0.15);
    border-radius: 6px;
    gridline-color: rgba(255, 255, 255, 0.06);
    selection-background-color: rgba(100, 181, 246, 0.25);
    selection-color: #FFFFFF;
    padding: 0px;
}
QTableWidget::item {
    padding: 6px 8px;
}
QHeaderView::section {
    background-color: #0f1a30;
    color: rgba(255, 255, 255, 0.6);
    font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.5px;
    padding: 8px;
    border: none;
    border-bottom: 1px solid rgba(100, 181, 246, 0.2);
}
"""

MANAGE_LIST_STYLE = """
QListWidget {
    background-color: #16213e;
    color: #E0E0E0;
    font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    border: 1px solid rgba(100, 181, 246, 0.15);
    border-radius: 6px;
    outline: none;
}
QListWidget::item {
    padding: 10px 12px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}
QListWidget::item:hover {
    background-color: rgba(100, 181, 246, 0.1);
}
QListWidget::item:selected {
    background-color: rgba(100, 181, 246, 0.25);
    color: #FFFFFF;
}
"""

MANAGE_BUTTON_STYLE = """
QPushButton {
    background-color: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 6px;
    color: rgba(255, 255, 255, 0.8);
    font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    font-weight: 500;
    padding: 6px 16px;
    min-width: 80px;
}
QPushButton:hover {
    background-color: rgba(255, 255, 255, 0.14);
    color: #FFFFFF;
}
QPushButton:pressed {
    background-color: rgba(255, 255, 255, 0.18);
}
QPushButton#exportBtn {
    background-color: rgba(100, 181, 246, 0.2);
    border-color: rgba(100, 181, 246, 0.4);
    color: #64B5F6;
}
QPushButton#exportBtn:hover {
    background-color: rgba(100, 181, 246, 0.3);
    color: #90CAF9;
}
QPushButton#deleteBtn {
    background-color: rgba(239, 83, 80, 0.15);
    border-color: rgba(239, 83, 80, 0.3);
    color: #EF5350;
}
QPushButton#deleteBtn:hover {
    background-color: rgba(239, 83, 80, 0.25);
    color: #EF9A9A;
}
"""

MANAGE_COMBO_STYLE = """
QComboBox {
    background-color: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 6px;
    color: #E0E0E0;
    font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    font-weight: 500;
    padding: 5px 12px;
    min-width: 140px;
}
QComboBox:hover {
    border-color: rgba(100, 181, 246, 0.5);
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid rgba(255, 255, 255, 0.5);
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #16213e;
    border: 1px solid rgba(100, 181, 246, 0.3);
    color: #E0E0E0;
    selection-background-color: rgba(100, 181, 246, 0.3);
    outline: none;
}
"""

MANAGE_TEXTBROWSER_STYLE = """
QTextBrowser {
    background-color: #16213e;
    color: #E0E0E0;
    font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    border: 1px solid rgba(100, 181, 246, 0.15);
    border-radius: 6px;
    padding: 12px;
    selection-background-color: rgba(100, 181, 246, 0.3);
}
"""
