import asyncio
import logging
from typing import Optional, Callable
from dataclasses import dataclass, field

import aiohttp

from sources.base import NovelInfo, ChapterInfo
from sources.biquge import BiqugeSource, create_all_sources, USER_AGENT

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    success: list[tuple[ChapterInfo, str]] = field(default_factory=list)
    failed: list[tuple[ChapterInfo, str]] = field(default_factory=list)


class NovelCrawler:

    def __init__(self, source: BiqugeSource, concurrency: int = 5, delay: float = 0.5):
        self.source = source
        self._concurrency = concurrency
        self._delay = delay
        self._sem = asyncio.Semaphore(concurrency)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    async def fetch_novel_info(self, url: str) -> Optional[NovelInfo]:
        return await self.source.get_novel_info(url)

    async def download_chapter(self, chapter: ChapterInfo) -> str:
        if self._cancelled:
            return ''
        async with self._sem:
            await asyncio.sleep(self._delay)
            content = await self.source.get_chapter_content(chapter.url)
            return content

    async def download_all_chapters(
        self,
        chapters: list[ChapterInfo],
        progress_callback: Callable[[int, int, str], None] = None,
        fail_callback: Callable[[ChapterInfo, str], None] = None,
    ) -> DownloadResult:
        result = DownloadResult()
        total = len(chapters)
        completed = 0

        async def _download_one(ch: ChapterInfo) -> tuple[ChapterInfo, str, str]:
            nonlocal completed
            try:
                content = await self.download_chapter(ch)
                completed += 1
                if progress_callback:
                    progress_callback(completed, total, ch.title)
                if not content:
                    return (ch, '', '空内容')
                return (ch, content, '')
            except Exception as e:
                completed += 1
                if progress_callback:
                    progress_callback(completed, total, ch.title)
                return (ch, '', str(e))

        tasks = [_download_one(ch) for ch in chapters]
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
                    if progress_callback:
                        progress_callback(completed, total, f'{ch.title} (重试失败)')
            except Exception as e:
                completed += 1
                if progress_callback:
                    progress_callback(completed, total, f'{ch.title} (重试失败)')

        tasks = [_redownload_one(i) for i in range(total)]
        await asyncio.gather(*tasks, return_exceptions=True)

        result.failed = [f for f in result.failed if f is not None]
        return result
