import os
import sys
import json
import tempfile
import logging
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

logger = logging.getLogger(__name__)


class UpdateChecker:

    GITHUB_API = 'https://api.github.com/repos/lulorime-ship-it/novel-search/releases/latest'
    CURRENT_VERSION = '2.0.0'

    def __init__(self):
        self._latest_version: Optional[str] = None
        self._download_url: Optional[str] = None
        self._release_notes: str = ''
        self._file_size: int = 0

    def check(self) -> bool:
        try:
            req = Request(self.GITHUB_API, headers={
                'User-Agent': 'NovelSearch-Updater/1.0',
                'Accept': 'application/vnd.github.v3+json',
            })
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))

            tag = data.get('tag_name', '').lstrip('v')
            self._latest_version = tag
            self._release_notes = data.get('body', '')

            assets = data.get('assets', [])
            for asset in assets:
                name = asset.get('name', '')
                if name.endswith('.exe') or name.endswith('.zip'):
                    self._download_url = asset.get('browser_download_url', '')
                    self._file_size = asset.get('size', 0)
                    break

            return self._is_newer(self._latest_version, self.CURRENT_VERSION)
        except URLError as e:
            logger.error(f"Update check failed (network): {e}")
            return False
        except Exception as e:
            logger.error(f"Update check failed: {e}")
            return False

    @property
    def latest_version(self) -> str:
        return self._latest_version or ''

    @property
    def download_url(self) -> str:
        return self._download_url or ''

    @property
    def release_notes(self) -> str:
        return self._release_notes

    @property
    def file_size(self) -> int:
        return self._file_size

    def download_update(self, callback=None) -> Optional[str]:
        if not self._download_url:
            return None

        try:
            tmp = tempfile.NamedTemporaryFile(suffix='.exe', delete=False)
            tmp_path = tmp.name
            tmp.close()

            req = Request(self._download_url, headers={
                'User-Agent': 'NovelSearch-Updater/1.0',
            })
            with urlopen(req, timeout=300) as resp:
                total = int(resp.headers.get('Content-Length', 0))
                downloaded = 0
                with open(tmp_path, 'wb') as f:
                    while True:
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if callback and total > 0:
                            callback(downloaded, total)

            return tmp_path
        except Exception as e:
            logger.error(f"Download update failed: {e}")
            return None

    def apply_update(self, downloaded_path: str) -> bool:
        try:
            current_exe = sys.executable
            if getattr(sys, 'frozen', False):
                target = current_exe
            else:
                return False

            backup = target + '.bak'
            if os.path.exists(backup):
                os.remove(backup)

            bat_path = os.path.join(tempfile.gettempdir(), 'novel_update.bat')
            with open(bat_path, 'w', encoding='utf-8') as f:
                f.write('@echo off\n')
                f.write('echo Waiting for app to close...\n')
                f.write('timeout /t 3 /nobreak >nul\n')
                f.write(f'echo Updating NovelSearch...\n')
                f.write(f'copy /y "{downloaded_path}" "{target}" >nul\n')
                f.write(f'if exist "{target}" (\n')
                f.write(f'    echo Update complete! Restarting...\n')
                f.write(f'    start "" "{target}"\n')
                f.write(f') else (\n')
                f.write(f'    echo Update failed. Restoring backup...\n')
                f.write(f'    if exist "{backup}" move /y "{backup}" "{target}" >nul\n')
                f.write(f'    pause\n')
                f.write(f')\n')
                f.write(f'del "%~f0"\n')

            os.startfile(bat_path)
            return True
        except Exception as e:
            logger.error(f"Apply update failed: {e}")
            return False

    @staticmethod
    def _is_newer(latest: str, current: str) -> bool:
        try:
            l_parts = [int(x) for x in latest.split('.')]
            c_parts = [int(x) for x in current.split('.')]
            while len(l_parts) < 3:
                l_parts.append(0)
            while len(c_parts) < 3:
                c_parts.append(0)
            for l, c in zip(l_parts, c_parts):
                if l > c:
                    return True
                if l < c:
                    return False
            return False
        except (ValueError, AttributeError):
            return False