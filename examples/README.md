# clipshelf examples

`My Clippings.txt` here is a realistic sample of the file a Kindle keeps at
`documents/My Clippings.txt`. It is small (11 entries) but deliberately
covers the awkward cases clipshelf exists for:

| Entries | What they exercise |
|---|---|
| *How to Read a Book* ×5 + 1 exact duplicate | a highlight extended seconds later (revision pair), a note anchored inside the highlight's range, a bookmark, and a byte-identical entry from a merged backup |
| *Meditations* ×3 | a pre-2011 firmware entry (`- Highlight on Page ix \| Loc. 210-12`) whose abbreviated range must expand to 210-212 and then merge into the modern re-highlight at `209-213` |
| *Cien años de soledad* ×1 | Spanish device-language metadata (`Tu subrayado … Añadido el …`) |
| *こころ* ×1 | Japanese device-language metadata (`位置No. 152-155のハイライト`) and a non-ASCII output filename |

Run everything from the repository root:

```bash
# What is in the file?
python3 -m clipshelf stats "examples/My Clippings.txt"

# Which books, and how many duplicates would dedupe remove?
python3 -m clipshelf list "examples/My Clippings.txt"

# Write one Markdown file per book into notes/
python3 -m clipshelf export "examples/My Clippings.txt" -o notes

# Compare with the raw, undeduplicated export
python3 -m clipshelf export "examples/My Clippings.txt" -o notes-raw --no-dedupe
diff notes/how-to-read-a-book.md notes-raw/how-to-read-a-book.md
```

(`python3 -m clipshelf` works straight from a checkout with
`PYTHONPATH=src`; after `pip install -e .` the `clipshelf` command does the
same thing.)

The expected numbers — 11 entries, 4 books, 3 duplicates removed (2
contained revisions + 1 identical re-sync) — are pinned by
`tests/test_end_to_end.py` and `scripts/smoke.sh`, so this example can
never silently drift from what the code actually does.
