# Kindle to Kobo Annotation Importer

A Python script that migrates highlights, notes, and bookmarks from a Kindle's
`My Clippings.txt` into a Kobo e-reader or Calibre library, or exports them to
a readable Markdown file.

## Features

- **Parses** `My Clippings.txt`, grouping annotations by book and pairing
  notes with the highlights they annotate.
- **Exports** all highlights and notes to a Markdown file with a table of
  contents.
- **Imports into Kobo**: inserts highlights, notes, and bookmarks directly
  into `KoboReader.sqlite`, matching Kindle clippings to Kobo library titles
  (fuzzy title matching) and locating the corresponding text inside the
  book's EPUB/KEPUB to position the annotation correctly.
- **Imports into Calibre**: inserts annotations into Calibre's
  `metadata.db`, generating EPUB CFI positions from the book's spine.
- Skips duplicate annotations on repeat runs; `--overwrite` can force
  re-insertion.
- Filters out Kindle's DRM "clipping limit reached" placeholder entries.
- Handles French-localized Kindle clipping metadata (e.g. `emplacement`,
  `page`, French month names).

## Requirements

- Python 3
- [`lxml`](https://pypi.org/project/lxml/)

```bash
pip install lxml
```

## Getting `My Clippings.txt` from your Kindle

`My Clippings.txt` is a plain-text file the Kindle generates automatically,
containing every highlight, note, and bookmark you've made across all books.

1. Connect your Kindle to your computer with a USB cable.
2. Wait for it to appear as a USB drive (on macOS: Finder; on Windows: File
   Explorer; on Linux: your file manager or `/media/...`).
3. Open the Kindle drive — `My Clippings.txt` is in the root `documents`
   folder (path is typically `Kindle/documents/My Clippings.txt`).
4. Copy the file to your computer.
5. Safely eject the Kindle before unplugging it.

## Usage

Export highlights to Markdown (no device needed):

```bash
python3 kindle_to_kobo_annotations.py --clippings "My Clippings.txt" --export highlights.md
```

Import into a connected Kobo:

```bash
python3 kindle_to_kobo_annotations.py --clippings "My Clippings.txt" \
  --kobo /Volumes/KOBOeReader --import
```

Import into a Calibre library:

```bash
python3 kindle_to_kobo_annotations.py --clippings "My Clippings.txt" \
  --calibre "/path/to/Calibre Library" --import-calibre
```

Do everything at once:

```bash
python3 kindle_to_kobo_annotations.py --clippings "My Clippings.txt" \
  --export highlights.md \
  --kobo /Volumes/KOBOeReader --import \
  --calibre "/path/to/Calibre Library" --import-calibre
```

### Options

| Flag | Description |
| --- | --- |
| `--clippings PATH` | Path to `My Clippings.txt` (required) |
| `--export PATH` | Export all annotations to a Markdown file |
| `--kobo PATH` | Path to the mounted Kobo root (e.g. `/Volumes/KOBOeReader`) |
| `--import` | Import annotations into the Kobo database |
| `--overwrite` | Delete and re-insert existing bookmarks (fixes broken prior imports) |
| `--calibre PATH` | Path to a Calibre library folder |
| `--import-calibre` | Import annotations into the Calibre database |

## How book matching works

Kindle titles are matched to library titles first by exact normalized-title
match, then by word-overlap similarity if no exact match is found. Books
that can't be matched with reasonable confidence are skipped and reported.

## Notes & caveats

- **Back up `KoboReader.sqlite` / `metadata.db` before importing** — this
  script writes directly to those databases.
- Position matching relies on locating the highlighted text inside the
  book's EPUB, so accuracy depends on the Kobo/Calibre edition matching the
  Kindle edition closely enough for the text to be found.
- The Kobo must be connected and mounted as a filesystem for `--import`.

## Known limitations

- **DRM-protected books cap the number of highlights.** Publishers can
  limit how much of a book you're allowed to clip. Once you hit that cap,
  Kindle replaces further highlights with a "You have reached the clipping
  limit for this item" placeholder instead of the actual text. The script
  filters out these placeholder entries, but the underlying highlights are
  gone from `My Clippings.txt` and can't be recovered by this tool.
- **Kindle location numbers are approximate.** Kindle "locations" are
  estimated at ~128 characters each, so mapping a location to an exact spot
  in the EPUB (used for Kobo bookmarks/notes) is approximate and may be off
  by a sentence or two.
- **Date parsing only handles French Kindle metadata.** `My Clippings.txt`
  timestamps in other locales (e.g. English) aren't recognized and fall
  back to the current time instead of the original annotation date.
- **Title matching can fail or mismatch.** Books are matched between
  Kindle, Kobo, and Calibre by title similarity; very different titles
  (e.g. translated editions) may not match, or may match to the wrong book.
- Text-based position lookup (used for Kobo highlights and all Calibre
  annotations) requires the highlighted text to appear verbatim in the
  target EPUB — retranslated, re-edited, or differently formatted editions
  may fail to position correctly even when the book itself matches.
