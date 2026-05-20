import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass, field

import aiohttp

from sources.base import NovelInfo, ChapterInfo, BaseSource
from engine.cleaner import NovelCleaner
from utils.helpers import safe_filename

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    success: list[tuple[ChapterInfo, str]] = field(default_factory=list)
    failed: list[tuple[ChapterInfo, str]] = field(default_factory=list)


@dataclass
class ChapterCache:
    index: int
    title: str
    url: str
    status: str
    file_path: str = ''


class NovelCrawler:

    _SUCCESS = 'success'
    _FAILED = 'failed'
    _PENDING = 'pending'

    def __init__(self, source: BaseSource, concurrency: int = 5, delay: float = 0.5,
                 checkpoint_dir: str = ''):
        self.source = source
        self._concurrency = concurrency
        self._delay = delay
        self._sem = asyncio.Semaphore(concurrency)
        self._cancelled = False
        self._checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else None
        self._checkpoint_file: Optional[Path] = None
        self._checkpoint_data: dict[str, ChapterCache] = {}
        self._chapters_dir: Optional[Path] = None

    def cancel(self):
        self._cancelled = True

    def init_checkpoint(self, novel_title: str, base_dir: str = 'downloads'):
        base = Path(base_dir)
        safe = safe_filename(novel_title)
        self._checkpoint_dir = base / safe
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._chapters_dir = self._checkpoint_dir / 'chapters'
        self._chapters_dir.mkdir(parents=True, exist_ok=True)
        self._checkpoint_file = self._checkpoint_dir / 'checkpoint.json'
        self._checkpoint_data = {}
        if self._checkpoint_file.exists():
            try:
                with open(self._checkpoint_file, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                for entry in raw:
                    cc = ChapterCache(
                        index=entry['index'], title=entry.get('title', ''),
                        url=entry['url'], status=entry['status'],
                        file_path=entry.get('file_path', ''),
                    )
                    if cc.file_path and not os.path.isfile(cc.file_path):
                        cc.status = self._PENDING
                        cc.file_path = ''
                    key = f'{cc.index}_{cc.url}'
                    self._checkpoint_data[key] = cc
            except Exception:
                self._checkpoint_data = {}

    def _save_checkpoint(self):
        if not self._checkpoint_file:
            return
        try:
            data = [{
                'index': cc.index, 'title': cc.title,
                'url': cc.url, 'status': cc.status,
                'file_path': cc.file_path,
            } for cc in self._checkpoint_data.values()]
            checkpoint_str = str(self._checkpoint_file)
            tmp_path = checkpoint_str + '.tmp'
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            try:
                os.replace(tmp_path, checkpoint_str)
            except OSError:
                try:
                    os.remove(checkpoint_str)
                    os.rename(tmp_path, checkpoint_str)
                except OSError:
                    with open(checkpoint_str, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f'Failed to save checkpoint: {e}')

    def get_checkpoint_summary(self) -> tuple[int, int, int]:
        done = sum(1 for c in self._checkpoint_data.values() if c.status == self._SUCCESS and c.file_path)
        failed = sum(1 for c in self._checkpoint_data.values() if c.status == self._FAILED)
        pending = sum(1 for c in self._checkpoint_data.values() if c.status == self._PENDING)
        return done, failed, pending

    def get_cached_chapters(self) -> list[tuple[ChapterInfo, str]]:
        cached = []
        for k, cc in self._checkpoint_data.items():
            if cc.status == self._SUCCESS and cc.file_path and os.path.isfile(cc.file_path):
                try:
                    with open(cc.file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    ch = ChapterInfo(index=cc.index, title=cc.title, url=cc.url)
                    cached.append((ch, content))
                except Exception:
                    cc.status = self._PENDING
                    cc.file_path = ''
                    self._save_checkpoint()
        return cached

    async def _save_chapter_to_disk(self, chapter: ChapterInfo, raw_content: str) -> str:
        if not self._chapters_dir:
            return ''
        title = NovelCleaner.clean_chapter_title(chapter.title)
        safe = safe_filename(f'{chapter.index:04d}_{title}')
        filepath = self._chapters_dir / f'{safe}.txt'
        content = NovelCleaner.clean_content(raw_content)
        if not content or len(content) < 50:
            return ''
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f'{title}\n\n{content}\n')
        return str(filepath)

    def _set_cache(self, chapter: ChapterInfo, status: str, file_path: str = ''):
        key = f'{chapter.index}_{chapter.url}'
        self._checkpoint_data[key] = ChapterCache(
            index=chapter.index, title=chapter.title,
            url=chapter.url, status=status, file_path=file_path,
        )
        self._save_checkpoint()

    async def fetch_novel_info(self, url: str) -> Optional[NovelInfo]:
        return await self.source.get_novel_info(url)

    async def download_chapter(self, chapter: ChapterInfo) -> str:
        if self._cancelled:
            return ''
        async with self._sem:
            await asyncio.sleep(self._delay)
            content = await self.source.get_chapter_content(chapter.url)
            if content and self._chapters_dir:
                saved_path = await self._save_chapter_to_disk(chapter, content)
                if saved_path:
                    self._set_cache(chapter, self._SUCCESS, saved_path)
            return content

    async def download_all_chapters(
        self,
        chapters: list[ChapterInfo],
        progress_callback: Callable[[int, int, str], None] = None,
        fail_callback: Callable[[ChapterInfo, str], None] = None,
    ) -> DownloadResult:
        result = DownloadResult()

        skip_map: dict[int, tuple[ChapterInfo, str]] = {}
        pending_chapters: list[ChapterInfo] = []
        for ch in chapters:
            key = f'{ch.index}_{ch.url}'
            cc = self._checkpoint_data.get(key)
            if cc and cc.status == self._SUCCESS and cc.file_path and os.path.isfile(cc.file_path):
                try:
                    with open(cc.file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    skip_map[ch.index] = (ch, content)
                except Exception:
                    pending_chapters.append(ch)
            else:
                pending_chapters.append(ch)

        skipped_count = len(skip_map)
        if skipped_count > 0:
            logger.info(f'Resuming: {skipped_count} chapters already cached, {len(pending_chapters)} remaining')
            for ch, content in skip_map.values():
                result.success.append((ch, content))

        if not pending_chapters:
            if progress_callback:
                progress_callback(len(result.success), len(chapters), '(断点续传完成)')
            return result

        total = len(chapters)
        base_completed = skipped_count
        completed_count = [base_completed]

        async def _download_one(ch: ChapterInfo) -> tuple[ChapterInfo, str, str]:
            nonlocal completed_count
            try:
                content = await self.download_chapter(ch)
                completed_count[0] += 1
                if progress_callback:
                    progress_callback(completed_count[0], total, ch.title)
                if not content:
                    self._set_cache(ch, self._FAILED)
                    return (ch, '', '空内容')
                return (ch, content, '')
            except Exception as e:
                completed_count[0] += 1
                self._set_cache(ch, self._FAILED)
                if progress_callback:
                    progress_callback(completed_count[0], total, ch.title)
                return (ch, '', str(e))

        tasks = [_download_one(ch) for ch in pending_chapters]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        for item in raw_results:
            if isinstance(item, Exception):
                logger.error(f'Download error: {item}')
                continue
            ch, content, err = item
            if err or not content:
                result.failed.append((ch, err))
                if fail_callback:
                    fail_callback(ch, err)
            else:
                result.success.append((ch, content))

        return result

    async def redownload_failed(
        self,
        failed_chapters: list[tuple[ChapterInfo, str]],
        progress_callback: Callable[[int, int, str], None] = None,
    ) -> DownloadResult:
        result = DownloadResult()
        result.failed = list(failed_chapters)
        total = len(failed_chapters)
        completed = 0

        async def _redownload_one(idx: int):
            nonlocal completed
            ch, _ = failed_chapters[idx]
            try:
                content = await self.download_chapter(ch)
                completed += 1
                if progress_callback:
                    progress_callback(completed, total, ch.title)
                if content:
                    result.success.append((ch, content))
                    result.failed[idx] = None
                else:
                    self._set_cache(ch, self._FAILED)
                    if progress_callback:
                        progress_callback(completed, total, f'{ch.title} (重试失败)')
            except Exception as e:
                completed += 1
                self._set_cache(ch, self._FAILED)
                if progress_callback:
                    progress_callback(completed, total, f'{ch.title} (重试失败)')

        tasks = [_redownload_one(i) for i in range(total)]
        await asyncio.gather(*tasks, return_exceptions=True)

        result.failed = [f for f in result.failed if f is not None]
        return result