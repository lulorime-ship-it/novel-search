# Novel Search & Download System v2.0

## Overview

Novel Search & Download System is a PySide6 + asyncio based novel search and download tool. It automatically discovers novel sites via multiple search engines, crawls all chapter content, removes ads and duplicate paragraphs, and combines them into a complete TXT file. Advanced features include bookshelf management, TTS voice reading, and a plugin system for custom sources.

## Features

- 🔍 **Smart Search** — 7 search engines: Bing / Baidu / Google / Yahoo / 360 / Sogou / Quark
- 🌐 **Generic Source Adapter** — Auto-detects novels from any website URL, no longer limited to specific sites
- 📥 **Batch Download** — Async concurrent downloads with chapter checkboxes, range selection, and select all/invert
- 💾 **Checkpoint Resume** — Each chapter saved to disk immediately with checkpoint.json; resume from interruption
- 🔄 **Retry Mechanism** — One-click retry for failed chapters without re-downloading successful ones
- 🧹 **Text Processor** — Deduplicate lines, remove ads, smart formatting, layout optimization, keyword deletion (line/sentence/keyword modes)
- 📖 **Streaming Preview** — Progressive chunk loading (100KB/30ms) for large files; real-time progress in title bar
- 📚 **Bookshelf Manager** — Drag & drop TXT/EPUB files, tag-based filtering (Fantasy, Romance, Sci-Fi, etc.), reading progress tracking
- 🎙️ **TTS Voice Reading** — System TTS engine reads aloud with adjustable speed, pitch, and volume
- 📤 **Multi-Format Export** — EPUB 2.0 and self-contained HTML export
- ⭐ **Favorites** — Save frequently accessed novels with one-click directory opening; search history dropdown
- 🔄 **Auto Update** — GitHub Release check on startup with one-click download and replace
- 🧩 **Plugin System** — Write Python scripts to add custom novel sources; community-sharable scripts
- 🌐 **Multi-language** — English, 简体中文, Español
- 💰 **Donation** — View wallet addresses and QR codes via the About page

## Requirements

- Windows 10/11
- Python 3.10+ (if running from source)
- Internet connection (for search and download)

## Quick Start

### Run exe

Double-click `NovelSearch.exe` to run the program.

### Run from source

```bash
pip install -r requirements.txt
python main.py
```

## Usage Guide

### 1. Search for a Novel

Enter the novel name in the search box and click "Search" or press Enter. The system will search via your selected search engine and display results. Double-click the target novel to fetch its chapter directory.

You can also paste a novel directory URL directly — the system will auto-detect the site type and parse it.

### 2. Download Chapters

After fetching the directory, all chapters are selected by default. Use checkboxes to select/deselect specific chapters. The "All", "None", and "Invert" buttons help with batch selection. Click "Download" to start.

Click "Stop" at any time to interrupt. Failed chapters are marked in red.

### 3. Retry Failed Chapters

After download completes, the "Retry Failed" button becomes available for re-downloading only the failed chapters — successful ones are not affected.

### 4. Checkpoint Resume

Each chapter is **immediately saved to disk** (`downloads/{novel_title}/chapters/`) as it downloads, with `checkpoint.json` tracking per-chapter status. If you close the app or it crashes mid-download:

- Reopen the novel directory page and click "Download" again
- The system auto-detects cached chapters: progress bar shows "Resume: N/total cached"
- Only downloads remaining chapters; already-successful ones are skipped

### 5. Compose TXT

After downloading, click "Compose TXT" to merge all valid chapters into a single clean TXT file. Ads, duplicates, and other noise are automatically removed.

### 6. Preview & Export

The "Preview" tab lets you view the composed novel. Large files use **streaming loading**: first 200KB appears instantly, then 100KB chunks are appended every 30ms with real-time `[Loading 45%]` progress in the title bar. You can also click "Open File" to load a local TXT. Export to EPUB or HTML formats is supported.

### 7. Text Processor

The preview page includes a dedicated novel text processor:
- **Remove Duplicates** — Duplicate paragraphs detected via Jaccard similarity
- **Remove Ads** — Intelligent ad text removal
- **Smart Format** — Auto-fix unreasonable paragraph breaks
- **Layout Optimize** — Unified blank lines and indentation
- **Keyword Deletion** — Delete lines/sentences/keywords containing specified terms

### 8. TTS Voice Reading

Click "Play" in the preview page to have the system TTS engine read the current text aloud. Adjust speed, pitch, and volume in real-time via sliders. Pause/Resume/Stop controls are available.

### 9. Bookshelf Management

- Click "Add Book" to select TXT/EPUB files, or drag & drop files directly onto the bookshelf area
- Filter books by tag category via the dropdown
- Double-click a book to open it in the preview tab
- Remove books from the shelf as needed

### 10. Favorites

On the search page, add the current novel to favorites for quick future access. Favorites support one-click opening and deletion.

### 11. Settings

- **Output Directory** — Where to save novel files
- **Concurrency** — Simultaneous chapter downloads (recommended: 3-5)
- **Request Interval** — Delay between requests in seconds; increase to avoid IP blocks
- **Search Engine** — Choose which engine to use for searching
- **Similarity Threshold** — Paragraphs exceeding this similarity are treated as duplicates (0.5-0.99)
- **Min Chapter Length** — Chapters below this character count are marked as too short
- **Auto Update** — Check for new versions on GitHub Release
- **Language** — Interface language (English / 简体中文 / Español)

### 12. Plugin Management

On the "Plugins" tab:
- Install third-party source plugins (`.py` script files)
- Click "Create Sample" to generate a template plugin; modify to adapt new sites
- Remove installed plugins

### 13. Auto Update

Updates are checked automatically on startup. You can also manually check via "Check Update" in the Settings tab. One-click download and automatic restart upon finding a new version.

## Interface

The program uses the Catppuccin dark theme with six tabs:

- 🔍 Search Novel
- 📥 Download Chapters
- 📖 Preview
- ⚙️ Settings
- 📚 Bookshelf
- 🧩 Plugins

## Technical Architecture

- **GUI**: PySide6
- **Async Networking**: asyncio + aiohttp
- **HTML Parsing**: BeautifulSoup4 + lxml
- **Search Engines**: Bing / Baidu / Google / Yahoo / 360 / Sogou / Quark
- **Text Cleaning**: Custom deduplication algorithm (Jaccard similarity)
- **TTS**: QTextToSpeech (Windows SAPI5)
- **Packaging**: PyInstaller onefile

## FAQ

**Q: Cannot find the novel in search results. What to do?**
A: Try switching search engines or directly paste the novel directory page URL — the system will auto-detect and parse it.

**Q: Download failed midway. What to do?**
A: Click "Retry Failed" — only the unsuccessful chapters will be re-downloaded.

**Q: How to increase download speed?**
A: Increase "Concurrency" in Settings, but setting it too high may result in IP blocks.

**Q: How to add a new novel source site?**
A: Generate a sample plugin on the Plugins tab, then modify the parsing logic following the template to adapt your target site.

## Author

- Author: Lorime
- Email: lorime@126.com

## Donation

If you find this tool helpful, donations to support development are welcome:

- **XMR**: 4DSQMNzzq46N1z2pZWAVdeA6JvUL9TCB2bnBiA3ZzoqEdYJnMydt5akCa3vtmapeDsbVKGPFdNkzzqTcJS8M8oyK7WGj5qMvNZRw61w6wMF
- **USDT (TRC20)**: TG6DCBoQszDxc64owRZKkSHqZfcAQrqR8uM
- **USDT (ERC20)**: 0x4323d39BA9b6Bd0570920e63a8D3a192b4459330

Scan the QR codes on the About page to view the corresponding addresses.