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

All of it is published to GitHub Pages and rebuilt daily.

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
python run.py vector     # build vector (MVT) tiles via WSL tippecanoe
python run.py raster     # build text-on-path raster (PNG) tiles
python run.py site       # render the landing page
python run.py publish    # force-push the site to the gh-pages branch

python run.py build      # download + slim + vector + raster + site
python run.py update     # build + publish  (the daily entry point)
```

Build output lands in `build/site/`; that directory is what gets published.

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

Run as Administrator:

```powershell
.\schedule-add.ps1      # registers a daily task "TorontoStreetsLayer" at 15:30
.\schedule-remove.ps1   # unregisters it
```

It is set for 15:30 &mdash; after the sibling address-layer task &mdash; so the
two tippecanoe/WSL builds do not contend.

### The link gate

Both network steps &mdash; the dataset download and the `gh-pages` push &mdash;
run behind `addressvault.net`, the same offline/metered gate the address vault
pulls behind. A dead link is not a build failure: `run.py` exits **75**
(`EX_TEMPFAIL`), nothing is written, and the task's restart-on-failure retries
three times half an hour apart rather than leaving a seven-day gap. It does not
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
pytest                       # the above, plus the download / publish tests
```

## Licence / attribution

Street data is &copy; City of Toronto, published under the
[Open Government Licence &ndash; Toronto](https://open.toronto.ca/open-data-licence/).
Tiles and the landing page carry that attribution.
