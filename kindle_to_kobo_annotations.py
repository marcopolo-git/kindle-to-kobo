#!/usr/bin/env python3
"""
Kindle Annotation Importer
===========================
1. Parses My Clippings.txt from a Kindle
2. Exports a Markdown file of all highlights and notes
3. Imports annotations into Kobo's KoboReader.sqlite
4. Imports annotations into Calibre's metadata.db

Usage:
  # Export highlights to Markdown (no device needed):
  python3 kindle_to_kobo.py --clippings "My Clippings.txt" --export highlights.md

  # Import into Kobo (Kobo must be connected and mounted):
  python3 kindle_to_kobo.py --clippings "My Clippings.txt" --kobo /Volumes/KOBOeReader --import

  # Import into Calibre:
  python3 kindle_to_kobo.py --clippings "My Clippings.txt" --calibre "/Users/macuser/Books/Calibre Library" --import-calibre

  # All at once:
  python3 kindle_to_kobo.py --clippings "My Clippings.txt" --export highlights.md --kobo /Volumes/KOBOeReader --import --calibre "/Users/macuser/Books/Calibre Library" --import-calibre
"""

import re
import os
import sys
import uuid
import sqlite3
import zipfile
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Optional, Tuple
from lxml import etree

# ─────────────────────────────────────────
# PARSING
# ─────────────────────────────────────────

MONTH_FR = {
    'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4,
    'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8,
    'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12
}

def parse_date(meta_line: str) -> Optional[str]:
    """Parse French Kindle date into ISO format."""
    m = re.search(r'(\d+)\s+(\w+)\s+(\d{4})\s+(\d+:\d+:\d+)', meta_line)
    if m:
        day, month_fr, year, time = m.groups()
        month = MONTH_FR.get(month_fr.lower())
        if month:
            return f"{year}-{month:02d}-{int(day):02d}T{time}Z"
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

def parse_clippings(filepath: str) -> Dict[str, List[Dict]]:
    """Parse My Clippings.txt and return clippings grouped by book title."""
    with open(filepath, encoding='utf-8-sig') as f:
        content = f.read()

    books = defaultdict(list)
    entries = content.split('==========')

    for entry in entries:
        entry = entry.strip().lstrip('﻿')
        if not entry:
            continue
        lines = [l for l in entry.split('\n')]
        if len(lines) < 2:
            continue

        raw_title = lines[0].strip().lstrip('﻿')
        meta_line = lines[1].strip() if len(lines) > 1 else ''
        text = '\n'.join(lines[2:]).strip()

        if not raw_title:
            continue

        # Determine type
        meta_lower = meta_line.lower()
        is_bookmark = 'signet' in meta_lower or 'marque-page' in meta_lower or ('bookmark' in meta_lower and 'note' not in meta_lower)
        is_note = 'note' in meta_lower and not is_bookmark

        # Bookmarks have no text body — that's expected
        if not text and not is_bookmark:
            continue

        # Skip Kindle DRM clipping-limit placeholder messages (French and English,
        # with or without angle-bracket wrapping).
        if text:
            t_lower = text.lower()
            if ('clipping limit' in t_lower or
                    'reached the limit' in t_lower or
                    'atteint la limite' in t_lower):
                continue

        # Parse location
        loc_m = re.search(r'emplacement (\d+)-?(\d*)', meta_line)
        loc_start = int(loc_m.group(1)) if loc_m else 0
        loc_end = int(loc_m.group(2)) if loc_m and loc_m.group(2) else loc_start

        # Parse page
        page_m = re.search(r'page (\d+)', meta_line)
        page = int(page_m.group(1)) if page_m else None

        # Parse date
        date = parse_date(meta_line)

        # Clean up title — strip author in parentheses
        title_m = re.match(r'^(.*?)\s*\(([^()]+)\)\s*$', raw_title)
        if title_m:
            book_title = title_m.group(1).strip()
            author = title_m.group(2).strip()
        else:
            book_title = raw_title
            author = ''

        books[book_title].append({
            'raw_title': raw_title,
            'book_title': book_title,
            'author': author,
            'is_note': is_note,
            'is_bookmark': is_bookmark,
            'page': page,
            'loc_start': loc_start,
            'loc_end': loc_end,
            'date': date,
            'text': text,
        })

    # Sort each book's clippings by location
    for title in books:
        books[title].sort(key=lambda x: x['loc_start'])

    return books


# ─────────────────────────────────────────
# MARKDOWN EXPORT
# ─────────────────────────────────────────

def export_markdown(books: Dict[str, List[Dict]], output_path: str):
    """Export all highlights and notes to a readable Markdown file."""
    lines = []
    lines.append('# Kindle Highlights & Notes\n')
    lines.append(f'*Exported on {datetime.now().strftime("%B %d, %Y")}*\n')
    lines.append(f'*{sum(len(v) for v in books.values())} annotations across {len(books)} books*\n')
    lines.append('\n---\n')

    # Table of contents
    lines.append('## Table of Contents\n')
    for i, title in enumerate(sorted(books.keys()), 1):
        anchor = re.sub(r'[^\w\s-]', '', title).strip().lower().replace(' ', '-')
        count = len(books[title])
        lines.append(f'{i}. [{title}](#{anchor}) *({count} annotations)*')
    lines.append('\n---\n')

    for title in sorted(books.keys()):
        clippings = books[title]
        anchor = re.sub(r'[^\w\s-]', '', title).strip().lower().replace(' ', '-')
        author = clippings[0]['author'] if clippings else ''

        lines.append(f'## {title}\n')
        if author:
            lines.append(f'*{author}*\n')
        lines.append(f'*{len(clippings)} annotations*\n')

        for c in clippings:
            loc_info = f'Location {c["loc_start"]}'
            if c['page']:
                loc_info += f', Page {c["page"]}'
            if c['is_note']:
                lines.append(f'\n> 📝 **Note** *(l{loc_info})*')
                lines.append(f'>\n> {c["text"]}')
            else:
                lines.append(f'\n> 💡 *{loc_info}*')
                lines.append(f'>\n> {c["text"]}')

        lines.append('\n---\n')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f'✅ Exported {sum(len(v) for v in books.values())} annotations to {output_path}')


# ─────────────────────────────────────────
# EPUB PARSING & TEXT FINDING
# ─────────────────────────────────────────

def build_epub_span_index(spine: List[Tuple[str, bytes]]) -> List[Tuple[str, str, str, int, int]]:
    """
    Build a global index of all kobo spans across the entire EPUB spine.
    Returns list of (href, content_id_suffix, span_id, global_char_start, span_len).
    Used to map Kindle locations (≈128 chars each) to exact kobo span positions.
    """
    index = []
    global_pos = 0
    for href, html_bytes in spine:
        try:
            parser = etree.HTMLParser(recover=True)
            tree = etree.fromstring(html_bytes, parser)
            body = tree.find('.//body') or tree
            for elem in body.iter():
                span_id = elem.get('id', '')
                if span_id.startswith('kobo.'):
                    text = ''.join(elem.itertext())
                    index.append((href, span_id, global_pos, len(text)))
                    global_pos += len(text)
        except Exception:
            pass
    return index


def kindle_location_to_span(loc: int, span_index: List[Tuple[str, str, int, int]]) -> Optional[Tuple[str, str, int]]:
    """
    Convert a Kindle location number to (href, span_id, offset_within_span).
    Kindle locations are ~128 characters each.
    """
    if not span_index:
        return None
    char_pos = loc * 128
    total = span_index[-1][2] + span_index[-1][3]
    char_pos = min(char_pos, total - 1)
    # Binary search for the span containing char_pos
    lo, hi = 0, len(span_index) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if span_index[mid][2] <= char_pos:
            lo = mid
        else:
            hi = mid - 1
    href, span_id, span_start, span_len = span_index[lo]
    offset = min(char_pos - span_start, span_len)
    return href, span_id, offset


def get_epub_spine(epub_path: str) -> List[Tuple[str, bytes]]:
    """Return list of (href, html_bytes) in spine order."""
    spine_items = []
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            # Find container.xml
            container = z.read('META-INF/container.xml')
            root = etree.fromstring(container)
            ns = {'c': 'urn:oasis:names:tc:opendocument:xmlns:container'}
            opf_path = root.find('.//c:rootfile', ns).get('full-path')

            # Parse OPF
            opf = z.read(opf_path)
            opf_root = etree.fromstring(opf)
            opf_dir = str(Path(opf_path).parent)
            if opf_dir == '.':
                opf_dir = ''

            ns2 = {
                'opf': 'http://www.idpf.org/2007/opf',
                'dc': 'http://purl.org/dc/elements/1.1/'
            }

            # Build manifest
            manifest = {}
            for item in opf_root.findall('.//opf:item', ns2):
                manifest[item.get('id')] = item.get('href')

            # Get spine order
            spine = opf_root.find('.//opf:spine', ns2)
            for itemref in spine.findall('opf:itemref', ns2):
                idref = itemref.get('idref')
                href = manifest.get(idref, '')
                if opf_dir:
                    full_href = f'{opf_dir}/{href}'
                else:
                    full_href = href
                try:
                    html_bytes = z.read(full_href)
                    spine_items.append((full_href, html_bytes))
                except Exception:
                    pass
    except Exception as e:
        pass
    return spine_items


def get_element_xpath(element, root) -> str:
    """Generate XPath for an element relative to root."""
    path_parts = []
    current = element
    while current is not None and current != root:
        parent = current.getparent()
        if parent is None:
            break
        tag = current.tag
        if '}' in tag:
            tag = tag.split('}')[1]
        siblings = [s for s in parent if s.tag == current.tag]
        idx = siblings.index(current) + 1
        if len(siblings) > 1:
            path_parts.append(f'{tag}[{idx}]')
        else:
            path_parts.append(tag)
        current = parent
    path_parts.reverse()
    return '/' + '/'.join(path_parts) if path_parts else '/body'


def find_text_in_html(html_bytes: bytes, search_text: str) -> Optional[Tuple[str, int, str, int]]:
    """
    Find search_text in HTML content.
    For kepub files (which have koboSpan elements), returns Kobo CSS selector paths
    in the form (span#kobo\\.N\\.N, start_offset, span#kobo\\.N\\.N, end_offset).
    Returns None if text not found.
    """
    if not search_text or len(search_text) < 5:
        return None

    search_snippet = search_text[:100].strip()

    try:
        parser = etree.HTMLParser(recover=True)
        tree = etree.fromstring(html_bytes, parser)
        if tree is None:
            return None

        body = tree.find('.//body')
        if body is None:
            body = tree

        # Collect koboSpan elements in document order (kepub format)
        kobo_spans = []
        for elem in body.iter():
            span_id = elem.get('id', '')
            if span_id.startswith('kobo.'):
                span_text = ''.join(elem.itertext())
                kobo_spans.append((span_id, span_text))

        if kobo_spans:
            # Search across concatenated kobo span text
            full_text = ''.join(t for _, t in kobo_spans)
            if search_snippet in full_text:
                pos = full_text.index(search_snippet)
                end_pos = min(pos + len(search_text), len(full_text))

                # Map character positions back to spans
                cumulative = 0
                start_id = end_id = None
                start_off = end_off = 0
                for span_id, span_text in kobo_spans:
                    span_end = cumulative + len(span_text)
                    if start_id is None and cumulative <= pos < span_end:
                        start_id = span_id
                        start_off = pos - cumulative
                    if end_id is None and cumulative < end_pos <= span_end:
                        end_id = span_id
                        end_off = end_pos - cumulative
                        break
                    cumulative = span_end

                if start_id:
                    if end_id is None:
                        end_id, end_text = kobo_spans[-1]
                        end_off = len(end_text)
                    # CSS selector escapes dots: span#kobo\.3\.1
                    start_path = 'span#' + start_id.replace('.', r'\.')
                    end_path = 'span#' + end_id.replace('.', r'\.')
                    return (start_path, start_off, end_path, end_off)

    except Exception:
        pass

    return None


# ─────────────────────────────────────────
# KOBO DATABASE
# ─────────────────────────────────────────

def get_kobo_books(kobo_db: str) -> Dict[str, Dict]:
    """
    Return dict of {normalized_title: {volumeid, title, filepath}} from Kobo.
    """
    books = {}
    try:
        conn = sqlite3.connect(kobo_db)
        cur = conn.cursor()
        cur.execute("""
            SELECT ContentID, Title, Attribution
            FROM content
            WHERE ContentType = 6
              AND MimeType LIKE '%epub%'
        """)
        for row in cur.fetchall():
            content_id, title, author = row
            if title:
                normalized = normalize_title(title)
                books[normalized] = {
                    'volumeid': content_id,
                    'title': title,
                    'author': author or '',
                }
        conn.close()
    except Exception as e:
        print(f'  Warning: could not read Kobo books: {e}')
    return books


def normalize_title(title: str) -> str:
    """Normalize title for fuzzy matching."""
    t = title.lower()
    t = re.sub(r'[^\w\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def title_similarity(a: str, b: str) -> float:
    """Simple word-overlap similarity between two titles."""
    a_words = set(normalize_title(a).split())
    b_words = set(normalize_title(b).split())
    if not a_words or not b_words:
        return 0.0
    return len(a_words & b_words) / len(a_words | b_words)


def find_kobo_match(kindle_title: str, kobo_books: Dict) -> Optional[Dict]:
    """Find the best matching Kobo book for a Kindle title."""
    kindle_norm = normalize_title(kindle_title)

    # Exact match
    if kindle_norm in kobo_books:
        return kobo_books[kindle_norm]

    # Fuzzy match
    best_score = 0.0
    best_match = None
    for kobo_norm, book in kobo_books.items():
        score = title_similarity(kindle_title, book['title'])
        if score > best_score and score > 0.5:
            best_score = score
            best_match = book

    return best_match


def get_epub_path_from_volumeid(volumeid: str, kobo_root: str) -> Optional[str]:
    """Resolve a Kobo VolumeID to a local file path."""
    # VolumeID is like: file:///mnt/onboard/Books/Title.epub
    if volumeid.startswith('file:///mnt/onboard'):
        rel = volumeid.replace('file:///mnt/onboard', '')
        return os.path.join(kobo_root, rel.lstrip('/'))
    return None


def bookmark_exists(cur, bookmark_id: str) -> bool:
    cur.execute("SELECT 1 FROM Bookmark WHERE BookmarkID = ?", (bookmark_id,))
    return cur.fetchone() is not None


def pair_notes_with_highlights(clippings: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """
    Merge Kindle notes into the Annotation field of their matching highlight.
    A note matches a highlight when the note's location falls within the
    highlight's location range (loc_start..loc_end).
    Returns (merged_clippings, list_of_paired_notes).
    """
    all_notes = [c for c in clippings if c['is_note'] and not c.get('is_bookmark')]
    highlights = [c for c in clippings if not c['is_note'] and not c.get('is_bookmark')]

    # Deduplicate notes at same location — Kindle records every edit.
    # Keep the longest version (most recent complete edit) per location.
    notes_by_loc: Dict[int, Dict] = {}
    for n in all_notes:
        loc = n['loc_start']
        if loc not in notes_by_loc or len(n['text']) > len(notes_by_loc[loc]['text']):
            notes_by_loc[loc] = n
    notes = list(notes_by_loc.values())

    paired_note_indices = set()
    result = []

    for h in highlights:
        h = dict(h)
        h['annotation'] = None
        best_ni = None
        best_range = float('inf')
        for ni, n in enumerate(notes):
            if ni in paired_note_indices:
                continue
            if h['loc_start'] <= n['loc_start'] <= max(h['loc_end'], h['loc_start']):
                # Prefer the tightest highlight containing this note
                rng = h['loc_end'] - h['loc_start']
                if rng < best_range:
                    best_range = rng
                    best_ni = ni
        if best_ni is not None:
            h['annotation'] = notes[best_ni]['text']
            paired_note_indices.add(best_ni)
        result.append(h)

    paired_notes = [notes[ni] for ni in paired_note_indices]

    # Standalone notes (no matching highlight)
    for ni, n in enumerate(notes):
        if ni not in paired_note_indices:
            n = dict(n)
            n['annotation'] = n['text']
            result.append(n)

    return result, paired_notes


def get_kobo_chapter_ids(cur, volume_id: str) -> List[str]:
    """Return chapter ContentIDs from the content table for a given VolumeID."""
    cur.execute("""
        SELECT ContentID FROM content
        WHERE BookID = ? AND ContentType != 6
        ORDER BY ContentID
    """, (volume_id,))
    return [row[0] for row in cur.fetchall()]


def cleanup_duplicate_notes(cur):
    """Delete standalone notes that are already merged into an annotated highlight."""
    cur.execute("""
        DELETE FROM Bookmark
        WHERE BookmarkID IN (
            SELECT DISTINCT s.BookmarkID
            FROM Bookmark s
            JOIN Bookmark h ON h.VolumeID = s.VolumeID
                            AND h.Annotation = s.Annotation
                            AND h.Text IS NOT NULL
            WHERE s.Text IS NULL AND s.Type = 'note'
        )
    """)
    return cur.rowcount


def get_kobo_user_id(cur) -> str:
    """Read the Kobo account UserID from existing bookmarks."""
    cur.execute("SELECT UserID FROM Bookmark WHERE UserID IS NOT NULL AND UserID != '' LIMIT 1")
    row = cur.fetchone()
    return row[0] if row else ''


def insert_bookmarks(kobo_db: str, kobo_root: str, books: Dict[str, List[Dict]], overwrite: bool = False):
    """Import Kindle clippings into Kobo's database."""
    kobo_books = get_kobo_books(kobo_db)
    if not kobo_books:
        print('❌ No books found in Kobo database. Is the Kobo connected and mounted?')
        return

    print(f'\nFound {len(kobo_books)} books in your Kobo library.')

    conn = sqlite3.connect(kobo_db)
    cur = conn.cursor()

    user_id = get_kobo_user_id(cur)
    if user_id:
        print(f'   → Kobo UserID: {user_id}')

    deleted = cleanup_duplicate_notes(cur)
    if deleted:
        print(f'   → Cleaned up {deleted} duplicate standalone notes')

    # Remove any leftover Kindle clipping-limit placeholder entries from prior runs
    cur.execute("""
        DELETE FROM Bookmark WHERE
            (Text LIKE '%atteint la limite%' OR Text LIKE '%clipping limit%' OR Text LIKE '%reached the limit%')
            OR (Annotation LIKE '%atteint la limite%' OR Annotation LIKE '%clipping limit%' OR Annotation LIKE '%reached the limit%')
    """)
    if cur.rowcount:
        print(f'   → Removed {cur.rowcount} leftover clipping-limit entries from DB')
    conn.commit()

    total_inserted = 0
    total_skipped = 0
    total_nomatch = 0

    for kindle_title, clippings in books.items():
        kobo_book = find_kobo_match(kindle_title, kobo_books)
        if not kobo_book:
            print(f'  ⚠️  No Kobo match for: {kindle_title}')
            total_nomatch += len(clippings)
            continue

        volume_id = kobo_book['volumeid']
        epub_path = get_epub_path_from_volumeid(volume_id, kobo_root)

        print(f'\n📖 {kindle_title}')
        print(f'   → Matched: {kobo_book["title"]}')

        # Load EPUB spine
        spine = []
        span_index = []
        if epub_path and os.path.exists(epub_path):
            spine = get_epub_spine(epub_path)
            span_index = build_epub_span_index(spine)
            print(f'   → EPUB loaded: {len(spine)} chapters, {len(span_index)} spans')
        else:
            print(f'   → EPUB not found at {epub_path}, inserting without position')

        # Get actual chapter ContentIDs from the Kobo content table as fallback
        chapter_ids = get_kobo_chapter_ids(cur, volume_id)
        fallback_content_id = chapter_ids[0] if chapter_ids else volume_id

        # Merge notes into their matching highlights; bookmarks handled separately
        book_bookmarks = [c for c in clippings if c.get('is_bookmark')]
        paired_clippings, paired_notes = pair_notes_with_highlights(clippings)
        paired_clippings = paired_clippings + book_bookmarks

        inserted = 0
        skipped = 0

        # loc_chapter_map: list of (loc_start, content_id, chapter_progress, span_path)
        # built from highlights that matched a chapter; used to estimate bookmark
        # positions since Kindle location numbers don't map directly to EPUB spans.
        loc_chapter_map: List[Tuple[int, str, float, str]] = []

        # Delete old standalone note bookmarks that are now merged into highlights
        if overwrite:
            for note in paired_notes:
                old_note_id = str(uuid.uuid5(uuid.NAMESPACE_URL,
                                             f"{volume_id}|{note['loc_start']}|{note['text'][:50]}"))
                cur.execute("DELETE FROM Bookmark WHERE BookmarkID = ?", (old_note_id,))

        for c in paired_clippings:
            id_text = c['text'][:50] if c.get('text') else f"bookmark|{c['loc_start']}"
            bookmark_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{volume_id}|{c['loc_start']}|{id_text}"))

            if bookmark_exists(cur, bookmark_id):
                if overwrite:
                    cur.execute("DELETE FROM Bookmark WHERE BookmarkID = ?", (bookmark_id,))
                else:
                    skipped += 1
                    continue

            # Try to find text position in EPUB
            start_xpath = r'span#kobo\.1\.1'
            start_offset = 0
            end_xpath = r'span#kobo\.1\.1'
            end_offset = 0
            chapter_progress = 0.0
            content_id = fallback_content_id

            if (c.get('is_bookmark') or c['is_note']) and span_index:
                # Map Kindle location (≈128 chars each) directly to a kobo span
                result = kindle_location_to_span(c['loc_start'], span_index)
                if result:
                    href, span_id, offset = result
                    base_vol = volume_id.replace('file://', '')
                    content_id = f"{base_vol}!!{href}"
                    chapter_progress = next(
                        (i / len(spine) for i, (h, _) in enumerate(spine) if h == href), 0.0)
                    start_xpath = 'span#' + span_id.replace('.', r'\.')
                    end_xpath = start_xpath
                    start_offset = offset
                    end_offset = offset
            elif spine and c.get('text'):
                for i, (href, html_bytes) in enumerate(spine):
                    result = find_text_in_html(html_bytes, c['text'])
                    if result:
                        start_xpath, start_offset, end_xpath, end_offset = result
                        chapter_progress = i / len(spine)
                        base_vol = volume_id.replace('file://', '')
                        content_id = f"{base_vol}!!{href}"
                        loc_chapter_map.append((c['loc_start'], content_id, chapter_progress, start_xpath))
                        break

            try:
                cur.execute("""
                    INSERT INTO Bookmark (
                        BookmarkID, VolumeID, ContentID,
                        StartContainerPath, StartContainerChildIndex, StartOffset,
                        EndContainerPath, EndContainerChildIndex, EndOffset,
                        Text, Annotation,
                        DateCreated, DateModified,
                        Hidden, Version, ChapterProgress, Type, UserID
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    bookmark_id, volume_id, content_id,
                    start_xpath, -99, start_offset,
                    end_xpath, -99, end_offset,
                    c['text'] if not c['is_note'] and not c.get('is_bookmark') else None,
                    c.get('annotation'),
                    c['date'], c['date'],
                    'false', '',
                    chapter_progress,
                    'dogear' if c.get('is_bookmark') else ('note' if (c['is_note'] or c.get('annotation')) else 'highlight'),
                    user_id,
                ))
                inserted += 1
            except sqlite3.Error as e:
                print(f'     ⚠️  DB error: {e}')

        conn.commit()
        print(f'   ✅ Inserted {inserted}, skipped {skipped} (already exist)')
        total_inserted += inserted
        total_skipped += skipped

    conn.close()
    print(f'\n🎉 Done! Inserted {total_inserted} annotations, skipped {total_skipped} duplicates, {total_nomatch} had no Kobo match.')


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

# ─────────────────────────────────────────
# CALIBRE IMPORT
# ─────────────────────────────────────────

def get_cfi_for_element(element, root) -> str:
    """Generate an EPUB CFI path for an element within its document."""
    path_parts = []
    current = element
    while current is not None and current != root:
        parent = current.getparent()
        if parent is None:
            break
        # CFI uses 2 * (1-based index among element siblings)
        idx = list(parent).index(current) + 1
        tag = current.tag.split('}')[-1] if '}' in current.tag else current.tag
        try:
            id_attr = current.get('id')
            if id_attr:
                path_parts.append(f'{idx * 2}[{id_attr}]')
            else:
                path_parts.append(str(idx * 2))
        except Exception:
            path_parts.append(str(idx * 2))
        current = parent
    path_parts.reverse()
    return '/' + '/'.join(path_parts) if path_parts else '/4/2'


def find_calibre_books(calibre_library: str) -> Dict[str, Dict]:
    """Return books from Calibre library keyed by normalized title."""
    db_path = os.path.join(calibre_library, 'metadata.db')
    books = {}
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
            SELECT b.id, b.title, b.path, d.name, d.format
            FROM books b
            JOIN data d ON b.id = d.book
            WHERE d.format IN ('EPUB', 'KEPUB')
            ORDER BY b.id
        """)
        for book_id, title, book_path, data_name, fmt in cur.fetchall():
            norm = normalize_title(title)
            epub_path = os.path.join(calibre_library, book_path, f'{data_name}.{fmt.lower()}')
            if norm not in books:  # prefer EPUB over KEPUB
                books[norm] = {
                    'id': book_id,
                    'title': title,
                    'epub_path': epub_path,
                    'format': fmt,
                }
        conn.close()
    except Exception as e:
        print(f'  Warning: could not read Calibre books: {e}')
    return books


def insert_calibre_annotations(calibre_library: str, books: Dict[str, List[Dict]]):
    """Import Kindle clippings into Calibre's annotations table."""
    db_path = os.path.join(calibre_library, 'metadata.db')
    if not os.path.exists(db_path):
        print(f'❌ Calibre database not found at {db_path}')
        return

    calibre_books = find_calibre_books(calibre_library)
    print(f'\nFound {len(calibre_books)} books in your Calibre library.')

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    total_inserted = 0
    total_skipped = 0
    total_nomatch = 0

    for kindle_title, clippings in books.items():
        # Find Calibre match
        calibre_book = find_kobo_match(kindle_title, calibre_books)
        if not calibre_book:
            print(f'  ⚠️  No Calibre match for: {kindle_title}')
            total_nomatch += len(clippings)
            continue

        book_id = calibre_book['id']
        epub_path = calibre_book['epub_path']
        fmt = calibre_book['format']

        print(f'\n📖 {kindle_title}')
        print(f'   → Matched: {calibre_book["title"]} (id={book_id})')

        # Load EPUB spine
        spine = []
        if os.path.exists(epub_path):
            spine = get_epub_spine(epub_path)
            print(f'   → EPUB loaded: {len(spine)} chapters')
        else:
            print(f'   → EPUB not found, inserting without position info')

        inserted = 0
        skipped = 0

        for c in clippings:
            annot_id = str(uuid.uuid5(uuid.NAMESPACE_URL,
                                      f"calibre|{book_id}|{c['loc_start']}|{c['text'][:50]}"))

            # Check for duplicate
            cur.execute("""
                SELECT 1 FROM annotations
                WHERE book=? AND annot_id=? AND user_type='local' AND user='user'
            """, (book_id, annot_id))
            if cur.fetchone():
                skipped += 1
                continue

            # Find text position in EPUB
            spine_index = 0
            spine_name = spine[0][0] if spine else ''
            start_cfi = '/4/2/2/1:0'
            end_cfi = f'/4/2/2/1:{len(c["text"])}'

            if spine:
                for i, (href, html_bytes) in enumerate(spine):
                    result = find_text_in_html(html_bytes, c['text'])
                    if result:
                        sx, so, ex, eo = result
                        spine_index = i
                        spine_name = Path(href).name
                        start_cfi = f'{sx}:{so}'
                        end_cfi = f'{ex}:{eo}'
                        break

            # Build package-level CFI: /2/N[spine-id] where N = 2*(spine_index+1)
            pkg_cfi = f'/2/{2*(spine_index+1)}'
            full_start_cfi = f'{pkg_cfi}!{start_cfi}'
            full_end_cfi = f'{pkg_cfi}!{end_cfi}'

            # Build annot_data JSON
            if c['is_note']:
                annot_type = 'bookmark'
                annot_data = {
                    'notes': c['text'],
                    'spine_index': spine_index,
                    'spine_name': spine_name,
                    'start_cfi': full_start_cfi,
                    'timestamp': c['date'],
                    'type': 'bookmark',
                    'uuid': annot_id,
                }
                searchable = c['text']
            else:
                annot_type = 'highlight'
                annot_data = {
                    'end_cfi': full_end_cfi,
                    'highlighted_text': c['text'],
                    'notes': '',
                    'spine_index': spine_index,
                    'spine_name': spine_name,
                    'start_cfi': full_start_cfi,
                    'timestamp': c['date'],
                    'type': 'highlight',
                    'uuid': annot_id,
                    'style': {'kind': 'color', 'type': 'builtin', 'which': 'yellow'},
                }
                searchable = c['text']

            import json as _json
            timestamp = datetime.fromisoformat(
                c['date'].replace('Z', '+00:00')).timestamp()

            try:
                cur.execute("""
                    INSERT INTO annotations
                        (book, format, user_type, user, timestamp,
                         annot_id, annot_type, annot_data, searchable_text)
                    VALUES (?, ?, 'local', 'user', ?, ?, ?, ?, ?)
                """, (
                    book_id, fmt, timestamp,
                    annot_id, annot_type,
                    _json.dumps(annot_data, ensure_ascii=False),
                    searchable,
                ))
                inserted += 1
            except sqlite3.Error as e:
                print(f'     ⚠️  DB error: {e}')

        conn.commit()
        print(f'   ✅ Inserted {inserted}, skipped {skipped} (already exist)')
        total_inserted += inserted
        total_skipped += skipped

    conn.close()
    print(f'\n🎉 Done! Inserted {total_inserted} Calibre annotations, '
          f'skipped {total_skipped} duplicates, {total_nomatch} had no match.')


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Kindle annotation importer')
    parser.add_argument('--clippings', required=True, help='Path to My Clippings.txt')
    parser.add_argument('--export', help='Export highlights to this Markdown file')
    parser.add_argument('--kobo', help='Path to mounted Kobo root (e.g. /Volumes/KOBOeReader)')
    parser.add_argument('--import', dest='do_import', action='store_true',
                        help='Import annotations into Kobo database')
    parser.add_argument('--overwrite', action='store_true',
                        help='Delete and re-insert existing bookmarks (fixes broken prior imports)')
    parser.add_argument('--calibre', help='Path to Calibre library folder')
    parser.add_argument('--import-calibre', dest='do_calibre', action='store_true',
                        help='Import annotations into Calibre database')
    args = parser.parse_args()

    print(f'📚 Parsing {args.clippings}...')
    books = parse_clippings(args.clippings)
    total = sum(len(v) for v in books.values())
    print(f'   Found {total} annotations across {len(books)} books.\n')

    if args.export:
        print(f'📝 Exporting Markdown to {args.export}...')
        export_markdown(books, args.export)

    if args.do_import:
        if not args.kobo:
            print('❌ --kobo path required for --import')
            sys.exit(1)
        kobo_db = os.path.join(args.kobo, '.kobo', 'KoboReader.sqlite')
        if not os.path.exists(kobo_db):
            print(f'❌ Kobo database not found at {kobo_db}')
            print('   Make sure your Kobo is connected and mounted.')
            sys.exit(1)
        print(f'🔌 Importing into Kobo at {args.kobo}...')
        insert_bookmarks(kobo_db, args.kobo, books, overwrite=args.overwrite)

    if args.do_calibre:
        if not args.calibre:
            print('❌ --calibre path required for --import-calibre')
            sys.exit(1)
        print(f'📚 Importing into Calibre at {args.calibre}...')
        insert_calibre_annotations(args.calibre, books)

    if not args.export and not args.do_import and not args.do_calibre:
        print('Nothing to do. Use --export, --import, and/or --import-calibre.')
        parser.print_help()


if __name__ == '__main__':
    main()
