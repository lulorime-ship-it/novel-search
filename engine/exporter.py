import os
import re
import uuid
import zipfile
from datetime import datetime
import html


def _split_chapters(text):
    pattern = r'(第[一二三四五六七八九十百千零\d]+[章节卷部篇回集][^\n]*)'
    parts = re.split(pattern, text)
    chapters = []
    start = 0
    if parts and not re.match(pattern, parts[0]):
        start = 1
    for i in range(start, len(parts) - 1, 2):
        title = parts[i].strip()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ''
        chapters.append((title, content))
    return chapters


def _paragraphs(text):
    paras = re.split(r'\n\s*\n', text.strip())
    return [p.strip() for p in paras if p.strip()]


def export_epub(text, output_path, title="Novel", author="Unknown"):
    chapters = _split_chapters(text)
    if not chapters:
        content = text.strip()
        if not content:
            content = '\u0020'
        chapters = [('\u6b63\u6587', content)]

    book_uuid = str(uuid.uuid4())
    book_id = f"urn:uuid:{book_uuid}"
    now = datetime.now().strftime("%Y-%m-%d")

    chapter_files = {}
    manifest_items = []
    spine_items = []
    nav_points = []

    for idx, (ch_title, ch_content) in enumerate(chapters, 1):
        file_id = f"chapter_{idx:03d}"
        file_name = f"chapter_{idx:03d}.xhtml"

        paras = _paragraphs(ch_content)
        paras_html = '\n'.join(
            f'    <p>{html.escape(p, quote=True)}</p>' for p in paras
        )

        xhtml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml">\n'
            '<head>\n'
            f'  <title>{html.escape(ch_title, quote=True)}</title>\n'
            '  <link rel="stylesheet" type="text/css" href="stylesheet.css"/>\n'
            '</head>\n'
            '<body>\n'
            f'  <h2>{html.escape(ch_title, quote=True)}</h2>\n'
            f'{paras_html}\n'
            '</body>\n'
            '</html>'
        )

        chapter_files[file_name] = xhtml
        manifest_items.append(
            f'    <item id="{file_id}" href="{file_name}" media-type="application/xhtml+xml"/>'
        )
        spine_items.append(f'    <itemref idref="{file_id}"/>')
        nav_points.append(
            f'    <navPoint id="{file_id}" playOrder="{idx}">\n'
            f'      <navLabel><text>{html.escape(ch_title, quote=True)}</text></navLabel>\n'
            f'      <content src="{file_name}"/>\n'
            f'    </navPoint>'
        )

    content_opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package version="2.0" unique-identifier="book-id" xmlns="http://www.idpf.org/2007/opf">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">\n'
        f'    <dc:title>{html.escape(title, quote=True)}</dc:title>\n'
        f'    <dc:creator opf:role="aut">{html.escape(author, quote=True)}</dc:creator>\n'
        f'    <dc:identifier id="book-id">{book_id}</dc:identifier>\n'
        '    <dc:language>zh-CN</dc:language>\n'
        f'    <dc:date>{now}</dc:date>\n'
        '  </metadata>\n'
        '  <manifest>\n'
        '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>\n'
        '    <item id="css" href="stylesheet.css" media-type="text/css"/>\n'
        + '\n'.join(manifest_items) + '\n'
        '  </manifest>\n'
        '  <spine toc="ncx">\n'
        + '\n'.join(spine_items) + '\n'
        '  </spine>\n'
        '</package>'
    )

    toc_ncx = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx version="2005-1" xmlns="http://www.daisy.org/z3986/2005/ncx/">\n'
        '  <head>\n'
        f'    <meta name="dtb:uid" content="{book_id}"/>\n'
        '    <meta name="dtb:depth" content="1"/>\n'
        '    <meta name="dtb:totalPageCount" content="0"/>\n'
        '    <meta name="dtb:maxPageNumber" content="0"/>\n'
        '  </head>\n'
        f'  <docTitle><text>{html.escape(title, quote=True)}</text></docTitle>\n'
        '  <navMap>\n'
        + '\n'.join(nav_points) + '\n'
        '  </navMap>\n'
        '</ncx>'
    )

    container_xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        '  <rootfiles>\n'
        '    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>\n'
        '  </rootfiles>\n'
        '</container>'
    )

    stylesheet_css = (
        'body {\n'
        '  font-family: serif;\n'
        '  line-height: 1.8;\n'
        '}\n'
        'h2 {\n'
        '  text-align: center;\n'
        '}\n'
        'p {\n'
        '  text-indent: 2em;\n'
        '  margin: 0.5em 0;\n'
        '}'
    )

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('mimetype', 'application/epub+zip', zipfile.ZIP_STORED)
        zf.writestr('META-INF/container.xml', container_xml)
        zf.writestr('OEBPS/content.opf', content_opf)
        zf.writestr('OEBPS/toc.ncx', toc_ncx)
        zf.writestr('OEBPS/stylesheet.css', stylesheet_css)
        for file_name, content in chapter_files.items():
            zf.writestr(f'OEBPS/{file_name}', content)

    return output_path


def export_html(text, output_path, title="Novel"):
    chapters = _split_chapters(text)
    if not chapters:
        content = text.strip()
        if not content:
            content = ''
        chapters = [('\u6b63\u6587', content)]

    toc_items = []
    chapter_divs = []

    for idx, (ch_title, ch_content) in enumerate(chapters, 1):
        anchor = f"chapter-{idx}"
        toc_items.append(
            f'      <li><a href="#{anchor}">{html.escape(ch_title, quote=True)}</a></li>'
        )

        paras = _paragraphs(ch_content)
        paras_html = '\n'.join(
            f'      <p>{html.escape(p, quote=True)}</p>' for p in paras
        )

        chapter_divs.append(
            f'    <div class="chapter" id="{anchor}">\n'
            f'      <h2>{html.escape(ch_title, quote=True)}</h2>\n'
            f'{paras_html}\n'
            f'    </div>'
        )

    toc_html = '\n'.join(toc_items)
    chapters_html = '\n\n'.join(chapter_divs)

    html_content = (
        '<!DOCTYPE html>\n'
        '<html lang="zh-CN">\n'
        '<head>\n'
        '  <meta charset="utf-8"/>\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>\n'
        f'  <title>{html.escape(title, quote=True)}</title>\n'
        '  <style>\n'
        '    body {\n'
        '      background: #fafafa;\n'
        '      color: #333;\n'
        '      max-width: 800px;\n'
        '      margin: 0 auto;\n'
        '      padding: 2em 1em;\n'
        '      font-family: serif;\n'
        '      line-height: 1.9;\n'
        '    }\n'
        '    h1 {\n'
        '      text-align: center;\n'
        '      margin-bottom: 1.5em;\n'
        '    }\n'
        '    h2 {\n'
        '      text-align: center;\n'
        '      margin-top: 2em;\n'
        '    }\n'
        '    p {\n'
        '      text-indent: 2em;\n'
        '      margin: 0.5em 0;\n'
        '    }\n'
        '    nav#toc {\n'
        '      background: #fff;\n'
        '      border: 1px solid #ddd;\n'
        '      border-radius: 4px;\n'
        '      padding: 1em 1.5em;\n'
        '      margin-bottom: 2em;\n'
        '    }\n'
        '    nav#toc h2 {\n'
        '      margin-top: 0;\n'
        '    }\n'
        '    nav#toc ol {\n'
        '      padding-left: 1.5em;\n'
        '    }\n'
        '    nav#toc li {\n'
        '      margin: 0.3em 0;\n'
        '    }\n'
        '    nav#toc a {\n'
        '      color: #3366cc;\n'
        '      text-decoration: none;\n'
        '    }\n'
        '    nav#toc a:hover {\n'
        '      text-decoration: underline;\n'
        '    }\n'
        '    .chapter {\n'
        '      margin-bottom: 2em;\n'
        '    }\n'
        '  </style>\n'
        '</head>\n'
        '<body>\n'
        f'  <h1>{html.escape(title, quote=True)}</h1>\n'
        '  <nav id="toc">\n'
        '    <h2>\u76ee\u5f55</h2>\n'
        '    <ol>\n'
        f'{toc_html}\n'
        '    </ol>\n'
        '  </nav>\n'
        f'\n{chapters_html}\n'
        '</body>\n'
        '</html>'
    )

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return output_path