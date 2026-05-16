import asyncio
import logging
from urllib.parse import quote, urljoin
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup

from sources.base import BaseSource, BaseParser, SearchResult, NovelInfo, ChapterInfo

logger = logging.getLogger(__name__)

BIQUGE_DOMAINS = [
    ('biquge365', 'https://www.biquge365.net'),
    ('biqubook', 'https://www.biqubook.com'),
    ('bxwx', 'https://www.bxwx.cc'),
    ('33yq', 'https://www.33yq.com'),
    ('ibiquge', 'https://www.ibiquge.net'),
    ('biquge5200', 'https://www.biquge5200.com'),
    ('69shu', 'https://www.69shuba.cx'),
    ('xbiquge', 'https://www.xbiquge.la'),
    ('bqg70', 'https://www.bqg70.com'),
]

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)


class BiqugeParser(BaseParser):

    def parse_search_results(self, html: str) -> list[SearchResult]:
        soup = BeautifulSoup(html, 'lxml')
        results = []
        selectors = [
            '.result-list .result-item',
            '.novelslist2 li',
            '#sitembox dl',
            '.library li',
            '.booklist li',
            '.list li',
            '.search-list li',
            '.result li',
            'table.grid tr',
        ]
        items = []
        for sel in selectors:
            items = soup.select(sel)
            if items:
                break
        if not items:
            items = soup.select('a[href*="/book/"], a[href*="/novel/"], a[href*="/txt/"], a[href*="/info/"]')

        seen_titles = set()
        for item in items:
            title_el = item.select_one('h3 a, .s2 a, h2 a, .name a')
            if not title_el:
                title_el = item.select_one('a[href*="/book/"], a[href*="/novel/"], a[href*="/txt/"], a[href*="/info/"]')
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            url = title_el.get('href', '')
            author = ''
            author_el = item.select_one('.s4, .s5, .author, p.author, .writer, td:nth-child(3)')
            if not author_el:
                for el in item.select('span, p, td'):
                    t = el.get_text(strip=True)
                    if '作者' in t:
                        author = t.replace('作者：', '').replace('作者:', '').strip()
                        break
            else:
                author = author_el.get_text(strip=True)
            latest = ''
            latest_el = item.select_one('.s3, .update, .latest, td:nth-child(4)')
            if latest_el:
                latest = latest_el.get_text(strip=True)
            results.append(SearchResult(
                title=title,
                author=author,
                url=url,
                latest_chapter=latest,
                source='biquge',
            ))
        return results

    def parse_novel_info(self, html: str) -> Optional[NovelInfo]:
        soup = BeautifulSoup(html, 'lxml')
        title = ''
        title_el = soup.select_one('#info h1, .book-info h1, .detail-title, h1, .btitle h1')
        if title_el:
            title = title_el.get_text(strip=True)
        author = ''
        author_el = soup.select_one('#info p, .book-info .author, .detail-author, p.author')
        if author_el:
            text = author_el.get_text(strip=True)
            if '作者' in text:
                author = text.split('作者')[1].replace('：', '').replace(':', '').strip()
        desc_el = soup.select_one('#intro, .book-intro, .desc, .description, #bookintro, .intro')
        description = desc_el.get_text(strip=True) if desc_el else ''
        chapters = []
        chapter_selectors = [
            '#list dd a',
            '.chapter-list dd a',
            '.mulu dd a',
            '.section-list li a',
            '#chapterlist dd a',
            '.catalog a',
            '.chapters a',
            'ul.list a',
            '.dirlist dd a',
        ]
        chapter_items = []
        for sel in chapter_selectors:
            chapter_items = soup.select(sel)
            if len(chapter_items) >= 3:
                break
        for idx, a in enumerate(chapter_items):
            ch_title = a.get_text(strip=True)
            ch_url = a.get('href', '')
            if ch_title and ch_url:
                chapters.append(ChapterInfo(title=ch_title, url=ch_url, index=idx))
        if not chapters and title:
            return None
        return NovelInfo(
            title=title,
            author=author,
            description=description,
            chapters=chapters,
            source='biquge',
        )

    def parse_chapter_content(self, html: str) -> str:
        soup = BeautifulSoup(html, 'lxml')
        content_el = soup.select_one(
            '#content, .content, .showtxt, #chaptercontent, '
            '.read-content, .article-content, #htmlContent, .novel-content, '
            '#TextContent, .txtnav, #contents'
        )
        if not content_el:
            content_el = soup.select_one('body')
        if not content_el:
            return ''
        return self.strip_html(str(content_el))


class BiqugeSource(BaseSource):
    _parser = BiqugeParser()

    def __init__(self, source_name: str = 'biquge365', base_url: str = 'https://www.biquge365.net'):
        self._name = source_name
        self._base_url = base_url.rstrip('/')
        self._unreachable = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def search_url(self) -> str:
        return f'{self._base_url}/search.php'

    @property
    def is_unreachable(self) -> bool:
        return self._unreachable

    async def _fetch(self, url: str, params: dict = None, encoding: str = 'utf-8') -> str:
        if self._unreachable:
            return ''
        headers = {'User-Agent': USER_AGENT, 'Accept': 'text/html,application/xhtml+xml'}
        timeout = aiohttp.ClientTimeout(total=8, connect=5)
        connector = aiohttp.TCPConnector(ssl=False, force_close=True)
        async with aiohttp.ClientSession(
            timeout=timeout, headers=headers, connector=connector,
        ) as session:
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        return ''
                    data = await resp.read()
                    try:
                        return data.decode(encoding)
                    except (UnicodeDecodeError, LookupError):
                        return data.decode('gbk', errors='ignore')
            except (aiohttp.ClientConnectorError, aiohttp.ClientConnectorDNSError) as e:
                self._unreachable = True
                logger.debug(f'Marked {self._name} unreachable: {e}')
                return ''
            except Exception as e:
                logger.debug(f'Fetch failed {url}: {e}')
                return ''

    async def search(self, keyword: str) -> list[SearchResult]:
        if self._unreachable:
            return []

        encoded = quote(keyword.encode('gbk'), safe='') if any('\u4e00' <= c <= '\u9fff' for c in keyword) else quote(keyword, safe='')
        html = await self._fetch(self.search_url, params={'keyword': keyword})
        if not html and not self._unreachable:
            html = await self._fetch(f'{self._base_url}/modules/article/search.php', params={'searchkey': encoded})
        if not html and not self._unreachable:
            html = await self._fetch(f'{self._base_url}/search.html', params={'q': keyword})
        if not html:
            return []
        results = self._parser.parse_search_results(html)
        for r in results:
            if r.url and not r.url.startswith('http'):
                r.url = urljoin(self._base_url, r.url)
            r.source = self._name
        return results

    async def get_novel_info(self, url: str) -> Optional[NovelInfo]:
        html = await self._fetch(url)
        if not html:
            return None
        info = self._parser.parse_novel_info(html)
        if info:
            info.url = url
            info.source = self._name
            for ch in info.chapters:
                if ch.url and not ch.url.startswith('http'):
                    ch.url = urljoin(url, ch.url)
        return info

    async def get_chapter_content(self, url: str) -> str:
        html = await self._fetch(url)
        if not html:
            return ''
        return self._parser.parse_chapter_content(html)


def create_all_sources() -> list[BiqugeSource]:
    sources = []
    for name, url in BIQUGE_DOMAINS:
        sources.append(BiqugeSource(source_name=name, base_url=url))
    return sources


def create_default_sources() -> list[BiqugeSource]:
    return create_all_sources()
