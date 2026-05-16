import asyncio
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThreadPool, QRunnable, Signal, QObject, Slot

from sources.base import SearchResult, NovelInfo, ChapterInfo
from sources.biquge import BiqugeSource, BIQUGE_DOMAINS
from engine.searcher import NovelSearcher, SearchResponse
from engine.crawler import NovelCrawler, DownloadResult
from engine.cleaner import NovelCleaner
from engine.composer import NovelComposer

logger = logging.getLogger(__name__)


class _Signals(QObject):
    finished = Signal()
    result = Signal(object)
    error = Signal(str)


class _AsyncTask(QRunnable):

    def __init__(self, coro_func, *args, **kwargs):
        super().__init__()
        self._coro_func = coro_func
        self._args = args
        self._kwargs = kwargs
        self.signals = _Signals()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @Slot()
    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self._coro_func(*self._args, **self._kwargs))
            if not self._cancelled:
                self.signals.result.emit(result)
        except Exception as e:
            if not self._cancelled:
                self.signals.error.emit(str(e))
        finally:
            loop.close()
            self.signals.finished.emit()


class NovelWorker(QObject):
    _instance: Optional['NovelWorker'] = None

    search_finished = Signal(object)
    search_error = Signal(str)
    source_status = Signal(int, int, int, str)

    novel_info_ready = Signal(object)
    novel_info_error = Signal(str)

    download_progress = Signal(int, int, str)
    download_finished = Signal(list, list)
    redownload_finished = Signal(list, list)
    download_error = Signal(str)
    download_cancelled = Signal()

    compose_finished = Signal(str, str)
    compose_error = Signal(str)

    log_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        NovelWorker._instance = self
        self._pool = QThreadPool.globalInstance()
        self._pool.setMaxThreadCount(8)
        self._searcher = NovelSearcher()
        self._crawler: Optional[NovelCrawler] = None
        self._composer = NovelComposer()
        self._current_source: Optional[BiqugeSource] = None
        self._cancelled = False
        self._active_tasks: list[_AsyncTask] = []

    @classmethod
    def instance(cls) -> 'NovelWorker':
        if cls._instance is None:
            cls._instance = NovelWorker()
        return cls._instance

    def _launch(self, coro_func, *args,
                on_result=None, on_error=None) -> _AsyncTask:
        task = _AsyncTask(coro_func, *args)
        self._active_tasks.append(task)
        task.signals.finished.connect(lambda: self._cleanup_task(task))
        if on_result:
            task.signals.result.connect(on_result)
        if on_error:
            task.signals.error.connect(on_error)
        self._pool.start(task)
        return task

    def _cleanup_task(self, task: _AsyncTask):
        if task in self._active_tasks:
            self._active_tasks.remove(task)

    def search(self, keyword: str, engine_code: str = 'bing'):
        self._cancelled = False

        self._launch(
            self._searcher.search, keyword, engine_code,
            on_result=self._on_search_done,
            on_error=self._on_search_fail,
        )

    def _on_search_done(self, resp: SearchResponse):
        method_label = '浏览器搜索' if resp.search_method == 'browser' else '直接站内搜索'
        if resp.search_method == 'browser':
            self._emit_log(f'Bing搜索完成 — 找到 {len(resp.results)} 本匹配小说')
            self.source_status.emit(1, 0, 1, method_label)
        else:
            self.source_status.emit(
                resp.reachable_count, resp.unreachable_count,
                resp.total_sources, method_label,
            )
            self._emit_log(f'直接搜索: {resp.reachable_count}可达/{resp.unreachable_count}不可达 — {len(resp.results)} 结果')
        self.search_finished.emit(resp.results)

    def _on_search_fail(self, error: str):
        self._emit_log(f'搜索出错: {error}')
        self.search_error.emit(error)

    def fetch_novel_info(self, url: str, source_name: str = ''):
        self._cancelled = False
        self._emit_log(f'正在获取小说目录: {url}')

        base_url = self._guess_base_url(url)
        if not source_name:
            source_name = self._guess_source_name(base_url)

        source = BiqugeSource(source_name=source_name, base_url=base_url)
        self._current_source = source
        self._crawler = NovelCrawler(source=source, concurrency=5, delay=0.5)

        self._launch(
            self._crawler.fetch_novel_info, url,
            on_result=self._on_info_done,
            on_error=self._on_info_fail,
        )

    def _guess_base_url(self, url: str) -> str:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return f'{parsed.scheme}://{parsed.netloc}'

    def _guess_source_name(self, base_url: str) -> str:
        for name, url in BIQUGE_DOMAINS:
            if name in base_url or url in base_url:
                return name
        from urllib.parse import urlparse
        host = urlparse(base_url).netloc.replace('www.', '')
        return host.split('.')[0]

    def _on_info_done(self, info: Optional[NovelInfo]):
        if info:
            self._emit_log(f'获取成功: 《{info.title}》共 {len(info.chapters)} 章')
            self.novel_info_ready.emit(info)
        else:
            self._emit_log('获取小说信息失败')
            self.novel_info_error.emit('无法解析小说目录页，请确认URL正确并手动在浏览器打开测试')

    def _on_info_fail(self, error: str):
        self._emit_log(f'获取小说信息出错: {error}')
        self.novel_info_error.emit(
            f'网络请求失败，该网站可能不可达。\n'
            f'提示：请在浏览器中手动搜索小说，复制目录页URL到搜索框使用"直接输入网址"功能。\n'
            f'错误: {error}'
        )

    def download_chapters(self, chapters: list[ChapterInfo]):
        if not self._crawler:
            self._emit_log('错误: 未初始化爬虫')
            self.download_error.emit('未初始化爬虫，请先获取小说目录')
            return
        self._cancelled = False
        self._emit_log(f'开始下载 {len(chapters)} 个章节...')

        async def _download_all():
            def _progress(completed, total, title):
                if not self._cancelled:
                    self.download_progress.emit(completed, total, title)
                    if completed % 10 == 0:
                        self._emit_log(f'下载进度: {completed}/{total}')

            return await self._crawler.download_all_chapters(
                chapters, progress_callback=_progress,
            )

        self._launch(
            _download_all,
            on_result=self._on_download_done,
            on_error=self._on_download_fail,
        )

    def _on_download_done(self, result: DownloadResult):
        if self._cancelled:
            self._emit_log('下载已取消')
            self.download_cancelled.emit()
            return

        success_count = len(result.success)
        fail_count = len(result.failed)
        self._emit_log(f'下载完成: {success_count}章成功, {fail_count}章失败')
        
        if fail_count > 0:
            for ch, err in result.failed:
                self._emit_log(f'  失败章节: {ch.title} - {err}')
        
        self.download_finished.emit(result.success, result.failed)

    def _on_download_fail(self, error: str):
        self._emit_log(f'下载出错: {error}')
        self.download_error.emit(error)

    def redownload_failed(self, failed_chapters: list[tuple[ChapterInfo, str]]):
        if not self._crawler:
            self._emit_log('错误: 未初始化爬虫')
            return
        if not failed_chapters:
            self._emit_log('没有需要重试的章节')
            return

        self._cancelled = False
        self._emit_log(f'重新下载 {len(failed_chapters)} 个失败章节...')

        async def _redownload():
            def _progress(completed, total, title):
                if not self._cancelled:
                    self.download_progress.emit(completed, total, title)

            return await self._crawler.redownload_failed(
                failed_chapters, progress_callback=_progress,
            )

        self._launch(
            _redownload,
            on_result=self._on_redownload_done,
            on_error=self._on_download_fail,
        )

    def _on_redownload_done(self, result: DownloadResult):
        if self._cancelled:
            self._emit_log('重新下载已取消')
            return

        success_count = len(result.success)
        fail_count = len(result.failed)
        self._emit_log(f'重新下载完成: {success_count}章成功, {fail_count}章仍失败')

        self.redownload_finished.emit(result.success, result.failed)

    def compose_novel(
        self,
        title: str,
        author: str,
        chapters_data: list,
        intro: str = '',
        output_dir: str = 'downloads',
    ):
        self._emit_log(f'正在组合小说: 《{title}》...')
        self._composer._output_dir = Path(output_dir)

        async def _compose():
            return self._composer.compose(title, author, chapters_data, intro)

        self._launch(
            _compose,
            on_result=lambda fp: self._on_compose_done(fp, title),
            on_error=self._on_compose_fail,
        )

    def _on_compose_done(self, filepath: str, title: str):
        self._emit_log(f'小说已保存: {filepath}')
        self.compose_finished.emit(filepath, title)

    def _on_compose_fail(self, error: str):
        self._emit_log(f'组合小说出错: {error}')
        self.compose_error.emit(error)

    def cancel_all(self):
        self._cancelled = True
        if self._crawler:
            self._crawler.cancel()
        for task in list(self._active_tasks):
            task.cancel()
            self._pool.cancel(task)
        self._active_tasks.clear()

    def _emit_log(self, msg: str):
        self.log_message.emit(msg)
