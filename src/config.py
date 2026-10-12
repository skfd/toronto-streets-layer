"""Configuration constants for the Toronto street-names tile layer build.

Single source of truth. No logic here.
"""

import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_DIR, "data")
BUILD_DIR = os.path.join(PROJECT_DIR, "build")
SITE_DIR = os.path.join(BUILD_DIR, "site")
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")
LOGS_DIR = os.path.join(PROJECT_DIR, "logs")

MBTILES_PATH = os.path.join(BUILD_DIR, "streets.mbtiles")
SLIM_PATH = os.path.join(DATA_DIR, "streets-slim.geojsonl")
COUNT_PATH = os.path.join(DATA_DIR, "streets.count")
LAST_DOWNLOAD_PATH = os.path.join(DATA_DIR, ".last-download.json")

VECTOR_TILE_DIR = os.path.join(SITE_DIR, "tiles", "vector")
RASTER_TILE_DIR = os.path.join(SITE_DIR, "tiles", "raster")

# Data source: Toronto Centreline (TCL) Version 2, published in WGS84.
# Resource IDs mirror the sibling toronto-streets-osm project's config.
TCL_PACKAGE_ID = "1d079757-377b-4564-82df-eb5638583bfb"
TCL_RESOURCE_ID = "7bc94ccf-7bcf-4a7d-88b1-bdfc8ec5aaf1"
TCL_FILENAME = "centreline-version-2-4326.geojson"
DATASET_URL = (
    f"https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/"
    f"{TCL_PACKAGE_ID}/resource/{TCL_RESOURCE_ID}/download/{TCL_FILENAME}"
)
DATASET_PAGE = "https://open.toronto.ca/dataset/toronto-centreline-tcl/"
LICENSE_URL = "https://open.toronto.ca/open-data-licence/"
# Plain-ASCII attribution embedded in tile metadata (safe through the WSL shell).
ATTRIBUTION = "(c) City of Toronto, Open Government Licence - Toronto"

# GitHub Pages target. Update both if the repo/account differs.
GITHUB_REPO = "skfd/toronto-streets-layer"
PAGES_URL = "https://skfd.github.io/toronto-streets-layer"

# WSL distro that has tippecanoe installed (see the sibling addresses layer).
WSL_DISTRO = "Ubuntu"

# Vector tiles. iD requests tiles at (map zoom - 1) and does NOT overzoom, so
# tiles must be generated natively through the zooms used for street mapping.
VECTOR_MINZOOM = 12
VECTOR_MAXZOOM = 19
VECTOR_LAYER_NAME = "streets"

# Raster tiles. Native through z19; editors overzoom z19 -> z20+.
RASTER_ZOOMS = [14, 15, 16, 17, 18, 19]

# TCL FEATURE_CODE_DESC values that are NOT streets: descriptive feature labels
# (watercourses, rail, hydro corridors, shorelines, municipal boundary lines,
# ferry routes) and Walkways, whose TCL "names" are coded gibberish
# ("Ww E Midland N Artillery"). Everything else with a name is kept.
EXCLUDE_FEATURE_CODES = frozenset({
    "River", "Creek/Tributary",
    "Hydro Line",
    "Major Railway", "Minor Railway",
    "Major Shoreline", "Minor Shoreline (Land locked)",
    "Geostatistical line",
    "Ferry Route",
    "Walkway",
})

# Source property keys read from the TCL GeoJSON.
NAME_KEY = "LINEAR_NAME_FULL_LEGAL"   # expanded name, e.g. "Daisy Avenue"
CLASS_KEY = "FEATURE_CODE_DESC"       # road class, e.g. "Local"
NAME_ID_KEY = "LINEAR_NAME_ID"        # groups segments of one street

# --- Update history (trend page) ---
# One JSON line per source date: what that TCL release holds (features, names,
# per-class counts) and which streets it added, removed or renamed against the
# previous release on record. Lives in data/ with the rest of the build state;
# the tiles are rebuilt and force-pushed each time, this file only grows, and
# its published copy re-seeds a checkout that has none.
HISTORY_PATH = os.path.join(DATA_DIR, "history.jsonl")
HISTORY_URL = f"{PAGES_URL}/history.jsonl"
# Per-release name_id -> name maps, the input to the added/removed/renamed diff.
# Small (~0.5 MB each, one per release) and local only: a wiped data/ loses the
# diff for the next release, never the recorded rows.
NAMES_DIR = os.path.join(DATA_DIR, "names")
# How many changed names a row lists per kind; the counts are never capped.
HISTORY_LIST_CAP = 25
USER_AGENT = f"toronto-streets-layer (+https://github.com/{GITHUB_REPO})"
