"""Dark-themed stylesheet for the UI. Defense-grade aesthetic."""

DARK_THEME = """
QMainWindow, QWidget {
    background-color: #0d1117;
    color: #c9d1d9;
    font-family: 'Segoe UI', 'Cantarell', sans-serif;
    font-size: 13px;
}

QLabel#headingLabel {
    font-size: 22px;
    font-weight: 700;
    color: #f0f6fc;
    padding: 12px 0;
}

QLabel#subheadingLabel {
    font-size: 14px;
    color: #8b949e;
}

QLabel#statusOK {
    color: #3fb950;
    font-size: 18px;
    font-weight: 700;
}

QLabel#statusWarn {
    color: #d29922;
    font-size: 18px;
    font-weight: 700;
}

QLabel#statusAlert {
    color: #f85149;
    font-size: 22px;
    font-weight: 800;
}

QFrame#card {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 16px;
}

QPushButton {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
}
QPushButton:hover { background-color: #30363d; }
QPushButton:pressed { background-color: #1c2128; }

QPushButton#primary {
    background-color: #238636;
    border: 1px solid #3fb950;
    color: #ffffff;
}
QPushButton#primary:hover { background-color: #2ea043; }

QPushButton#danger {
    background-color: #b62324;
    border: 1px solid #f85149;
    color: #ffffff;
}
QPushButton#danger:hover { background-color: #da3633; }

QListWidget, QTableWidget, QTreeWidget {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #c9d1d9;
    gridline-color: #21262d;
}
QHeaderView::section {
    background-color: #161b22;
    color: #c9d1d9;
    padding: 6px;
    border: 1px solid #30363d;
    font-weight: 600;
}

QLineEdit, QTextEdit {
    background-color: #0d1117;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 6px;
}
QLineEdit:focus { border-color: #58a6ff; }

QTabWidget::pane { border: 1px solid #30363d; background-color: #0d1117; }
QTabBar::tab {
    background-color: #161b22;
    color: #c9d1d9;
    padding: 10px 20px;
    border: 1px solid #30363d;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected { background-color: #0d1117; color: #58a6ff; }

QStatusBar { background-color: #161b22; color: #8b949e; }

QScrollBar:vertical { background-color: #0d1117; width: 10px; }
QScrollBar::handle:vertical { background-color: #30363d; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background-color: #484f58; }
"""

LOCKDOWN_STYLE = """
QWidget#lockdownRoot {
    background-color: #0a0000;
}
QLabel#lockdownTitle {
    color: #ff3333;
    font-size: 64px;
    font-weight: 900;
    qproperty-alignment: AlignCenter;
}
QLabel#lockdownSubtitle {
    color: #ff8888;
    font-size: 22px;
    qproperty-alignment: AlignCenter;
}
QLabel#lockdownDevice {
    color: #ffffff;
    font-size: 16px;
    qproperty-alignment: AlignCenter;
    font-family: 'Consolas', 'Courier New', monospace;
}
QLabel#lockdownPrompt {
    color: #ffcc00;
    font-size: 28px;
    font-weight: 700;
    qproperty-alignment: AlignCenter;
}
"""
