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
    QComboBox, QDialog, QScrollArea, QGridLayout, QCheckBox,
    QSlider, QDialogButtonBox,
)
from PySide6.QtCore import Qt, QTimer, Slot, QSize, QThreadPool, QUrl, Signal
from PySide6.QtGui import QFont, QIcon, QColor, QPixmap

from sources.base import SearchResult, NovelInfo, ChapterInfo
from sources.generic import GenericSource
from engine.cleaner import NovelCleaner
from engine.novel_processor import NovelProcessor
from engine.exporter import export_epub, export_html
from engine.bookshelf import BookshelfManager, TAG_CATEGORIES
from engine.tts_player import TTSPlayer
from engine.updater import UpdateChecker
from engine.plugin_manager import PluginManager
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
    'search_history', 'favorites',
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
        'search_history': [],
        'favorites': [],
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


class BookshelfDropList(QListWidget):

    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                fp = url.toLocalFile()
                if fp.lower().endswith(('.txt', '.epub')):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            fp = url.toLocalFile()
            if fp.lower().endswith(('.txt', '.epub')):
                self.file_dropped.emit(fp)


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

        self._bookshelf = BookshelfManager()
        self._tts_player = TTSPlayer(self)
        self._tts_player.state_changed.connect(self._on_tts_state_changed)
        self._plugin_manager = PluginManager()
        self._update_checker = UpdateChecker()

        self._setup_ui()
        self._connect_signals()
        self._load_settings_into_ui()
        self._refresh_favorites_list()
        self._refresh_history_combo()

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

        self._bookshelf_tab = self._create_bookshelf_tab()
        self._tab_widget.addTab(self._bookshelf_tab, LM.t('tab_bookshelf'))

        self._plugin_tab = self._create_plugin_tab()
        self._tab_widget.addTab(self._plugin_tab, LM.t('tab_plugins'))

        main_layout.addWidget(self._tab_widget)

        self._status_label = QLabel(LM.t('status_ready'))
        self._status_label.setStyleSheet('color: #a6adc8; padding: 4px; font-size: 12px;')
        main_layout.addWidget(self._status_label)

        QTimer.singleShot(2000, self._check_for_updates)

    def _create_search_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        search_layout = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(LM.t('search_placeholder'))
        self._search_input.returnPressed.connect(self._on_search)
        self._search_input.setMinimumHeight(36)

        self._history_combo = QComboBox()
        self._history_combo.setMinimumHeight(36)
        self._history_combo.setEditable(False)
        self._history_combo.setMinimumWidth(40)
        self._history_combo.currentTextChanged.connect(self._on_history_selected)
        search_layout.addWidget(self._history_combo)

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

        self._fav_btn = QPushButton(LM.t('fav_add_btn'))
        self._fav_btn.setObjectName('searchBtn')
        self._fav_btn.clicked.connect(self._on_add_favorite)
        btn_layout.addWidget(self._fav_btn)
        layout.addLayout(btn_layout)

        bottom_split = QHBoxLayout()
        bottom_split.setSpacing(8)

        info_col = QVBoxLayout()
        self._info_display = QTextEdit()
        self._info_display.setReadOnly(True)
        self._info_display.setPlaceholderText(LM.t('fetch_info_hint'))
        info_col.addWidget(self._info_display)
        bottom_split.addLayout(info_col, 1)

        fav_col = QVBoxLayout()
        fav_header = QHBoxLayout()
        fav_header.addWidget(QLabel(LM.t('favorites_label')))

        self._fav_remove_btn = QPushButton(LM.t('fav_remove_btn'))
        self._fav_remove_btn.setFixedWidth(80)
        self._fav_remove_btn.clicked.connect(self._on_remove_favorite)
        fav_header.addWidget(self._fav_remove_btn)

        self._fav_open_btn = QPushButton(LM.t('fav_open_btn'))
        self._fav_open_btn.setFixedWidth(80)
        self._fav_open_btn.setObjectName('searchBtn')
        self._fav_open_btn.clicked.connect(self._on_open_favorite)
        fav_header.addWidget(self._fav_open_btn)
        fav_col.addLayout(fav_header)

        self._fav_list = QListWidget()
        self._fav_list.doubleClicked.connect(self._on_open_favorite)
        fav_col.addWidget(self._fav_list)
        bottom_split.addLayout(fav_col, 1)

        layout.addLayout(bottom_split)

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

        self._sel_all_btn = QPushButton(LM.t('select_all_btn'))
        self._sel_all_btn.setFixedWidth(70)
        self._sel_all_btn.clicked.connect(lambda: self._select_chapters(True))
        chapter_select_layout.addWidget(self._sel_all_btn)

        self._sel_none_btn = QPushButton(LM.t('select_none_btn'))
        self._sel_none_btn.setFixedWidth(70)
        self._sel_none_btn.clicked.connect(lambda: self._select_chapters(False))
        chapter_select_layout.addWidget(self._sel_none_btn)

        self._sel_invert_btn = QPushButton(LM.t('select_invert_btn'))
        self._sel_invert_btn.setFixedWidth(70)
        self._sel_invert_btn.clicked.connect(self._invert_chapters)
        chapter_select_layout.addWidget(self._sel_invert_btn)

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
        outer = QVBoxLayout(tab)
        outer.setSpacing(8)

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

        self._export_epub_btn = QPushButton(LM.t('export_epub_btn'))
        self._export_epub_btn.clicked.connect(self._on_export_epub)
        toolbar.addWidget(self._export_epub_btn)

        self._export_html_btn = QPushButton(LM.t('export_html_btn'))
        self._export_html_btn.clicked.connect(self._on_export_html)
        toolbar.addWidget(self._export_html_btn)
        outer.addLayout(toolbar)

        tts_layout = QHBoxLayout()
        self._tts_play_btn = QPushButton(LM.t('tts_play'))
        self._tts_play_btn.setObjectName('searchBtn')
        self._tts_play_btn.setFixedWidth(60)
        self._tts_play_btn.clicked.connect(self._on_tts_play)
        tts_layout.addWidget(self._tts_play_btn)

        self._tts_pause_btn = QPushButton(LM.t('tts_pause'))
        self._tts_pause_btn.setFixedWidth(60)
        self._tts_pause_btn.clicked.connect(self._on_tts_pause)
        tts_layout.addWidget(self._tts_pause_btn)

        self._tts_stop_btn = QPushButton(LM.t('tts_stop'))
        self._tts_stop_btn.setFixedWidth(60)
        self._tts_stop_btn.clicked.connect(self._on_tts_stop)
        tts_layout.addWidget(self._tts_stop_btn)

        tts_layout.addWidget(QLabel(LM.t('tts_rate')))
        self._tts_rate_slider = QSlider(Qt.Orientation.Horizontal)
        self._tts_rate_slider.setRange(-10, 10)
        self._tts_rate_slider.setValue(0)
        self._tts_rate_slider.setFixedWidth(100)
        self._tts_rate_slider.valueChanged.connect(self._on_tts_rate_changed)
        tts_layout.addWidget(self._tts_rate_slider)

        tts_layout.addWidget(QLabel(LM.t('tts_pitch')))
        self._tts_pitch_slider = QSlider(Qt.Orientation.Horizontal)
        self._tts_pitch_slider.setRange(-10, 10)
        self._tts_pitch_slider.setValue(0)
        self._tts_pitch_slider.setFixedWidth(100)
        self._tts_pitch_slider.valueChanged.connect(self._on_tts_pitch_changed)
        tts_layout.addWidget(self._tts_pitch_slider)

        tts_layout.addWidget(QLabel(LM.t('tts_volume')))
        self._tts_volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._tts_volume_slider.setRange(0, 10)
        self._tts_volume_slider.setValue(10)
        self._tts_volume_slider.setFixedWidth(100)
        self._tts_volume_slider.valueChanged.connect(self._on_tts_volume_changed)
        tts_layout.addWidget(self._tts_volume_slider)

        self._tts_status_label = QLabel('')
        self._tts_status_label.setStyleSheet('color: #a6e3a1; font-size: 12px;')
        tts_layout.addWidget(self._tts_status_label)
        tts_layout.addStretch()
        outer.addLayout(tts_layout)

        self._preview_edit = QPlainTextEdit()
        self._preview_edit.setReadOnly(True)
        self._preview_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._preview_edit.setPlaceholderText(LM.t('preview_placeholder'))
        outer.addWidget(self._preview_edit, 1)

        proc_group = QGroupBox(LM.t('processor_group'))
        proc_layout = QVBoxLayout(proc_group)
        proc_layout.setSpacing(6)

        check_layout = QHBoxLayout()
        self._proc_dedup_cb = QCheckBox(LM.t('processor_dedup'))
        self._proc_dedup_cb.setChecked(True)
        check_layout.addWidget(self._proc_dedup_cb)

        self._proc_ads_cb = QCheckBox(LM.t('processor_ads'))
        self._proc_ads_cb.setChecked(True)
        check_layout.addWidget(self._proc_ads_cb)

        self._proc_format_cb = QCheckBox(LM.t('processor_format'))
        self._proc_format_cb.setChecked(True)
        check_layout.addWidget(self._proc_format_cb)

        self._proc_layout_cb = QCheckBox(LM.t('processor_layout'))
        self._proc_layout_cb.setChecked(True)
        check_layout.addWidget(self._proc_layout_cb)

        self._proc_stats_label = QLabel('')
        self._proc_stats_label.setStyleSheet('color: #a6e3a1; font-size: 12px;')
        check_layout.addWidget(self._proc_stats_label)
        check_layout.addStretch()

        proc_layout.addLayout(check_layout)

        kw_layout = QHBoxLayout()
        kw_layout.addWidget(QLabel('  '))
        self._proc_kw_edit = QLineEdit()
        self._proc_kw_edit.setPlaceholderText(LM.t('processor_delete_kw'))
        self._proc_kw_edit.setToolTip(LM.t('processor_delete_kw'))
        kw_layout.addWidget(self._proc_kw_edit, 1)

        self._proc_kw_mode = QComboBox()
        self._proc_kw_mode.addItem(LM.t('processor_del_line'), 'line')
        self._proc_kw_mode.addItem(LM.t('processor_del_sentence'), 'sentence')
        self._proc_kw_mode.addItem(LM.t('processor_del_keyword'), 'keyword')
        kw_layout.addWidget(self._proc_kw_mode)

        proc_layout.addLayout(kw_layout)

        self._proc_undo_btn = QPushButton(LM.t('processor_undo'))
        self._proc_undo_btn.setEnabled(False)
        self._proc_undo_btn.clicked.connect(self._on_undo_process)
        check_layout.addWidget(self._proc_undo_btn)

        self._proc_run_btn = QPushButton(LM.t('processor_run'))
        self._proc_run_btn.setObjectName('downloadBtn')
        self._proc_run_btn.clicked.connect(self._on_process)
        check_layout.addWidget(self._proc_run_btn)

        self._proc_save_btn = QPushButton(LM.t('processor_save'))
        self._proc_save_btn.setObjectName('searchBtn')
        self._proc_save_btn.setEnabled(False)
        self._proc_save_btn.clicked.connect(self._on_save_processed)
        check_layout.addWidget(self._proc_save_btn)

        proc_layout.addLayout(check_layout)
        outer.addWidget(proc_group)

        self._original_full_text = ''
        self._processed_full_text = ''

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

        update_group = QGroupBox(LM.t('settings_update'))
        update_layout = QVBoxLayout(update_group)
        self._update_status_label = QLabel(LM.t('update_current', version=UpdateChecker.CURRENT_VERSION))
        self._update_status_label.setStyleSheet('color: #a6adc8;')
        update_layout.addWidget(self._update_status_label)
        self._update_check_btn = QPushButton(LM.t('update_check_btn'))
        self._update_check_btn.setObjectName('searchBtn')
        self._update_check_btn.clicked.connect(self._on_check_update_clicked)
        update_layout.addWidget(self._update_check_btn)
        content_layout.addWidget(update_group)

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

    def _create_bookshelf_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self._bs_tag_combo = QComboBox()
        self._bs_tag_combo.addItem(LM.t('bs_tag_all'), '全部')
        for tag in TAG_CATEGORIES:
            self._bs_tag_combo.addItem(tag, tag)
        self._bs_tag_combo.currentIndexChanged.connect(self._on_bs_tag_changed)
        toolbar.addWidget(QLabel(LM.t('bs_tag_label')))
        toolbar.addWidget(self._bs_tag_combo)

        toolbar.addStretch()

        self._bs_add_btn = QPushButton(LM.t('bs_add_btn'))
        self._bs_add_btn.setObjectName('searchBtn')
        self._bs_add_btn.clicked.connect(self._on_bs_add_file)
        toolbar.addWidget(self._bs_add_btn)

        self._bs_remove_btn = QPushButton(LM.t('bs_remove_btn'))
        self._bs_remove_btn.clicked.connect(self._on_bs_remove)
        toolbar.addWidget(self._bs_remove_btn)

        self._bs_open_btn = QPushButton(LM.t('bs_open_btn'))
        self._bs_open_btn.setObjectName('downloadBtn')
        self._bs_open_btn.clicked.connect(self._on_bs_open)
        toolbar.addWidget(self._bs_open_btn)
        layout.addLayout(toolbar)

        self._bs_list = BookshelfDropList()
        self._bs_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._bs_list.file_dropped.connect(self._on_bs_file_dropped)
        self._bs_list.doubleClicked.connect(self._on_bs_open)
        layout.addWidget(self._bs_list, 1)

        self._refresh_bookshelf()
        return tab

    def _create_plugin_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self._pl_install_btn = QPushButton(LM.t('pl_install'))
        self._pl_install_btn.setObjectName('searchBtn')
        self._pl_install_btn.clicked.connect(self._on_pl_install)
        toolbar.addWidget(self._pl_install_btn)

        self._pl_remove_btn = QPushButton(LM.t('pl_remove'))
        self._pl_remove_btn.clicked.connect(self._on_pl_remove)
        toolbar.addWidget(self._pl_remove_btn)

        self._pl_create_sample_btn = QPushButton(LM.t('pl_create_sample'))
        self._pl_create_sample_btn.clicked.connect(self._on_pl_create_sample)
        toolbar.addWidget(self._pl_create_sample_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._pl_list = QListWidget()
        layout.addWidget(self._pl_list, 1)

        self._refresh_plugins()
        return tab

    def _rebuild_ui(self):
        self.setWindowTitle(LM.t('app_title'))
        self._title_label.setText(LM.t('header_title'))
        self._tab_widget.setTabText(0, LM.t('tab_search'))
        self._tab_widget.setTabText(1, LM.t('tab_download'))
        self._tab_widget.setTabText(2, LM.t('tab_preview'))
        self._tab_widget.setTabText(3, LM.t('tab_settings'))
        self._tab_widget.setTabText(4, LM.t('tab_bookshelf'))
        self._tab_widget.setTabText(5, LM.t('tab_plugins'))
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
        self._fav_btn.setText(LM.t('fav_add_btn'))
        self._fav_remove_btn.setText(LM.t('fav_remove_btn'))
        self._fav_open_btn.setText(LM.t('fav_open_btn'))

        self._dl_novel_label.setText(LM.t('no_novel_selected'))
        self._progress_label.setText(LM.t('wait_download'))
        self._sel_all_btn.setText(LM.t('select_all_btn'))
        self._sel_none_btn.setText(LM.t('select_none_btn'))
        self._sel_invert_btn.setText(LM.t('select_invert_btn'))
        self._download_btn.setText(LM.t('download_btn'))
        self._stop_btn.setText(LM.t('stop_btn'))
        self._retry_btn.setText(LM.t('retry_btn'))
        self._compose_btn.setText(LM.t('compose_btn'))

        self._preview_info_label.setText(LM.t('preview_info_placeholder'))
        self._preview_edit.setPlaceholderText(LM.t('preview_placeholder'))
        self._open_file_btn.setText(LM.t('open_file_btn'))
        self._refresh_btn.setText(LM.t('refresh_btn'))
        self._export_epub_btn.setText(LM.t('export_epub_btn'))
        self._export_html_btn.setText(LM.t('export_html_btn'))

        self._proc_dedup_cb.setText(LM.t('processor_dedup'))
        self._proc_ads_cb.setText(LM.t('processor_ads'))
        self._proc_format_cb.setText(LM.t('processor_format'))
        self._proc_layout_cb.setText(LM.t('processor_layout'))
        self._proc_undo_btn.setText(LM.t('processor_undo'))
        self._proc_run_btn.setText(LM.t('processor_run'))
        self._proc_save_btn.setText(LM.t('processor_save'))
        self._proc_kw_edit.setPlaceholderText(LM.t('processor_delete_kw'))
        self._proc_kw_edit.setToolTip(LM.t('processor_delete_kw'))

        if hasattr(self, '_proc_kw_mode'):
            current = self._proc_kw_mode.currentData()
            self._proc_kw_mode.clear()
            self._proc_kw_mode.addItem(LM.t('processor_del_line'), 'line')
            self._proc_kw_mode.addItem(LM.t('processor_del_sentence'), 'sentence')
            self._proc_kw_mode.addItem(LM.t('processor_del_keyword'), 'keyword')
            idx = self._proc_kw_mode.findData(current)
            if idx >= 0:
                self._proc_kw_mode.setCurrentIndex(idx)

        for grp in self._preview_tab.findChildren(QGroupBox):
            if LM.t('processor_group') in grp.title():
                grp.setTitle(LM.t('processor_group'))
                break

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
        w.checkpoint_available.connect(self._on_checkpoint_available)
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

        history = self._config.get('search_history', [])
        if keyword not in history:
            history.insert(0, keyword)
            self._config['search_history'] = history[:50]
            save_config(self._config)

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
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
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
        selected = []
        for i in range(self._chapter_listwidget.count()):
            item = self._chapter_listwidget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                ch = item.data(Qt.ItemDataRole.UserRole)
                if ch:
                    if start <= ch.index < end:
                        selected.append(ch)

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
        output_dir = self._output_dir_edit.text().strip() or 'downloads'
        self._worker.download_chapters(selected, output_dir)

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

    @Slot(int, int, int)
    def _on_checkpoint_available(self, done: int, failed: int, pending: int):
        total = done + failed + pending
        msg = LM.t('checkpoint_found', done=done, total=total, failed=failed, pending=pending)
        self._progress_label.setText(msg)

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
        self._preview_chunk_pos = 0
        self._preview_chunk_total = 0
        self._preview_filepath = filepath
        try:
            self._preview_file_size = os.path.getsize(filepath)
        except OSError:
            self._preview_file_size = 0
        CHUNK = 100000
        INITIAL = CHUNK * 2
        if self._preview_file_size <= INITIAL:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    self._preview_edit.setPlainText(f.read())
            except Exception as e:
                self._preview_edit.setPlainText(LM.t('preview_load_fail', error=str(e)))
            self._preview_info_label.setText(
                LM.t('preview_file_label', title=os.path.basename(filepath), filepath=filepath)
            )
            return

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                initial = f.read(INITIAL)
            self._preview_edit.setPlainText(initial)
            self._preview_chunk_pos = INITIAL
            self._preview_chunk_total = self._preview_file_size
            self._update_preview_progress_label()
            QTimer.singleShot(30, self._load_next_chunk)
        except Exception as e:
            self._preview_edit.setPlainText(LM.t('preview_load_fail', error=str(e)))

    def _update_preview_progress_label(self):
        if self._preview_chunk_total > 0:
            pct = min(100, self._preview_chunk_pos * 100 // self._preview_chunk_total)
            self._preview_info_label.setText(
                LM.t('preview_file_label', title=os.path.basename(self._preview_filepath),
                     filepath=self._preview_filepath) +
                f'  [Loading {pct}%]'
            )
        else:
            self._preview_info_label.setText(
                LM.t('preview_file_label', title=os.path.basename(self._preview_filepath),
                     filepath=self._preview_filepath)
            )

    def _load_next_chunk(self):
        if self._preview_chunk_pos >= self._preview_chunk_total:
            self._update_preview_progress_label()
            return
        CHUNK = 100000
        try:
            with open(self._preview_filepath, 'r', encoding='utf-8') as f:
                f.seek(self._preview_chunk_pos)
                chunk = f.read(CHUNK)
            if chunk:
                cursor = self._preview_edit.textCursor()
                cursor.movePosition(cursor.MoveOperation.End)
                cursor.insertText(chunk)
                self._preview_chunk_pos += len(chunk)
            self._update_preview_progress_label()
        except Exception:
            pass
        if self._preview_chunk_pos < self._preview_chunk_total:
            QTimer.singleShot(30, self._load_next_chunk)

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

    def _load_full_file_text(self) -> str:
        filepath = self._composed_file
        if not filepath or not os.path.isfile(filepath):
            return ''
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return ''

    @Slot()
    def _on_process(self):
        full_text = self._load_full_file_text()
        if not full_text:
            QMessageBox.warning(self, LM.t('msg_title_hint'), LM.t('processor_no_file'))
            return

        self._original_full_text = full_text
        self._proc_run_btn.setEnabled(False)
        self._status_label.setText(LM.t('status_composing'))

        kw_text = self._proc_kw_edit.text().strip()
        keywords = [k.strip() for k in kw_text.split(';') if k.strip()] if kw_text else None
        delete_mode = self._proc_kw_mode.currentData()

        processed = NovelProcessor.process_full(
            full_text,
            dedup_lines=self._proc_dedup_cb.isChecked(),
            remove_ads=self._proc_ads_cb.isChecked(),
            smart_format=self._proc_format_cb.isChecked(),
            layout_optimize=self._proc_layout_cb.isChecked(),
            delete_keywords=keywords,
            delete_mode=delete_mode,
        )

        self._processed_full_text = processed

        self._preview_edit.setPlainText(processed)
        stats = NovelProcessor.get_stats(full_text, processed)
        self._proc_stats_label.setText(LM.t('processor_stats',
                                             before=stats['chars_before'],
                                             after=stats['chars_after'],
                                             pct=stats['reduction']))
        self._proc_undo_btn.setEnabled(True)
        self._proc_save_btn.setEnabled(True)
        self._proc_run_btn.setEnabled(True)
        self._status_label.setText(LM.t('processor_done'))

    @Slot()
    def _on_save_processed(self):
        if not self._processed_full_text:
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, LM.t('processor_save'), self._composed_file,
            LM.t('open_txt_filter'),
        )
        if not filepath:
            return
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self._processed_full_text)
            self._composed_file = filepath
            self._preview_info_label.setText(
                LM.t('preview_file_label', title='', filepath=filepath))
            self._status_label.setText(LM.t('msg_save_settings'))
        except Exception as e:
            QMessageBox.critical(self, 'Error', str(e))

    @Slot()
    def _on_undo_process(self):
        if not self._original_full_text:
            return
        self._preview_edit.setPlainText(self._original_full_text)
        self._processed_full_text = ''
        self._proc_stats_label.setText('')
        self._proc_undo_btn.setEnabled(False)
        self._proc_save_btn.setEnabled(False)
        self._status_label.setText(LM.t('status_ready'))

    @Slot()
    def _on_export_epub(self):
        filepath = self._composed_file
        text = self._load_full_file_text()
        if not filepath or not text:
            QMessageBox.warning(self, LM.t('msg_title_hint'), LM.t('processor_no_file'))
            return
        title = os.path.splitext(os.path.basename(filepath))[0]
        save_path, _ = QFileDialog.getSaveFileName(
            self, LM.t('export_epub_title'), filepath.replace('.txt', '.epub'),
            'EPUB (*.epub)',
        )
        if not save_path:
            return
        try:
            result = export_epub(text, save_path, title=title)
            self._status_label.setText(LM.t('export_done', path=result))
            QMessageBox.information(self, LM.t('processor_done'), LM.t('export_done', path=result))
        except Exception as e:
            QMessageBox.critical(self, 'Error', str(e))

    @Slot()
    def _on_export_html(self):
        filepath = self._composed_file
        text = self._load_full_file_text()
        if not filepath or not text:
            QMessageBox.warning(self, LM.t('msg_title_hint'), LM.t('processor_no_file'))
            return
        title = os.path.splitext(os.path.basename(filepath))[0]
        save_path, _ = QFileDialog.getSaveFileName(
            self, LM.t('export_html_title'), filepath.replace('.txt', '.html'),
            'HTML (*.html)',
        )
        if not save_path:
            return
        try:
            result = export_html(text, save_path, title=title)
            self._status_label.setText(LM.t('export_done', path=result))
            QMessageBox.information(self, LM.t('processor_done'), LM.t('export_done', path=result))
        except Exception as e:
            QMessageBox.critical(self, 'Error', str(e))

    def _select_chapters(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self._chapter_listwidget.count()):
            item = self._chapter_listwidget.item(i)
            item.setCheckState(state)

    @Slot()
    def _invert_chapters(self):
        for i in range(self._chapter_listwidget.count()):
            item = self._chapter_listwidget.item(i)
            new = Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
            item.setCheckState(new)

    @Slot()
    def _on_add_favorite(self):
        if not self._novel_info:
            return
        fav = {
            'title': self._novel_info.title,
            'author': self._novel_info.author,
            'url': self._novel_info.url,
        }
        existing = self._config.get('favorites', [])
        urls = {f.get('url', '') for f in existing}
        if fav['url'] in urls:
            QMessageBox.information(self, LM.t('msg_title_hint'), LM.t('favorite_exists'))
            return
        existing.insert(0, fav)
        self._config['favorites'] = existing[:50]
        save_config(self._config)
        self._status_label.setText(LM.t('favorite_added'))
        self._refresh_favorites_list()

    @Slot()
    def _on_remove_favorite(self):
        row = self._fav_list.currentRow()
        if row < 0:
            return
        existing = self._config.get('favorites', [])
        if 0 <= row < len(existing):
            del existing[row]
            self._config['favorites'] = existing
            save_config(self._config)
            self._refresh_favorites_list()

    def _refresh_favorites_list(self):
        if not hasattr(self, '_fav_list'):
            return
        self._fav_list.clear()
        for fav in self._config.get('favorites', []):
            text = f"{fav.get('title', '')}  — {fav.get('author', '')}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, fav.get('url', ''))
            self._fav_list.addItem(item)

    @Slot()
    def _on_open_favorite(self):
        row = self._fav_list.currentRow()
        if row < 0:
            return
        favs = self._config.get('favorites', [])
        if 0 <= row < len(favs):
            url = favs[row].get('url', '')
            if url:
                self._url_btn.setEnabled(False)
                self._status_label.setText(LM.t('fetching_info'))
                self._worker.fetch_novel_info(url, '')
                self._tab_widget.setCurrentIndex(1)

    def _refresh_history_combo(self):
        if not hasattr(self, '_history_combo'):
            return
        self._history_combo.blockSignals(True)
        self._history_combo.clear()
        self._history_combo.addItem('')
        for kw in self._config.get('search_history', [])[:20]:
            self._history_combo.addItem(kw)
        self._history_combo.blockSignals(False)

    @Slot(str)
    def _on_history_selected(self, text: str):
        if text:
            self._search_input.setText(text)
            self._on_search()

    def _refresh_bookshelf(self):
        tag = self._bs_tag_combo.currentData()
        items = self._bookshelf.get_items_by_tag(tag)
        self._bs_list.clear()
        for item in items:
            progress_text = f'{item.read_progress:.0f}%' if item.read_progress > 0 else ''
            display = f'{item.title}  — {item.author or "Unknown"}  [{item.file_type.upper()}]\t{progress_text}'
            list_item = QListWidgetItem(display)
            list_item.setData(Qt.ItemDataRole.UserRole, item.id)
            list_item.setToolTip(
                f"Tags: {', '.join(item.tags)}\nProgress: {item.read_progress:.1f}%\n"
                f"Characters: {item.total_chars:,}\nAdded: {item.date_added}"
            )
            if item.read_progress >= 100:
                list_item.setForeground(QColor('#a6e3a1'))
            self._bs_list.addItem(list_item)

    def _on_bs_tag_changed(self):
        self._refresh_bookshelf()

    def _on_bs_add_file(self):
        filepaths, _ = QFileDialog.getOpenFileNames(
            self, LM.t('bs_add_title'), '',
            'Book files (*.txt *.epub);;Text files (*.txt);;EPUB files (*.epub);;All files (*)',
        )
        for fp in filepaths:
            self._bookshelf.add_book(fp)
        self._refresh_bookshelf()
        if filepaths:
            self._status_label.setText(LM.t('bs_added', count=len(filepaths)))

    def _on_bs_file_dropped(self, filepath: str):
        self._bookshelf.add_book(filepath)
        self._refresh_bookshelf()
        self._status_label.setText(LM.t('bs_added', count=1))

    def _on_bs_remove(self):
        selected = self._bs_list.selectedItems()
        if not selected:
            return
        for item in selected:
            item_id = item.data(Qt.ItemDataRole.UserRole)
            self._bookshelf.remove_book(item_id)
        self._refresh_bookshelf()
        self._status_label.setText(LM.t('bs_removed', count=len(selected)))

    def _on_bs_open(self):
        selected = self._bs_list.selectedItems()
        if not selected:
            return
        item_id = selected[0].data(Qt.ItemDataRole.UserRole)
        book = self._bookshelf.get_book(item_id)
        if book and os.path.isfile(book.file_path):
            self._composed_file = book.file_path
            self._preview_info_label.setText(LM.t('preview_file_label', title=book.title, filepath=book.file_path))
            self._load_preview(book.file_path)
            self._tab_widget.setCurrentIndex(2)

    def _on_tts_play(self):
        text = self._preview_edit.toPlainText()
        if not text or len(text) < 2000:
            full = self._load_full_file_text()
            if full:
                text = full
        if not text.strip():
            return
        self._tts_player.speak(text)

    def _on_tts_pause(self):
        self._tts_player.toggle_pause()

    def _on_tts_stop(self):
        self._tts_player.stop()

    def _on_tts_rate_changed(self, value: int):
        self._tts_player.set_rate(value / 10.0)

    def _on_tts_pitch_changed(self, value: int):
        self._tts_player.set_pitch(value / 10.0)

    def _on_tts_volume_changed(self, value: int):
        self._tts_player.set_volume(value / 10.0)

    @Slot(str)
    def _on_tts_state_changed(self, state: str):
        if state == TTSPlayer.STATE_PLAYING:
            self._tts_status_label.setText(LM.t('tts_playing'))
        elif state == TTSPlayer.STATE_PAUSED:
            self._tts_status_label.setText(LM.t('tts_paused'))
        elif state == TTSPlayer.STATE_STOPPED:
            self._tts_status_label.setText(LM.t('tts_stopped_status'))

    def _check_for_updates(self):
        has_update = self._update_checker.check()
        if has_update:
            self._update_status_label.setText(
                LM.t('update_available', version=self._update_checker.latest_version)
            )
            self._update_status_label.setStyleSheet('color: #a6e3a1;')
            reply = QMessageBox.question(
                self, LM.t('update_title'),
                LM.t('update_ask', version=self._update_checker.latest_version),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._do_update()
        else:
            self._update_status_label.setText(
                LM.t('update_current', version=UpdateChecker.CURRENT_VERSION)
            )
            self._update_status_label.setStyleSheet('color: #a6adc8;')

    def _on_check_update_clicked(self):
        self._update_check_btn.setEnabled(False)
        self._update_status_label.setText(LM.t('update_checking'))
        self._update_status_label.setStyleSheet('color: #f9e2af;')
        QTimer.singleShot(500, self._check_for_updates)
        QTimer.singleShot(2000, lambda: self._update_check_btn.setEnabled(True))

    def _do_update(self):
        self._status_label.setText(LM.t('update_downloading'))
        tmp_path = self._update_checker.download_update(
            callback=lambda d, t: self._update_status_label.setText(
                LM.t('update_progress', downloaded=d, total=t)
            )
        )
        if tmp_path:
            self._update_checker.apply_update(tmp_path)
            self._status_label.setText(LM.t('update_restarting'))
        else:
            self._update_status_label.setText(LM.t('update_failed'))
            self._update_status_label.setStyleSheet('color: #f38ba8;')

    def _refresh_plugins(self):
        self._pl_list.clear()
        for plugin in self._plugin_manager.plugins:
            status = '✅' if plugin.enabled else '❌'
            text = f'{status}  {plugin.name} v{plugin.version}  — {plugin.description}  [{plugin.author}]'
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, plugin.name)
            if plugin.enabled:
                item.setForeground(QColor('#a6e3a1'))
            else:
                item.setForeground(QColor('#6c7086'))
            self._pl_list.addItem(item)

    def _on_pl_install(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, LM.t('pl_install_title'), '',
            'Python files (*.py);;All files (*)',
        )
        if filepath:
            plugin = self._plugin_manager.install_plugin(filepath)
            if plugin:
                self._refresh_plugins()
                self._status_label.setText(LM.t('pl_installed', name=plugin.name))
            else:
                QMessageBox.warning(self, LM.t('msg_title_hint'), LM.t('pl_install_fail'))

    def _on_pl_remove(self):
        selected = self._pl_list.selectedItems()
        if not selected:
            return
        name = selected[0].data(Qt.ItemDataRole.UserRole)
        if self._plugin_manager.uninstall_plugin(name):
            self._refresh_plugins()
            self._status_label.setText(LM.t('pl_removed', name=name))

    def _on_pl_create_sample(self):
        path = self._plugin_manager.create_sample_plugin()
        self._status_label.setText(LM.t('pl_sample_created', path=path))
        self._refresh_plugins()

    def closeEvent(self, event):
        self._tts_player.stop()
        self._worker.cancel_all()
        QThreadPool.globalInstance().waitForDone(3000)
        super().closeEvent(event)