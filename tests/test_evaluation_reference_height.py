"""fmu.evaluation.reference_height on synthetic rasters: the centre rule, overlaps refused, and R2
against the formula worked by hand (pixel-weighted, both sums over the same pixels)."""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("rasterio")
from shapely.geometry import Polygon, box  # noqa: E402

from fmu.evaluation.reference_height import height_variance_explained, stand_raster  # noqa: E402

# a 4 x 6 grid of 10 m pixels, top-left corner at (0, 40)
T = (10.0, 0.0, 0.0, 0.0, -10.0, 40.0)


def test_a_pixel_belongs_to_the_stand_holding_its_centre():
    # stand 0 covers x 0-25: centres at 5 and 15 are in it, 25 is on its edge, 35 is not
    # stand 1 covers x 26-60
    lab = stand_raster([box(0, 0, 25, 40), box(26, 0, 60, 40)], T, (4, 6))
    assert lab.shape == (4, 6)
    assert (lab[:, :2] == 0).all()
    assert (lab[:, 3:] == 1).all()
    # centre x = 25 lies on stand 0's edge, and a centre on a stand's boundary is in the stand
    assert (lab[:, 2] == 0).all()


def test_pixels_outside_every_stand_and_empty_stands():
    lab = stand_raster([box(0, 20, 20, 40), Polygon()], T, (4, 6))
    assert (lab[:2, :2] == 0).all() and (lab[2:, :] == -1).all() and (lab[:, 2:] == -1).all()
    assert (stand_raster([], T, (4, 6)) == -1).all()


def test_overlapping_stands_are_refused():
    with pytest.raises(ValueError, match="more than one stand"):
        stand_raster([box(0, 0, 30, 40), box(20, 0, 60, 40)], T, (4, 6))


def test_r2_is_the_hand_worked_formula():
    rng = np.random.default_rng(0)
    lab = np.array([[0, 0, 0, 1, 1, 2]] * 4)
    lab[3, 5] = -1                                   # one pixel with no stand
    h = rng.normal(20, 5, lab.shape)
    h[0, 0] = np.nan                                 # one pixel with no height
    used = (lab >= 0) & ~np.isnan(h)
    x, g = h[used], lab[used]
    ss_tot = ((x - x.mean()) ** 2).sum()
    ss_w = sum(((x[g == k] - x[g == k].mean()) ** 2).sum() for k in np.unique(g))
    r = height_variance_explained(lab, h)
    assert math.isclose(r.r2, 1 - ss_w / ss_tot, rel_tol=1e-12)
    assert (r.n_pixels, r.n_stands) == (int(used.sum()), 3)
    assert r.n_height_pixels == 23 and r.n_height_pixels_without_stand == 1
    assert math.isclose(r.share_without_stand, 1 / 23)


def test_r2_is_pixel_weighted_and_bounded():
    # stands uniform inside: R2 = 1, whatever their sizes
    lab = np.array([[0] * 5 + [1]] * 4)
    h = np.where(lab == 0, 10.0, 30.0)
    assert height_variance_explained(lab, h).r2 == pytest.approx(1.0)
    # one stand: R2 = 0; equal heights: undefined
    assert height_variance_explained(np.zeros((4, 6), int), np.arange(24.0).reshape(4, 6)).r2 == pytest.approx(0.0)
    assert math.isnan(height_variance_explained(lab, np.full((4, 6), 7.0)).r2)


def test_valid_mask_and_bad_input():
    lab = np.array([[0, 0, 1, 1]])
    h = np.array([[1.0, 3.0, 10.0, 12.0]])
    full = height_variance_explained(lab, h)
    masked = height_variance_explained(lab, h, valid=np.array([[True, True, True, False]]))
    assert full.n_pixels == 4 and masked.n_pixels == 3 and masked.n_height_pixels == 3
    with pytest.raises(ValueError):
        height_variance_explained(lab, h[:, :3])
    with pytest.raises(ValueError, match="infinite"):
        height_variance_explained(lab, np.array([[1.0, np.inf, 2.0, 3.0]]))


def test_the_raster_and_the_r2_together():
    """Two stands drawn as polygons onto the height grid; heights differ only between them."""
    lab = stand_raster([box(0, 0, 30, 40), box(30, 0, 60, 40)], T, (4, 6))
    h = np.where(lab == 0, 8.0, 25.0) + np.tile([0.0, 0.5, -0.5, 0.0, 0.5, -0.5], (4, 1))
    r = height_variance_explained(lab, h)
    assert r.n_stands == 2 and r.n_height_pixels_without_stand == 0
    assert 0.98 < r.r2 < 1.0


def test_a_shared_horizontal_edge_through_a_row_of_centres_is_not_an_overlap():
    """B23 (review of 19 Oct 2026): the centres of row 1 (y = 25) lie on the edge the two stands share.
    GDAL's burn count gave them 2 and the map was refused; each such centre goes to the first listed stand."""
    top, bottom = box(0, 25, 60, 40), box(0, 0, 60, 25)
    lab = stand_raster([top, bottom], T, (4, 6))
    assert (lab[:2] == 0).all() and (lab[2:] == 1).all()
    lab = stand_raster([bottom, top], T, (4, 6))
    assert (lab[0] == 1).all() and (lab[1:] == 0).all()


def test_a_hole_whose_bottom_edge_is_on_a_row_of_centres():
    """B23: one stand with a hole; the hole's bottom edge (y = 15) runs through two centres, which are on
    the stand's boundary and so in the stand; the two centres strictly inside the hole are in no stand."""
    ring = [(0, 0), (60, 0), (60, 40), (0, 40)]
    hole = [(20, 15), (40, 15), (40, 30), (20, 30)]
    lab = stand_raster([Polygon(ring, [hole])], T, (4, 6))
    expected = np.zeros((4, 6), dtype=int)
    expected[1, 2:4] = -1
    assert (lab == expected).all()


def test_the_sliver_tolerance():
    """B23: a sliver overlap no deeper than the declared tolerance goes to the first listed stand; an
    overlap deeper than it is still refused."""
    # stand 0 reaches x = 25.5 and stand 1 starts at x = 24.8: the centres at x = 25 are 0.5 inside
    # stand 0 and 0.2 inside stand 1
    sliver = [box(0, 0, 25.5, 40), box(24.8, 0, 60, 40)]
    with pytest.raises(ValueError, match="more than one stand"):
        stand_raster(sliver, T, (4, 6))
    lab = stand_raster(sliver, T, (4, 6), sliver_tolerance=1.0)
    assert (lab[:, :3] == 0).all() and (lab[:, 3:] == 1).all()
    # the centres at x = 25 are 5 inside each stand
    with pytest.raises(ValueError, match="more than one stand"):
        stand_raster([box(0, 0, 30, 40), box(20, 0, 60, 40)], T, (4, 6), sliver_tolerance=1.0)
    with pytest.raises(ValueError, match="sliver_tolerance"):
        stand_raster(sliver, T, (4, 6), sliver_tolerance=-1.0)
