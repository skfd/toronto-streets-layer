"""CLI entry point for the Toronto street-names tile layer build."""

import argparse
import json
import os
import sys
import traceback
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from addressvault import LinkUnavailable  # noqa: E402

from src import config  # noqa: E402

# Offline or metered is not a build failure -- same as if the machine had been
# off, the run just did not happen. 75 is the conventional EX_TEMPFAIL, matching
# the addressvault CLI, so the scheduled task's restart-on-failure retries it
# and a wrapper can tell "no network" apart from a broken build.
EXIT_LINK_UNAVAILABLE = 75
# Anything else that stops a run. Nothing is marked published, so a retry
# rebuilds the same release.
EXIT_FAILED = 1


def _banner(text):
    print()
    print(f"=== {text} ===")


def cmd_download(args):
    _banner("Download")
    from src.download import download
    status, path = download(force=args.force)
    print(f"{status}: {path}")
    return status, path


def cmd_slim(args):
    _banner("Slim")
    from src.slim import slim
    slim(_latest_geojson())


def cmd_history(args):
    _banner("History")
    from src.history import record
    record(_latest_geojson())


def cmd_backfill(args):
    _banner("Backfill release history")
    from src.history import backfill
    added = backfill()
    print(f"Added {added} row(s) to {config.HISTORY_PATH}")


def cmd_vector(args):
    _banner("Vector tiles")
    from src.vector import build_vector
    build_vector()


def cmd_raster(args):
    _banner("Raster tiles")
    from src.raster import build_raster
    counts = build_raster()
    for zoom, n in sorted(counts.items()):
        print(f"  z{zoom}: {n:,} tiles")
        if n == 0:
            raise RuntimeError(f"Raster zoom {zoom} produced no tiles.")


def cmd_site(args):
    _banner("Site")
    from src.site import build_site
    build_site()


def cmd_publish(args):
    _banner("Publish")
    from src.publish import publish
    publish()
    # Only now is the release that build/site holds actually live.
    built = _read_marker(config.LAST_BUILT_PATH)
    if built:
        _write_marker(config.LAST_PUBLISHED_PATH, built)


def cmd_build(args):
    cmd_download(args)
    cmd_slim(args)
    cmd_history(args)
    cmd_vector(args)
    cmd_raster(args)
    cmd_site(args)
    _write_marker(config.LAST_BUILT_PATH, os.path.basename(_latest_geojson()))


def cmd_update(args):
    # The full rebuild is multi-hour, so skip it when the current TCL release is
    # already live. "Unchanged" means published, not merely downloaded: a build
    # that died after the download leaves the release on disk, and the task's
    # restart-on-failure retry must rebuild it rather than call it done.
    status, path = cmd_download(args)
    release = os.path.basename(path)
    if not args.force and _read_marker(config.LAST_PUBLISHED_PATH) == release:
        print(f"Source unchanged - {release} is already published.")
        return
    if status == "SKIPPED":
        print(f"{release} was downloaded but never published - rebuilding.")
    cmd_slim(args)
    # After slim, so a release that fails slim's sanity check is not recorded.
    cmd_history(args)
    cmd_vector(args)
    cmd_raster(args)
    cmd_site(args)
    _write_marker(config.LAST_BUILT_PATH, release)
    cmd_publish(args)


def _read_marker(path):
    """The release filename a marker file names, or None."""
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("release")


def _write_marker(path, release):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"release": release,
                   "at": datetime.now().isoformat(timespec="seconds")}, f)


def _latest_geojson():
    """Return the newest downloaded TCL centreline GeoJSON in data/."""
    if not os.path.isdir(config.DATA_DIR):
        raise RuntimeError("No data/ directory. Run 'download' first.")
    files = sorted(
        f for f in os.listdir(config.DATA_DIR)
        if f.startswith("centreline-") and f.endswith(".geojson")
    )
    if not files:
        raise RuntimeError("No centreline GeoJSON in data/. Run 'download' first.")
    return os.path.join(config.DATA_DIR, files[-1])


COMMANDS = {
    "download": (cmd_download, "Download the latest TCL centreline GeoJSON"),
    "slim": (cmd_slim, "Filter + convert the GeoJSON into slim GeoJSONL"),
    "history": (cmd_history, "Record the current release's statistics"),
    "backfill": (cmd_backfill, "Record every archived release in data/ not on record"),
    "vector": (cmd_vector, "Build vector (MVT) tiles via WSL tippecanoe"),
    "raster": (cmd_raster, "Build text-on-path labelled raster (PNG) tiles"),
    "site": (cmd_site, "Render the GitHub Pages landing page"),
    "publish": (cmd_publish, "Force-push the site to the gh-pages branch"),
    "build": (cmd_build, "download + slim + history + vector + raster + site"),
    "update": (cmd_update, "build + publish (monthly scheduled-task entry point)"),
}


def main():
    parser = argparse.ArgumentParser(
        description="Toronto Street-Names Tile Layer builder"
    )
    sub = parser.add_subparsers(dest="command")
    for name, (_, help_text) in COMMANDS.items():
        p = sub.add_parser(name, help=help_text)
        if name in ("download", "build", "update"):
            p.add_argument(
                "--force", action="store_true",
                help="Re-download even if the remote file is unchanged",
            )

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return
    if not hasattr(args, "force"):
        args.force = False

    try:
        COMMANDS[args.command][0](args)
    except LinkUnavailable as e:
        print(f"\nSkipped: {e}")
        print("Nothing was fetched or published; the task will retry.")
        sys.exit(EXIT_LINK_UNAVAILABLE)
    except Exception as e:
        # One greppable line in scheduler.log, then the traceback. Nonzero, so
        # the task's restart-on-failure retries -- and the retry rebuilds,
        # since nothing is marked published until the push succeeds.
        sys.stdout.flush()
        traceback.print_exc()
        sys.stderr.flush()
        print(f"ERROR {datetime.now():%Y-%m-%d %H:%M}: run.py {args.command} "
              f"failed: {type(e).__name__}: {e}", flush=True)
        sys.exit(EXIT_FAILED)


if __name__ == "__main__":
    main()
