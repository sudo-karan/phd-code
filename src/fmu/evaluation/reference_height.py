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
    CENTRE lies in (the GDAL / rasterio rule with `all_touched=False`). A
    pixel whose centre lies in no stand is in no stand. Stands that overlap
    are an error, not resolved: on overlapping stands a pixel's stand is not
    defined.
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

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

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
) -> IntArray:
    """The stand map on a raster's grid: `labels[row, col]` is the position in
    `stands` of the stand whose polygon holds the pixel's centre, or -1.

    `stands` are shapely polygons or multipolygons in the raster's projected
    coordinate system (one per stand; an empty geometry covers nothing).
    `transform` is the raster's affine transform (see `Transform6`); `shape`
    is `(rows, cols)`. Two stands holding the same pixel centre raise
    `ValueError`, with the number of such pixels: a pixel's stand is then not
    defined, and no rule is picked here to define it.
    """
    import rasterio.features
    from affine import Affine
    from rasterio.enums import MergeAlg

    polys, positions = _as_polygons(stands, "stands")
    rows, cols = int(shape[0]), int(shape[1])
    if rows <= 0 or cols <= 0:
        raise ValueError(f"shape must be two positive integers, got {shape}")
    aff = Affine(*(float(v) for v in transform))
    labels = np.full((rows, cols), -1, dtype=np.int64)
    if polys.size == 0:
        return labels
    count = rasterio.features.rasterize(
        ((g, 1) for g in polys), out_shape=(rows, cols), transform=aff, fill=0,
        all_touched=False, merge_alg=MergeAlg.add, dtype="int32",
    )
    if (count > 1).any():
        raise ValueError(
            f"{int((count > 1).sum())} pixel centre(s) lie in more than one stand; "
            "a pixel's stand is not defined on overlapping stands"
        )
    burnt = rasterio.features.rasterize(
        ((g, int(p)) for g, p in zip(polys, positions, strict=True)),
        out_shape=(rows, cols), transform=aff, fill=-1, all_touched=False, dtype="int64",
    )
    labels[:] = burnt
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
