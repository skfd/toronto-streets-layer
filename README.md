# Toronto Streets Layer

Turns the City of Toronto [Centreline (TCL)](https://open.toronto.ca/dataset/toronto-centreline-tcl/)
dataset into map-tile layers that OpenStreetMap mappers can add to the **iD**
and **JOSM** editors as a reference overlay of street **centrelines labelled
with their full names**.

**Live layer and how to add it: https://skfd.github.io/toronto-streets-layer/**

It is a sibling of the read-only comparison report
[toronto-streets-osm](https://github.com/skfd/toronto-streets-osm), but where
that project *reports* TCL-vs-OSM differences, this one produces an overlay you
*map against*. It is standalone: the City publishes the data in WGS84, so this
project downloads it directly.

## What it produces

- **Vector tiles** (MVT) &mdash; interactive in iD; click a street to read its
  `name` (full expanded name) and `class` (road type) tags.
- **Raster tiles** (PNG) &mdash; street names drawn as text-on-path along the
  centrelines; a readable backdrop for JOSM.
- A **landing page** with copy-paste "add this layer" instructions for both
  editors.
- A **release history** page, [`history.html`](https://skfd.github.io/toronto-streets-layer/history.html),
  charting the streets each City release added, removed or renamed (see
  [Release history](#release-history)).

All of it is published to GitHub Pages and rebuilt monthly.

## Data scope

The full TCL has ~64k line features. This layer keeps the ~61.7k that are real,
named ways &mdash; roads, ramps, laneways, access roads, busways, and trails
&mdash; and drops descriptive non-street features whose TCL "names" are not
street names: rivers, creeks, hydro lines, railways, shorelines, ferry routes,
municipal boundary (geostatistical) lines, and walkways (whose TCL names are
coded). Names are the City's full legal names (e.g. *Avenue*, not *Ave*),
matching OSM's unabbreviated-name convention. The exclude set lives in
`src/config.py` (`EXCLUDE_FEATURE_CODES`).

## Setup

1. Install Python dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Set up WSL2 + tippecanoe once (used for the vector tiles); the sibling
   `toronto-addresses-layer` has the same requirement.
3. Confirm the GitHub repo in `src/config.py` (`GITHUB_REPO`, `PAGES_URL`).

## Usage

```
python run.py download   # fetch the latest TCL centreline GeoJSON (smart-cached)
python run.py slim       # filter + stream it into a slim GeoJSONL of named lines
python run.py history    # record the current release's statistics
python run.py backfill   # record every archived release in data/ not yet on record
python run.py vector     # build vector (MVT) tiles via WSL tippecanoe
python run.py raster     # build text-on-path raster (PNG) tiles
python run.py site       # render the landing page
python run.py publish    # force-push the site to the gh-pages branch

python run.py build      # download + slim + history + vector + raster + site
python run.py update     # build + publish  (the monthly scheduled entry point)
```

Build output lands in `build/site/`; that directory is what gets published.

## Release history

This layer does not compare with OSM &mdash; the sibling
[toronto-streets-osm](https://github.com/skfd/toronto-streets-osm) does &mdash; so
what each update records is what it can honestly measure about the City data
itself. Every build appends one line to `data/history.jsonl`, and the site step
charts it at [`/history.html`](https://skfd.github.io/toronto-streets-layer/history.html)
with the rows published beside it as `history.jsonl`. A row holds:

| field | meaning |
| --- | --- |
| `date` | the City release date (`centreline-YYYY-MM-DD.geojson`, from the portal's Last-Modified) |
| `source` | `live` (recorded by a build) or `archive` (measured later by `backfill`) |
| `features` | named segments the layer keeps &mdash; the same count as `slim` |
| `streets` | distinct TCL linear names (`LINEAR_NAME_ID`) |
| `names` | distinct name strings (~90 names belong to more than one street) |
| `classes` | segments per `FEATURE_CODE_DESC` road class |
| `added` / `removed` / `renamed` | streets, by name id, against the previous release on record; `null` for the oldest |
| `changes` | the names behind those counts, up to 25 of each |

Rows are dated by the **release, not the run**: rebuilding on the same release
replaces its row instead of adding a point. The diff is taken by name id because
a string diff cannot tell a renamed street from a new one; it needs the previous
release's id&rarr;name map, which is kept per release in `data/names/` (~0.4 MB
each). In practice the City issues a new id when it names a laneway (*Ln N
Robinson St E Palmerston* &rarr; *Palmira Lane*), so such a change shows as one
added and one removed street, and `renamed` has stayed 0 so far.

Every download is kept in `data/`, so the past is measured from the very files
earlier builds used: `python run.py backfill` adds a row for each archived
`centreline-*.geojson` not on record (the record starts 2026-06-03) and
re-diffs the rows after it. It reads only local files and is safe to re-run.

A checkout without `data/history.jsonl` (a fresh clone, a wiped `data/`) seeds
itself from the published `history.jsonl` before recording, so the record
survives the machine it was made on. Without `data/names/` the next release's
diff is unknown (`null`); the rows themselves are kept.

## How the raster labels work

Street names are drawn *along* the centreline. Segments sharing a `name_id` are
stitched into long polylines (`src/stitch.py`); then each name is laid out
glyph-by-glyph along the path, every character rotated to the local tangent and
haloed (`src/raster.py`). Names repeat along long streets and are placed once
globally per zoom, so a label straddling a tile seam is identical in both tiles;
colliding labels are dropped.

## Hosting

The tile pyramid is published to an orphan `gh-pages` branch, recreated and
force-pushed on every build so repository history never grows. One-time step: in
the GitHub repo, set **Settings &rarr; Pages &rarr; Source** to the `gh-pages`
branch (root).

## Scheduling (Windows)

```powershell
.\schedule-add.ps1      # registers "kk-TorontoStreetsLayer": monthly, the 1st at 09:00
.\schedule-remove.ps1   # unregisters it
```

The task runs `python run.py update` from the project folder, after sweeping
stale git locks with `..\check-git-locks.ps1 -Clear`, and appends everything to
`logs\scheduler.log`. `update` exits early when the City has not republished
since the last download. The City republishes the centreline weekly, but a
release changes a handful of streets at most, so a monthly build keeps the
layer current; each one adds a row to the release history. 09:00 keeps it clear
of the sibling `kk-TorontoAddressLayer` task (14:00), so the two
tippecanoe/WSL builds do not contend. `StartWhenAvailable` runs a missed 1st as
soon as the machine is next on.

`New-ScheduledTaskTrigger` has no monthly trigger, and `Register-ScheduledTask`
rejects a hand-built `MSFT_TaskMonthlyTrigger`, so the script creates the task
with `schtasks /SC MONTHLY` and then applies the action and settings with
`Set-ScheduledTask`. Re-running it replaces the task.

### The link gate

Both network steps &mdash; the dataset download and the `gh-pages` push &mdash;
run behind `addressvault.net`, the same offline/metered gate the address vault
pulls behind. A dead link is not a build failure: `run.py` exits **75**
(`EX_TEMPFAIL`), nothing is written, and the task's restart-on-failure retries
three times half an hour apart rather than leaving a month-long gap. It does not
wait the link out, since the task carries a hard `ExecutionTimeLimit` that would
kill a long wait anyway.

A download dropped mid-body resumes with a Range request instead of starting
over, and a push that cannot resolve `github.com` is retried without rebuilding
&mdash; the finished tiles stay on disk, so `python run.py publish` can complete
the run later. Before this, a dead resolver on 2026-07-27 threw away a whole
150k-tile build at the push.

Re-run `schedule-add.ps1` to apply the restart settings to an already registered
task.

## Tests

```
python tests\test_tilemath.py
python tests\test_stitch.py
pytest                       # the above, plus the download / publish / history tests
```

## Licence / attribution

Street data is &copy; City of Toronto, published under the
[Open Government Licence &ndash; Toronto](https://open.toronto.ca/open-data-licence/).
Tiles and the landing page carry that attribution.
