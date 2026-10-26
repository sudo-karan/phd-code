"""How much of a reference height raster's variation a stand map explains.

For a site with a lidar canopy height model (or any reference height raster):
the share of the raster's pixel-to-pixel variation that lies between stands,

    R2 = 1 - SS_within / SS_total,

    SS_total  = sum over used pixels of (h - mean h)^2,
    SS_within = sum over used pixels of (h - mean h of the pixel's stand)^2.

Pixel-weighted: every used pixel counts once, so a stand counts in proportion
to its area. This is the explained variance of Xiong et al. (2024, section
2.7.2), applied there to the cells of a 5 m canopy height model, and the
definition `unsupervised.explained_variance` already implements on arrays;
this module only puts a stand map on the height raster's grid, computes it,
and says how much of the raster it covers.

Source and what it supports (CLAUDE.md, "Sources"):

  Xiong, H., Pang, Y., Jia, W., Bai, Y. (2024). Forest stand delineation using
  airborne LiDAR and hyperspectral data. Silva Fennica 58(2), article 23014.
  DOI 10.14214/sf.23014. Support: (a) others use the method. The DOI's
  Crossref record was checked on 17 Oct 2026 (in Jaskaran's other session):
  the title and journal match; Crossref deposits affiliations in the author
  field, and the article page lists Xiong first. Verified. The publisher's
  page (read 17 Oct 2026) describes SS_total and SS_within in words; its
  equations are images that could not be read then, and docs/decisions.yaml
  records one earlier reader who read them as R2 = 1 - SS_within / SS_total.

Where the paper does not say, and what this module does instead (each is a
question for the evaluation stage, not a finding):

  - **Which pixel belongs to which stand.** A pixel belongs to the stand its
    CENTRE lies in, a centre on the stand's boundary included (tested on the
    polygons, `stand_raster`; GDAL's `all_touched=False` burn decides centres
    on an edge by its own scanline rule). A centre on an edge two stands
    share goes to the first of them in the order given, and a sliver
    of overlap no deeper than a declared tolerance is resolved the same way.
    A pixel whose centre lies in no stand is in no stand. Stands that overlap
    more deeply are an error, not resolved: on overlapping stands a pixel's
    stand is not defined.
  - **Which pixels are used.** Those with a stand and a height (finite, and
    `valid` where a mask is given). Both sums are over exactly these pixels,
    so the mean in SS_total is the mean of the pixels with a stand. Xiong
    writes the mean "of cells in the whole study area"; where the stands cover
    the whole study area the two are the same. Where they do not (stands drawn
    on kept land only, say), the share of height pixels with no stand is
    reported beside R2, and the value is not comparable with Xiong's unless
    that share is near 0.

R2 rises with the number of stands for any layer at all (it is 1 at one stand
per pixel), so it is always reported with `n_stands`, and two maps are not
compared on R2 alone. Nothing here knows about any site and nothing is tuned.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import shapely

from fmu.evaluation._common import IntArray
from fmu.evaluation.segmentation_accuracy import _as_polygons
from fmu.evaluation.unsupervised import explained_variance

#: A raster's affine transform as six numbers (a, b, c, d, e, f): x = a*col + b*row + c, y = d*col + e*row + f,
#: for the pixel's top-left corner, as rasterio and GDAL (in a different order) give it.
Transform6 = tuple[float, float, float, float, float, float]


@dataclass(frozen=True)
class HeightVarianceExplained:
    """The result of `height_variance_explained`.

    `r2`, `ss_within`, `ss_total`, `n_pixels` (used pixels) and `n_stands`
    (stands with at least one used pixel) are as in the module docstring.
    `n_height_pixels` counts the pixels with a height (and `valid`), with or
    without a stand; `n_height_pixels_without_stand` those of them with no
    stand, and `share_without_stand` their share. `r2` is NaN when no pixel is
    used or the used heights are all equal.
    """

    r2: float
    ss_within: float
    ss_total: float
    n_pixels: int
    n_stands: int
    n_height_pixels: int
    n_height_pixels_without_stand: int
    share_without_stand: float

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def stand_raster(
    stands: Sequence[Any],
    transform: Transform6,
    shape: tuple[int, int],
    *,
    sliver_tolerance: float = 0.0,
) -> IntArray:
    """The stand map on a raster's grid: `labels[row, col]` is the position in
    `stands` of the stand that holds the pixel's centre, or -1.

    `stands` are shapely polygons or multipolygons in the raster's projected
    coordinate system (one per stand; an empty geometry covers nothing).
    `transform` is the raster's affine transform (see `Transform6`); `shape`
    is `(rows, cols)`.

    A stand holds a centre that lies in its polygon or on its boundary (a hole
    is outside the stand, its edge on the stand's boundary). The centre is
    DEEP in the stand when it lies strictly inside it and more than
    `sliver_tolerance` (map units, default 0) from its boundary (outside a
    buffer of the boundary with 16 segments per quarter circle). Then:

      - a centre deep in one stand is in that stand;
      - a centre held by stands but deep in none (on a shared edge, or in a
        sliver of overlap no deeper than the tolerance) is in the FIRST of
        them in the order of `stands`: the tie rule;
      - a centre deep in two or more stands is a real overlap, and raises
        `ValueError` with the number of such pixels: a pixel's stand is then
        not defined, and no rule is picked here to define it.

    The tolerance must be declared before the map is scored, never tuned on a
    result; 0 accepts only exact shared edges.
    """
    polys, positions = _as_polygons(stands, "stands")
    rows, cols = int(shape[0]), int(shape[1])
    if rows <= 0 or cols <= 0:
        raise ValueError(f"shape must be two positive integers, got {shape}")
    tol = float(sliver_tolerance)
    if not (math.isfinite(tol) and tol >= 0):
        raise ValueError(f"sliver_tolerance must be a finite distance >= 0, got {sliver_tolerance!r}")
    a, b, c, d, e, f = (float(v) for v in transform)
    det = a * e - b * d
    if not (math.isfinite(det) and det != 0):
        raise ValueError(f"transform {transform} is not invertible")
    labels = np.full((rows, cols), -1, dtype=np.int64)
    n_deep = np.zeros((rows, cols), dtype=np.int64)       # stands each centre is deep in
    deep_in = np.full((rows, cols), -1, dtype=np.int64)   # the stand it is deep in, where it is one
    for g, p in zip(polys, positions, strict=True):
        # the window of pixels whose centres can lie within `tol` of the stand, one pixel wider all round
        x0, y0, x1, y1 = (float(v) for v in shapely.bounds(g))
        corners = [(x0 - tol, y0 - tol), (x0 - tol, y1 + tol), (x1 + tol, y0 - tol), (x1 + tol, y1 + tol)]
        cs = [(e * (x - c) - b * (y - f)) / det for x, y in corners]
        rs = [(-d * (x - c) + a * (y - f)) / det for x, y in corners]
        c_lo, c_hi = max(math.floor(min(cs)) - 1, 0), min(math.ceil(max(cs)) + 1, cols)
        r_lo, r_hi = max(math.floor(min(rs)) - 1, 0), min(math.ceil(max(rs)) + 1, rows)
        if c_lo >= c_hi or r_lo >= r_hi:
            continue
        cc, rr = np.meshgrid(np.arange(c_lo, c_hi) + 0.5, np.arange(r_lo, r_hi) + 0.5)
        x, y = a * cc + b * rr + c, d * cc + e * rr + f
        shapely.prepare(g)
        held = shapely.intersects_xy(g, x, y)
        deep = shapely.contains_xy(g, x, y)
        if tol > 0:
            near = shapely.buffer(shapely.boundary(g), tol, quad_segs=16)
            shapely.prepare(near)
            deep &= ~shapely.intersects_xy(near, x, y)
        win = (slice(r_lo, r_hi), slice(c_lo, c_hi))
        lab_w, n_w, in_w = labels[win], n_deep[win], deep_in[win]
        lab_w[held & (lab_w < 0)] = p                     # the first stand that holds it
        n_w += deep
        in_w[deep] = p
    overlap = n_deep > 1
    if overlap.any():
        raise ValueError(
            f"{int(overlap.sum())} pixel centre(s) lie inside more than one stand, deeper than "
            f"sliver_tolerance={tol:g} in each; a pixel's stand is not defined on overlapping stands"
        )
    one = n_deep == 1
    labels[one] = deep_in[one]
    return labels


def height_variance_explained(
    labels: npt.ArrayLike,
    height: npt.ArrayLike,
    *,
    valid: npt.ArrayLike | None = None,
) -> HeightVarianceExplained:
    """R2 of a reference height raster on stand membership, pixel-weighted.

    `labels` is a 2-D integer array (a stand per pixel, -1 none), for example
    from `stand_raster`; `height` a float array of the same shape, NaN where
    there is no height. `valid`, if given, masks pixels out as well. See the
    module docstring for the definition and for what `share_without_stand`
    is for.
    """
    lab = np.asarray(labels)
    h = np.asarray(height, dtype=np.float64)
    if lab.shape != h.shape or lab.ndim != 2:
        raise ValueError(f"labels and height must be 2-D arrays of one shape, got {lab.shape} and {h.shape}")
    ok = np.ones(h.shape, dtype=bool) if valid is None else np.asarray(valid, dtype=bool)
    if ok.shape != h.shape:
        raise ValueError(f"valid has shape {ok.shape}, height {h.shape}")
    if np.isinf(h[ok]).any():
        raise ValueError("height has an infinite value; mark missing heights as NaN")
    row = explained_variance(lab, h, valid=ok, band_names=["height"]).iloc[0]
    has_height = ok & ~np.isnan(h)
    n_height = int(has_height.sum())
    without = int((has_height & (lab < 0)).sum())
    return HeightVarianceExplained(
        r2=float(row.r2),
        ss_within=float(row.ss_within),
        ss_total=float(row.ss_total),
        n_pixels=int(row.n_pixels),
        n_stands=int(row.n_segments),
        n_height_pixels=n_height,
        n_height_pixels_without_stand=without,
        share_without_stand=(without / n_height) if n_height else float("nan"),
    )
