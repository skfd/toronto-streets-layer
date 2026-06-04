"""Convert the full TCL centreline GeoJSON into a slim newline-delimited GeoJSON.

The source is a single ~88 MB GeoJSON FeatureCollection, so it is parsed as a
stream with ijson -- never loaded into memory at once. Each kept feature becomes
one compact line, geometry preserved (LineString / MultiLineString), carrying
only the name, road class, and name id. This slim file is the shared input to
both tile builders.
"""

import json
import os

import ijson

from src import config

# Sanity bounds for the slimmed feature count (~61.7k after the exclude filter).
MIN_EXPECTED = 55_000
MAX_EXPECTED = 65_000


def slim(src_path):
    """Stream the big GeoJSON into data/streets-slim.geojsonl.

    Drops features whose FEATURE_CODE_DESC is in EXCLUDE_FEATURE_CODES, and any
    without a name or line geometry. Returns the slim file path. Raises if the
    feature count is implausible.
    """
    print(f"Slimming {src_path} ...")
    os.makedirs(config.DATA_DIR, exist_ok=True)

    count = 0
    skipped = 0
    with open(src_path, "rb") as src, \
            open(config.SLIM_PATH, "w", encoding="utf-8") as out:
        for feature in ijson.items(src, "features.item"):
            props_in = feature.get("properties") or {}
            if props_in.get(config.CLASS_KEY) in config.EXCLUDE_FEATURE_CODES:
                skipped += 1
                continue

            geom = _line_geometry(feature.get("geometry") or {})
            name = _clean(props_in.get(config.NAME_KEY))
            if geom is None or not name:
                skipped += 1
                continue

            props_out = {"name": name}
            klass = _clean(props_in.get(config.CLASS_KEY))
            if klass:
                props_out["class"] = klass
            name_id = props_in.get(config.NAME_ID_KEY)
            if name_id is not None:
                props_out["name_id"] = name_id

            out.write(json.dumps({
                "type": "Feature",
                "geometry": geom,
                "properties": props_out,
            }) + "\n")
            count += 1
            if count % 10_000 == 0:
                print(f"  {count:,} features ...")

    with open(config.COUNT_PATH, "w", encoding="utf-8") as f:
        f.write(str(count))

    print(f"Done: {config.SLIM_PATH} ({count:,} features, {skipped:,} skipped)")
    if not MIN_EXPECTED <= count <= MAX_EXPECTED:
        raise RuntimeError(
            f"Slim feature count {count:,} is outside the expected range "
            f"{MIN_EXPECTED:,}-{MAX_EXPECTED:,} -- aborting."
        )
    return config.SLIM_PATH


def _clean(val):
    """Strip a source string value, treating the literal 'None' as empty."""
    if val is None:
        return ""
    text = str(val).strip()
    return "" if text in ("", "None") else text


def _line_geometry(geom):
    """Return a LineString/MultiLineString geometry with float coords, or None.

    ijson yields coordinates as Decimal; convert to plain floats (rounded to
    ~0.1 m) so the result is JSON-serializable and compact.
    """
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if not coords or gtype not in ("LineString", "MultiLineString"):
        return None
    if gtype == "LineString":
        out = _round_line(coords)
    else:
        out = [_round_line(line) for line in coords if line]
        out = [line for line in out if line]
    if not out:
        return None
    return {"type": gtype, "coordinates": out}


def _round_line(line):
    return [[round(float(lon), 6), round(float(lat), 6)] for lon, lat in line]
