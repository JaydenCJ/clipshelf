#!/usr/bin/env bash
# Smoke test for clipshelf: parse the shipped example clippings file,
# export per-book Markdown, and verify dedupe, note attachment, list/stats
# output, and --version — end to end through the real CLI.
# Self-contained: pure stdlib, no network, idempotent (works from a clean tree).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

# The package has zero runtime dependencies, so running from src/ needs no install.
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/clipshelf-smoke.XXXXXX")"
trap 'rm -rf "$WORKDIR"' EXIT

fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

CLIPPINGS="$ROOT/examples/My Clippings.txt"
[ -f "$CLIPPINGS" ] || fail "example clippings file missing"

echo "[smoke] python: $("$PYTHON" --version 2>&1)"

# 1. stats: totals and dedupe reasons on the example file.
stats_out="$("$PYTHON" -m clipshelf stats "$CLIPPINGS")"
echo "$stats_out" | sed 's/^/[stats] /'
echo "$stats_out" | grep -q "entries             11" || fail "stats: wrong entry count"
echo "$stats_out" | grep -q "books               4" || fail "stats: wrong book count"
echo "$stats_out" | grep -q "duplicates removed  3" || fail "stats: dedupe did not remove 3"
echo "$stats_out" | grep -q "contained         2" || fail "stats: missing containment reason"

# 2. export: one Markdown file per book, duplicates collapsed.
export_out="$("$PYTHON" -m clipshelf export "$CLIPPINGS" -o "$WORKDIR/notes")"
echo "$export_out" | sed 's/^/[export] /'
echo "$export_out" | grep -q "4 books, 6 highlights, 1 note, 3 duplicates removed" \
  || fail "export summary wrong"
for f in how-to-read-a-book meditations cien-años-de-soledad こころ; do
  [ -f "$WORKDIR/notes/$f.md" ] || fail "missing exported file $f.md"
done

# 3. dedupe: the final revision survives, earlier partials are gone.
doc="$WORKDIR/notes/how-to-read-a-book.md"
[ "$(grep -c "Reading a book should be a conversation" "$doc")" -eq 1 ] \
  || fail "revision was not deduplicated"
grep -q "Presumably he knows more" "$doc" || fail "extended revision did not survive"
grep -q '\*\*Note:\*\* The core idea' "$doc" || fail "note not attached under its highlight"

# 4. pre-2011 abbreviated locations ("Loc. 210-12") merge into the modern entry.
grep -q "Remember: you have power" "$WORKDIR/notes/meditations.md" \
  || fail "meditations final revision missing"
grep -q "location 209-213" "$WORKDIR/notes/meditations.md" \
  || fail "expanded location range missing"

# 5. --no-dedupe keeps the raw revisions.
"$PYTHON" -m clipshelf export "$CLIPPINGS" -o "$WORKDIR/raw" --no-dedupe >/dev/null
[ "$(grep -c "Reading a book should be a conversation" "$WORKDIR/raw/how-to-read-a-book.md")" -eq 2 ] \
  || fail "--no-dedupe still deduplicated"

# 6. list --json is machine-readable and counts match.
"$PYTHON" -m clipshelf list "$CLIPPINGS" --json > "$WORKDIR/list.json"
"$PYTHON" - "$WORKDIR/list.json" <<'PYEOF' || fail "list --json shape wrong"
import json, sys
rows = json.load(open(sys.argv[1], encoding="utf-8"))
by_title = {r["title"]: r for r in rows}
assert len(rows) == 4
assert by_title["How to Read a Book"]["duplicates_removed"] == 2
assert by_title["Meditations"]["highlights"] == 2
PYEOF

# 7. exports are deterministic: run twice, byte-identical.
"$PYTHON" -m clipshelf export "$CLIPPINGS" -o "$WORKDIR/notes2" >/dev/null
diff -r "$WORKDIR/notes" "$WORKDIR/notes2" >/dev/null || fail "export not deterministic"

# 8. --version agrees with the package version.
version_out="$("$PYTHON" -m clipshelf --version)"
pkg_version="$("$PYTHON" -c 'import clipshelf; print(clipshelf.__version__)')"
[ "$version_out" = "clipshelf $pkg_version" ] \
  || fail "--version mismatch: '$version_out' vs package '$pkg_version'"

echo "SMOKE OK"
