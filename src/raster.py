"""Render street names as text-on-path raster (PNG) tiles using Pillow.

Pure Python -- no native dependencies, runs the same on Windows and Linux.

A street name is drawn glyph-by-glyph along its (stitched) centreline: each
character is rendered to a small RGBA image with a white halo, rotated to the
local tangent of the path, and pasted at its position along the line. Names are
repeated along long streets and placed once globally per zoom (so a label that
straddles a tile seam is identical in both tiles), with collision avoidance.
"""

import bisect
import math
import os
import shutil
from collections import defaultdict

from PIL import Image, ImageDraw, ImageFont

from src import config, stitch
from src.tilemath import TILE_SIZE, lonlat_to_pixel

FONT_PATH = os.path.join(config.ASSETS_DIR, "font", "DejaVuSans-Bold.ttf")
FONT_SIZE = 13
TEXT_COLOR = (40, 40, 40, 255)
HALO_COLOR = (255, 255, 255, 235)
HALO_WIDTH = 2
LINE_COLOR = (90, 90, 90, 150)
LINE_WIDTH = 1

# Repeat a street's name roughly every this many pixels along a long run.
REPEAT_SPACING = 500.0
# Spatial-hash cell size for label collision lookups (px).
GRID_CELL = 64


# --- path geometry ---------------------------------------------------------

def _project(poly, zoom):
    return [lonlat_to_pixel(lon, lat, zoom) for lon, lat in poly]


def _cumulative(poly_px):
    cum = [0.0]
    for (x0, y0), (x1, y1) in zip(poly_px, poly_px[1:]):
        cum.append(cum[-1] + math.hypot(x1 - x0, y1 - y0))
    return cum


def _point_angle(poly_px, cum, s):
    """Return (x, y, angle_rad) at arc-length s along the polyline."""
    k = bisect.bisect_right(cum, s) - 1
    k = max(0, min(k, len(poly_px) - 2))
    seg_len = (cum[k + 1] - cum[k]) or 1.0
    t = (s - cum[k]) / seg_len
    x0, y0 = poly_px[k]
    x1, y1 = poly_px[k + 1]
    return x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, math.atan2(y1 - y0, x1 - x0)


def _layout_label(poly_px, cum, s_start, text, font):
    """Lay out `text` along the path starting at arc-length s_start.

    Returns [(char, cx, cy, angle_rad), ...] in world-pixel coords, or None if
    the text does not fit. Flips the walk direction so text reads left-to-right.
    """
    total = cum[-1]
    tw = font.getlength(text)
    if s_start < 0 or s_start + tw > total:
        return None

    x0, _, _ = _point_angle(poly_px, cum, s_start)
    x1, _, _ = _point_angle(poly_px, cum, s_start + tw)
    if x1 < x0:  # path heads left here -> reverse so glyphs stay upright
        poly_px = poly_px[::-1]
        cum = _cumulative(poly_px)
        s_start = total - (s_start + tw)

    glyphs = []
    s = s_start
    for ch in text:
        w = font.getlength(ch)
        cx, cy, ang = _point_angle(poly_px, cum, s + w / 2)
        glyphs.append((ch, cx, cy, ang))
        s += w
    return glyphs


# --- glyph rendering -------------------------------------------------------

_glyph_cache = {}


def _glyph_image(ch, font):
    cached = _glyph_cache.get(ch)
    if cached is not None:
        return cached
    asc, desc = font.getmetrics()
    w = max(1, math.ceil(font.getlength(ch)))
    h = asc + desc
    pad = HALO_WIDTH + 1
    img = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(img).text(
        (pad, pad), ch, font=font, fill=TEXT_COLOR,
        stroke_width=HALO_WIDTH, stroke_fill=HALO_COLOR,
    )
    _glyph_cache[ch] = img
    return img


def _paste_glyph(canvas, glyph, font, origin):
    """Rotate a glyph to its tangent and alpha-composite it onto canvas.

    `glyph` is (char, cx, cy, angle); `origin` is the canvas top-left in world
    pixels. The path runs through the glyph's centre.
    """
    ch, cx, cy, ang = glyph
    g = _glyph_image(ch, font)
    rot = g.rotate(-math.degrees(ang), expand=True, resample=Image.BICUBIC)
    px = round(cx - origin[0] - rot.width / 2)
    py = round(cy - origin[1] - rot.height / 2)
    canvas.alpha_composite(rot, (px, py))


# --- M5b debug: render one street's label into a cropped image -------------

def debug_render(name, zoom, out_path):
    """Render the longest run of `name` with one centred label; save a PNG.

    Used for the M5b visual check -- not part of the tile pipeline.
    """
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    polys = [p for n, p in stitch.stitched_streets() if n == name]
    if not polys:
        raise SystemExit(f"no street named {name!r}")
    poly_px = _project(max(polys, key=len), zoom)
    cum = _cumulative(poly_px)

    tw = font.getlength(name)
    glyphs = _layout_label(poly_px, cum, max(0.0, (cum[-1] - tw) / 2), name, font)
    if glyphs is None:
        raise SystemExit(f"{name!r} does not fit at z{zoom}")

    # Crop region around the placed label (with margin).
    xs = [cx for _, cx, _, _ in glyphs]
    ys = [cy for _, _, cy, _ in glyphs]
    margin = 40
    minx, miny = min(xs) - margin, min(ys) - margin
    w = int(max(xs) - minx + margin)
    h = int(max(ys) - miny + margin)
    img = Image.new("RGBA", (w, h), (245, 245, 245, 255))
    draw = ImageDraw.Draw(img)
    draw.line([(x - minx, y - miny) for x, y in poly_px],
              fill=LINE_COLOR, width=LINE_WIDTH)
    for glyph in glyphs:
        _paste_glyph(img, glyph, font, (minx, miny))
    img.save(out_path)
    print(f"wrote {out_path} ({w}x{h}) for {name!r} at z{zoom}")


# --- global label placement ------------------------------------------------

def _label_starts(total, tw):
    """Arc-length start positions for repeated labels along a run of length total."""
    n = max(1, round(total / REPEAT_SPACING))
    starts = []
    for i in range(n):
        s0 = (i + 0.5) / n * total - tw / 2
        if 0 <= s0 <= total - tw:
            starts.append(s0)
    return starts


def _label_bbox(glyphs):
    """Coarse axis-aligned box covering a laid-out label (glyph centres + pad)."""
    xs = [cx for _, cx, _, _ in glyphs]
    ys = [cy for _, _, cy, _ in glyphs]
    pad = FONT_SIZE
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def _cells(box):
    x0, y0, x1, y1 = box
    for cx in range(int(x0 // GRID_CELL), int(x1 // GRID_CELL) + 1):
        for cy in range(int(y0 // GRID_CELL), int(y1 // GRID_CELL) + 1):
            yield cx, cy


def _collides(grid, box):
    x0, y0, x1, y1 = box
    for key in _cells(box):
        for ox0, oy0, ox1, oy1 in grid.get(key, ()):
            if x0 < ox1 and x1 > ox0 and y0 < oy1 and y1 > oy0:
                return True
    return False


def _add(grid, box):
    for key in _cells(box):
        grid[key].append(box)


def _place_all(projected, font):
    """Place labels for every street globally, longest streets first.

    `projected` is [(name, poly_px), ...]. Returns a list of laid-out labels
    (each a glyph list). Repeated along long runs; collisions dropped.
    """
    grid = defaultdict(list)
    ordered = sorted(projected, key=lambda np: -_poly_len(np[1]))
    placements = []
    for name, poly_px in ordered:
        cum = _cumulative(poly_px)
        total = cum[-1]
        tw = font.getlength(name)
        if total < tw:
            continue
        for s0 in _label_starts(total, tw):
            glyphs = _layout_label(poly_px, cum, s0, name, font)
            if glyphs is None:
                continue
            box = _label_bbox(glyphs)
            if _collides(grid, box):
                continue
            _add(grid, box)
            placements.append(glyphs)
    return placements


def _poly_len(poly_px):
    return _cumulative(poly_px)[-1]


# --- tile bucketing + rendering --------------------------------------------

def _bucket_segments(tiles, poly_px):
    """Add each line segment to every tile its bounding box touches."""
    for a, b in zip(poly_px, poly_px[1:]):
        tx0, tx1 = int(min(a[0], b[0]) // TILE_SIZE), int(max(a[0], b[0]) // TILE_SIZE)
        ty0, ty1 = int(min(a[1], b[1]) // TILE_SIZE), int(max(a[1], b[1]) // TILE_SIZE)
        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                tiles[(tx, ty)]["segs"].append((a, b))


def _bucket_glyph(tiles, glyph, font):
    """Add a glyph to every tile its rotated image overlaps."""
    ch, cx, cy, _ang = glyph
    w, h = _glyph_image(ch, font).size
    half = math.hypot(w, h) / 2  # safe over-estimate of the rotated extent
    tx0, tx1 = int((cx - half) // TILE_SIZE), int((cx + half) // TILE_SIZE)
    ty0, ty1 = int((cy - half) // TILE_SIZE), int((cy + half) // TILE_SIZE)
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            tiles[(tx, ty)]["glyphs"].append(glyph)


def _render_tile(content, font, tx, ty):
    origin = (tx * TILE_SIZE, ty * TILE_SIZE)
    img = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for a, b in content["segs"]:
        draw.line(
            [(a[0] - origin[0], a[1] - origin[1]),
             (b[0] - origin[0], b[1] - origin[1])],
            fill=LINE_COLOR, width=LINE_WIDTH,
        )
    for glyph in content["glyphs"]:
        _paste_glyph(img, glyph, font, origin)
    return img


def _render_zoom(streets, zoom, font, tile_filter=None):
    """Render every tile for one zoom. Returns the tile count.

    `tile_filter`, if given, is a predicate (tx, ty) -> bool limiting output.
    """
    projected = [(name, _project(poly, zoom)) for name, poly in streets]
    print(f"Raster z{zoom}: placing labels for {len(projected):,} runs ...")
    placements = _place_all(projected, font)
    print(f"Raster z{zoom}: {len(placements):,} labels placed; bucketing ...")

    tiles = defaultdict(lambda: {"segs": [], "glyphs": []})
    for _name, poly_px in projected:
        _bucket_segments(tiles, poly_px)
    for glyphs in placements:
        for glyph in glyphs:
            _bucket_glyph(tiles, glyph, font)

    out_dir = os.path.join(config.RASTER_TILE_DIR, str(zoom))
    made_dirs = set()
    written = 0
    for (tx, ty), content in tiles.items():
        if tile_filter and not tile_filter(tx, ty):
            continue
        img = _render_tile(content, font, tx, ty)
        tdir = os.path.join(out_dir, str(tx))
        if tdir not in made_dirs:
            os.makedirs(tdir, exist_ok=True)
            made_dirs.add(tdir)
        img.save(os.path.join(tdir, f"{ty}.png"), optimize=True)
        written += 1
    print(f"Raster z{zoom}: wrote {written:,} tiles")
    return written


def build_raster(slim_path=None):
    """Render PNG tiles for every zoom in config.RASTER_ZOOMS.

    Returns {zoom: tile_count}.
    """
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    streets = stitch.stitched_streets(slim_path)
    # Clear stale tiles so a rebuild never leaves orphaned PNGs behind.
    if os.path.isdir(config.RASTER_TILE_DIR):
        shutil.rmtree(config.RASTER_TILE_DIR)
    return {z: _render_zoom(streets, z, font) for z in config.RASTER_ZOOMS}


# --- M5c debug: composite a lon/lat region's real tiles into one image ------

def debug_render_region(zoom, west, south, east, north, out_path):
    """Render the real tiles covering a lon/lat box and composite them.

    Tiles are produced by the actual pipeline (global placement), then stitched
    side by side over a light background with seam lines, so cross-tile
    continuity and collisions can be eyeballed. Used for the M5c visual check.
    """
    from src.tilemath import lonlat_to_tile

    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    streets = stitch.stitched_streets()
    projected = [(name, _project(poly, zoom)) for name, poly in streets]
    placements = _place_all(projected, font)

    tiles = defaultdict(lambda: {"segs": [], "glyphs": []})
    for _name, poly_px in projected:
        _bucket_segments(tiles, poly_px)
    for glyphs in placements:
        for glyph in glyphs:
            _bucket_glyph(tiles, glyph, font)

    tx0, ty0 = lonlat_to_tile(west, north, zoom)
    tx1, ty1 = lonlat_to_tile(east, south, zoom)
    cols, rows = tx1 - tx0 + 1, ty1 - ty0 + 1
    canvas = Image.new(
        "RGBA", (cols * TILE_SIZE, rows * TILE_SIZE), (245, 245, 245, 255)
    )
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            content = tiles.get((tx, ty))
            if content:
                tile = _render_tile(content, font, tx, ty)
                canvas.alpha_composite(
                    tile, ((tx - tx0) * TILE_SIZE, (ty - ty0) * TILE_SIZE)
                )
    # Seam lines so tile boundaries are visible in the check.
    draw = ImageDraw.Draw(canvas)
    for c in range(cols + 1):
        draw.line([(c * TILE_SIZE, 0), (c * TILE_SIZE, rows * TILE_SIZE)],
                  fill=(0, 120, 215, 90))
    for r in range(rows + 1):
        draw.line([(0, r * TILE_SIZE), (cols * TILE_SIZE, r * TILE_SIZE)],
                  fill=(0, 120, 215, 90))
    canvas.convert("RGB").save(out_path)
    print(f"wrote {out_path} ({cols}x{rows} tiles) z{zoom}")
