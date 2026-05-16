import os
import sys
import asyncio
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
                self._real.write(line + '\n')
                self._real.flush()
        return len(s)

    def flush(self):
        if self._buf.strip() and 'libpng warning' not in self._buf.lower():
            self._real.write(self._buf)
        self._buf = ''
        self._real.flush()

    def __getattr__(self, name):
        return getattr(self._real, name)


def _apply_stderr_filter():
    if not getattr(sys, 'frozen', False):
        return
    try:
        if not isinstance(sys.stderr, _StderrFilter):
            sys.stderr = _StderrFilter(sys.stderr)
    except Exception:
        pass


from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from gui.main_window import MainWindow
from gui.styles import STYLE_QSS

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S',
)


def main():
    _apply_stderr_filter()
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
