import re
import hashlib
from collections import OrderedDict


class NovelProcessor:

    SENTENCE_END = frozenset({'。', '！', '？', '…', '”', '』', '」'})
    SENTENCE_PAUSE = frozenset({'，', '、', '；', '：', '）', ')', '》', '〉', '】', ']'})

    LONG_PARAGRAPH_THRESHOLD = 800

    AD_KEYWORDS = [
        '天才一秒记住', '记住本站', '一秒记住', '笔下文学',
        '笔趣阁', '顶点小说', '飘天文学', '书迷楼', '风雨小说网',
        '手机用户请浏览', '电脑版', '手机版',
        '请收藏本站', '收藏本站', '加入书签', '加入书架',
        '推荐票', '月票', '打赏', '催更',
        '最新章节', '更新最快', '最快更新', '无弹窗', '无广告', '免费小说',
        '求推荐', '求收藏', '求订阅', '求月票', '求打赏', '求鲜花',
        '新书上传', '新书发布', '求点击',
        '搜索引擎', '转码', '百度', '谷歌', '搜狗', '360',
        '啃书手机版', '啃书小说',
        '抢个红包', '收到红包', '红包到账',
        '未完待续', '如果喜欢', '看书就来', '看书就找',
        '欢迎阅读', '欢迎光临', '群号', '下载器',
    ]

    @classmethod
    def process_full(cls, text: str,
                     dedup_lines: bool = True,
                     remove_ads: bool = True,
                     smart_format: bool = True,
                     layout_optimize: bool = True,
                     delete_keywords: list[str] | None = None,
                     delete_mode: str = 'line') -> str:
        if not text:
            return ''

        text = cls._normalize_newlines(text)

        if delete_keywords:
            text = cls.delete_by_keywords(text, delete_keywords, mode=delete_mode)

        if remove_ads:
            text = cls.remove_ads(text)

        if smart_format:
            text = cls.smart_format(text)

        if layout_optimize:
            text = cls.layout_optimize(text)

        if dedup_lines:
            text = cls.dedup_lines(text)

        text = cls._final_cleanup(text)
        return text

    # ── normalize ──────────────────────────────────────────────

    @classmethod
    def _normalize_newlines(cls, text: str) -> str:
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = re.sub(r'\n{4,}', '\n\n\n', text)
        return text

    # ── dedup ───────────────────────────────────────────────────

    @classmethod
    def dedup_lines(cls, text: str) -> str:
        lines = text.split('\n')
        result = []
        prev = None
        for line in lines:
            stripped = line.strip()
            if stripped == prev:
                continue
            result.append(line)
            prev = stripped
        return '\n'.join(result)

    @classmethod
    def dedup_paragraphs(cls, text: str) -> str:
        paragraphs = text.split('\n\n')
        seen = OrderedDict()
        for para in paragraphs:
            h = hashlib.md5(para.encode('utf-8', errors='ignore')).hexdigest()
            if h not in seen:
                seen[h] = para
        return '\n\n'.join(seen.values())

    # ── ad removal ──────────────────────────────────────────────

    @classmethod
    def remove_ads(cls, text: str) -> str:
        lines = text.split('\n')
        result = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                result.append(line)
                continue
            if cls._is_ad_line(stripped):
                continue
            result.append(line)
        return '\n'.join(result)

    @classmethod
    def _is_ad_line(cls, line: str) -> bool:
        for kw in cls.AD_KEYWORDS:
            if kw in line:
                return True
        return False

    # ── smart format ────────────────────────────────────────────

    @classmethod
    def smart_format(cls, text: str) -> str:
        lines = text.split('\n')
        merged = []
        buf = ''

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if buf:
                    merged.append(buf)
                    buf = ''
                merged.append('')
                continue

            if cls._is_chapter_header(stripped):
                if buf:
                    merged.append(buf)
                    buf = ''
                merged.append('')
                merged.append(stripped)
                merged.append('')
                continue

            if not buf:
                buf = stripped
                continue

            last_char = buf[-1] if buf else ''
            if last_char in cls.SENTENCE_END:
                merged.append(buf)
                buf = stripped
            elif last_char in cls.SENTENCE_PAUSE:
                buf += stripped
            elif len(buf) > 200:
                if buf[-1] in cls.SENTENCE_PAUSE:
                    buf += stripped
                else:
                    merged.append(buf)
                    buf = stripped
            else:
                buf += stripped

        if buf:
            merged.append(buf)

        return '\n'.join(merged)

    @classmethod
    def _is_chapter_header(cls, line: str) -> bool:
        return bool(re.match(r'^\s*第[一二三四五六七八九十百千零\d]+[章节卷部篇回集]\b', line))

    # ── layout optimize ─────────────────────────────────────────

    @classmethod
    def layout_optimize(cls, text: str) -> str:
        lines = text.split('\n')
        result = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                result.append('')
                continue

            cleaned = cls._clean_line_noise(stripped)
            if not cleaned:
                result.append('')
                continue

            if cls._is_chapter_header(cleaned):
                result.append('')
                result.append(cleaned)
                result.append('')
                continue

            paragraphs = cls._split_long_paragraph(cleaned)
            for para in paragraphs:
                result.append('\u3000\u3000' + para)

        return '\n'.join(result)

    @classmethod
    def _clean_line_noise(cls, line: str) -> str:
        line = re.sub(r'^\s+', '', line)
        line = re.sub(r'\s+$', '', line)
        line = re.sub(r'[|]{2,}', '', line)
        line = re.sub(r'\s{2,}', '', line)
        line = re.sub(r'^\d+/\d+\s*$', '', line)
        return line.strip()

    @classmethod
    def _split_long_paragraph(cls, text: str) -> list[str]:
        if len(text) <= cls.LONG_PARAGRAPH_THRESHOLD:
            return [text]
        result = []
        current = ''
        for ch in text:
            current += ch
            if ch in cls.SENTENCE_END and len(current) > 200:
                result.append(current)
                current = ''
        if current:
            result.append(current)
        return result if result else [text]

    # ── final cleanup ───────────────────────────────────────────

    @classmethod
    def _final_cleanup(cls, text: str) -> str:
        text = re.sub(r'\n{4,}', '\n\n\n', text)
        text = re.sub(r'^\n+', '', text)
        text = re.sub(r'\n+$', '', text)
        return text

    # ── delete user keywords ────────────────────────────────────

    DELETE_KEYWORD = 'keyword'
    DELETE_SENTENCE = 'sentence'
    DELETE_LINE = 'line'

    @classmethod
    def delete_by_keywords(cls, text: str, keywords: list[str],
                           mode: str = 'line') -> str:
        if not keywords:
            return text
        if mode == cls.DELETE_KEYWORD:
            return cls._delete_kw_text(text, keywords)
        elif mode == cls.DELETE_SENTENCE:
            return cls._delete_kw_sentence(text, keywords)
        else:
            return cls._delete_kw_line(text, keywords)

    @classmethod
    def _delete_kw_text(cls, text: str, keywords: list[str]) -> str:
        for kw in keywords:
            if not kw:
                continue
            text = text.replace(kw, '')
        text = re.sub(r'  +', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text

    @classmethod
    def _delete_kw_sentence(cls, text: str, keywords: list[str]) -> str:
        lines = text.split('\n')
        result = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                result.append(line)
                continue
            if not any(kw and kw in stripped for kw in keywords):
                result.append(line)
                continue
            sentences = cls._split_sentences(stripped)
            kept = [s for s in sentences
                    if not any(kw and kw in s for kw in keywords)]
            if kept:
                result.append(''.join(kept))
        return '\n'.join(result)

    @classmethod
    def _split_sentences(cls, text: str) -> list[str]:
        result = []
        buf = ''
        for ch in text:
            buf += ch
            if ch in ('。', '！', '？', '…'):
                result.append(buf)
                buf = ''
        if buf:
            result.append(buf)
        return result if result else [text]

    @classmethod
    def _delete_kw_line(cls, text: str, keywords: list[str]) -> str:
        lines = text.split('\n')
        result = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                result.append(line)
                continue
            if any(kw and kw in stripped for kw in keywords):
                continue
            result.append(line)
        return '\n'.join(result)

    # ── convenience methods for UI ──────────────────────────────

    @classmethod
    def get_stats(cls, before: str, after: str) -> dict:
        return {
            'chars_before': len(before),
            'chars_after': len(after),
            'lines_before': len(before.split('\n')),
            'lines_after': len(after.split('\n')),
            'reduction': (1 - len(after) / max(len(before), 1)) * 100,
        }