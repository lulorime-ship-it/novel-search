"""Sample novel source plugin.
Copy this template and modify to add your own novel source.
"""
import logging
from urllib.parse import urljoin, urlparse

from sources.base import BaseSource, SearchResult, NovelInfo, ChapterInfo

logger = logging.getLogger(__name__)


class MyCustomSource(BaseSource):
    """Custom novel source - modify to parse your target website."""

    DOMAIN = "example.com"
    SOURCE_NAME = "MySource"

    @classmethod
    def match(cls, domain: str) -> bool:
        """Return True if this source can handle the given domain."""
        return cls.DOMAIN in domain

    async def get_novel_info(self, url: str) -> NovelInfo | None:
        """Parse novel directory page and return NovelInfo.
        Must extract: title, author, description, list of chapters.
        """
        html = await self._fetch(url)
        if not html:
            return None

        soup = self._parse_html(html)
        if not soup:
            return None

        # TODO: Extract title, author, description
        title = self._extract_first_text(soup, "h1")
        author = self._extract_first_text(soup, ".author")
        description = self._extract_first_text(soup, ".intro")

        # TODO: Extract chapter list
        chapters = []
        for link in soup.select("a[href]"):
            ch_title = link.get_text(strip=True)
            ch_url = urljoin(url, link["href"])
            if ch_title and ch_url:
                chapters.append(ChapterInfo(
                    index=len(chapters),
                    title=ch_title,
                    url=ch_url,
                ))

        return NovelInfo(
            url=url,
            title=title or "Unknown",
            author=author or "Unknown",
            source_name=self.SOURCE_NAME,
            description=description or "",
            chapters=chapters,
        )

    async def get_chapter_content(self, chapter: ChapterInfo) -> str:
        """Fetch and return chapter content (clean text)."""
        html = await self._fetch(chapter.url)
        if not html:
            return ""
        soup = self._parse_html(html)
        if not soup:
            return ""

        # TODO: Extract chapter content
        content_div = soup.select_one("#content")
        if content_div:
            return content_div.get_text("\n", strip=True)
        return ""


def create_source():
    """Factory function - PluginManager calls this to create an instance."""
    return MyCustomSource()
