import asyncio
import logging
from dataclasses import dataclass, field

from sources.base import SearchResult
from sources.biquge import BiqugeSource, create_default_sources
from engine.browser_searcher import get_browser_searcher

logger = logging.getLogger(__name__)


@dataclass
class SearchResponse:
    results: list[SearchResult] = field(default_factory=list)
    reachable_count: int = 0
    unreachable_count: int = 0
    total_sources: int = 0
    search_method: str = ''
    candidates_checked: int = 0


class NovelSearcher:

    def __init__(self, sources: list[BiqugeSource] = None):
        self._sources = sources or create_default_sources()

    async def search(self, keyword: str, engine_code: str = 'bing') -> SearchResponse:
        if not keyword.strip():
            return SearchResponse()

        browser_results = await self._search_via_browser(keyword, engine_code)
        if browser_results:
            logger.info(f'Browser search found {len(browser_results)} results')
            return SearchResponse(
                results=browser_results,
                reachable_count=1,
                unreachable_count=0,
                total_sources=1,
                search_method='browser',
            )

        logger.info('Browser search returned no results, falling back to direct site search')
        direct_resp = await self._search_direct(keyword)
        direct_resp.search_method = 'direct'
        return direct_resp

    async def _search_via_browser(self, keyword: str, engine_code: str = 'bing') -> list[SearchResult]:
        try:
            bs = get_browser_searcher()
            results = await bs.search(keyword, engine_code=engine_code)
            diag = bs.get_diagnostics()
            logger.info(f'Browser: checked {diag.get("candidates", 0)} URLs, found {diag.get("results", 0)} valid')
            return results
        except Exception as e:
            logger.warning(f'Browser search failed: {e}')
            return []

    async def _search_direct(self, keyword: str) -> SearchResponse:
        tasks = [src.search(keyword) for src in self._sources]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        merged: list[SearchResult] = []
        seen_urls = set()
        reachable = 0
        unreachable = 0
        for idx, result_list in enumerate(all_results):
            if isinstance(result_list, Exception):
                unreachable += 1
                continue
            if self._sources[idx].is_unreachable:
                unreachable += 1
            else:
                reachable += 1
            for r in result_list:
                if r.url not in seen_urls:
                    seen_urls.add(r.url)
                    merged.append(r)
        return SearchResponse(
            results=merged,
            reachable_count=reachable,
            unreachable_count=unreachable,
            total_sources=len(self._sources),
        )
