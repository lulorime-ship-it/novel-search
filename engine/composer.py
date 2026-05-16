import os
import re
from datetime import datetime
from pathlib import Path

from sources.base import ChapterInfo
from engine.cleaner import NovelCleaner
from utils.helpers import safe_filename


class NovelComposer:

    def __init__(self, output_dir: str = 'downloads'):
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def compose(
        self,
        novel_title: str,
        novel_author: str,
        chapters: list[tuple[ChapterInfo, str]],
        intro: str = '',
    ) -> str:
        safe_title = safe_filename(novel_title)
        filename = f'{safe_title}.txt'
        filepath = self._output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f'《{novel_title}》\n')
            if novel_author:
                f.write(f'作者：{novel_author}\n')
            f.write(f'生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write('=' * 50 + '\n\n')
            if intro:
                clean_intro = NovelCleaner.clean_content(intro)
                f.write(f'【内容简介】\n{clean_intro}\n\n')
                f.write('=' * 50 + '\n\n')

            valid_chapters = 0
            for ch_info, raw_content in chapters:
                title = NovelCleaner.clean_chapter_title(ch_info.title)
                content = NovelCleaner.clean_content(raw_content)
                if not content or len(content) < 50:
                    continue
                valid_chapters += 1
                f.write(f'{title}\n')
                f.write('-' * 30 + '\n\n')
                f.write(content)
                f.write('\n\n')

            if valid_chapters == 0:
                f.write('（未能获取到有效章节内容）\n')

        return str(filepath.resolve())

    def get_chapter_files_dir(self, novel_title: str) -> Path:
        safe_title = safe_filename(novel_title)
        ch_dir = self._output_dir / safe_title / 'chapters'
        ch_dir.mkdir(parents=True, exist_ok=True)
        return ch_dir

    def save_individual_chapters(
        self,
        novel_title: str,
        chapters: list[tuple[ChapterInfo, str]],
    ) -> list[str]:
        ch_dir = self.get_chapter_files_dir(novel_title)
        saved = []
        for ch_info, raw_content in chapters:
            title = NovelCleaner.clean_chapter_title(ch_info.title)
            content = NovelCleaner.clean_content(raw_content)
            if not content or len(content) < 50:
                continue
            safe_ch = safe_filename(f'{ch_info.index:04d}_{title}')
            ch_path = ch_dir / f'{safe_ch}.txt'
            with open(ch_path, 'w', encoding='utf-8') as f:
                f.write(f'{title}\n\n{content}\n')
            saved.append(str(ch_path))
        return saved
