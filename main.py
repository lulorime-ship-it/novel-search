import os
import sys
import asyncio
import io
import logging


class _StderrFilter:
    """Drop libpng/iCCP warnings from stderr for the entire app lifetime."""

    def __init__(self, real_stderr):
        self._real = real_stderr
        self._buf = ''

    def write(self, s: str) -> int:
        if not s:
            return 0
        self._buf += s
        lines = self._buf.split('\n')
        self._buf = lines[-1]
        for line in lines[:-1]:
            stripped = line.strip()
            if stripped and 'libpng warning' not in stripped.lower():
                if self._real is not None:
                    self._real.write(line + '\n')
                    self._real.flush()
        return len(s)

    def flush(self):
        if self._buf.strip() and 'libpng warning' not in self._buf.lower():
            if self._real is not None:
                self._real.write(self._buf)
        self._buf = ''
        if self._real is not None:
            self._real.flush()

    def __getattr__(self, name):
        if self._real is not None:
            return getattr(self._real, name)
        raise AttributeError(name)


def _apply_stderr_filter():
    if not getattr(sys, 'frozen', False):
        return
    try:
        if sys.stderr is not None and not isinstance(sys.stderr, _StderrFilter):
            sys.stderr = _StderrFilter(sys.stderr)
        elif sys.stderr is None:
            sys.stderr = _StderrFilter(None)
    except Exception:
        pass


def _setup_logging():
    is_frozen = getattr(sys, 'frozen', False)
    handlers = []
    if is_frozen:
        log_dir = _get_log_dir()
        try:
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, 'novel_search.log')
            handlers.append(logging.FileHandler(log_file, encoding='utf-8'))
        except Exception:
            pass
    console_handler = logging.StreamHandler(sys.stderr)
    handlers.append(console_handler)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S',
        handlers=handlers,
    )


def _get_log_dir():
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'logs')


from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from gui.main_window import MainWindow
from gui.styles import STYLE_QSS


def main():
    _apply_stderr_filter()
    _setup_logging()
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('novel.search.v1')
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName('小说搜索下载系统')
    app.setOrganizationName('NovelSearch')
    app.setStyleSheet(STYLE_QSS)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
