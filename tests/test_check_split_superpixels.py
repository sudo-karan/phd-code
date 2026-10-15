"""scripts/check_split_superpixels.py, offline: how it tells apart what separates the pieces.

Each case is a small window of the five arrays the script reads back from Earth Engine (the
stage's label, SNIC's own label, kept land, the ROI, A6's piece label), built by hand so that
one kind of gap is between two pieces of superpixel 5.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

SCRIPT = Path(__file__).parent.parent / "scripts" / "check_split_superpixels.py"
spec = importlib.util.spec_from_file_location("check_split_superpixels", SCRIPT)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

NONE = mod.NONE
L = 5


def _window(h: int = 8, w: int = 12):
    final = np.full((h, w), 7)  # another superpixel everywhere
    kept = np.ones((h, w), dtype=int)
    roi = np.ones((h, w), dtype=int)
    return final, kept, roi


def _pieces_of(final: np.ndarray) -> np.ndarray:
    """A6's piece labels: a distinct label per 8-connected piece of each value."""
    from scipy import ndimage

    piece = np.full(final.shape, NONE)
    nxt = 100
    for v in np.unique(final):
        if v == NONE:
            continue
        lab, n = ndimage.label(final == v, structure=np.ones((3, 3), dtype=int))
        for k in range(1, n + 1):
            piece[lab == k] = nxt
            nxt += 1
    return piece


def test_two_pieces_with_masked_land_between():
    final, kept, roi = _window()
    final[2:5, 1:4] = L
    final[2:5, 6:9] = L
    final[:, 4:6] = NONE  # two columns of land the mask removes, right across the window
    kept[:, 4:6] = 0
    out = mod.classify(final, final.copy(), kept, roi, _pieces_of(final), L, i0=1000, j0=1000)
    assert out["pieces_8_connected"] == 2 and out["pieces_4_connected"] == 2
    assert [p["pixels"] for p in out["pieces"]] == [9, 9]
    assert [p["area_ha"] for p in out["pieces"]] == [0.09, 0.09]
    assert out["pieces"][0]["columns"] == [1001, 1003] and out["pieces"][0]["rows"] == [1002, 1004]
    (sep,) = out["between_pieces"]
    assert sep["separated_by"] == ["masked pixels"]
    assert sep["fewest_pixels_between_through_not_kept_land_only"] == 2
    assert sep["gap_crosses"]["not_kept"] == sep["gap_pixels_on_a_shortest_path"] == 2
    assert sep["snics_own_label_joins_them"] is False
    assert out["split_by_the_count"] == []


def test_two_pieces_that_snics_own_label_joins_outside_the_roi():
    final, kept, roi = _window()
    final[1:3, 1:11] = L  # a strip of the superpixel...
    final[5:7, 1:11] = L  # ...and another, below
    roi[3:5, :] = 0  # the ROI's edge runs between them
    kept[3:5, :] = NONE
    final[3:5, :] = NONE
    raw = final.copy()
    raw[3:5, 1] = L  # SNIC's own label joins them outside the ROI, where the clip cuts it
    out = mod.classify(final, raw, kept, roi, _pieces_of(final), L, i0=1000, j0=1000)
    (sep,) = out["between_pieces"]
    assert sep["snics_own_label_joins_them"] is True
    assert sep["joined_through_pixels_outside_roi"] == 2
    assert sep["joined_through_pixels_not_kept"] == 0
    assert sep["separated_by"] == ["ROI edge"]


def test_two_pieces_on_either_side_of_a_tile_line():
    final, kept, roi = _window()
    final[2:5, 1:4] = L  # global columns 251..253 with i0 = 250
    final[2:5, 8:11] = L  # global columns 258..260; other superpixels between
    out = mod.classify(final, final.copy(), kept, roi, _pieces_of(final), L, i0=250, j0=1000)
    (sep,) = out["between_pieces"]
    assert sep["tile_lines_between"] == ["x=256"]
    assert sep["separated_by"] == ["tile edge", "other superpixels"]
    assert sep["gap_crosses"]["other_superpixels"] == sep["gap_pixels_on_a_shortest_path"] == 4
    assert sep["fewest_pixels_between_through_not_kept_land_only"] is None


def test_one_piece_the_count_splits_at_a_corner():
    final, kept, roi = _window()
    final[2:4, 2:4] = L
    final[4:6, 4:6] = L  # touches the first block at one corner only
    piece = _pieces_of(final)
    piece[4:6, 4:6] = 999  # as if the count did not join across the corner
    out = mod.classify(final, final.copy(), kept, roi, piece, L, i0=1000, j0=1000)
    assert out["pieces_8_connected"] == 1 and out["pieces_4_connected"] == 2
    assert out["pieces_in_window_as_a6_counts_them"] == 2
    (split,) = out["split_by_the_count"]
    assert split["separated_by"] == ["diagonal touch only"]
    assert out["between_pieces"] == []


def test_tile_lines_between_two_pieces():
    a = np.zeros((3, 20), dtype=bool)
    b = np.zeros((3, 20), dtype=bool)
    a[:, 0:4] = True
    b[:, 10:14] = True
    assert mod._tile_lines_between(a, b, 250, 0, 256) == ["x=256"]
    assert mod._tile_lines_between(a, b, 0, 0, 256) == []
    assert mod._tile_lines_between(b, a, 250, 0, 256) == ["x=256"]


def test_verdict_lines():
    result = {
        "totals": {"superpixels": 9, "pieces": 10, "superpixels_as_a6_counts_them": 10,
                   "pieces_as_a6_counts_them": 11, "superpixels_without_a_piece_label": {"42": 3}},
        "split": [{
            "label": 5, "pieces_over_the_roi_as_a6_counts_them": 2, "pieces_8_connected": 2,
            "pieces_4_connected": 2, "pieces": [{"area_ha": 0.3}, {"area_ha": 0.02}],
            "between_pieces": [{"separated_by": ["tile edge", "other superpixels"]}],
            "split_by_the_count": [],
        }, {"label": 9, "error": "not found in its window"}],
        "export_tasks_submitted": 0,
    }
    assert mod.verdicts(result) == [
        "over the ROI: 9 superpixels in 10 pieces (counted as A6 counted them until 15 Oct 2026: "
        "10 and 11, a key 'null' included where there is one); 2 superpixels in more than one "
        "piece",
        "superpixels with no piece label (not in the grouped count): 42 (3 px)",
        "superpixel 5: 2 pieces as A6 counts them over the ROI, 2 8-connected and 2 4-connected "
        "in its window, of 0.3 ha, 0.02 ha; separated by: tile edge, other superpixels",
        "superpixel 9: not found in its window",
        "export tasks submitted: 0",
    ]


def test_the_window_says_what_lies_outside_the_roi():
    final, kept, roi = _window()
    final[1:3, 1:11] = L
    final[5:7, 1:11] = L
    roi[3:5, :] = 0
    kept[3:5, :] = 1  # kept land outside the ROI, which SNIC can grow through
    final[3:5, :] = NONE
    raw = final.copy()
    raw[3:5, 1] = L
    out = mod.classify(final, raw, kept, roi, _pieces_of(final), L, i0=1000, j0=1000)
    assert out["kept_pixels_outside_roi_in_window"] == 24
    assert out["snic_label_pixels_outside_roi"] == 2
