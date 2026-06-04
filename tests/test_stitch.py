"""Unit tests for the segment-stitching helper."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.stitch import stitch_lines  # noqa: E402


def test_chains_touching_segments():
    # Three segments meeting end-to-end collapse into one polyline.
    lines = [
        [(0.0, 0.0), (1.0, 0.0)],
        [(1.0, 0.0), (2.0, 0.0)],
        [(2.0, 0.0), (3.0, 0.0)],
    ]
    out = stitch_lines(lines)
    assert len(out) == 1
    assert out[0][0] == (0.0, 0.0)
    assert out[0][-1] == (3.0, 0.0)
    assert len(out[0]) == 4


def test_reversed_segment_is_joined():
    # The middle segment is stored backwards; it must still chain.
    lines = [
        [(0.0, 0.0), (1.0, 0.0)],
        [(2.0, 0.0), (1.0, 0.0)],  # reversed
    ]
    out = stitch_lines(lines)
    assert len(out) == 1
    assert out[0][0] == (0.0, 0.0)
    assert out[0][-1] == (2.0, 0.0)


def test_disjoint_segments_stay_separate():
    lines = [
        [(0.0, 0.0), (1.0, 0.0)],
        [(5.0, 5.0), (6.0, 5.0)],
    ]
    out = stitch_lines(lines)
    assert len(out) == 2


def test_all_points_preserved_without_duplication():
    lines = [
        [(0.0, 0.0), (1.0, 0.0)],
        [(1.0, 0.0), (2.0, 0.0)],
    ]
    out = stitch_lines(lines)
    # Shared endpoint (1,0) appears once, not twice.
    assert out[0] == [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("All stitch tests passed.")
