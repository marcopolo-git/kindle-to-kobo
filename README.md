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
