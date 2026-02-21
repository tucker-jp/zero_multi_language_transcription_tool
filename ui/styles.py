"""QSS themes for the overlay UI."""

OVERLAY_STYLE = """
QWidget#overlay {
    background-color: rgba(20, 20, 30, 217);
    border-radius: 14px;
}
"""

CAPTION_STYLE = """
QTextBrowser {
    background: transparent;
    border: none;
    color: #FFFFFF;
    font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: {font_size}px;
    font-weight: 500;
    padding: 10px 20px;
    selection-background-color: rgba(100, 181, 246, 0.3);
}
"""

CONTROLS_STYLE = """
QPushButton {
    background-color: rgba(255, 255, 255, 30);
    border: 1px solid rgba(255, 255, 255, 50);
    border-radius: 8px;
    color: rgba(255, 255, 255, 0.6);
    padding: 4px 12px;
    font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    font-weight: 500;
    letter-spacing: 0.3px;
    min-width: 60px;
}
QPushButton:hover {
    background-color: rgba(255, 255, 255, 50);
    color: rgba(255, 255, 255, 0.9);
}
QPushButton:pressed {
    background-color: rgba(255, 255, 255, 70);
    color: rgba(255, 255, 255, 1.0);
}
QPushButton#pauseBtn[paused="true"] {
    background-color: rgba(255, 100, 100, 60);
    border-color: rgba(255, 100, 100, 100);
    color: rgba(255, 150, 150, 0.9);
}
"""

POPUP_STYLE = """
QFrame#translationPopup {
    background-color: transparent;
    border: none;
    border-radius: 12px;
    padding: 12px;
}
QLabel#typeLabel {
    color: rgba(187, 222, 251, 0.9);
    font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.5px;
    padding-bottom: 2px;
}
QLabel#wordLabel {
    color: #FFFFFF;
    font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: 22px;
    font-weight: bold;
    padding-bottom: 2px;
}
QLabel#translationLabel {
    color: #FFF9C4;
    font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: 18px;
    font-weight: 600;
    padding-bottom: 4px;
}
QLabel#sentenceLabel {
    color: rgba(227, 242, 253, 0.85);
    font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    font-style: italic;
}
QLabel#sentenceTransLabel {
    color: #E3F2FD;
    font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    padding-bottom: 4px;
}
QPushButton#undoBtn {
    background-color: rgba(255, 255, 255, 40);
    border: 1px solid rgba(255, 255, 255, 120);
    border-radius: 6px;
    color: #FFFFFF;
    font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    padding: 4px 16px;
    font-size: 13px;
    font-weight: 600;
}
QPushButton#undoBtn:hover {
    background-color: rgba(255, 255, 255, 70);
}
QPushButton#undoBtn:pressed {
    background-color: rgba(255, 255, 255, 100);
}
QPushButton#undoBtn:disabled {
    background-color: rgba(255, 255, 255, 15);
    border-color: rgba(255, 255, 255, 40);
    color: rgba(255, 255, 255, 0.3);
}
"""
