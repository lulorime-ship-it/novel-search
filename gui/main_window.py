import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QProgressBar, QTextEdit, QPlainTextEdit,
    QSplitter, QHeaderView, QMessageBox, QFileDialog,
    QSpinBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QListWidget, QListWidgetItem, QAbstractItemView,
    QComboBox, QDialog, QScrollArea, QGridLayout,
)
from PySide6.QtCore import Qt, QTimer, Slot, QSize, QThreadPool
from PySide6.QtGui import QFont, QIcon, QColor, QPixmap

from sources.base import SearchResult, NovelInfo, ChapterInfo
from engine.cleaner import NovelCleaner
from gui.worker import NovelWorker
from gui.styles import STYLE_QSS

logger = logging.getLogger(__name__)


def _resource_file(filename: str) -> Path:
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent.parent
    path = base / filename
    if path.exists():
        return path
    if not getattr(sys, 'frozen', False):
        alt = Path('.') / filename
        if alt.exists():
            return alt
    return path


def load_json_file(filename: str) -> dict:
    path = _resource_file(filename)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {filename}: {e}")
        return {}


def save_json_file(filename: str, data: dict):
    path = _resource_file(filename)
    try:
        os.makedirs(path.parent, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Failed to save {filename}: {e}")


LANG_DATA = load_json_file('language.json')
LANGUAGES = LANG_DATA.get('languages', {'en': 'English'})
TRANSLATIONS = LANG_DATA.get('translations', {'en': {}})

SEARCH_ENGINE_URLS = {
    'bing': 'https://www.bing.com/search?q={query}&count=20',
    'baidu': 'https://www.baidu.com/s?wd={query}',
    'google': 'https://www.google.com/search?q={query}',
    'yahoo': 'https://search.yahoo.com/search?p={query}',
    '360': 'https://www.so.com/s?q={query}',
    'sogou': 'https://www.sogou.com/web?query={query}',
    'quark': 'https://quark.sm.cn/s?q={query}',
}

SEARCH_ENGINE_RESULT_SELECTORS = {
    'bing': '#b_results > li.b_algo',
    'baidu': '#content_left > .result',
    'google': '#search .g',
    'yahoo': '#web .algo',
    '360': '.result',
    'sogou': '.results .vrwrap',
    'quark': '.result',
}

CONFIG_KEYS = [
    'language', 'search_engine', 'output_dir',
    'concurrency', 'delay', 'similarity', 'min_para_len', 'dark_mode',
]


def load_config() -> dict:
    data = load_json_file('config.json')
    defaults = {
        'language': 'en',
        'search_engine': 'bing',
        'output_dir': 'downloads',
        'concurrency': 5,
        'delay': 0.5,
        'similarity': 0.85,
        'min_para_len': 50,
        'dark_mode': True,
    }
    for k, v in defaults.items():
        if k not in data:
            data[k] = v
    return data


def save_config(data: dict):
    out = {k: data[k] for k in CONFIG_KEYS if k in data}
    save_json_file('config.json', out)


class LanguageManager:
    _instance = None

    def __init__(self):
        self._lang = 'en'

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_language(self, lang: str):
        if lang in TRANSLATIONS:
            self._lang = lang

    def get_language(self) -> str:
        return self._lang

    def t(self, key: str, **kwargs) -> str:
        text = TRANSLATIONS[self._lang].get(key, TRANSLATIONS['en'].get(key, key))
        if kwargs:
            try:
                return text.format(**kwargs)
            except KeyError:
                return text
        return text

    def t_engines(self) -> dict:
        return TRANSLATIONS[self._lang].get('search_engines', TRANSLATIONS['en'].get('search_engines', {}))


LM = LanguageManager.instance()


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self._config = load_config()
        LM.set_language(self._config.get('language', 'en'))

        self.setWindowTitle(LM.t('app_title'))
        self.resize(1100, 750)
        self.setMinimumSize(900, 600)

        self._worker = NovelWorker.instance()
        self._novel_info: NovelInfo | None = None
        self._all_chapters: list[tuple[ChapterInfo, str, bool]] = []
        self._composed_file: str = ''
        self._lang_combo: QComboBox | None = None
        self._engine_combo: QComboBox | None = None

        self._setup_ui()
        self._connect_signals()
        self._load_settings_into_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        header_layout = QHBoxLayout()
        self._title_label = QLabel(LM.t('header_title'))
        self._title_label.setStyleSheet('font-size: 20px; font-weight: bold; color: #89b4fa; padding: 4px 0;')
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()

        self._theme_btn = QPushButton(LM.t('theme_btn'))
        self._theme_btn.setFixedWidth(100)
        header_layout.addWidget(self._theme_btn)

        self._about_btn = QPushButton(LM.t('about_btn'))
        self._about_btn.setFixedWidth(80)
        self._about_btn.clicked.connect(self._on_show_about)
        header_layout.addWidget(self._about_btn)

        main_layout.addLayout(header_layout)

        self._tab_widget = QTabWidget()

        self._search_tab = self._create_search_tab()
        self._tab_widget.addTab(self._search_tab, LM.t('tab_search'))

        self._download_tab = self._create_download_tab()
        self._tab_widget.addTab(self._download_tab, LM.t('tab_download'))

        self._preview_tab = self._create_preview_tab()
        self._tab_widget.addTab(self._preview_tab, LM.t('tab_preview'))

        self._settings_tab = self._create_settings_tab()
        self._tab_widget.addTab(self._settings_tab, LM.t('tab_settings'))

        main_layout.addWidget(self._tab_widget)

        self._status_label = QLabel(LM.t('status_ready'))
        self._status_label.setStyleSheet('color: #a6adc8; padding: 4px; font-size: 12px;')
        main_layout.addWidget(self._status_label)

    def _create_search_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        search_layout = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(LM.t('search_placeholder'))
        self._search_input.setMinimumHeight(36)
        self._search_input.returnPressed.connect(self._on_search)
        search_layout.addWidget(self._search_input, 3)

        self._search_btn = QPushButton(LM.t('search_btn'))
        self._search_btn.setObjectName('searchBtn')
        self._search_btn.setMinimumHeight(36)
        self._search_btn.setMinimumWidth(90)
        self._search_btn.clicked.connect(self._on_search)
        search_layout.addWidget(self._search_btn)
        layout.addLayout(search_layout)

        url_layout = QHBoxLayout()
        self._direct_url_input = QLineEdit()
        self._direct_url_input.setPlaceholderText(LM.t('url_placeholder'))
        self._direct_url_input.setMinimumHeight(32)
        url_layout.addWidget(self._direct_url_input, 3)

        self._url_btn = QPushButton(LM.t('url_btn'))
        self._url_btn.setObjectName('searchBtn')
        self._url_btn.setMinimumHeight(32)
        self._url_btn.setMinimumWidth(90)
        self._url_btn.clicked.connect(self._on_direct_url)
        url_layout.addWidget(self._url_btn)
        layout.addLayout(url_layout)

        self._source_status_label = QLabel('')
        self._source_status_label.setStyleSheet('color: #a6adc8; font-size: 12px; padding: 2px 0;')
        self._source_status_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._source_status_label)

        self._results_table = QTableWidget()
        self._results_table.setColumnCount(5)
        self._results_table.setHorizontalHeaderLabels([
            LM.t('col_title'), LM.t('col_author'), LM.t('col_latest'),
            LM.t('col_source'), LM.t('col_url'),
        ])
        self._results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._results_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._results_table.setAlternatingRowColors(True)
        self._results_table.horizontalHeader().setStretchLastSection(True)
        self._results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._results_table.doubleClicked.connect(self._on_result_double_click)
        layout.addWidget(self._results_table, 1)

        btn_layout = QHBoxLayout()
        self._fetch_info_btn = QPushButton(LM.t('fetch_info_btn'))
        self._fetch_info_btn.setObjectName('downloadBtn')
        self._fetch_info_btn.setEnabled(False)
        self._fetch_info_btn.clicked.connect(self._on_fetch_info)
        btn_layout.addWidget(self._fetch_info_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self._info_display = QTextEdit()
        self._info_display.setReadOnly(True)
        self._info_display.setMaximumHeight(150)
        self._info_display.setPlaceholderText(LM.t('fetch_info_hint'))
        layout.addWidget(self._info_display)

        return tab

    def _create_download_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        info_layout = QHBoxLayout()
        self._dl_novel_label = QLabel(LM.t('no_novel_selected'))
        self._dl_novel_label.setStyleSheet('font-size: 15px; font-weight: bold; color: #f5c2e7;')
        info_layout.addWidget(self._dl_novel_label)
        info_layout.addStretch()
        self._dl_chapter_count = QLabel('')
        info_layout.addWidget(self._dl_chapter_count)
        layout.addLayout(info_layout)

        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(0)
        layout.addWidget(self._progress_bar)

        self._progress_label = QLabel(LM.t('wait_download'))
        self._progress_label.setStyleSheet('color: #a6adc8;')
        layout.addWidget(self._progress_label)

        chapter_select_layout = QHBoxLayout()
        chapter_select_layout.addWidget(QLabel(LM.t('label_chapter_range')))

        self._chapter_start = QSpinBox()
        self._chapter_start.setMinimum(1)
        self._chapter_start.setMaximum(99999)
        self._chapter_start.setValue(1)
        self._chapter_start.setMinimumWidth(70)
        chapter_select_layout.addWidget(self._chapter_start)

        chapter_select_layout.addWidget(QLabel(LM.t('label_to')))

        self._chapter_end = QSpinBox()
        self._chapter_end.setMinimum(0)
        self._chapter_end.setMaximum(99999)
        self._chapter_end.setValue(0)
        self._chapter_end.setMinimumWidth(70)
        self._chapter_end.setSpecialValueText(LM.t('label_all'))
        chapter_select_layout.addWidget(self._chapter_end)

        chapter_select_layout.addStretch()

        self._download_btn = QPushButton(LM.t('download_btn'))
        self._download_btn.setObjectName('downloadBtn')
        self._download_btn.setMinimumHeight(36)
        self._download_btn.clicked.connect(self._on_download)
        self._download_btn.setEnabled(False)
        chapter_select_layout.addWidget(self._download_btn)

        self._stop_btn = QPushButton(LM.t('stop_btn'))
        self._stop_btn.setObjectName('stopBtn')
        self._stop_btn.setMinimumHeight(36)
        self._stop_btn.clicked.connect(self._on_stop)
        self._stop_btn.setEnabled(False)
        chapter_select_layout.addWidget(self._stop_btn)

        self._retry_btn = QPushButton(LM.t('retry_btn'))
        self._retry_btn.setObjectName('searchBtn')
        self._retry_btn.setMinimumHeight(36)
        self._retry_btn.clicked.connect(self._on_retry_failed)
        self._retry_btn.setEnabled(False)
        chapter_select_layout.addWidget(self._retry_btn)

        layout.addLayout(chapter_select_layout)

        self._chapter_listwidget = QListWidget()
        self._chapter_listwidget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self._chapter_listwidget, 1)

        compose_layout = QHBoxLayout()
        self._compose_btn = QPushButton(LM.t('compose_btn'))
        self._compose_btn.setObjectName('downloadBtn')
        self._compose_btn.setMinimumHeight(36)
        self._compose_btn.clicked.connect(self._on_compose)
        self._compose_btn.setEnabled(False)
        compose_layout.addWidget(self._compose_btn)

        self._save_path_label = QLabel('')
        self._save_path_label.setStyleSheet('color: #a6e3a1;')
        compose_layout.addWidget(self._save_path_label, 1)
        layout.addLayout(compose_layout)

        return tab

    def _create_preview_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self._preview_info_label = QLabel(LM.t('preview_info_placeholder'))
        toolbar.addWidget(self._preview_info_label)
        toolbar.addStretch()

        self._open_file_btn = QPushButton(LM.t('open_file_btn'))
        self._open_file_btn.clicked.connect(self._on_open_file)
        toolbar.addWidget(self._open_file_btn)

        self._refresh_btn = QPushButton(LM.t('refresh_btn'))
        self._refresh_btn.clicked.connect(self._on_refresh_preview)
        toolbar.addWidget(self._refresh_btn)
        layout.addLayout(toolbar)

        self._preview_edit = QPlainTextEdit()
        self._preview_edit.setReadOnly(True)
        self._preview_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._preview_edit.setPlaceholderText(LM.t('preview_placeholder'))
        layout.addWidget(self._preview_edit, 1)

        return tab

    def _create_settings_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._settings_scroll = QScrollArea()
        layout.addWidget(self._settings_scroll)
        self._settings_scroll.setWidgetResizable(True)
        self._settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._build_settings_content()
        return tab

    def _build_settings_content(self):
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(16)

        group1 = QGroupBox(LM.t('settings_download'))
        form1 = QFormLayout(group1)
        self._output_dir_edit = QLineEdit(str(Path('downloads').resolve()))
        output_layout = QHBoxLayout()
        output_layout.addWidget(self._output_dir_edit)
        browse_btn = QPushButton(LM.t('browse_btn'))
        browse_btn.clicked.connect(self._on_browse_output)
        output_layout.addWidget(browse_btn)
        form1.addRow(LM.t('settings_output_dir'), output_layout)

        self._concurrency_spin = QSpinBox()
        self._concurrency_spin.setRange(1, 20)
        self._concurrency_spin.setValue(5)
        form1.addRow(LM.t('settings_concurrency'), self._concurrency_spin)

        self._delay_spin = QDoubleSpinBox()
        self._delay_spin.setRange(0.1, 10.0)
        self._delay_spin.setSingleStep(0.1)
        self._delay_spin.setValue(0.5)
        self._delay_spin.setSuffix(' s')
        form1.addRow(LM.t('settings_delay'), self._delay_spin)

        engine_layout = QHBoxLayout()
        self._engine_combo = QComboBox()
        engine_names = LM.t_engines()
        for code in SEARCH_ENGINE_URLS:
            self._engine_combo.addItem(engine_names.get(code, code), code)
        engine_layout.addWidget(self._engine_combo)
        engine_layout.addStretch()
        form1.addRow(LM.t('settings_search_engine'), engine_layout)

        lang_layout = QHBoxLayout()
        self._lang_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self._lang_combo.addItem(name, code)
        self._lang_combo.currentIndexChanged.connect(self._on_language_changed)
        lang_layout.addWidget(self._lang_combo)
        lang_layout.addStretch()
        form1.addRow(LM.t('settings_language'), lang_layout)
        content_layout.addWidget(group1)

        group2 = QGroupBox(LM.t('settings_dedup'))
        form2 = QFormLayout(group2)
        self._similarity_spin = QDoubleSpinBox()
        self._similarity_spin.setRange(0.5, 0.99)
        self._similarity_spin.setSingleStep(0.05)
        self._similarity_spin.setValue(0.85)
        form2.addRow(LM.t('settings_similarity'), self._similarity_spin)

        self._min_para_len = QSpinBox()
        self._min_para_len.setRange(20, 500)
        self._min_para_len.setValue(50)
        self._min_para_len.setSuffix((' chars'))
        form2.addRow(LM.t('settings_min_len'), self._min_para_len)
        content_layout.addWidget(group2)

        group3 = QGroupBox(LM.t('settings_author'))
        author_layout = QVBoxLayout(group3)
        author_layout.addWidget(QLabel(f"{LM.t('settings_name')} Lorime"))
        author_layout.addWidget(QLabel(f"{LM.t('settings_email')} lorime@126.com"))
        content_layout.addWidget(group3)

        group4 = QGroupBox(LM.t('settings_donate'))
        donate_layout = QVBoxLayout(group4)
        donate_layout.addWidget(QLabel(LM.t('settings_donate_desc')))

        base = Path(__file__).parent.parent
        qr_dir = base / 'erweima'

        grid = QGridLayout()
        grid.setSpacing(8)

        def add_qr(row, col, label_text, qr_file):
            lbl = QLabel(label_text)
            lbl.setStyleSheet('font-weight: bold; color: #89b4fa;')
            grid.addWidget(lbl, row, col)
            qr_path = qr_dir / qr_file
            if qr_path.exists():
                pixmap = QPixmap(str(qr_path))
                if not pixmap.isNull():
                    img = QLabel()
                    img.setPixmap(pixmap.scaledToWidth(120, Qt.SmoothTransformation))
                    img.setAlignment(Qt.AlignCenter)
                    grid.addWidget(img, row + 1, col)
                else:
                    grid.addWidget(QLabel(f"({qr_file} load failed)"), row + 1, col)
            else:
                grid.addWidget(QLabel(f"(QR: {qr_file} not found)"), row + 1, col)

        add_qr(0, 0, 'XMR', 'xmr.jpg')
        add_qr(0, 1, 'USDT (TRC20)', 'usdt-tr20.jpg')
        add_qr(0, 2, 'USDT (ERC20)', 'usdt-erc20.jpg')

        donate_layout.addLayout(grid)
        donate_layout.addSpacing(4)

        xmr_addr = QLabel('XMR: 4DSQMNzzq46N1z2pZWAVdeA6JvUL9TCB2bnBiA3ZzoqEdYJnMydt5akCa3vtmapeDsbVKGPFdNkzzqTcJS8M8oyK7WGj5qMvNZRw61w6wMF')
        xmr_addr.setStyleSheet('font-family: monospace; font-size: 10px; color: #a6adc8;')
        donate_layout.addWidget(xmr_addr)

        trc_addr = QLabel('USDT (TRC20): TG6DCBoQszDxc64owRZKkSHqZfcAQrqR8uM')
        trc_addr.setStyleSheet('font-family: monospace; font-size: 10px; color: #a6adc8;')
        donate_layout.addWidget(trc_addr)

        erc_addr = QLabel('USDT (ERC20): 0x4323d39BA9b6Bd0570920e63a8D3a192b4459330')
        erc_addr.setStyleSheet('font-family: monospace; font-size: 10px; color: #a6adc8;')
        donate_layout.addWidget(erc_addr)

        content_layout.addWidget(group4)

        content_layout.addStretch()

        save_layout = QHBoxLayout()
        save_layout.addStretch()
        self._save_settings_btn = QPushButton(LM.t('save_settings_btn'))
        self._save_settings_btn.setObjectName('searchBtn')
        self._save_settings_btn.clicked.connect(self._on_save_settings)
        save_layout.addWidget(self._save_settings_btn)
        content_layout.addLayout(save_layout)

        self._settings_scroll.setWidget(content)

    def _rebuild_ui(self):
        self.setWindowTitle(LM.t('app_title'))
        self._title_label.setText(LM.t('header_title'))
        self._tab_widget.setTabText(0, LM.t('tab_search'))
        self._tab_widget.setTabText(1, LM.t('tab_download'))
        self._tab_widget.setTabText(2, LM.t('tab_preview'))
        self._tab_widget.setTabText(3, LM.t('tab_settings'))
        self._theme_btn.setText(LM.t('theme_btn'))
        self._about_btn.setText(LM.t('about_btn'))

        self._search_input.setPlaceholderText(LM.t('search_placeholder'))
        self._search_btn.setText(LM.t('search_btn'))
        self._direct_url_input.setPlaceholderText(LM.t('url_placeholder'))
        self._url_btn.setText(LM.t('url_btn'))

        self._results_table.setHorizontalHeaderLabels([
            LM.t('col_title'), LM.t('col_author'), LM.t('col_latest'),
            LM.t('col_source'), LM.t('col_url'),
        ])

        self._fetch_info_btn.setText(LM.t('fetch_info_btn'))
        self._info_display.setPlaceholderText(LM.t('fetch_info_hint'))

        self._dl_novel_label.setText(LM.t('no_novel_selected'))
        self._progress_label.setText(LM.t('wait_download'))
        self._download_btn.setText(LM.t('download_btn'))
        self._stop_btn.setText(LM.t('stop_btn'))
        self._retry_btn.setText(LM.t('retry_btn'))
        self._compose_btn.setText(LM.t('compose_btn'))

        self._preview_info_label.setText(LM.t('preview_info_placeholder'))
        self._preview_edit.setPlaceholderText(LM.t('preview_placeholder'))
        self._open_file_btn.setText(LM.t('open_file_btn'))
        self._refresh_btn.setText(LM.t('refresh_btn'))

        old_engine = self._get_engine_code()
        old_lang = self._get_lang_code()
        self._build_settings_content()
        self._engine_combo.blockSignals(True)
        self._lang_combo.blockSignals(True)
        self._load_settings_into_ui()
        self._set_engine_code(old_engine)
        self._set_lang_code(old_lang)
        self._engine_combo.blockSignals(False)
        self._lang_combo.blockSignals(False)

    def _get_engine_code(self) -> str:
        if self._engine_combo:
            return self._engine_combo.currentData() or 'bing'
        return self._config.get('search_engine', 'bing')

    def _set_engine_code(self, code: str):
        if self._engine_combo:
            for i in range(self._engine_combo.count()):
                if self._engine_combo.itemData(i) == code:
                    self._engine_combo.setCurrentIndex(i)
                    return

    def _get_lang_code(self) -> str:
        if self._lang_combo:
            return self._lang_combo.currentData() or 'en'
        return self._config.get('language', 'en')

    def _set_lang_code(self, code: str):
        if self._lang_combo:
            for i in range(self._lang_combo.count()):
                if self._lang_combo.itemData(i) == code:
                    self._lang_combo.setCurrentIndex(i)
                    return

    def _load_settings_into_ui(self):
        cfg = self._config
        self._output_dir_edit.setText(str(cfg.get('output_dir', 'downloads')))
        self._concurrency_spin.setValue(cfg.get('concurrency', 5))
        self._delay_spin.setValue(cfg.get('delay', 0.5))
        self._similarity_spin.setValue(cfg.get('similarity', 0.85))
        self._min_para_len.setValue(cfg.get('min_para_len', 50))
        self._set_engine_code(cfg.get('search_engine', 'bing'))
        self._set_lang_code(cfg.get('language', 'en'))

    def _collect_settings(self) -> dict:
        return {
            'language': self._get_lang_code(),
            'search_engine': self._get_engine_code(),
            'output_dir': self._output_dir_edit.text(),
            'concurrency': self._concurrency_spin.value(),
            'delay': self._delay_spin.value(),
            'similarity': self._similarity_spin.value(),
            'min_para_len': self._min_para_len.value(),
            'dark_mode': self._config.get('dark_mode', True),
        }

    def _connect_signals(self):
        w = self._worker

        w.log_message.connect(self._on_log_message)
        w.source_status.connect(self._on_source_status)
        w.search_finished.connect(self._on_search_finished)
        w.search_error.connect(self._on_search_error)
        w.novel_info_ready.connect(self._on_novel_info_ready)
        w.novel_info_error.connect(self._on_novel_info_error)
        w.download_progress.connect(self._on_download_progress)
        w.download_finished.connect(self._on_download_finished)
        w.redownload_finished.connect(self._on_redownload_finished)
        w.download_error.connect(self._on_download_error)
        w.download_cancelled.connect(self._on_download_cancelled)
        w.compose_finished.connect(self._on_compose_finished)
        w.compose_error.connect(self._on_compose_error)

    @Slot()
    def _on_search(self):
        keyword = self._search_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, LM.t('msg_title_hint'), LM.t('msg_input_keyword'))
            return
        self._search_btn.setEnabled(False)
        self._results_table.setRowCount(0)
        self._info_display.clear()
        self._fetch_info_btn.setEnabled(False)
        self._source_status_label.setText('')
        engine_code = self._get_engine_code()
        engine_name = LM.t_engines().get(engine_code, engine_code)
        self._status_label.setText(LM.t('searching_engine', keyword=keyword))
        self._worker._emit_log(LM.t('searching_log', engine=engine_name, keyword=keyword))
        self._worker.search(keyword, engine_code)

    @Slot(list)
    def _on_search_finished(self, results: list):
        self._search_btn.setEnabled(True)
        self._status_label.setText(LM.t('search_found', count=len(results)))
        self._results_table.setRowCount(0)
        for r in results:
            row = self._results_table.rowCount()
            self._results_table.insertRow(row)
            self._results_table.setItem(row, 0, QTableWidgetItem(r.title))
            self._results_table.setItem(row, 1, QTableWidgetItem(r.author))
            self._results_table.setItem(row, 2, QTableWidgetItem(r.latest_chapter))
            self._results_table.setItem(row, 3, QTableWidgetItem(r.source))
            self._results_table.setItem(row, 4, QTableWidgetItem(r.url))
        self._results_table.selectRow(0)
        self._fetch_info_btn.setEnabled(len(results) > 0)
        if not results:
            existing = self._source_status_label.text()
            no_match = LM.t('no_match_result')
            self._source_status_label.setText(
                f'{existing} <span style="color:#f9e2af">{no_match}</span>'
            )

    @Slot(str)
    def _on_search_error(self, error: str):
        self._search_btn.setEnabled(True)
        self._source_status_label.setText('')
        self._status_label.setText(LM.t('search_failed_status', error=error))
        QMessageBox.critical(self, LM.t('search_error_title'),
                             LM.t('search_error_content', error=error))

    @Slot(int, int, int, str)
    def _on_source_status(self, reachable: int, unreachable: int, total: int, method: str):
        engine_code = self._get_engine_code()
        engine_name = LM.t_engines().get(engine_code, engine_code)
        if '浏览器' in method or 'browser' in method.lower() or 'engine' in method.lower():
            self._source_status_label.setText(
                f'<span style="color:#a6e3a1">{LM.t("source_status_browser", engine=engine_name)}</span>'
            )
            return
        color = '#a6e3a1' if reachable > 0 else '#f38ba8'
        if reachable > 0:
            self._source_status_label.setText(
                f'{LM.t("source_status_reachable", reachable=reachable, unreachable=unreachable, total=total)}'
            )
        else:
            self._source_status_label.setText(
                f'<span style="color:#f38ba8">{LM.t("source_status_none", total=total)}</span>'
            )

    @Slot()
    def _on_direct_url(self):
        url = self._direct_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, LM.t('msg_title_hint'), LM.t('msg_paste_url'))
            return
        if not url.startswith('http'):
            url = 'https://' + url
            self._direct_url_input.setText(url)
        self._url_btn.setEnabled(False)
        self._status_label.setText(LM.t('fetching_info'))
        self._worker.fetch_novel_info(url, '')

    @Slot()
    def _on_result_double_click(self):
        self._on_fetch_info()

    @Slot()
    def _on_fetch_info(self):
        row = self._results_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, LM.t('msg_title_hint'), LM.t('msg_select_novel'))
            return
        url = self._results_table.item(row, 4).text()
        source = self._results_table.item(row, 3).text()

        self._fetch_info_btn.setEnabled(False)
        self._status_label.setText(LM.t('fetching_info'))
        self._worker.fetch_novel_info(url, source)

    @Slot(object)
    def _on_novel_info_ready(self, info: NovelInfo):
        self._fetch_info_btn.setEnabled(True)
        self._url_btn.setEnabled(True)
        self._novel_info = info
        self._status_label.setText(LM.t('info_fetched', title=info.title, count=len(info.chapters)))

        clean_intro = ''
        if info.description:
            clean_intro = NovelCleaner.clean_content(info.description)[:300]
        info_text = LM.t('info_template',
                         title=info.title, author=info.author,
                         count=len(info.chapters), intro=clean_intro)
        self._info_display.setPlainText(info_text)

        self._dl_novel_label.setText(f'📖 《{info.title}》')
        self._dl_chapter_count.setText(str(len(info.chapters)))
        self._chapter_listwidget.clear()
        for ch in info.chapters:
            item = QListWidgetItem(f'[{ch.index + 1}] {ch.title}')
            item.setData(Qt.ItemDataRole.UserRole, ch)
            self._chapter_listwidget.addItem(item)

        self._chapter_end.setMaximum(len(info.chapters))
        self._chapter_end.setValue(len(info.chapters))
        self._download_btn.setEnabled(True)
        self._tab_widget.setCurrentIndex(1)

    @Slot(str)
    def _on_novel_info_error(self, error: str):
        self._fetch_info_btn.setEnabled(True)
        self._url_btn.setEnabled(True)
        self._status_label.setText(LM.t('info_fetch_error', error=error))
        QMessageBox.critical(self, LM.t('info_fetch_error_title'), error)

    @Slot()
    def _on_download(self):
        if not self._novel_info:
            return
        chapters = self._novel_info.chapters
        start = self._chapter_start.value() - 1
        end = self._chapter_end.value()
        if end <= 0 or end > len(chapters):
            end = len(chapters)
        if start >= end:
            QMessageBox.warning(self, LM.t('msg_title_hint'), LM.t('msg_chapter_range_invalid'))
            return
        selected = chapters[start:end]

        self._download_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._compose_btn.setEnabled(False)
        self._progress_bar.setValue(0)
        self._progress_label.setText(LM.t('prep_download', count=len(selected)))
        self._save_path_label.clear()
        self._all_chapters = []
        self._composed_file = ''

        self._worker._crawler = None
        source = self._worker._current_source
        if source:
            from engine.crawler import NovelCrawler
            concurrency = self._concurrency_spin.value()
            delay = self._delay_spin.value()
            self._worker._crawler = NovelCrawler(source=source, concurrency=concurrency, delay=delay)
        self._status_label.setText(LM.t('downloading_status', count=len(selected)))
        self._worker.download_chapters(selected)

    @Slot(int, int, str)
    def _on_download_progress(self, completed: int, total: int, chapter_title: str):
        pct = int(completed / total * 100) if total > 0 else 0
        self._progress_bar.setValue(pct)
        self._progress_label.setText(LM.t('download_progress_label', completed=completed, total=total, title=chapter_title))

    @Slot(list, list)
    def _on_download_finished(self, success: list, failed: list):
        self._download_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

        success_count = len(success)
        fail_count = len(failed)

        self._progress_bar.setValue(100)
        self._progress_label.setText(LM.t('download_complete', success=success_count, failed=fail_count))
        self._status_label.setText(LM.t('download_result_status', success=success_count, total=success_count + fail_count))

        success_dict = {ch.index: content for ch, content in success}

        if self._novel_info:
            self._all_chapters = []
            for ch in self._novel_info.chapters:
                content = success_dict.get(ch.index, '')
                is_success = ch.index in success_dict
                self._all_chapters.append((ch, content, is_success))
        else:
            self._all_chapters = [(ch, content, True) for ch, content in success]
            for ch, error in failed:
                self._all_chapters.append((ch, '', False))

        self._update_chapter_list()

        if fail_count > 0:
            self._retry_btn.setEnabled(True)
            self._retry_btn.setToolTip(LM.t('retry_btn_tooltip', count=fail_count))
        else:
            self._retry_btn.setEnabled(False)

        self._compose_btn.setEnabled(success_count > 0)

    def _update_chapter_list(self):
        self._chapter_listwidget.clear()
        for ch_info, content, is_success in self._all_chapters:
            if is_success:
                status = '✅' if content and len(content.strip()) > 50 else '⚠️'
                item = QListWidgetItem(f'{status} [{ch_info.index + 1}] {ch_info.title}')
                item.setData(Qt.ItemDataRole.UserRole, (ch_info, content))
            else:
                item = QListWidgetItem(f'❌ [{ch_info.index + 1}] {ch_info.title}')
                item.setData(Qt.ItemDataRole.UserRole, (ch_info, None))
                item.setForeground(QColor('#f38ba8'))
            self._chapter_listwidget.addItem(item)

    @Slot(str)
    def _on_download_error(self, error: str):
        self._download_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._status_label.setText(LM.t('download_error_status', error=error))

    @Slot()
    def _on_download_cancelled(self):
        self._download_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

    @Slot()
    def _on_stop(self):
        self._worker.cancel_all()
        self._stop_btn.setEnabled(False)
        self._status_label.setText(LM.t('status_cancelling'))

    @Slot()
    def _on_retry_failed(self):
        failed_items = [(ch, '') for ch, content, is_success in self._all_chapters if not is_success]
        if not failed_items:
            return

        self._retry_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._progress_bar.setValue(0)
        self._progress_label.setText(LM.t('retry_progress', count=len(failed_items)))
        self._status_label.setText(LM.t('retry_status', count=len(failed_items)))

        self._worker.redownload_failed(failed_items)

    @Slot(list, list)
    def _on_redownload_finished(self, success: list, failed: list):
        self._stop_btn.setEnabled(False)

        success_count = len(success)
        fail_count = len(failed)

        for ch, content in success:
            for i, (info, old_content, is_success) in enumerate(self._all_chapters):
                if info.index == ch.index:
                    self._all_chapters[i] = (ch, content, True)
                    break

        failed_indices = {ch.index for ch, error in failed}
        for i, (info, content, is_success) in enumerate(self._all_chapters):
            if info.index in failed_indices and is_success:
                self._all_chapters[i] = (info, content, False)

        self._update_chapter_list()

        if fail_count > 0:
            self._retry_btn.setEnabled(True)
            self._retry_btn.setToolTip(LM.t('retry_btn_tooltip', count=fail_count))
        else:
            self._retry_btn.setEnabled(False)

        total_success = sum(1 for _, _, s in self._all_chapters if s)
        self._compose_btn.setEnabled(total_success > 0)

        self._progress_bar.setValue(100)
        self._progress_label.setText(LM.t('retry_result', success=success_count, failed=fail_count))
        self._status_label.setText(LM.t('retry_status_final', success=total_success, total=len(self._all_chapters)))

    @Slot()
    def _on_compose(self):
        if not self._novel_info or not self._all_chapters:
            return
        valid_chapters = []
        for ch, content, is_success in self._all_chapters:
            if is_success and content and len(content.strip()) >= self._min_para_len.value():
                valid_chapters.append((ch, content))
        if not valid_chapters:
            QMessageBox.warning(self, LM.t('msg_title_hint'), LM.t('msg_no_content_compose'))
            return
        NovelCleaner.SIMILARITY_THRESHOLD = self._similarity_spin.value()

        output_dir = self._output_dir_edit.text() or 'downloads'
        self._compose_btn.setEnabled(False)
        self._status_label.setText(LM.t('composing_status'))
        self._worker.compose_novel(
            self._novel_info.title,
            self._novel_info.author,
            valid_chapters,
            self._novel_info.description,
            output_dir,
        )

    @Slot(str, str)
    def _on_compose_finished(self, filepath: str, title: str):
        self._compose_btn.setEnabled(True)
        self._composed_file = filepath
        self._save_path_label.setText(LM.t('compose_saved', filepath=filepath))
        self._status_label.setText(LM.t('compose_exported', filepath=filepath))

        self._preview_info_label.setText(LM.t('preview_file_label', title=title, filepath=filepath))
        self._load_preview(filepath)
        self._tab_widget.setCurrentIndex(2)

    @Slot(str)
    def _on_compose_error(self, error: str):
        self._compose_btn.setEnabled(True)
        self._status_label.setText(LM.t('compose_fail_status', error=error))

    def _load_preview(self, filepath: str):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read(50000)
            self._preview_edit.setPlainText(content)
        except Exception as e:
            self._preview_edit.setPlainText(LM.t('preview_load_fail', error=str(e)))

    @Slot()
    def _on_open_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, LM.t('open_txt_title'), '', LM.t('open_txt_filter')
        )
        if filepath:
            self._composed_file = filepath
            self._preview_info_label.setText(LM.t('preview_file_label', title='', filepath=filepath))
            self._load_preview(filepath)

    @Slot()
    def _on_refresh_preview(self):
        if self._composed_file:
            self._load_preview(self._composed_file)

    @Slot(int)
    def _on_language_changed(self, index: int):
        code = self._lang_combo.currentData()
        if code and code != LM.get_language():
            LM.set_language(code)
            self._config['language'] = code
            save_config(self._config)
            self._rebuild_ui()

    @Slot()
    def _on_browse_output(self):
        dir_path = QFileDialog.getExistingDirectory(self, LM.t('browse_output_title'))
        if dir_path:
            self._output_dir_edit.setText(dir_path)

    @Slot()
    def _on_save_settings(self):
        self._config.update(self._collect_settings())
        save_config(self._config)
        QMessageBox.information(self, LM.t('save_settings_btn'), LM.t('msg_save_settings'))
        self._status_label.setText(LM.t('msg_save_settings'))

    @Slot(str)
    def _on_log_message(self, msg: str):
        timestamp = datetime.now().strftime('%H:%M:%S')
        self._status_label.setText(f'[{timestamp}] {msg}')

    @Slot()
    def _on_show_about(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(LM.t('about_title'))
        dialog.setMinimumSize(520, 420)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        title = QLabel(LM.t('app_title'))
        title.setStyleSheet('font-size: 18px; font-weight: bold; color: #89b4fa;')
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        donate_label = QLabel(LM.t('about_donate'))
        donate_label.setStyleSheet('font-weight: bold; color: #89b4fa;')
        layout.addWidget(donate_label)

        donate_desc = QLabel(LM.t('about_donate_desc'))
        donate_desc.setStyleSheet('color: #a6adc8;')
        layout.addWidget(donate_desc)

        base = Path(__file__).parent.parent
        qr_dir = base / 'erweima'

        qr_grid = QGridLayout()
        qr_grid.setSpacing(8)

        def add_qr_col(col, label_text, qr_file):
            lbl = QLabel(label_text)
            lbl.setStyleSheet('font-weight: bold; color: #cdd6f4; font-size: 12px;')
            lbl.setAlignment(Qt.AlignCenter)
            qr_grid.addWidget(lbl, 0, col)
            qr_path = qr_dir / qr_file
            if qr_path.exists():
                pixmap = QPixmap(str(qr_path))
                if not pixmap.isNull():
                    img = QLabel()
                    img.setPixmap(pixmap.scaledToWidth(140, Qt.SmoothTransformation))
                    img.setAlignment(Qt.AlignCenter)
                    qr_grid.addWidget(img, 1, col)
                else:
                    qr_grid.addWidget(QLabel(LM.t('label_qr_load_fail')), 1, col)
            else:
                qr_grid.addWidget(QLabel(LM.t('label_qr_not_found')), 1, col)

        add_qr_col(0, LM.t('about_qr_xmr'), 'xmr.jpg')
        add_qr_col(1, LM.t('about_qr_usdt_trc'), 'usdt-tr20.jpg')
        add_qr_col(2, LM.t('about_qr_usdt_erc'), 'usdt-erc20.jpg')

        layout.addLayout(qr_grid)

        addr_style = 'font-family: monospace; font-size: 10px; color: #a6adc8; padding: 2px 0;'
        xmr_addr = QLabel('XMR: 4DSQMNzzq46N1z2pZWAVdeA6JvUL9TCB2bnBiA3ZzoqEdYJnMydt5akCa3vtmapeDsbVKGPFdNkzzqTcJS8M8oyK7WGj5qMvNZRw61w6wMF')
        xmr_addr.setStyleSheet(addr_style)
        layout.addWidget(xmr_addr)

        trc_addr = QLabel('USDT (TRC20): TG6DCBoQszDxc64owRZKkSHqZfcAQrqR8uM')
        trc_addr.setStyleSheet(addr_style)
        layout.addWidget(trc_addr)

        erc_addr = QLabel('USDT (ERC20): 0x4323d39BA9b6Bd0570920e63a8D3a192b4459330')
        erc_addr.setStyleSheet(addr_style)
        layout.addWidget(erc_addr)

        layout.addSpacing(8)

        author_title = QLabel(LM.t('about_author'))
        author_title.setStyleSheet('font-weight: bold; color: #89b4fa;')
        layout.addWidget(author_title)

        name_lbl = QLabel(f"{LM.t('about_name')} Lorime")
        name_lbl.setStyleSheet('color: #cdd6f4;')
        layout.addWidget(name_lbl)

        email_lbl = QLabel(f"{LM.t('about_email')} lorime@126.com")
        email_lbl.setStyleSheet('color: #cdd6f4;')
        layout.addWidget(email_lbl)

        layout.addStretch()

        close_btn = QPushButton(LM.t('about_ok'))
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(dialog.accept)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        dialog.setLayout(layout)
        dialog.exec()

    def closeEvent(self, event):
        self._worker.cancel_all()
        QThreadPool.globalInstance().waitForDone(3000)
        super().closeEvent(event)