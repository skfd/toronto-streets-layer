"""Stitch TCL street segments into longer polylines for label placement.

The slim GeoJSONL has one feature per TCL centreline segment, and a street is
split into many segments at every intersection. For drawing a name *along* a
street we want few long polylines, not hundreds of stubs, so segments that share
the same `name_id` and touch end-to-end are chained together.

Topology is approximate -- good enough for label placement, not for routing.
Endpoints come from the noded TCL network and match exactly once rounded.
"""

import json
import math

from src import config

# Join runs of the same street whose endpoints fall within this many metres.
# Covers both tiny coordinate-precision gaps (sub-metre) and real breaks in a
# street's centreline (e.g. Violet Avenue's ~43 m gap), so each street becomes
# one run carrying a single label. A short connector is drawn across the gap.
SNAP_TOLERANCE_M = 50.0


def read_groups(slim_path=None):
    """Return {name_id: {"name": str, "lines": [[(lon,lat), ...], ...]}}.

    Each feature's LineString / MultiLineString parts become individual lines,
    grouped by name_id (features with no name_id are keyed by their name).
    """
    slim_path = slim_path or config.SLIM_PATH
    groups = {}
    with open(slim_path, encoding="utf-8") as f:
        for line in f:
            feat = json.loads(line)
            props = feat["properties"]
            name = props["name"]
            key = props.get("name_id", f"name:{name}")
            geom = feat["geometry"]
            parts = (
                [geom["coordinates"]]
                if geom["type"] == "LineString"
                else geom["coordinates"]
            )
            g = groups.get(key)
            if g is None:
                g = groups[key] = {"name": name, "lines": []}
            for part in parts:
                if len(part) >= 2:
                    g["lines"].append([tuple(pt) for pt in part])
    return groups


def stitch_lines(lines):
    """Chain a list of polylines into fewer, longer polylines.

    Greedy: pick an unused line, then repeatedly extend both ends with any
    unused line that shares the current endpoint (reversing it if needed).
    Returns a list of polylines (each a list of (lon, lat) tuples).
    """
    # endpoint -> set of line indices that start or end there
    ends = {}
    for i, ln in enumerate(lines):
        ends.setdefault(ln[0], set()).add(i)
        ends.setdefault(ln[-1], set()).add(i)

    used = [False] * len(lines)
    result = []

    def take_at(point, exclude):
        """Pop an unused line index incident to `point` (not `exclude`)."""
        for j in ends.get(point, ()):
            if j != exclude and not used[j]:
                return j
        return None

    for i, ln in enumerate(lines):
        if used[i]:
            continue
        used[i] = True
        chain = list(ln)

        # Extend forward from the tail.
        while True:
            j = take_at(chain[-1], i)
            if j is None:
                break
            used[j] = True
            seg = lines[j]
            if seg[0] == chain[-1]:
                chain.extend(seg[1:])
            else:  # seg[-1] == chain[-1]
                chain.extend(reversed(seg[:-1]))

        # Extend backward from the head.
        while True:
            j = take_at(chain[0], i)
            if j is None:
                break
            used[j] = True
            seg = lines[j]
            if seg[-1] == chain[0]:
                chain[:0] = seg[:-1]
            else:  # seg[0] == chain[0]
                chain[:0] = list(reversed(seg))[:-1]

        result.append(chain)

    return result


def _gap_m(a, b):
    """Approximate metres between two (lon, lat) points (equirectangular)."""
    lon1, lat1 = a
    lon2, lat2 = b
    dx = (lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2)) * 111320
    dy = (lat2 - lat1) * 110540
    return math.hypot(dx, dy)


def join_close_runs(runs, tol_m=SNAP_TOLERANCE_M):
    """Greedily join runs whose endpoints lie within tol_m of each other.

    Unlike exact stitching this bridges a gap: the two endpoints differ, so
    concatenating leaves a connector segment spanning the gap. Same-name runs
    only (callers pass one street's runs), so joining never merges streets.
    """
    runs = [list(r) for r in runs]
    merged = True
    while merged and len(runs) > 1:
        merged = False
        for i in range(len(runs)):
            a = runs[i]
            for j in range(i + 1, len(runs)):
                b = runs[j]
                # Four endpoint pairings; orient so a's tail meets b's head.
                if _gap_m(a[-1], b[0]) <= tol_m:
                    runs[i] = a + b
                elif _gap_m(a[-1], b[-1]) <= tol_m:
                    runs[i] = a + b[::-1]
                elif _gap_m(a[0], b[0]) <= tol_m:
                    runs[i] = a[::-1] + b
                elif _gap_m(a[0], b[-1]) <= tol_m:
                    runs[i] = b + a
                else:
                    continue
                runs.pop(j)
                merged = True
                break
            if merged:
                break
    return runs


def stitched_streets(slim_path=None):
    """Return [(name, polyline), ...] for every stitched run of every street."""
    out = []
    for g in read_groups(slim_path).values():
        runs = join_close_runs(stitch_lines(g["lines"]))
        for poly in runs:
            out.append((g["name"], poly))
    return out
