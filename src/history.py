"""Keep a few numbers about every TCL release the layer is built from.

This project does not compare with OSM (the sibling toronto-streets-osm does
that), so what an update can honestly measure is the City data itself: how many
named segments the layer keeps, how many distinct streets and names, the
per-class breakdown, and which streets appeared, disappeared or were renamed
since the previous release on record. One JSON line per release goes to
data/history.jsonl and history.html charts it.

Rows are dated by the release (the date in ``centreline-YYYY-MM-DD.geojson``,
taken from the portal's Last-Modified), never by the run: rerunning on the same
release replaces its row instead of adding a point.

A "street" here is a TCL linear name (``LINEAR_NAME_ID``): every id carries
exactly one name, but ~90 names are shared by more than one id, so the diff is
taken by id -- a string diff could not tell a renamed street from a new one.
The diff needs the previous release's id -> name map, kept per release in
data/names/. Those are local only; a checkout that lost them still has every
recorded row, and only the next release's diff is unknown (null).
"""

import json
import os
import re
from collections import Counter

import requests

from src import config
from src.slim import kept_features

FIELDS = ("features", "streets", "names", "added", "removed", "renamed")
DIFF_FIELDS = ("added", "removed", "renamed")

_DATED = re.compile(r"^centreline-(\d{4}-\d{2}-\d{2})\.geojson$")


def source_date(path):
    """The release date in a downloaded centreline file's name."""
    match = _DATED.match(os.path.basename(path))
    if not match:
        raise ValueError(f"Not a dated centreline file: {path}")
    return match.group(1)


def measure(src_path):
    """Count what the layer keeps from one release.

    Returns (stats, names) where names maps str(name_id) -> name. Counts the
    same features slim keeps, by the same rule, so ``features`` always equals
    the slim count of that release.
    """
    features = 0
    classes = Counter()
    names = {}
    with open(src_path, "rb") as src:
        for feature in kept_features(src):
            if feature is None:
                continue
            props = feature["properties"]
            features += 1
            classes[props.get("class", "")] += 1
            if "name_id" in props:
                names[str(props["name_id"])] = props["name"]
    stats = {
        "features": features,
        "streets": len(names),
        "names": len(set(names.values())),
        "classes": dict(sorted(classes.items())),
    }
    return stats, names


def record(src_path, source="live"):
    """Measure a release and record its row, replacing any row of that date."""
    day = source_date(src_path)
    stats, names = measure(src_path)
    seed()
    _save_names(day, names)
    row = {"date": day, "source": source, **stats}
    rows = _rediff([r for r in load() if r["date"] != day] + [row])
    _write(rows)
    row = next(r for r in rows if r["date"] == day)
    print(f"History: recorded {day} -- {row['features']:,} features, "
          f"{row['streets']:,} streets, {_diff_text(row)} "
          f"({len(rows):,} releases on record).")
    return row


def backfill(data_dir=None):
    """Add rows for every archived release in data/ that is not on record.

    Every download is kept in data/, so the past is measured from the very
    files those builds used -- the same method as a live row, only later.
    Idempotent: dates on record are skipped. Returns the number of rows added.
    """
    data_dir = data_dir or config.DATA_DIR
    seed()
    have = {r["date"] for r in load()}
    archives = sorted(
        os.path.join(data_dir, f) for f in os.listdir(data_dir) if _DATED.match(f)
    )
    todo = [p for p in archives if source_date(p) not in have]
    if not todo:
        print("History: nothing to backfill.")
        return 0
    rows = load()
    for path in todo:
        day = source_date(path)
        stats, names = measure(path)
        _save_names(day, names)
        rows.append({"date": day, "source": "archive", **stats})
        print(f"  {day}: {stats['features']:,} features, "
              f"{stats['streets']:,} streets")
    _write(_rediff(rows))
    return len(todo)


def load():
    """All rows, oldest first. An absent file is an empty history."""
    if not os.path.isfile(config.HISTORY_PATH):
        return []
    with open(config.HISTORY_PATH, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return sorted(rows, key=lambda r: r["date"])


def seed():
    """Start a checkout that has no history from the published copy.

    data/ is not in git, so a fresh clone (or a wiped data dir) would otherwise
    begin the record again from this release. Best-effort: before the first
    publish there is nothing to fetch, and that is fine.
    """
    if os.path.isfile(config.HISTORY_PATH):
        return False
    try:
        resp = requests.get(config.HISTORY_URL,
                            headers={"User-Agent": config.USER_AGENT}, timeout=30)
    except requests.RequestException as e:
        print(f"History: could not fetch the published copy ({e}).")
        return False
    # Pages serves .jsonl without a charset; the file is always UTF-8.
    text = resp.content.decode("utf-8") if resp.status_code == 200 else ""
    if not text.strip():
        return False
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(config.HISTORY_PATH, "w", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")
    print(f"History: seeded from {config.HISTORY_URL}.")
    return True


def diff(before, after, cap=None):
    """Streets added, removed and renamed between two id -> name maps."""
    cap = config.HISTORY_LIST_CAP if cap is None else cap
    added = sorted(after[i] for i in after.keys() - before.keys())
    removed = sorted(before[i] for i in before.keys() - after.keys())
    renamed = sorted([before[i], after[i]] for i in before.keys() & after.keys()
                     if before[i] != after[i])
    return {
        "added": len(added), "removed": len(removed), "renamed": len(renamed),
        "changes": {"added": added[:cap], "removed": removed[:cap],
                    "renamed": renamed[:cap]},
    }


def _rediff(rows):
    """Recompute each row's diff against the row before it, where both maps exist.

    Run after every change to the record, so a backfilled release slotted in
    before an existing row also corrects that row's diff. A row whose maps are
    gone keeps the diff it was recorded with; the oldest row has none.
    """
    rows = sorted(rows, key=lambda r: r["date"])
    cache = {}

    def names(day):
        if day not in cache:
            cache[day] = _load_names(day)
        return cache[day]

    for i, row in enumerate(rows):
        if i == 0:
            row.update({k: None for k in DIFF_FIELDS})
            row.pop("changes", None)
            continue
        before, after = names(rows[i - 1]["date"]), names(row["date"])
        if before is not None and after is not None:
            row.update(diff(before, after))
        else:
            for k in DIFF_FIELDS:
                row.setdefault(k, None)
    return rows


def _names_path(day):
    return os.path.join(config.NAMES_DIR, f"{day}.json")


def _save_names(day, names):
    os.makedirs(config.NAMES_DIR, exist_ok=True)
    with open(_names_path(day), "w", encoding="utf-8") as f:
        json.dump(names, f, ensure_ascii=False, sort_keys=True)


def _load_names(day):
    path = _names_path(day)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _diff_text(row):
    if row.get("added") is None:
        return "no earlier release to diff against"
    return (f"+{row['added']} / -{row['removed']} / "
            f"{row['renamed']} renamed streets")


def _write(rows):
    os.makedirs(config.DATA_DIR, exist_ok=True)
    rows = sorted(rows, key=lambda r: r["date"])
    with open(config.HISTORY_PATH, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
