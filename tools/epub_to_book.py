#!/usr/bin/env python3
"""Converts an EPUB into the app's book format (see the README).

    python3 tools/epub_to_book.py BOOK.epub BOOK_ID

Writes books/BOOK_ID/book.json, one JSON file per chapter, and the cover image. It only uses the
standard library. Built on Diyanet's InDesign EPUBs; other publishers' EPUBs may name their styles
differently, so check the result and extend STYLE_BLOCKS when a book needs it.
"""

import json
import posixpath
import re
import shutil
import sys
import unicodedata
import zipfile
from urllib.parse import unquote
from pathlib import Path
from xml.etree import ElementTree as ET

XHTML = '{http://www.w3.org/1999/xhtml}'
OPF = '{http://www.idpf.org/2007/opf}'
CONTAINER = '{urn:oasis:names:tc:opendocument:xmlns:container}'

# Diyanet's honorific font ("Arabic calligraph") draws each honorific from one letter.
HONORIFICS = {
    's': 'ﷺ',  # sallallahu aleyhi ve sellem
    'd': 'رَضِيَ اللَّهُ عَنْهُ',  # radıyallahu anh
    'g': 'رَضِيَ اللَّهُ عَنْهَا',  # radıyallahu anhâ
    'f': 'رَضِيَ اللَّهُ عَنْهُمْ',  # radıyallahu anhüm
}

# Paragraph styles → block types. Anything else is a paragraph.
STYLE_BLOCKS = {
    'baslik': 'heading',
    'h2baslik': 'heading',
    'solbaslik': 'heading',
    'ARAP-A': 'arabic',
}

# Small words that stay lowercase in a title: `Allah, Âlem, İnsan ve Din`.
SMALL_WORDS = {'ve', 'ile', 'ya', 'da', 'de', 'ki', 'veya', 'yahut'}

PART_TITLE = re.compile(r'^\d+\.\s*BÖLÜM\b', re.IGNORECASE)
SENTENCE_END = tuple('.!?:;…”"»)')


def read(epub, path):
    """A file in the EPUB by a path from its manifest or links, which may be percent-encoded and
    spell `İ` as `I` with a combining dot where the archive spells it as one letter, or the other
    way round."""
    key = unicodedata.normalize('NFC', unquote(path))
    for name in epub.namelist():
        if unicodedata.normalize('NFC', unquote(name)) == key:
            return epub.read(name)
    # Some archives garble such names past decoding (`I%A6%E7slam` for `İslam`): matched then by
    # what's left of them in plain letters, if only one name matches.
    def skeleton(name):
        return re.sub(r'%[0-9A-Fa-f]{2}|[^A-Za-z0-9/._-]', '', name)

    matches = [name for name in epub.namelist() if skeleton(name) == skeleton(path)]
    return epub.read(matches[0] if len(matches) == 1 else path)


def turkish_lower(text):
    return text.replace('I', 'ı').replace('İ', 'i').lower()


def turkish_title(text):
    """`ALLAH’IN İSİM ve SIFATLARI` → `Allah’ın İsim ve Sıfatları`. Mixed-case text is kept."""
    # All capitals apart from small words, which some titles already write in lowercase.
    without_small = ' '.join(w for w in text.split() if w not in SMALL_WORDS)
    if without_small != without_small.upper():
        return text

    def word(w, first):
        # Roman numerals stay as they are: `II.`, `XIV.`.
        if re.fullmatch(r'[IVXLC]+[.)]?', w):
            return w
        lower = turkish_lower(w)
        if not first and lower in SMALL_WORDS:
            return lower
        # The first letter, past an opening bracket or quote: `(Şer’î Deliller)`.
        lead = re.match(r'^[(“"‘\']*', lower).group(0)
        rest = lower[len(lead):]
        head = rest[:1]
        head = 'İ' if head == 'i' else 'I' if head == 'ı' else head.upper()
        # Only the first letter: `Kelime-i`, `Resûl’e` keep the rest lowercase.
        return lead + head + rest[1:]

    # Also start a word after `/`: `Ortak Koşmak/En Büyük Zulüm`.
    pieces = re.split(r'(\s+|/)', text)
    out, first = [], True
    for piece in pieces:
        if piece and not piece.isspace() and piece != '/':
            out.append(word(piece, first))
            first = False
        else:
            out.append(piece)
            if piece == '/':
                first = True
    return ''.join(out)


def classes(element):
    return set((element.get('class') or '').split())


def collapse(parts):
    """Joins neighbouring parts with the same style and normalizes spaces."""
    merged = []
    for part in parts:
        text = re.sub(r'\s+', ' ', part.get('text', ''))
        if not text and 'note' not in part:
            continue
        part = {**part, 'text': text} if 'text' in part else part
        last = merged[-1] if merged else None
        if (
            last is not None
            and 'note' not in part
            and 'note' not in last
            and last.get('italic') == part.get('italic')
            and last.get('bold') == part.get('bold')
        ):
            last['text'] += part['text']
        else:
            merged.append(part)
    if merged and 'text' in merged[0]:
        merged[0]['text'] = merged[0]['text'].lstrip()
    if merged and 'text' in merged[-1]:
        merged[-1]['text'] = merged[-1]['text'].rstrip()
    return [p for p in merged if p.get('text') or 'note' in p]


def inline_parts(element, italic=False, bold=False):
    """The element's text as parts: plain, italic and/or bold runs, and footnote references."""
    parts = []

    def add(text):
        if text:
            part = {'text': text}
            if italic:
                part['italic'] = True
            if bold:
                part['bold'] = True
            parts.append(part)

    add(element.text)
    for child in element:
        tag = child.tag.replace(XHTML, '')
        cls = classes(child)
        if tag == 'br':
            add(' ')
        elif tag == 'img':
            pass
        elif tag == 'sup' or '_idFootnoteLink' in cls:
            link = child if '_idFootnoteLink' in cls else child.find(f'.//{XHTML}a')
            label = ''.join(link.itertext()) if link is not None else ''
            number = re.sub(r'\D', '', label)
            if number:
                parts.append({'note': number})
            else:
                parts.extend(inline_parts(child, italic, bold))
        elif tag == 'span' and 'DAV' in cls:
            letter = ''.join(child.itertext()).strip()
            add(f' {HONORIFICS.get(letter, letter)} ')
        else:
            child_italic = italic or 'ideitalik' in cls or 'idebolditalik' in cls or tag in ('i', 'em')
            child_bold = bold or 'idebold' in cls or 'idebolditalik' in cls or tag in ('b', 'strong')
            parts.extend(inline_parts(child, child_italic, child_bold))
        add(child.tail)
    return parts


def plain(parts):
    return ''.join(p.get('text', '') for p in parts).strip()


def block_from(element):
    """One paragraph or heading → a block, or None to skip it."""
    tag = element.tag.replace(XHTML, '')
    cls = classes(element)
    if element.find(f'.//{XHTML}img') is not None and not plain(inline_parts(element)):
        # A picture of text, e.g. Riyâzü's Sâlihîn's Arabic (`resim`), can't be read as text: left
        # out. Any other, an ornament between sections, is a divider.
        return None if 'resim' in cls else {'type': 'divider'}
    parts = collapse(inline_parts(element))
    if not parts:
        return None
    kind = next((STYLE_BLOCKS[c] for c in cls if c in STYLE_BLOCKS), None)
    if kind is None and tag in ('h1', 'h2', 'h3'):
        kind = 'heading'
    # Other books' heading styles, e.g. İslam İlmihali's `başlık3`, `başlık2222222`.
    if kind is None and any(turkish_lower(c).startswith(('başlık', 'baslik')) for c in cls):
        kind = 'heading'
    # Arabic by its letters, whatever the style it's set in (`Hadis-metni`, `ARAP-ALAR`, …).
    if kind in (None, 'paragraph'):
        text = plain(parts)
        letters = [ch for ch in text if ch.isalpha()]
        arabic = sum('\u0600' <= ch <= '\u06ff' or '\u0750' <= ch <= '\u077f' for ch in letters)
        if letters and arabic >= 0.6 * len(letters):
            kind = 'arabic'
    # A paragraph that's only a source reference, e.g. `(M1090 Müslim, Salât, 222)`.
    if kind is None and element.find(f".//{XHTML}span[@class]") is not None:
        spans = [s for s in element.iter(f'{XHTML}span') if 'icDipnot' in classes(s)]
        if spans and plain(parts) == ''.join(''.join(s.itertext()) for s in spans).strip():
            kind = 'source'
    kind = kind or 'paragraph'
    # A line of a printed table of contents, its page number after a tab (`Abdest\t96`): the
    # app has its own, so it's left out.
    if re.search(r'\t\s*\d+\s*$', ''.join(element.itertext())):
        return None
    if kind == 'heading':
        heading = {'type': 'heading', 'text': turkish_title(plain(parts))}
        # Its level, from a style such as `başlık2222222` (2), to split a book at its top
        # headings; kept only while converting.
        level = next(
            (re.match(r'ba[şs]l[ıi]k(\d)', turkish_lower(c)) for c in cls if re.match(r'ba[şs]l[ıi]k\d', turkish_lower(c))),
            None,
        )
        if level:
            heading['_level'] = int(level.group(1))
        return heading
    if kind in ('arabic', 'source'):
        return {'type': kind, 'text': re.sub(r'\s+', ' ', plain(parts))}
    if all('note' not in p and not p.get('italic') and not p.get('bold') for p in parts):
        return {'type': 'paragraph', 'text': plain(parts)}
    return {'type': 'paragraph', 'parts': parts}


def continues(previous, block):
    """A paragraph split by a line break in the layout: it ends with a comma, or with no sentence
    end before a lowercase start."""
    if previous.get('type') != 'paragraph' or block.get('type') != 'paragraph':
        return False
    before = plain(previous['parts']) if 'parts' in previous else previous['text']
    after = plain(block['parts']) if 'parts' in block else block['text']
    if not before or not after:
        return False
    return before.endswith(',') or (not before.endswith(SENTENCE_END) and after[:1].islower())


def as_parts(block):
    return block['parts'] if 'parts' in block else [{'text': block['text']}]


def read_file(epub, path):
    root = ET.fromstring(read(epub, path))
    body = root.find(f'{XHTML}body')
    blocks, notes = [], []
    for element in body.iter():
        tag = element.tag.replace(XHTML, '')
        cls = classes(element)
        if tag == 'div' and '_idFootnote' in cls:
            paragraph = element.find(f'.//{XHTML}p')
            if paragraph is None:
                continue
            # Its number: its link back to the text, which some books set inside a span; or, with
            # no link, the figures it starts with.
            anchor = paragraph.find(f'.//{XHTML}a')
            if anchor is not None:
                number = re.sub(r'\D', '', ''.join(anchor.itertext()))
                anchor.text = ''
                for child in list(anchor):
                    anchor.remove(child)
            else:
                number = re.match(r'\s*(\d*)', ''.join(paragraph.itertext())).group(1)
            notes.append({'id': number, 'text': re.sub(r'\s+', ' ', plain(inline_parts(paragraph)))})
            continue
        if tag not in ('p', 'h1', 'h2', 'h3'):
            continue
        # Footnote paragraphs are read above, with their note.
        if any('_idFootnote' in classes(a) for a in body.iter() if element in list(a.iter())[1:]):
            continue
        block = block_from(element)
        if block:
            blocks.append(block)
    return blocks, notes


def tidy(blocks):
    """Joins split paragraphs and drops dividers at the start, the end and in a row."""
    out = []
    for block in blocks:
        if block['type'] == 'divider' and (not out or out[-1]['type'] == 'divider'):
            continue
        if out and continues(out[-1], block):
            before = [dict(p) for p in as_parts(out[-1])]
            # The space goes on the text before it, so italic runs on both sides join up.
            if before and 'text' in before[-1]:
                before[-1]['text'] += ' '
            joined = collapse(before + as_parts(block))
            out[-1] = (
                {'type': 'paragraph', 'parts': joined}
                if any(len(p) > 1 or 'note' in p for p in joined)
                else {'type': 'paragraph', 'text': plain(joined)}
            )
            continue
        out.append(block)
    while out and out[-1]['type'] == 'divider':
        out.pop()
    return out


ORDINAL_PART = re.compile(
    r'^(Birinci|İkinci|Üçüncü|Dördüncü|Beşinci|Altıncı|Yedinci|Sekizinci|Dokuzuncu|Onuncu) Bölüm$'
)


def tidy_split(pending, book_title):
    """A book split at its headings, tidied: `Birinci Bölüm` and the name under it (`İTİKAD`) the
    part of the chapters after it, not a chapter; what's left of a printed table of contents
    (headings only) left out; a foreword started at its `ÖN SÖZ`; the imprint at the front named
    so."""
    out, part = [], None
    for title, _part, blocks, notes in pending:
        if ORDINAL_PART.match(title):
            name = blocks[0].get('text', '') if len(blocks) == 1 else ''
            part = f'{title}: {turkish_title(name)}' if name else title
            continue
        if all(b['type'] == 'heading' for b in blocks):
            continue
        start = next(
            (i for i, b in enumerate(blocks) if b.get('text', '').strip() in ('ÖN SÖZ', 'ÖNSÖZ')), None
        )
        if start is not None:
            if any(b['type'] != 'heading' for b in blocks[:start]):
                out.append((title, part, blocks[:start], notes))
            out.append(('Ön Söz', part, blocks[start + 1:], notes))
            continue
        if not out and title == book_title:
            title = 'Künye'
        out.append((title, part, blocks, notes))
    return out


def convert(epub_path, book_id, out_root):
    epub = zipfile.ZipFile(epub_path)
    container = ET.fromstring(epub.read('META-INF/container.xml'))
    opf_path = container.find(f'.//{CONTAINER}rootfile').get('full-path')
    base = posixpath.dirname(opf_path)
    opf = ET.fromstring(epub.read(opf_path))
    manifest = {item.get('id'): item for item in opf.find(f'{OPF}manifest')}
    spine = [posixpath.join(base, manifest[i.get('idref')].get('href')) for i in opf.find(f'{OPF}spine')]
    title = opf.find('.//{http://purl.org/dc/elements/1.1/}title').text.strip()

    entries = []
    nav_item = next((i for i in manifest.values() if 'nav' in (i.get('properties') or '').split()), None)
    if nav_item is not None:
        nav_path = posixpath.join(base, nav_item.get('href'))
        nav = ET.fromstring(read(epub, nav_path))
        # Only the table of contents, not the other navigation lists (e.g. landmarks such as the
        # cover); or the only list there is.
        navs = list(nav.iter(f'{XHTML}nav'))
        toc = next(
            (n for n in navs if n.get('{http://www.idpf.org/2007/ops}type') == 'toc'), navs[0]
        )
        for link in toc.iter(f'{XHTML}a'):
            href = posixpath.normpath(posixpath.join(posixpath.dirname(nav_path), link.get('href').split('#')[0]))
            entries.append((''.join(link.itertext()).strip(), href))
    else:
        # EPUB 2: no navigation document, its table of contents in toc.ncx.
        NCX = '{http://www.daisy.org/z3986/2005/ncx/}'
        ncx_item = next(i for i in manifest.values() if i.get('media-type') == 'application/x-dtbncx+xml')
        ncx_path = posixpath.join(base, ncx_item.get('href'))
        ncx = ET.fromstring(read(epub, ncx_path))
        for point in ncx.iter(f'{NCX}navPoint'):
            label = ''.join(point.find(f'{NCX}navLabel').itertext()).strip()
            src = point.find(f'{NCX}content').get('src').split('#')[0]
            entries.append((label, posixpath.normpath(posixpath.join(posixpath.dirname(ncx_path), src))))

    out = Path(out_root) / str(book_id)
    # Each conversion is a new version, so the app downloads the chapters again.
    version = 1
    if (out / 'book.json').exists():
        version = json.loads((out / 'book.json').read_text(encoding='utf-8')).get('version', 0) + 1
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    chapters, pending, part = [], [], None
    for index, (entry_title, href) in enumerate(entries):
        start = spine.index(href)
        end = spine.index(entries[index + 1][1]) if index + 1 < len(entries) else len(spine)
        if PART_TITLE.match(entry_title):
            part = turkish_title(entry_title)
            continue
        blocks, notes = [], []
        for path in spine[start:end]:
            file_blocks, file_notes = read_file(epub, path)
            blocks += file_blocks
            notes += file_notes
        chapter_title = turkish_title(entry_title)
        # The chapter's own title heading is shown from `title`, so it isn't repeated as a block.
        if blocks and blocks[0]['type'] == 'heading':
            blocks = blocks[1:]
        blocks = tidy(blocks)
        if not blocks:
            continue
        pending.append((chapter_title, part, blocks, notes))

    # A book whose table of contents is a single entry (e.g. İslam İlmihali) is split at its
    # headings instead, each starting a chapter, so it isn't read as one long page.
    if len(pending) == 1 and sum(b['type'] == 'heading' for b in pending[0][2]) >= 3:
        title_, part_, blocks_, notes_ = pending[0]
        # At its top level of heading, the lowest numbered style there is, with three or more.
        levels = [b.get('_level') for b in blocks_ if b['type'] == 'heading' and b.get('_level')]
        top = next((lv for lv in sorted(set(levels)) if levels.count(lv) >= 3), None)
        splits = lambda b: b['type'] == 'heading' and (top is None or b.get('_level') == top)
        pending = []
        for block in blocks_:
            if splits(block) and pending and not pending[-1][2] and block['text'].startswith('('):
                pending[-1] = (f"{pending[-1][0]} {block['text']}",) + pending[-1][1:]
                continue
            if splits(block) or not pending:
                heading = block['text'] if splits(block) else title_
                pending.append((heading, part_, [], notes_))
                if splits(block):
                    continue
            pending[-1][2].append(block)
        pending = [(t, p, b, n) for t, p, b, n in pending if b]
        pending = tidy_split(pending, title_)

    for chapter_title, part, blocks, notes in pending:
        for block in blocks:
            block.pop('_level', None)
        n = len(chapters) + 1
        chapter = {'n': n, 'title': chapter_title, 'blocks': blocks}
        # Only the notes this chapter points to, where a split chapter shares its book's.
        used = {p['note'] for b in blocks for p in b.get('parts', []) if 'note' in p}
        own = [note for note in notes if note['id'] in used] if len(pending) > 1 else notes
        if own:
            chapter['notes'] = own
        # Without spaces between the parts: the books together stay small enough to serve.
        (out / f'{n}.json').write_text(
            json.dumps(chapter, ensure_ascii=False, separators=(',', ':')), encoding='utf-8'
        )
        chapters.append({'n': n, 'title': chapter_title, **({'part': part} if part else {})})

    # The book list's title, when the book is in it: EPUB titles are sometimes styled differently.
    index_path = Path(out_root) / 'index.json'
    if index_path.exists():
        listed = next(
            (b for b in json.loads(index_path.read_text(encoding='utf-8'))['books'] if b['id'] == book_id),
            None,
        )
        if listed:
            title = listed['title']

    (out / 'book.json').write_text(
        json.dumps(
            {'id': book_id, 'title': title, 'version': version, 'chapters': chapters},
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )

    cover = next((i for i in manifest.values() if 'cover-image' in (i.get('properties') or '')), None)
    if cover is None:
        # EPUB 2: the cover named by a `<meta name="cover" content="ITEM_ID">`.
        meta = next((m for m in opf.iter(f'{OPF}meta') if m.get('name') == 'cover'), None)
        if meta is not None:
            cover = manifest.get(meta.get('content'))
    cover_file = None
    if cover is not None:
        cover_path = posixpath.join(base, cover.get('href'))
        cover_file = 'cover' + posixpath.splitext(cover_path)[1].lower()
        (out / cover_file).write_bytes(read(epub, cover_path))

    return title, chapters, cover_file


if __name__ == '__main__':
    epub_path, book_id = sys.argv[1], int(sys.argv[2])
    root = Path(__file__).resolve().parent.parent / 'books'
    title, chapters, cover = convert(epub_path, book_id, root)
    print(f'{title}: {len(chapters)} chapters, cover: {cover}')
    for chapter in chapters:
        print(f"  {chapter['n']:3} {chapter.get('part', ''):40.40} | {chapter['title']}")
