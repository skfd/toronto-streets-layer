"""Render the GitHub Pages landing page into the build output."""

import json
import os
import re
import shutil
from datetime import date

from PIL import Image

from src import config

# Optional landing-page screenshots, copied from the project root if present.
SCREENSHOT_MAX_WIDTH = 1500
_ID_FIGURE = (
    '<figure>\n'
    '  <img src="iD.png" loading="lazy"\n'
    '       alt="The vector layer in iD: a street with its name and class tags '
    'open in the inspector">\n'
    '  <figcaption>The vector layer in iD &mdash; a clicked street\'s tags in '
    'the inspector.</figcaption>\n'
    '</figure>'
)
_JOSM_FIGURE = (
    '<figure>\n'
    '  <img src="JOSM.png" loading="lazy"\n'
    '       alt="The raster layer in JOSM: street names rendered along the '
    'centrelines over aerial imagery">\n'
    '  <figcaption>The raster layer in JOSM &mdash; street names over aerial '
    'imagery.</figcaption>\n'
    '</figure>'
)


def build_site():
    """Render index.html, copy assets into build/site/."""
    os.makedirs(config.SITE_DIR, exist_ok=True)

    street_count = "60,000+"
    if os.path.isfile(config.COUNT_PATH):
        with open(config.COUNT_PATH, encoding="utf-8") as f:
            street_count = f"{int(f.read().strip()):,}"

    build_date = date.today().isoformat()

    with open(os.path.join(config.ASSETS_DIR, "index.html.tmpl"),
              encoding="utf-8") as f:
        html = f.read()

    replacements = {
        "{{PAGES_URL}}": config.PAGES_URL,
        "{{VECTOR_URL}}": f"{config.PAGES_URL}/tiles/vector/{{z}}/{{x}}/{{y}}.pbf",
        "{{RASTER_URL}}": f"{config.PAGES_URL}/tiles/raster/{{z}}/{{x}}/{{y}}.png",
        "{{RASTER_URL_JOSM}}": (
            f"{config.PAGES_URL}/tiles/raster/{{zoom}}/{{x}}/{{y}}.png"
        ),
        "{{VECTOR_URL_JOSM}}": (
            f"{config.PAGES_URL}/tiles/vector/{{zoom}}/{{x}}/{{y}}.pbf"
        ),
        "{{BUILD_DATE}}": build_date,
        "{{DATA_DATE}}": _data_date(build_date),
        "{{STREET_COUNT}}": street_count,
        "{{GITHUB_REPO}}": config.GITHUB_REPO,
        "{{DATASET_PAGE}}": config.DATASET_PAGE,
        "{{LICENSE_URL}}": config.LICENSE_URL,
        "{{ID_FIGURE}}": _figure("iD.png", _ID_FIGURE),
        "{{JOSM_FIGURE}}": _figure("JOSM.png", _JOSM_FIGURE),
    }
    for key, value in replacements.items():
        html = html.replace(key, value)

    with open(os.path.join(config.SITE_DIR, "index.html"), "w",
              encoding="utf-8") as f:
        f.write(html)
    for name in ("index.css", "index.js"):
        shutil.copy(
            os.path.join(config.ASSETS_DIR, name),
            os.path.join(config.SITE_DIR, name),
        )
    # .nojekyll stops GitHub Pages running Jekyll over the tile directories.
    open(os.path.join(config.SITE_DIR, ".nojekyll"), "w").close()
    print(f"Site rendered: {config.SITE_DIR}")


def _figure(filename, figure_html):
    """Copy a screenshot into the site and return its <figure>, or "" if absent."""
    src = os.path.join(config.PROJECT_DIR, filename)
    if not os.path.isfile(src):
        return ""
    _copy_image(src, os.path.join(config.SITE_DIR, filename), SCREENSHOT_MAX_WIDTH)
    return figure_html


def _copy_image(src, dst, max_width):
    """Copy an image into the site, downscaling it if wider than max_width."""
    with Image.open(src) as img:
        if img.width > max_width:
            height = round(img.height * max_width / img.width)
            img.resize((max_width, height), Image.LANCZOS).save(dst, optimize=True)
        else:
            shutil.copy(src, dst)


def _data_date(fallback):
    """Return the City data's date (YYYY-MM-DD) from the download sidecar."""
    if os.path.isfile(config.LAST_DOWNLOAD_PATH):
        with open(config.LAST_DOWNLOAD_PATH, encoding="utf-8") as f:
            sidecar = json.load(f)
        match = re.search(r"\d{4}-\d{2}-\d{2}", sidecar.get("filename", ""))
        if match:
            return match.group(0)
    return fallback
