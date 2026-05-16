from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import re


@dataclass
class SearchResult:
    title: str
    author: str = ''
    url: str = ''
    latest_chapter: str = ''
    update_time: str = ''
    source: str = ''


@dataclass
class ChapterInfo:
    title: str
    url: str
    index: int = 0


@dataclass
class NovelInfo:
    title: str = ''
    author: str = ''
    url: str = ''
    cover: str = ''
    description: str = ''
    chapters: list[ChapterInfo] = field(default_factory=list)
    source: str = ''


class BaseSource(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def base_url(self) -> str:
        ...

    @property
    @abstractmethod
    def search_url(self) -> str:
        ...

    @abstractmethod
    async def search(self, keyword: str) -> list[SearchResult]:
        ...

    @abstractmethod
    async def get_novel_info(self, url: str) -> Optional[NovelInfo]:
        ...

    @abstractmethod
    async def get_chapter_content(self, url: str) -> str:
        ...


class BaseParser(ABC):

    @abstractmethod
    def parse_search_results(self, html: str) -> list[SearchResult]:
        ...

    @abstractmethod
    def parse_novel_info(self, html: str) -> Optional[NovelInfo]:
        ...

    @abstractmethod
    def parse_chapter_content(self, html: str) -> str:
        ...

    def strip_html(self, html: str) -> str:
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&quot;', '"', text)
        text = re.sub(r'&#?\w+;', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()
