STYLE_QSS = """
QMainWindow {
    background-color: #2a2a30;
    color: #c4c4cc;
}

QWidget {
    font-family: "Microsoft YaHei", "SimHei", "Segoe UI", sans-serif;
    font-size: 13px;
}

QLabel {
    color: #c4c4cc;
}

QGroupBox {
    color: #b0b0bc;
    font-weight: bold;
    border: 1px solid #3a3a44;
    border-radius: 8px;
    margin-top: 14px;
    padding: 14px 10px 10px 10px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #8a8a94;
}

QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #32323a;
    color: #c4c4cc;
    border: 1px solid #3a3a44;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #7a9ec9;
    selection-color: #2a2a30;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #7a9ec9;
}

QPushButton {
    background-color: #3a3a44;
    color: #c4c4cc;
    border: none;
    border-radius: 6px;
    padding: 7px 18px;
    font-weight: bold;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #484856;
}

QPushButton:pressed {
    background-color: #32323a;
}

QPushButton#searchBtn, QPushButton#downloadBtn {
    background-color: #7a9ec9;
    color: #2a2a30;
    font-weight: bold;
}

QPushButton#searchBtn:hover, QPushButton#downloadBtn:hover {
    background-color: #8eafd6;
}

QPushButton#stopBtn {
    background-color: #c9808e;
    color: #2a2a30;
}

QPushButton#stopBtn:hover {
    background-color: #d494a0;
}

QPushButton:disabled {
    background-color: #2e2e36;
    color: #5a5a66;
}

QTableWidget {
    background-color: #32323a;
    color: #c4c4cc;
    border: 1px solid #3a3a44;
    border-radius: 6px;
    gridline-color: #3a3a44;
    selection-background-color: #7a9ec9;
    selection-color: #2a2a30;
}

QTableWidget::item {
    padding: 4px 8px;
}

QHeaderView::section {
    background-color: #363640;
    color: #b0b0bc;
    padding: 6px;
    border: none;
    border-bottom: 1px solid #444452;
    font-weight: bold;
}

QTabWidget::pane {
    border: 1px solid #3a3a44;
    border-radius: 6px;
    background-color: #2a2a30;
    top: -1px;
}

QTabBar::tab {
    background-color: #2e2e36;
    color: #8a8a94;
    padding: 8px 20px;
    border: 1px solid #3a3a44;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #2a2a30;
    color: #7a9ec9;
    border-bottom: 2px solid #7a9ec9;
    font-weight: bold;
}

QTabBar::tab:hover:!selected {
    background-color: #363640;
    color: #b0b0bc;
}

QProgressBar {
    border: 1px solid #3a3a44;
    border-radius: 6px;
    background-color: #32323a;
    text-align: center;
    color: #b0b0bc;
    min-height: 20px;
    font-weight: bold;
}

QProgressBar::chunk {
    background-color: #8aba9a;
    border-radius: 5px;
}

QScrollBar:vertical {
    background-color: #2a2a30;
    width: 10px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background-color: #3a3a44;
    border-radius: 5px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #484856;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: #2a2a30;
    height: 10px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal {
    background-color: #3a3a44;
    border-radius: 5px;
    min-width: 30px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #484856;
}

QComboBox {
    background-color: #32323a;
    color: #c4c4cc;
    border: 1px solid #3a3a44;
    border-radius: 6px;
    padding: 6px 10px;
}

QComboBox:hover {
    border: 1px solid #7a9ec9;
}

QComboBox::drop-down {
    border: none;
    padding-right: 6px;
}

QComboBox QAbstractItemView {
    background-color: #32323a;
    color: #c4c4cc;
    border: 1px solid #3a3a44;
    selection-background-color: #7a9ec9;
    selection-color: #2a2a30;
}

QSpinBox, QDoubleSpinBox {
    background-color: #32323a;
    color: #c4c4cc;
    border: 1px solid #3a3a44;
    border-radius: 6px;
    padding: 4px 8px;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #7a9ec9;
}

QCheckBox {
    color: #c4c4cc;
    spacing: 6px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #3a3a44;
    border-radius: 4px;
    background-color: #32323a;
}

QCheckBox::indicator:checked {
    background-color: #7a9ec9;
    border: 1px solid #7a9ec9;
}

QListWidget {
    background-color: #32323a;
    color: #c4c4cc;
    border: 1px solid #3a3a44;
    border-radius: 6px;
    outline: none;
}

QListWidget::item {
    padding: 4px 8px;
}

QListWidget::item:selected {
    background-color: #7a9ec9;
    color: #2a2a30;
}
"""