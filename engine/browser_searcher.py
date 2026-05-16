import re
import asyncio
import logging
from urllib.parse import quote, urlparse
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup

from sources.base import SearchResult

logger = logging.getLogger(__name__)

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/121.0.0.0 Safari/537.36'
)

NON_NOVEL_DOMAINS = {
    'zhihu.com', 'tieba.baidu.com', 'zhidao.baidu.com',
    'douban.com', 'baike.baidu.com', 'baike.com',
    'qidian.com', 'zongheng.com', 'jjwxc.net',
    'baidu.com', 'bing.com', 'wikipedia.org',
    'sohu.com', 'sina.com.cn', '163.com', 'qq.com',
    'jd.com', 'taobao.com', 'tmall.com', 'pinduoduo.com',
    'weibo.com', 'weixin.qq.com', 'renren.com',
}

CHAPTER_SIGNALS = [
    r'第[一二三四五六七八九十百千零\d]+[章节卷部篇回]',
    r'最新章节',
    r'章节列表',
    r'章节目录',
    r'正文卷',
    r'正文目录',
    r'目录列表',
    r'小说目录',
    r'分卷阅读',
    r'全文阅读',
    r'上一章',
    r'下一章',
]

SEARCH_ENGINE_CONFIGS = {
    'bing': {
        'url': 'https://www.bing.com/search?q={query}&count=20',
        'selector': '#b_results > li.b_algo',
    },
    'baidu': {
        'url': 'https://www.baidu.com/s?wd={query}',
        'selector': '#content_left > .result',
    },
    'google': {
        'url': 'https://www.google.com/search?q={query}&num=20',
        'selector': '#search .g',
    },
    'yahoo': {
        'url': 'https://search.yahoo.com/search?p={query}',
        'selector': '#web .algo',
    },
    '360': {
        'url': 'https://www.so.com/s?q={query}',
        'selector': '.result',
    },
    'sogou': {
        'url': 'https://www.sogou.com/web?query={query}',
        'selector': '.results .vrwrap',
    },
    'quark': {
        'url': 'https://quark.sm.cn/s?q={query}',
        'selector': '.result',
    },
}


class BrowserSearcher:

    def __init__(self):
        self._diagnostics: dict = {}

    def get_diagnostics(self) -> dict:
        return dict(self._diagnostics)

    async def _fetch(self, url: str, timeout_sec: float = 8.0) -> str:
        timeout = aiohttp.ClientTimeout(total=timeout_sec, connect=5)
        headers = {
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        connector = aiohttp.TCPConnector(ssl=False, force_close=True, limit=1)
        async with aiohttp.ClientSession(
            timeout=timeout, headers=headers, connector=connector,
        ) as session:
            try:
                async with session.get(url, allow_redirects=True) as resp:
                    if resp.status != 200:
                        return ''
                    data = await resp.read()
                    for enc in ('utf-8', 'gbk', 'gb2312', 'gb18030'):
                        try:
                            return data.decode(enc)
                        except (UnicodeDecodeError, LookupError):
                            continue
                    return data.decode('utf-8', errors='ignore')
            except (asyncio.TimeoutError, aiohttp.ClientError, OSError) as e:
                logger.debug(f'Fetch failed: {url[:70]}: {e}')
                return ''

    async def search(self, keyword: str, max_results: int = 15, engine_code: str = 'bing') -> list[SearchResult]:
        self._diagnostics = {'keyword': keyword, 'steps': [], 'engine': engine_code}
        if not keyword.strip():
            return []

        engine_cfg = SEARCH_ENGINE_CONFIGS.get(engine_code, SEARCH_ENGINE_CONFIGS['bing'])
        search_url_template = engine_cfg['url']
        result_selector = engine_cfg['selector']

        all_urls: dict[str, tuple[str, str]] = {}

        search_terms = [
            (f'{keyword} 笔趣阁', '笔趣阁'),
            (f'{keyword} 小说 最新章节', '最新章节'),
            (f'{keyword} 小说 全文阅读', '全文阅读'),
            (keyword, '简洁'),
        ]

        for term, label in search_terms:
            url = search_url_template.format(query=quote(term, safe=''))
            engine_label = engine_code.upper()
            logger.info(f'{engine_label}搜索: "{label}" → {url[:90]}')
            self._diagnostics['steps'].append(f'{engine_label}: "{label}"')

            html = await self._fetch(url)
            if not html:
                self._diagnostics['steps'].append(f'  ↳ 无响应')
                continue

            urls = self._extract_links(html, result_selector)
            self._diagnostics['steps'].append(f'  ↳ {len(urls)}个候选URL')
            for href, text in urls:
                if href not in all_urls:
                    all_urls[href] = (text, label)
            if len(all_urls) >= max_results * 2:
                break

        self._diagnostics['candidates'] = len(all_urls)
        engine_label = engine_code.upper()
        logger.info(f'{engine_label}总共找到 {len(all_urls)} 个候选URL')

        results = []
        urls_to_check = list(all_urls.keys())[:max_results * 2]
        for url in urls_to_check:
            title_hint, _ = all_urls[url]
            logger.debug(f'验证: {url[:80]}')
            result = await self._verify(url, title_hint, keyword)
            if result:
                results.append(result)
                if len(results) >= max_results:
                    break

        self._diagnostics['results'] = len(results)
        logger.info(f'最终有效结果: {len(results)}')
        return results

    def _extract_links(self, html: str, selector: str) -> list[tuple[str, str]]:
        soup = BeautifulSoup(html, 'lxml')
        items = soup.select(selector)
        links = []
        seen = set()
        for item in items:
            for a in item.select('a[href]'):
                href = a.get('href', '').strip()
                if not href or not href.startswith('http'):
                    continue
                domain = urlparse(href).netloc.lower()
                if domain in NON_NOVEL_DOMAINS:
                    continue
                if any(bad in domain for bad in NON_NOVEL_DOMAINS):
                    continue
                parsed = urlparse(href)
                normalized = f'{parsed.scheme}://{domain}{parsed.path.rstrip("/")}'
                if normalized in seen:
                    continue
                seen.add(normalized)
                text = a.get_text(strip=True)
                if text and len(text) >= 2:
                    links.append((normalized, text))
        return links[:20]

    async def _verify(self, url: str, title_hint: str, keyword: str) -> Optional[SearchResult]:
        html = await self._fetch(url, timeout_sec=6.0)
        if not html or len(html) < 200:
            return None
        soup = BeautifulSoup(html, 'lxml')
        page_text = soup.get_text()

        chapter_count = 0
        for pat in CHAPTER_SIGNALS:
            chapter_count += len(re.findall(pat, page_text))
        if chapter_count < 1:
            return None

        title = self._extract_title(soup) or title_hint
        title_l = title.lower().replace(' ', '')
        kw_l = keyword.lower().replace(' ', '')
        if self._fuzzy_match(kw_l, title_l) < 0.15 and len(keyword) >= 2:
            return None

        author = self._extract_author(soup)
        latest = self._extract_latest(soup)

        return SearchResult(
            title=title,
            author=author,
            url=url,
            latest_chapter=latest,
            source=_domain_label(url),
        )

    def _fuzzy_match(self, kw: str, title: str) -> float:
        if not kw or not title:
            return 0.0
        if kw in title or title in kw:
            return 1.0
        overlap = set(kw) & set(title)
        return len(overlap) / max(len(set(kw)), 1) if overlap else 0.0

    def _extract_title(self, soup: BeautifulSoup) -> str:
        for sel in ('#info h1', '.book-info h1', 'h1', '.btitle h1',
                     '.detail-title', '#bookname h1', 'meta[property="og:title"]'):
            el = soup.select_one(sel)
            if el:
                t = el.get_text(strip=True) if el.name != 'meta' else el.get('content', '')
                if 2 <= len(t) <= 60 and t not in ('笔趣阁', '笔趣阁网', '首页'):
                    return t
        t = soup.select_one('title')
        if t:
            text = t.get_text(strip=True)
            for sep in (' - ', ' | ', '_', '—', ',', '，'):
                if sep in text and len(text.split(sep)[0].strip()) >= 2:
                    first = text.split(sep)[0].strip()
                    if first not in ('笔趣阁', '笔趣阁网'):
                        return first
            if 2 <= len(text) <= 60 and text not in ('笔趣阁', '笔趣阁网'):
                return text
        return ''

    def _extract_author(self, soup: BeautifulSoup) -> str:
        for sel in ('#info p', '.book-info .author', '.detail-author',
                     'p.author', '.writer', 'meta[property="og:novel:author"]'):
            el = soup.select_one(sel)
            if el:
                text = el.get_text(strip=True) if el.name != 'meta' else el.get('content', '')
                for p in ('作者：', '作者:', '作    者：'):
                    if p in text:
                        return text.split(p, 1)[1].strip()
        return ''

    def _extract_latest(self, soup: BeautifulSoup) -> str:
        for sel in ('#list dd:last-child a', '.chapter-list dd:last-child a',
                     '.mulu dd:last-child a', '#chapterlist dd:last-child a',
                     '#list a:last-child'):
            el = soup.select_one(sel)
            if el:
                return el.get_text(strip=True)
        return ''


def _domain_label(url: str) -> str:
    return urlparse(url).netloc.replace('www.', '').split('.')[0]


_browser_searcher: Optional[BrowserSearcher] = None


def get_browser_searcher() -> BrowserSearcher:
    global _browser_searcher
    if _browser_searcher is None:
        _browser_searcher = BrowserSearcher()
    return _browser_searcher
