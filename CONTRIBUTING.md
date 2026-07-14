# Contributing to clipshelf

Thanks for your interest in contributing. Issues, discussions, and pull
requests are all welcome.

## Development setup

```bash
git clone https://github.com/JaydenCJ/clipshelf
cd clipshelf
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running the checks

```bash
pytest                 # 91 unit and CLI tests, fully offline
bash scripts/smoke.sh  # end-to-end: parse, dedupe, export, verify
```

Both must pass before a pull request is reviewed; `scripts/smoke.sh` runs
the real CLI against the shipped example file and must print `SMOKE OK`.

## Ground rules

- **No new runtime dependencies.** The package is standard-library only;
  that is a feature. Test-only dependencies belong in the `dev` extra.
- **Dedupe changes need a paired negative test.** Anything that makes the
  merger more aggressive must add a test proving that genuinely distinct
  highlights still survive.
- **New locales are data, not code.** Add keyword/month rows to
  `src/clipshelf/locales.py` and a real metadata line to
  `tests/test_locales.py`; the parser itself should not need changes.
- **Rendering must stay deterministic.** No wall-clock timestamps, no
  dict-order dependence; `test_render_full_document_is_byte_stable` and
  smoke step 7 enforce this.
- **Keep the three READMEs aligned.** `README.md`, `README.zh.md`, and
  `README.ja.md` share the same structure; update all three when you
  change one (English is the authoritative version).

## Reporting bugs

Please include the smallest clippings excerpt that reproduces the problem
(a single entry between `==========` separators is usually enough), your
device language, and the output of `clipshelf --version` and
`clipshelf stats <file>`.

## Security

Please do not open public issues for security problems; use GitHub's
private vulnerability reporting instead.
