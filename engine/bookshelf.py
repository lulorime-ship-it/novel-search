import os
import json
import shutil
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

TAG_CATEGORIES = [
    '玄幻', '言情', '科幻', '武侠', '都市',
    '历史', '游戏', '悬疑', '轻小说', '奇幻',
    '军事', '竞技', '同人', '其他',
]


@dataclass
class BookshelfItem:
    id: str
    title: str
    author: str
    file_path: str
    file_type: str
    tags: list[str] = field(default_factory=lambda: ['其他'])
    read_progress: float = 0.0
    total_chars: int = 0
    date_added: str = ''

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'BookshelfItem':
        fields = cls.__dataclass_fields__
        return cls(**{k: d.get(k) for k in fields if k in d})


class BookshelfManager:

    def __init__(self, data_dir: str = ''):
        self._data_dir = Path(data_dir) if data_dir else Path.cwd() / 'bookshelf'
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._data_dir / 'index.json'
        self._items: dict[str, BookshelfItem] = {}
        self._load()

    def _load(self):
        if self._index_path.exists():
            try:
                with open(self._index_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for item_data in data:
                    item = BookshelfItem.from_dict(item_data)
                    if os.path.isfile(item.file_path):
                        self._items[item.id] = item
            except Exception as e:
                logger.error(f"Failed to load bookshelf index: {e}")

    def _save(self):
        try:
            with open(self._index_path, 'w', encoding='utf-8') as f:
                json.dump([item.to_dict() for item in self._items.values()],
                          f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save bookshelf index: {e}")

    @property
    def items(self) -> list[BookshelfItem]:
        return list(self._items.values())

    def get_items_by_tag(self, tag: str) -> list[BookshelfItem]:
        if tag == '全部':
            return self.items
        return [item for item in self._items.values() if tag in item.tags]

    def add_book(self, file_path: str, title: str = '', author: str = '',
                 tags: list[str] | None = None) -> BookshelfItem | None:
        if not os.path.isfile(file_path):
            return None

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in ('.txt', '.epub'):
            return None

        if not title:
            title = os.path.splitext(os.path.basename(file_path))[0]

        import uuid
        from datetime import datetime

        stored_path = self._data_dir / os.path.basename(file_path)
        if not stored_path.exists() or str(stored_path) != str(file_path):
            try:
                shutil.copy2(file_path, str(stored_path))
            except shutil.SameFileError:
                pass

        item_id = str(uuid.uuid4())[:8]
        item = BookshelfItem(
            id=item_id,
            title=title,
            author=author,
            file_path=str(stored_path),
            file_type=ext[1:],
            tags=tags or ['其他'],
            read_progress=0.0,
            total_chars=self._count_chars(str(stored_path)),
            date_added=datetime.now().strftime('%Y-%m-%d'),
        )
        self._items[item_id] = item
        self._save()
        return item

    def remove_book(self, item_id: str) -> bool:
        if item_id not in self._items:
            return False
        item = self._items.pop(item_id)
        self._save()
        return True

    def update_progress(self, item_id: str, progress: float):
        if item_id in self._items:
            self._items[item_id].read_progress = min(100.0, max(0.0, progress))
            self._save()

    def update_tags(self, item_id: str, tags: list[str]):
        if item_id in self._items:
            self._items[item_id].tags = tags
            self._save()

    def get_book(self, item_id: str) -> BookshelfItem | None:
        return self._items.get(item_id)

    def _count_chars(self, file_path: str) -> int:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return len(f.read())
        except Exception:
            return 0