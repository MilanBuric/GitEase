"""
Dark theme stylesheet for GitEase, in Qt's QSS format (a CSS-like syntax).
Kept in its own file so tweaking the look never means touching the UI logic.
"""

DARK_THEME = """
QWidget {
    background-color: #0d1117;
    color: #c9d1d9;
    font-family: "Segoe UI", "Cantarell", "Helvetica Neue", sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #0d1117;
}

QLabel {
    color: #c9d1d9;
    font-weight: 500;
}

QLabel#sectionLabel {
    color: #8b949e;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 6px;
}

QLineEdit {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px 10px;
    color: #e6edf3;
    selection-background-color: #2f81f7;
}

QLineEdit:focus {
    border: 1px solid #2f81f7;
}

QLineEdit::placeholder {
    color: #6e7681;
}

QPushButton {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px 16px;
    color: #c9d1d9;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #30363d;
    border: 1px solid #8b949e;
}

QPushButton:pressed {
    background-color: #161b22;
}

QPushButton:disabled {
    background-color: #161b22;
    color: #6e7681;
    border: 1px solid #21262d;
}

QPushButton#primaryButton {
    background-color: #238636;
    border: 1px solid #2ea043;
    color: #ffffff;
    font-weight: 600;
    font-size: 14px;
}

QPushButton#primaryButton:hover {
    background-color: #2ea043;
}

QPushButton#primaryButton:pressed {
    background-color: #1a6e2c;
}

QPushButton#primaryButton:disabled {
    background-color: #21262d;
    border: 1px solid #30363d;
    color: #6e7681;
}

QGroupBox {
    border: 1px solid #30363d;
    border-radius: 8px;
    margin-top: 14px;
    padding: 14px 10px 10px 10px;
    font-weight: 500;
    color: #8b949e;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: #8b949e;
}

QPlainTextEdit {
    background-color: #010409;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 10px;
    color: #7ee787;
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 12px;
    selection-background-color: #2f81f7;
}

QMessageBox {
    background-color: #161b22;
}

QScrollBar:vertical {
    background: #0d1117;
    width: 12px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #30363d;
    border-radius: 6px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: #484f58;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""