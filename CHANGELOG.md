# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-13

### Added

- Forgiving parser for `My Clippings.txt`: UTF-8 BOM and UTF-16 files,
  CRLF/LF, multi-line highlights, authorless titles, nested parentheses in
  title lines, roman-numeral pages, and malformed entries that degrade to
  warnings instead of exceptions.
- Metadata support for eight device languages in one pass — English,
  Spanish, French, German, Italian, Portuguese, Chinese, Japanese — driven
  by keyword/month tables, so mixed-locale files parse without flags.
- Pre-2011 firmware compatibility: `Loc. 351-52` abbreviated range ends
  are expanded (`351-352`), and the old `- Highlight on Page …` and
  page-less `- Highlight Loc. …` metadata shapes parse alongside the
  modern one.
- Offline dedupe engine for overlapping highlight revisions: identical
  re-syncs, contained extensions/trims, and moved-both-edges revisions all
  collapse to the final version, with an audit trail of what was dropped
  and why. Timestamps decide the survivor; file order is the fallback.
- Deliberate-trim handling: a strictly later, strictly shorter revision
  wins over the longer text only when timestamps prove intent.
- Per-book Markdown export with deterministic, byte-stable output: sorted
  reading order, blockquoted highlights, location/page/date metadata,
  notes attached beneath the highlight they annotate, collision-free
  Unicode-preserving filename slugs.
- `clipshelf` CLI: `export` (with `--book`, `--no-dedupe`,
  `--overlap-ratio`, `--include-bookmarks`, `--no-location`, `--no-date`,
  `--dry-run`), `list` and `stats` (both with `--json`).
- Runnable example clippings file covering four books, four locales, and
  three duplicate patterns, pinned by end-to-end tests.
- 91 offline pytest tests and `scripts/smoke.sh`.

### Notes

- The repository ships no CI workflow; verification is local —
  `pip install -e '.[dev]' && pytest && bash scripts/smoke.sh`.

[0.1.0]: https://github.com/JaydenCJ/clipshelf/releases/tag/v0.1.0
