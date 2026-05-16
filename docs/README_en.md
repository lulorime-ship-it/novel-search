# Novel Search & Download System

## Overview

Novel Search & Download System is a PySide6 + asyncio based novel search and download tool. It automatically discovers novel sites via Bing search engine, crawls all chapter content, removes ads and duplicate paragraphs, and combines them into a complete TXT file.

## Features

- 🔍 **Smart Search** — Search novels via Bing with fuzzy matching across multiple Biquge (笔趣阁) sites
- 📥 **Batch Download** — Async concurrent chapter downloads with pause/stop/retry support
- 🧹 **Auto Clean** — Automatic removal of ads, duplicate paragraphs, and chapter title noise
- 📖 **Preview** — Built-in TXT viewer, no external editor needed
- 🌐 **Multi-language** — Supports English, 简体中文, Español
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

Enter the novel name in the search box and click "Search" or press Enter. The system will search via Bing and display results. Double-click the target novel in the results list to fetch its chapter directory.

### 2. Download Chapters

After fetching the directory, all chapters are selected by default. You can select or deselect specific chapters using checkboxes. Click "Download" to start downloading.

You can click "Stop" at any time to interrupt the download. Failed chapters are displayed in red.

### 3. Retry Failed Chapters

After download completes, if there are failed chapters, the "Retry Failed" button becomes available. Click it to re-download only the previously failed chapters — successfully downloaded chapters will not be affected.

### 4. Compose TXT

After all chapters are downloaded, click "Compose TXT" to merge all valid chapters into a single complete TXT file. The system automatically removes ads, duplicate content, and other noise.

### 5. Preview

The "Preview" tab lets you view the composed novel content. You can also click "Open File" to load a local TXT file.

### 6. Settings

- **Output Directory** — Where to save novel files
- **Concurrency** — Number of simultaneous chapter downloads (recommended: 3-5)
- **Request Interval** — Delay between requests in seconds; increase to avoid IP blocks
- **Similarity Threshold** — Paragraphs exceeding this similarity are treated as duplicates (0.5-0.99)
- **Min Chapter Length** — Chapters below this character count are marked as too short
- **Language** — Interface language (English / 简体中文 / Español)

### 7. About

Click the "About" button to view author information and donation QR codes / wallet addresses.

## Interface

The program uses the Catppuccin dark theme and contains four tabs:

- 🔍 Search Novel
- 📥 Download Chapters
- 📖 Preview
- ⚙️ Settings

## Technical Architecture

- **GUI**: PySide6
- **Async Networking**: asyncio + aiohttp
- **HTML Parsing**: BeautifulSoup4 + lxml
- **Search Engine**: Bing
- **Text Cleaning**: Custom deduplication algorithm (Jaccard similarity)

## FAQ

**Q: Cannot find the novel in search results. What to do?**
A: Try directly pasting the novel directory page URL — the system will automatically detect and start downloading.

**Q: Download failed midway. What to do?**
A: Click "Retry Failed" — only the unsuccessful chapters will be re-downloaded.

**Q: How to increase download speed?**
A: Increase "Concurrency" in Settings, but setting it too high may result in IP blocks.

## Author

- Author: Lorime
- Email: lorime@126.com

## Donation

If you find this tool helpful, donations to support development are welcome:

- **XMR**: 4DSQMNzzq46N1z2pZWAVdeA6JvUL9TCB2bnBiA3ZzoqEdYJnMydt5akCa3vtmapeDsbVKGPFdNkzzqTcJS8M8oyK7WGj5qMvNZRw61w6wMF
- **USDT (TRC20)**: TG6DCBoQszDxc64owRZKkSHqZfcAQrqR8uM
- **USDT (ERC20)**: 0x4323d39BA9b6Bd0570920e63a8D3a192b4459330

Scan the QR codes on the About page to view the corresponding addresses.
