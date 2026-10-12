# TODO

## Detect street renames by segment, not by name id

`renamed` in the update history (`data/history.jsonl`, see README "Statistics") has been 0 in every
release since 2026-06-03. When the City names or renames a street, usually a laneway, it issues a
new `LINEAR_NAME_ID`. The id-based diff in `src/history.py` therefore records one street added and
one removed, never a rename.

Fix: diff individual segments by `CENTRELINE_ID` between releases. If a segment keeps its id but its
name id or name changes, that's a rename. Report it as old → new name, and drop the pair from
added/removed.

- Needs the previous release's segment → name map. Today `data/names/` keeps only name id → name per
  release, and only on this machine. Keep a per-release `CENTRELINE_ID → LINEAR_NAME_ID` map beside
  it, or derive it from the dated downloads in `data/`.
- `run.py backfill` can then recompute `renamed` for the releases already on disk.
- Noted 2026-10-12.
