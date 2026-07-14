# The My Clippings.txt format, and how clipshelf reads it

Every Kindle keeps a single append-only log at `documents/My Clippings.txt`.
This document describes the shapes clipshelf understands and the exact rules
its dedupe engine applies. It is the reference for anyone extending the
parser or tuning the merger.

## Entry anatomy

```text
How to Read a Book (Mortimer J. Adler)
- Your Highlight on page 23 | Location 351-352 | Added on Tuesday, March 5, 2024 9:12:45 PM

Reading a book should be a conversation between you and the author.
==========
```

1. **Title line** — `Title (Author)`. The author is the *last* parenthesized
   group at the end of the line, so `Ficciones (Spanish Edition) (Jorge Luis
   Borges)` keeps `(Spanish Edition)` in the title. Entries without any
   parentheses have no author; when exactly one authored book shares the
   title, authorless entries fold into it.
2. **Metadata line** — starts with `-`. Segments are `|`-separated:
   kind (`Your Highlight` / `Your Note` / `Your Bookmark` / `Clip This
   Article`), optional page, optional location range, timestamp.
3. **Text** — zero or more lines (bookmarks have none), then the separator
   line of ten `=` characters.

Files are UTF-8 with a BOM on current devices; very old devices wrote
UTF-16, which is also handled. Line endings are CRLF.

## Firmware and locale variance

| Variant | Example | Handling |
|---|---|---|
| Pre-2011 metadata | `- Highlight on Page ix \| Loc. 351-52 \| …` and the page-less `- Highlight Loc. 351-52 \| …` | `Loc.` keyword, roman pages, abbreviated range ends |
| Abbreviated range end | `Loc. 351-52` | end borrows the start's leading digits → `351-352` |
| Roman-numeral pages | `page ix` | pages are stored as text, never coerced to int |
| Device languages | `Tu subrayado…`, `Votre surlignement…`, `Ihre Markierung…`, `La tua evidenziazione…`, `Seu destaque…`, `您在位置 #351-352的标注`, `位置No. 152-155のハイライト` | keyword tables in `locales.py`; one file may mix all of them |
| Timestamps | US/UK English, dotted German days, `de marzo de`, `2024年3月5日`, `上午/下午`, numeric fallbacks | independent piece extraction in `dates.py`; unparseable dates become `None`, never a lost entry |

Malformed entries produce warnings on `ParseResult.warnings` and are kept
with `Kind.UNKNOWN` when they have text; parsing never raises for a bad
entry.

## Dedupe rules

Kindle appends a *complete new entry* every time a highlight's edges are
adjusted. clipshelf collapses these per book, for highlights only:

1. Candidates must have **overlapping location ranges**. Disjoint ranges
   never merge, even with identical text (the same sentence highlighted in
   two chapters is two highlights).
2. Texts are normalized (NFKC, casefold, whitespace collapse) and compared:
   - equal → `identical`
   - one contains the other → `contained` (an extension or a trim)
   - otherwise, if `longest common run / shorter length >=` the overlap
     ratio (default **0.6**, tunable with `--overlap-ratio`) → `revised`
3. The **survivor** is the later revision: by timestamp when both entries
   have one, else by file position (Kindle appends, so later = newer).
   Exception: for containment without timestamp evidence the *longer* text
   wins — keeping more of the user's words is the safer default — but a
   strictly later, strictly shorter revision is honored as a deliberate trim.

Notes and bookmarks only lose exact repeats (same normalized text at the
same location, as produced by merged backups). Two different notes at one
location are both kept: notes are the user's own words, and clipshelf never
fuzzy-merges them. Entries of unknown kind pass through untouched.

Every removal is recorded as a `Dropped(clipping, reason, kept)` record, so
`stats` can report `duplicates_by_reason` and nothing disappears silently.
