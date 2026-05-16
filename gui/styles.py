STYLE_QSS = """
QMainWindow {
    background-color: #1e1e2e;
    color: #cdd6f4;
}

QWidget {
    font-family: "Microsoft YaHei", "SimHei", "Segoe UI", sans-serif;
    font-size: 13px;
}

QLabel {
    color: #cdd6f4;
}

QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #89b4fa;
}

QPushButton {
    background-color: #45475a;
    color: #cdd6f4;
    border: none;
    border-radius: 6px;
    padding: 7px 18px;
    font-weight: bold;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #585b70;
}

QPushButton:pressed {
    background-color: #313244;
}

QPushButton#searchBtn, QPushButton#downloadBtn {
    background-color: #89b4fa;
    color: #1e1e2e;
    font-weight: bold;
}

QPushButton#searchBtn:hover, QPushButton#downloadBtn:hover {
    background-color: #b4d0fb;
}

QPushButton#stopBtn {
    background-color: #f38ba8;
    color: #1e1e2e;
}

QPushButton#stopBtn:hover {
    background-color: #fab387;
}

QPushButton:disabled {
    background-color: #313244;
    color: #6c7086;
}

QTableWidget {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    gridline-color: #45475a;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}

QTableWidget::item {
    padding: 4px 8px;
}

QHeaderView::section {
    background-color: #45475a;
    color: #cdd6f4;
    padding: 6px;
    border: none;
    border-bottom: 1px solid #585b70;
    font-weight: bold;
}

QTabWidget::pane {
    border: 1px solid #45475a;
    border-radius: 6px;
    background-color: #1e1e2e;
    top: -1px;
}

QTabBar::tab {
    background-color: #313244;
    color: #a6adc8;
    padding: 8px 20px;
    border: 1px solid #45475a;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #1e1e2e;
    color: #89b4fa;
    border-bottom: 2px solid #89b4fa;
    font-weight: bold;
}

QTabBar::tab:hover:!selected {
    background-color: #45475a;
    color: #cdd6f4;
}

QProgressBar {
    border: 1px solid #45475a;
    border-radius: 6px;
    background-color: #313244;
    text-align: center;
    color: #cdd6f4;
    min-height: 20px;
    font-weight: bold;
}

QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 5px;
}

QScrollBar:vertical {
    background-color: #1e1e2e;
    width: 10px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 5px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #585b70;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: #1e1e2e;
    height: 10px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal {
    background-color: #45475a;
    border-radius: 5px;
    min-width: 30px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #585b70;
}
"""
