import re
import hashlib
from collections import OrderedDict


class NovelCleaner:

    AD_PATTERNS = [
        re.compile(r'(?:天才一秒记住|记住本站|一秒记住|笔下文学|笔趣阁|顶点小说|飘天文学|书迷楼|风雨小说网)', re.IGNORECASE),
        re.compile(r'(?:https?://[^\s]*?\.(?:com|cn|net|org|cc|la|tv)[^\s]*)', re.IGNORECASE),
        re.compile(r'(?:手机用户请浏览|电脑版|手机版|m\.[^\s]+)', re.IGNORECASE),
        re.compile(r'(?:请收藏本站|收藏本站|加入书签|加入书架|推荐票|月票|打赏|催更)', re.IGNORECASE),
        re.compile(r'(?:求(?:推荐|收藏|订阅|月票|打赏|鲜花)[!！。，]*)', re.IGNORECASE),
        re.compile(r'(?:新书(?:上传|发布|期间)|求(?:点击|推|一切))', re.IGNORECASE),
        re.compile(r'(?:最新章节|更新最快|最快更新|无弹窗|无广告|免费小说)', re.IGNORECASE),
        re.compile(r'(?:[\(（][^)）]*?(?:未完待续|求收藏|求推荐|求月票|如果喜欢|请收藏)[^)）]*?[\)）])', re.IGNORECASE),
        re.compile(r'(?:PS[:：].*?(?:\n|$))', re.IGNORECASE),
        re.compile(r'(?:看书就(?:来|找)|欢迎.*?(?:阅读|光临|来到).*?(?:小说|阅读))', re.IGNORECASE),
        re.compile(r'(?:搜索引擎.*?(?:小说|阅读)|转码|百度|谷歌|搜狗|360)', re.IGNORECASE),
        re.compile(r'(?:啃书?手机版|啃书?小说|lashu|lashuo|laishu)', re.IGNORECASE),
        re.compile(r'(?:抢个红包|收到红包|收到一个红包|红包到账)', re.IGNORECASE),
        re.compile(r'^\d+/\d+\s*$', re.MULTILINE),
        re.compile(r'^第[一二三四五六七八九十百千\d]+[章节卷].*$', re.MULTILINE),
    ]

    FORMAT_PATTERNS = [
        re.compile(r'\|\s*', re.MULTILINE),
        re.compile(r'^\s*[-=*_#~]{3,}\s*$', re.MULTILINE),
    ]

    SIMILARITY_THRESHOLD = 0.85

    @classmethod
    def clean_chapter_title(cls, title: str) -> str:
        title = title.strip()
        title = re.sub(r'[\(（][^)）]*?(?:求收藏|求推荐|求月票|求订阅|加更|爆更|补更|\d+/?\d+|[一二三四五六七八九十]+更)[^)）]*?[\)）]', '', title)
        title = re.sub(r'\s+', ' ', title)
        return title.strip()

    @classmethod
    def clean_content(cls, text: str) -> str:
        if not text:
            return ''
        text = cls._normalize_whitespace(text)
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if cls._is_ad_line(line):
                continue
            for fmt_pat in cls.FORMAT_PATTERNS:
                line = fmt_pat.sub('', line).strip()
            if line:
                cleaned_lines.append(line)
        cleaned_lines = cls._deduplicate_lines(cleaned_lines)
        paragraphs = cls._lines_to_paragraphs(cleaned_lines)
        paragraphs = cls._deduplicate_paragraphs(paragraphs)
        paragraphs = cls._deduplicate_similar_paragraphs(paragraphs)
        result = '\n\n'.join(paragraphs)
        result = cls._remove_trailing_junk(result)
        return result

    @classmethod
    def _normalize_whitespace(cls, text: str) -> str:
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = re.sub(r'\u3000', '  ', text)
        text = re.sub(r'\xa0', ' ', text)
        text = re.sub(r'\t', '    ', text)
        text = re.sub(r' +', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text

    @classmethod
    def _is_ad_line(cls, line: str) -> bool:
        for pattern in cls.AD_PATTERNS:
            if pattern.search(line):
                return True
        return False

    @classmethod
    def _deduplicate_lines(cls, lines: list[str]) -> list[str]:
        seen = OrderedDict()
        for line in lines:
            key = line.strip().lower()
            if key not in seen:
                seen[key] = line
        return list(seen.values())

    @classmethod
    def _lines_to_paragraphs(cls, lines: list[str]) -> list[str]:
        paragraphs = []
        current = []
        for line in lines:
            if len(line) < 3:
                if current:
                    paragraphs.append(''.join(current))
                    current = []
                paragraphs.append(line)
            else:
                if line.endswith(('。', '！', '？', '”', '…', '——')) and current:
                    current.append(line)
                    paragraphs.append(''.join(current))
                    current = []
                elif current and len(''.join(current)) > 200:
                    current.append(line)
                    paragraphs.append(''.join(current))
                    current = []
                else:
                    current.append(line)
        if current:
            paragraphs.append(''.join(current))
        return [p.strip() for p in paragraphs if p.strip()]

    @classmethod
    def _deduplicate_paragraphs(cls, paragraphs: list[str]) -> list[str]:
        seen = OrderedDict()
        for para in paragraphs:
            key = hashlib.md5(para.encode('utf-8', errors='ignore')).hexdigest()
            if key not in seen:
                seen[key] = para
        return list(seen.values())

    @classmethod
    def _deduplicate_similar_paragraphs(cls, paragraphs: list[str]) -> list[str]:
        if len(paragraphs) < 2:
            return paragraphs
        result = [paragraphs[0]]
        for para in paragraphs[1:]:
            if cls._similar_to_any(para, result[-3:]):
                continue
            result.append(para)
        return result

    @classmethod
    def _similar_to_any(cls, text: str, candidates: list[str]) -> bool:
        if not candidates:
            return False
        text_set = set(text)
        for cand in candidates:
            cand_set = set(cand)
            if not text_set or not cand_set:
                continue
            intersection = text_set & cand_set
            union = text_set | cand_set
            if not union:
                continue
            jaccard = len(intersection) / len(union)
            if jaccard > cls.SIMILARITY_THRESHOLD:
                return True
        return False

    @classmethod
    def _remove_trailing_junk(cls, text: str) -> str:
        lines = text.split('\n')
        while lines and len(lines[-1].strip()) < 10:
            last = lines[-1].strip()
            if last and cls._is_ad_line(last):
                lines.pop()
            else:
                break
        return '\n'.join(lines).strip()
