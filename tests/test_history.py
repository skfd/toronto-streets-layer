"""The release history: what an update records, what a backfill adds, and what
the history page is rendered from.

Two properties matter more than the rest: a row is dated by the City release,
so rerunning on the same release replaces its row instead of adding a point;
and the added/removed/renamed diff is taken by TCL name id against the previous
release on record -- including when a backfill slots an older release in after
a later one was recorded.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config, history, site  # noqa: E402

LINE = {"type": "LineString", "coordinates": [[-79.4, 43.7], [-79.39, 43.71]]}


def feature(name, name_id, klass="Local", geometry=LINE):
    return {"type": "Feature", "geometry": geometry,
            "properties": {config.NAME_KEY: name, config.NAME_ID_KEY: name_id,
                           config.CLASS_KEY: klass}}


# Two segments of one street, a second street sharing nothing, and features the
# layer drops: a river (excluded class), an unnamed segment, and a point.
BASE = [
    feature("Daisy Avenue", 1), feature("Daisy Avenue", 1),
    feature("King Street West", 2, "Major Arterial"),
    feature("Humber River", 90, "River"),
    feature("None", 91),
    feature("Point Street", 92, geometry={"type": "Point", "coordinates": [0, 0]}),
]


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "HISTORY_PATH", str(tmp_path / "history.jsonl"))
    monkeypatch.setattr(config, "NAMES_DIR", str(tmp_path / "names"))
    monkeypatch.setattr(history, "seed", lambda: False)
    return tmp_path


def release(tmp_path, day, features):
    path = tmp_path / f"centreline-{day}.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}),
                    encoding="utf-8")
    return str(path)


def test_the_row_is_dated_by_the_release_not_the_run():
    assert history.source_date("data/centreline-2026-10-02.geojson") == "2026-10-02"
    with pytest.raises(ValueError):
        history.source_date("data/streets-slim.geojsonl")


def test_measure_counts_what_slim_keeps(paths):
    stats, names = history.measure(release(paths, "2026-10-02", BASE))
    assert stats == {"features": 3, "streets": 2, "names": 2,
                     "classes": {"Local": 2, "Major Arterial": 1}}
    assert names == {"1": "Daisy Avenue", "2": "King Street West"}


def test_names_and_streets_differ_when_two_ids_share_a_name(paths):
    stats, _ = history.measure(release(paths, "2026-10-02", BASE + [
        feature("Daisy Avenue", 3)]))
    assert stats["streets"] == 3 and stats["names"] == 2


def test_the_oldest_release_has_no_diff(paths):
    row = history.record(release(paths, "2026-09-25", BASE))
    assert row["date"] == "2026-09-25" and row["source"] == "live"
    assert row["added"] is None and row["removed"] is None and row["renamed"] is None
    assert "changes" not in row


def test_a_release_is_diffed_by_name_id_against_the_one_before(paths):
    history.record(release(paths, "2026-09-25", BASE))
    row = history.record(release(paths, "2026-10-02", [
        feature("Daisy Avenue", 1),
        feature("King Street W", 2, "Major Arterial"),   # renamed, same id
        feature("Scarborough Busway", 7, "Busway"),      # new id
    ]))
    assert (row["added"], row["removed"], row["renamed"]) == (1, 0, 1)
    assert row["changes"] == {"added": ["Scarborough Busway"], "removed": [],
                              "renamed": [["King Street West", "King Street W"]]}


def test_rerunning_the_same_release_replaces_its_row(paths):
    path = release(paths, "2026-10-02", BASE)
    history.record(path)
    history.record(path)
    assert [r["date"] for r in history.load()] == ["2026-10-02"]


def test_a_rerun_still_diffs_against_the_previous_release(paths):
    history.record(release(paths, "2026-09-25", BASE))
    later = release(paths, "2026-10-02", BASE[:2])          # King St removed
    history.record(later)
    row = history.record(later)
    assert (row["added"], row["removed"]) == (0, 1)


def test_change_lists_are_capped_but_counts_are_not(paths, monkeypatch):
    monkeypatch.setattr(config, "HISTORY_LIST_CAP", 2)
    history.record(release(paths, "2026-09-25", BASE))
    row = history.record(release(paths, "2026-10-02", BASE + [
        feature(f"New Street {i}", 100 + i) for i in range(5)]))
    assert row["added"] == 5 and len(row["changes"]["added"]) == 2


def test_backfill_measures_archives_oldest_first_and_skips_dates_on_record(paths):
    release(paths, "2026-09-18", BASE[:2])
    release(paths, "2026-09-25", BASE)
    history.record(release(paths, "2026-10-02", BASE))       # live, no diff yet
    assert history.backfill() == 2
    rows = history.load()
    assert [(r["date"], r["source"]) for r in rows] == [
        ("2026-09-18", "archive"), ("2026-09-25", "archive"), ("2026-10-02", "live")]
    assert rows[1]["added"] == 1, "King Street West appeared on 09-25"
    assert rows[2]["added"] == 0, "the live row is re-diffed against 09-25"
    assert history.backfill() == 0, "a second run has nothing to do"


def test_a_row_whose_names_are_gone_keeps_its_recorded_diff(paths):
    history.record(release(paths, "2026-09-25", BASE))
    history.record(release(paths, "2026-10-02", BASE[:2]))
    os.remove(os.path.join(config.NAMES_DIR, "2026-09-25.json"))
    history.record(release(paths, "2026-10-09", BASE[:2]))
    rows = history.load()
    assert rows[1]["removed"] == 1
    assert rows[2]["removed"] == 0


def test_the_history_page_inlines_the_rows_and_tables_them(paths):
    history.record(release(paths, "2026-09-25", BASE))
    history.record(release(paths, "2026-10-02", BASE + [
        feature("Queen's Quay <East>", 8)]))
    site_dir = paths / "site"
    site_dir.mkdir()
    site._build_history_page(str(site_dir), "2026-10-11")

    html = (site_dir / "history.html").read_text(encoding="utf-8")
    assert "2 releases since 2026-09-25" in html
    inline = html.split('id="history-data">', 1)[1].split("</script>", 1)[0]
    assert [r["added"] for r in json.loads(inline)] == [None, 1]
    assert html.index("<td>2026-10-02</td>") < html.index("<td>2026-09-25</td>")
    assert "+ Queen&#x27;s Quay &lt;East&gt;" in html
    assert "{{" not in html
    assert (site_dir / "history.js").is_file()
    assert (site_dir / "history.jsonl").read_text(encoding="utf-8").count("\n") == 2


def test_the_history_page_renders_without_any_history(paths):
    site_dir = paths / "site"
    site_dir.mkdir()
    site._build_history_page(str(site_dir), "2026-10-11")
    html = (site_dir / "history.html").read_text(encoding="utf-8")
    assert "0 releases since 2026-10-11" in html
    assert not (site_dir / "history.jsonl").exists()
