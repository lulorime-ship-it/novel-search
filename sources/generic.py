import asyncio
import logging
import re
from urllib.parse import quote, urljoin
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup

from sources.base import BaseSource, BaseParser, SearchResult, NovelInfo, ChapterInfo
from sources.biquge import BiqugeParser

logger = logging.getLogger(__name__)

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)

CHAPTER_SELECTORS = [
    '#list dd a',
    '#chapterlist dd a',
    '.chapter-list a',
    'ul.list a',
    '.mulu a',
    '#chapters a',
    '.catalog a',
    '.section-list li a',
    '.dirlist dd a',
    '.mulu dd a',
    '.chapterlist dd a',
    '.chapter li a',
    '.novel-list dd a',
    '#ul_all_chapters a',
    '.book-list a',
    '#chapters-list a',
    'div#list a',
    '.listmain dd a',
    '.book_last dl dd a',
    '.infoindex dd a',
    '.chapter a',
    '.chapters a',
    'dl.chapter a',
    '.book-chapter-list a',
    '.novel-content-list a',
]

CONTENT_SELECTORS = [
    '#content', '.content', '.showtxt', '#chaptercontent',
    '.read-content', '.article-content', '#htmlContent', '.novel-content',
    '#TextContent', '.txtnav', '#contents', '.bookcontent',
    '#chapterContent', '.chapter-content', '.reader-content',
    '.content-wrap', '#read-content', '.readbox',
    '.noveltext', '#text', '.article', '.post-content',
    '.entry-content', 'article',
]

CHAPTER_TITLE_PATTERNS = [
    re.compile(r'第[一二三四五六七八九十百千零\d]+[章节卷部篇回集]'),
    re.compile(r'^[第序终卷][一二三四五六七八九十百千零\d]+'),
    re.compile(r'Chapter\s*\d+', re.IGNORECASE),
    re.compile(r'^\d+[\.\、\s]'),
]

TITLE_SELECTORS = [
    '#info h1',
    '.book-info h1',
    '.book-title',
    '.detail-title h1',
    '.btitle h1',
    '.novel-title',
    '.bookname h1',
    '.book-name',
    'h1',
    'title',
]

AUTHOR_PATTERNS = [
    '#info p',
    '.book-info .author',
    '.detail-author',
    'p.author',
    '.book-author',
    '.writer',
    '#author',
    '.novel-author',
]


class GenericSource(BaseSource):
    _parser = BiqugeParser()

    @property
    def name(self) -> str:
        return 'generic'

    @property
    def base_url(self) -> str:
        return ''

    @property
    def search_url(self) -> str:
        return ''

    async def _fetch(self, url: str, params: dict = None, encoding: str = 'utf-8') -> str:
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
            except Exception as e:
                logger.debug(f'Fetch failed {url}: {e}')
                return ''

    async def search(self, keyword: str) -> list[SearchResult]:
        return []

    def _detect_title(self, soup: BeautifulSoup) -> str:
        for sel in TITLE_SELECTORS:
            el = soup.select_one(sel)
            if el:
                if sel == 'title':
                    text = el.get_text(strip=True)
                    for sep in [' - ', ' | ', '—', '_']:
                        if sep in text:
                            return text.split(sep)[0].strip()
                    return text
                text = el.get_text(strip=True)
                if text and len(text) >= 2:
                    return text
        return ''

    def _detect_author(self, soup: BeautifulSoup) -> str:
        meta_author = soup.select_one('meta[name="author"], meta[property="og:novel:author"], meta[property="book:author"]')
        if meta_author:
            content = meta_author.get('content', '')
            if content:
                return content.strip()

        for sel in AUTHOR_PATTERNS:
            els = soup.select(sel)
            for el in els:
                text = el.get_text(strip=True)
                if '作者' in text:
                    author = text.split('作者')[1]
                    author = author.replace('：', '').replace(':', '').strip()
                    if author:
                        return author
        return ''

    def _detect_description(self, soup: BeautifulSoup) -> str:
        desc_sel = soup.select_one('#intro, .book-intro, .desc, .description, #bookintro, .intro, .novel-desc, #book-description')
        if desc_sel:
            return desc_sel.get_text(strip=True)

        meta_desc = soup.select_one('meta[name="description"], meta[property="og:description"]')
        if meta_desc:
            content = meta_desc.get('content', '')
            if content:
                return content.strip()
        return ''

    def _detect_chapters(self, soup: BeautifulSoup, base_url: str) -> list[ChapterInfo]:
        best_items = []
        best_sel = ''

        for sel in CHAPTER_SELECTORS:
            items = soup.select(sel)
            if len(items) > len(best_items):
                best_items = items
                best_sel = sel

        if len(best_items) < 3:
            candidates = self._scan_all_links(soup)
            if len(candidates) > len(best_items):
                best_items = candidates
                best_sel = 'fallback'

        chapters = []
        seen_urls = set()
        for idx, a in enumerate(best_items):
            ch_title = a.get_text(strip=True)
            ch_url = a.get('href', '')
            if not ch_title or not ch_url:
                continue
            if ch_url.startswith('javascript:') or ch_url == '#':
                continue
            ch_url = urljoin(base_url, ch_url)
            if ch_url in seen_urls:
                continue
            seen_urls.add(ch_url)

            is_chapter = any(p.search(ch_title) for p in CHAPTER_TITLE_PATTERNS)
            if best_sel == 'fallback' and not is_chapter:
                continue

            chapters.append(ChapterInfo(title=ch_title, url=ch_url, index=idx))

        logger.debug(f'Detected {len(chapters)} chapters via "{best_sel}" from {base_url}')
        return chapters

    @staticmethod
    def _scan_all_links(soup: BeautifulSoup) -> list:
        all_links = soup.select('a[href]')
        candidates = []
        for a in all_links:
            href = a.get('href', '')
            text = a.get_text(strip=True)
            if not text or not href:
                continue
            if href.startswith('javascript:') or href == '#':
                continue
            if any(p.search(text) for p in CHAPTER_TITLE_PATTERNS):
                candidates.append(a)
            elif '.html' in href or '.htm' in href:
                candidates.append(a)
        return candidates

    async def get_novel_info(self, url: str) -> Optional[NovelInfo]:
        html = await self._fetch(url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'lxml')

        title = self._detect_title(soup)
        author = self._detect_author(soup)
        description = self._detect_description(soup)
        chapters = self._detect_chapters(soup, url)

        if not title and not chapters:
            return None

        return NovelInfo(
            title=title,
            author=author,
            url=url,
            description=description,
            chapters=chapters,
            source='generic',
        )

    async def get_chapter_content(self, url: str) -> str:
        html = await self._fetch(url)
        if not html:
            return ''
        soup = BeautifulSoup(html, 'lxml')
        for sel in CONTENT_SELECTORS:
            content_el = soup.select_one(sel)
            if content_el:
                return self._parser.strip_html(str(content_el))
        return self._parser.strip_html(str(soup.find('body') or ''))