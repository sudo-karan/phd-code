"""Overlap of a stand map with a reference stand map, as two stand-delineation papers measure it.

For a site with reference stands (an agency's compartment map, hand-drawn
stands). Two established measures, each exactly as its paper defines it, kept
apart because they match the maps in opposite directions:

  - `overlap_agreement` (Vatandaslar et al. 2025, section 3.3, eq. 1-3). Each
    REFERENCE stand x_i is matched to the delineated stand y_i it overlaps
    most ("largest overlap" spatial join). Per pair

        OLO = area(x_i n y_i) / area(y_i)   (over-segmentation term)
        OLU = area(x_i n y_i) / area(x_i)   (under-segmentation term)
        overall = (OLO + OLU) / 2,

    and the map's agreement is the mean over the reference stands assessed
    (the paper's 0.430 is the mean of its pairs; as the mean is linear this
    equals the mean of the mean OLO and the mean OLU).
  - `iou_agreement` (Xiong et al. 2024, section 2.7.2). Each DELINEATED stand
    has an IoU with its corresponding reference, area of the intersection over
    area of the union, and the map is scored by the shares of delineated stands
    with IoU > 0.5 and IoU > 0.7.

Both take shapely polygons or multipolygons in ONE projected coordinate system
(metres), as `segmentation_accuracy` does; an empty geometry is dropped and an
invalid one raises. A stand is named in the output by its position in the
sequence passed. Nothing here knows about any site, and nothing is tuned.

Sources and what they support (CLAUDE.md, "Sources"); support (a) for both,
others use the method:

  Vatandaslar, C., Bettinger, P., Merry, K., Stober, J., Lee, T. (2025).
  Semi-Automatic Stand Delineation Based on Very-High-Resolution
  Orthophotographs and Topographic Features: A Case Study from a Structurally
  Complex Natural Forest in the Southern USA. Forests 16(4), 666.
  DOI 10.3390/f16040666. The equations above were read on the publisher's
  page (plain text there) on 17 Oct 2026. The authors say the approach is
  like that of Sanchez-Lopez et al. (2018) and Ucar et al.; those papers were
  not checked.

  Xiong, H., Pang, Y., Jia, W., Bai, Y. (2024). Forest stand delineation using
  airborne LiDAR and hyperspectral data. Silva Fennica 58(2), article 23014.
  DOI 10.14214/sf.23014. The definition of IoU and the two thresholds were
  read in the text of the publisher's page on 17 Oct 2026; its equation (an
  image) could not be read. The thresholds are cited there to Luo et al. 2020,
  which was not checked.

  Both DOIs' Crossref records were checked on 17 Oct 2026 (in Jaskaran's other
  session) and are verified: 10.3390/f16040666 returns the title above, first
  author Vatandaslar, Forests 16(4) 666, 2025; 10.14214/sf.23014 returns the
  title above, Silva Fennica 58(2), 2024, with affiliations deposited in the
  author field, so the authors are taken from the article page (Xiong first).

UNVERIFIED: what neither paper says, and what this module does instead. Each
is a question for the evaluation stage (docs/handoff/2026-10-17-round9-chat.md),
not a finding:

  1. Xiong: how a delineated stand is paired with "its corresponding
     reference". Here: the reference it overlaps most, as Vatandaslar pairs in
     the other direction. A delineated stand that overlaps no reference has
     IoU 0 (its intersection with every reference is empty) and counts in the
     shares; how many there are is reported, so a caller can pass only the
     stands inside the reference map's extent.
  2. Xiong: "IoU > 0.7, and IoU > 0.5" in the methods, "IoU >= 0.5" in the
     results. Here: strictly greater, as the methods state it.
  3. Both: a tie for the largest overlap (two candidates with exactly equal
     intersection areas). Here: the candidate that comes first in the sequence
     passed.
  4. Vatandaslar: a reference stand that overlaps no delineated stand. The
     paper reports none. Here: it has no pair, is counted in
     `n_unmatched_references`, and is left out of the means.
  5. Vatandaslar assessed 62 randomly chosen reference stands, not all of
     them. Here: every reference stand passed is assessed; the caller draws a
     sample if one is wanted.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import shapely

from fmu.evaluation._common import FloatArray, IntArray
from fmu.evaluation.segmentation_accuracy import _as_polygons

OVERLAP_COLUMNS = ["reference", "stand", "intersection_area", "reference_area", "stand_area",
                   "olo", "olu", "overall"]
IOU_COLUMNS = ["stand", "reference", "intersection_area", "stand_area", "reference_area", "union_area", "iou"]
#: Xiong et al. (2024): shares of delineated stands with IoU above these.
XIONG_IOU_THRESHOLDS = (0.5, 0.7)


def _intersections(a: np.ndarray, b: np.ndarray) -> tuple[IntArray, IntArray, FloatArray]:
    """Every pair (i in a, j in b) whose intersection has positive area, with that area."""
    if a.size == 0 or b.size == 0:
        return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0)
    tree = shapely.STRtree(b)
    ia, jb = tree.query(a, predicate="intersects")
    if ia.size == 0:
        return ia.astype(np.int64), jb.astype(np.int64), np.zeros(0)
    area = np.asarray(shapely.area(shapely.intersection(a[ia], b[jb])), dtype=np.float64)
    keep = area > 0
    return ia[keep].astype(np.int64), jb[keep].astype(np.int64), area[keep]


def _largest(owner: IntArray, other: IntArray, area: FloatArray) -> tuple[IntArray, IntArray, FloatArray]:
    """Per owner, the other with the largest intersection area; ties to the lowest `other` position."""
    if owner.size == 0:
        return owner, other, area
    order = np.lexsort((other, -area, owner))
    owner, other, area = owner[order], other[order], area[order]
    first = np.unique(owner, return_index=True)[1]
    return owner[first], other[first], area[first]


@dataclass(frozen=True)
class OverlapAgreement:
    """`pairs`: one row per matched reference stand (columns `OVERLAP_COLUMNS`;
    `reference` and `stand` are positions in the sequences passed). `summary`:
    `olo`, `olu`, `overall` (means over the pairs), `n_references`,
    `n_matched`, `n_unmatched_references`, `n_stands`."""

    pairs: pd.DataFrame
    summary: dict[str, Any]


def overlap_agreement(references: Sequence[Any], stands: Sequence[Any]) -> OverlapAgreement:
    """Vatandaslar et al. (2025) eq. 1-3: each reference stand matched to the
    delineated stand it overlaps most; OLO, OLU and their mean per pair, and
    their means over the pairs. See the module docstring, points 3-5."""
    refs, ref_pos = _as_polygons(references, "references")
    sts, st_pos = _as_polygons(stands, "stands")
    ri, sj, inter = _largest(*_intersections(refs, sts))
    ra = np.asarray(shapely.area(refs[ri]), dtype=np.float64) if ri.size else np.zeros(0)
    sa = np.asarray(shapely.area(sts[sj]), dtype=np.float64) if sj.size else np.zeros(0)
    olo, olu = inter / sa, inter / ra
    pairs = pd.DataFrame({"reference": ref_pos[ri], "stand": st_pos[sj], "intersection_area": inter,
                          "reference_area": ra, "stand_area": sa, "olo": olo, "olu": olu,
                          "overall": (olo + olu) / 2}, columns=OVERLAP_COLUMNS)
    n = int(refs.size)
    summary = {
        "olo": float(olo.mean()) if olo.size else float("nan"),
        "olu": float(olu.mean()) if olu.size else float("nan"),
        "overall": float(pairs.overall.mean()) if olo.size else float("nan"),
        "n_references": n, "n_matched": int(ri.size), "n_unmatched_references": n - int(ri.size),
        "n_stands": int(sts.size),
    }
    return OverlapAgreement(pairs=pairs, summary=summary)


@dataclass(frozen=True)
class IouAgreement:
    """`stands`: one row per delineated stand (columns `IOU_COLUMNS`; `reference`
    is -1 and `iou` 0 for a stand overlapping no reference). `summary`:
    `share_iou_gt_<t>` for each threshold, `mean_iou`, `n_stands`,
    `n_stands_without_reference`, `n_references`."""

    stands: pd.DataFrame
    summary: dict[str, Any]


def iou_agreement(
    references: Sequence[Any],
    stands: Sequence[Any],
    thresholds: Sequence[float] = XIONG_IOU_THRESHOLDS,
) -> IouAgreement:
    """Xiong et al. (2024) section 2.7.2: IoU of each delineated stand with its
    reference, and the shares of delineated stands with IoU above each
    threshold (strictly). `mean_iou` is given for description; the paper
    reports the shares. See the module docstring, points 1-3."""
    th = [float(t) for t in thresholds]
    if any(not (0.0 <= t <= 1.0) for t in th):
        raise ValueError(f"thresholds must lie in [0, 1], got {thresholds}")
    refs, ref_pos = _as_polygons(references, "references")
    sts, st_pos = _as_polygons(stands, "stands")
    sj, ri, inter = _largest(*_intersections(sts, refs))
    n = int(sts.size)
    stand_area = np.asarray(shapely.area(sts), dtype=np.float64) if n else np.zeros(0)
    ref_of = np.full(n, -1, dtype=np.int64)
    inter_of = np.zeros(n)
    ref_area = np.full(n, np.nan)
    ref_of[sj] = ref_pos[ri]
    inter_of[sj] = inter
    if ri.size:
        ref_area[sj] = np.asarray(shapely.area(refs[ri]), dtype=np.float64)
    union = np.where(ref_of >= 0, stand_area + np.nan_to_num(ref_area) - inter_of, stand_area)
    iou = np.where(ref_of >= 0, inter_of / union, 0.0)
    table = pd.DataFrame({"stand": st_pos, "reference": ref_of, "intersection_area": inter_of,
                          "stand_area": stand_area, "reference_area": ref_area, "union_area": union,
                          "iou": iou}, columns=IOU_COLUMNS)
    summary: dict[str, Any] = {f"share_iou_gt_{t:g}": (float((iou > t).mean()) if n else float("nan")) for t in th}
    summary.update({"mean_iou": float(iou.mean()) if n else float("nan"), "n_stands": n,
                    "n_stands_without_reference": int((ref_of < 0).sum()), "n_references": int(refs.size)})
    return IouAgreement(stands=table, summary=summary)
