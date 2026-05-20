import os
import sys
import json
import importlib.util
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class PluginInfo:
    def __init__(self, name: str, path: str, source: dict):
        self.name = name
        self.path = path
        self.description = source.get('description', '')
        self.version = source.get('version', '1.0')
        self.author = source.get('author', '')
        self.enabled = source.get('enabled', True)
        self.domain = source.get('domain', '')
        self.script_path = os.path.join(path, source.get('script', 'source.py'))
        self._instance = None

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'description': self.description,
            'version': self.version,
            'author': self.author,
            'enabled': self.enabled,
            'domain': self.domain,
        }

    def load(self):
        if not self.enabled:
            return None
        script_path = self.script_path
        if not os.path.isfile(script_path):
            logger.error(f"Plugin script not found: {script_path}")
            return None

        try:
            spec = importlib.util.spec_from_file_location(
                f"plugin_{self.name}", script_path
            )
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"plugin_{self.name}"] = module
            spec.loader.exec_module(module)

            if hasattr(module, 'create_source'):
                self._instance = module.create_source()
                return self._instance
        except Exception as e:
            logger.error(f"Failed to load plugin '{self.name}': {e}")
            return None

    def get_instance(self):
        return self._instance


class PluginManager:

    def __init__(self):
        self._plugins_dir = self._get_plugins_dir()
        self._plugins_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._plugins_dir / 'plugins.json'
        self._plugins: dict[str, PluginInfo] = {}
        self._load_index()
        self._discover()

    def _get_plugins_dir(self) -> Path:
        if getattr(sys, 'frozen', False):
            base = Path(os.path.dirname(sys.executable))
        else:
            base = Path(__file__).parent.parent
        return base / 'plugins'

    def _load_index(self):
        if self._index_path.exists():
            try:
                with open(self._index_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for entry in data:
                    name = entry.get('name', '')
                    if name:
                        plugin_dir = self._plugins_dir / name
                        self._plugins[name] = PluginInfo(
                            name=name,
                            path=str(plugin_dir),
                            source=entry,
                        )
            except Exception as e:
                logger.error(f"Failed to load plugin index: {e}")

    def _save_index(self):
        try:
            data = [p.to_dict() for p in self._plugins.values()]
            with open(self._index_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save plugin index: {e}")

    def _discover(self):
        if not self._plugins_dir.exists():
            return
        for entry in self._plugins_dir.iterdir():
            if not entry.is_dir():
                continue
            plugin_json = entry / 'plugin.json'
            if not plugin_json.is_file():
                continue
            try:
                with open(plugin_json, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                name = info.get('name', entry.name)
                if name not in self._plugins:
                    self._plugins[name] = PluginInfo(
                        name=name,
                        path=str(entry),
                        source=info,
                    )
                    self._save_index()
            except Exception as e:
                logger.error(f"Failed to discover plugin in {entry}: {e}")

    @property
    def plugins(self) -> list[PluginInfo]:
        return list(self._plugins.values())

    def get_plugin(self, name: str) -> Optional[PluginInfo]:
        return self._plugins.get(name)

    def enable_plugin(self, name: str) -> bool:
        plugin = self._plugins.get(name)
        if plugin:
            plugin.enabled = True
            self._save_index()
            return True
        return False

    def disable_plugin(self, name: str) -> bool:
        plugin = self._plugins.get(name)
        if plugin:
            plugin.enabled = False
            self._save_index()
            return True
        return False

    def install_plugin(self, script_path: str) -> Optional[PluginInfo]:
        if not os.path.isfile(script_path):
            return None

        script_dir = os.path.dirname(script_path)
        plugin_json_path = os.path.join(script_dir, 'plugin.json')

        info = {}
        if os.path.isfile(plugin_json_path):
            try:
                with open(plugin_json_path, 'r', encoding='utf-8') as f:
                    info = json.load(f)
            except Exception:
                pass

        name = info.get('name', os.path.splitext(os.path.basename(script_path))[0])
        plugin_dir = self._plugins_dir / name
        plugin_dir.mkdir(parents=True, exist_ok=True)

        dest_script = plugin_dir / 'source.py'
        with open(script_path, 'r', encoding='utf-8') as src:
            with open(dest_script, 'w', encoding='utf-8') as dst:
                dst.write(src.read())

        info['script'] = 'source.py'
        plugin_json = plugin_dir / 'plugin.json'
        with open(plugin_json, 'w', encoding='utf-8') as f:
            json.dump(info, f, ensure_ascii=False, indent=2)

        plugin = PluginInfo(name=name, path=str(plugin_dir), source=info)
        self._plugins[name] = plugin
        self._save_index()
        return plugin

    def uninstall_plugin(self, name: str) -> bool:
        if name not in self._plugins:
            return False
        del self._plugins[name]
        self._save_index()

        plugin_dir = self._plugins_dir / name
        if plugin_dir.exists():
            import shutil
            shutil.rmtree(plugin_dir, ignore_errors=True)

        return True

    def load_all_sources(self) -> list:
        sources = []
        for plugin in self._plugins.values():
            instance = plugin.load()
            if instance:
                sources.append(instance)
        return sources

    def create_sample_plugin(self) -> str:
        sample_dir = self._plugins_dir / 'sample_source'
        sample_dir.mkdir(parents=True, exist_ok=True)

        source_py = sample_dir / 'source.py'
        sample_code = (
            '"""Sample novel source plugin.\n'
            'Copy this template and modify to add your own novel source.\n'
            '"""\n'
            'import logging\n'
            'from urllib.parse import urljoin, urlparse\n'
            '\n'
            'from sources.base import BaseSource, SearchResult, NovelInfo, ChapterInfo\n'
            '\n'
            'logger = logging.getLogger(__name__)\n'
            '\n'
            '\n'
            'class MyCustomSource(BaseSource):\n'
            '    """Custom novel source - modify to parse your target website."""\n'
            '\n'
            '    DOMAIN = "example.com"\n'
            '    SOURCE_NAME = "MySource"\n'
            '\n'
            '    @classmethod\n'
            '    def match(cls, domain: str) -> bool:\n'
            '        """Return True if this source can handle the given domain."""\n'
            '        return cls.DOMAIN in domain\n'
            '\n'
            '    async def get_novel_info(self, url: str) -> NovelInfo | None:\n'
            '        """Parse novel directory page and return NovelInfo.\n'
            '        Must extract: title, author, description, list of chapters.\n'
            '        """\n'
            '        html = await self._fetch(url)\n'
            '        if not html:\n'
            '            return None\n'
            '\n'
            '        soup = self._parse_html(html)\n'
            '        if not soup:\n'
            '            return None\n'
            '\n'
            '        # TODO: Extract title, author, description\n'
            '        title = self._extract_first_text(soup, "h1")\n'
            '        author = self._extract_first_text(soup, ".author")\n'
            '        description = self._extract_first_text(soup, ".intro")\n'
            '\n'
            '        # TODO: Extract chapter list\n'
            '        chapters = []\n'
            '        for link in soup.select("a[href]"):\n'
            '            ch_title = link.get_text(strip=True)\n'
            '            ch_url = urljoin(url, link["href"])\n'
            '            if ch_title and ch_url:\n'
            '                chapters.append(ChapterInfo(\n'
            '                    index=len(chapters),\n'
            '                    title=ch_title,\n'
            '                    url=ch_url,\n'
            '                ))\n'
            '\n'
            '        return NovelInfo(\n'
            '            url=url,\n'
            '            title=title or "Unknown",\n'
            '            author=author or "Unknown",\n'
            '            source_name=self.SOURCE_NAME,\n'
            '            description=description or "",\n'
            '            chapters=chapters,\n'
            '        )\n'
            '\n'
            '    async def get_chapter_content(self, chapter: ChapterInfo) -> str:\n'
            '        """Fetch and return chapter content (clean text)."""\n'
            '        html = await self._fetch(chapter.url)\n'
            '        if not html:\n'
            '            return ""\n'
            '        soup = self._parse_html(html)\n'
            '        if not soup:\n'
            '            return ""\n'
            '\n'
            '        # TODO: Extract chapter content\n'
            '        content_div = soup.select_one("#content")\n'
            '        if content_div:\n'
            '            return content_div.get_text("\\n", strip=True)\n'
            '        return ""\n'
            '\n'
            '\n'
            'def create_source():\n'
            '    """Factory function - PluginManager calls this to create an instance."""\n'
            '    return MyCustomSource()\n'
        )
        with open(source_py, 'w', encoding='utf-8') as f:
            f.write(sample_code)

        plugin_json = sample_dir / 'plugin.json'
        sample_info = {
            'name': 'sample_source',
            'description': 'Sample plugin - modify source.py to add a custom novel source',
            'version': '1.0',
            'author': 'Your Name',
            'domain': 'example.com',
            'script': 'source.py',
            'enabled': False,
        }
        with open(plugin_json, 'w', encoding='utf-8') as f:
            json.dump(sample_info, f, ensure_ascii=False, indent=2)

        return str(sample_dir)