"""The torus-shift chance test for a contiguous grid of plots scored against a stand map.

For a site whose reference data is a contiguous grid of field plots (a
stem-mapped plot cut into quadrats, say): which stand each quadrat lies in is
compared with what the field says about it (its field type, a measurement)
through an established statistic chosen by the caller, the adjusted Rand
index for instance. This module only says how often a stand map that knows
nothing about the field would score as well. **It is a significance test, not
a metric**: it returns no score of its own, only the caller's statistic on the
real map and on every shifted map.

The test (Harms et al. 2001; the method of Kyle Harms's own script). The stand
map, put on the quadrat grid (one stand per quadrat), is translated over the
fixed field grid by every whole number of quadrats in both directions, with
what leaves one edge entering at the opposite edge (a torus). On an `h x w`
grid that is `h * w` maps, the real one included. The statistic is computed
on each; the real map's value is placed among the `h * w - 1` shifted maps'.
Every shift is used: the distribution is enumerated, not sampled, so the test
has no seed.

What each shift keeps: the stand map's shapes, sizes and neighbourhoods, and
the field grid's spatial pattern; what it breaks is only their registration.
The seam where opposite edges meet is not in the real map, and on a grid
little larger than a few stands it matters: read the result with the grid's
size in stands beside it. A stand map that repeats under a shift (stripes, a
regular block pattern) is a relabelling of itself there, and a statistic that
ignores stand labels, as the Rand indices do, ties with the real map at that
shift; the ties are counted in `n_equal` and make the test more conservative.

Counting. As ForestGEO's implementation of the test counts (`fgeo.analyze::
tt_test`, code by Russo, Zuleta, Detto and Harms): over the `h * w` maps, how
often the real map's value is greater than (`n_greater`), less than
(`n_less`) and equal to (`n_equal`, the real map included; equal within the
tolerance `_common.permutation_p_value` uses for ties) the shifted map's;
the three sum to `h * w`. Beside them the package's permutation p-value,
`(b + 1) / (n + 1)` with `n = h * w - 1` (`_common.permutation_p_value`):
on an enumerated null that is exactly the share of all `h * w` maps scoring at
least as high as the real one. ForestGEO reads a quantile below 0.025 or above
0.975 as a significant association; no threshold is set here, and none is
applied.

Sources and what they support (CLAUDE.md, "Sources"):

  Harms, K. E., Condit, R., Hubbell, S. P., Foster, R. B. (2001). Habitat
  associations of trees and shrubs in a 50-ha neotropical forest plot.
  Journal of Ecology 89(6), 947-959. DOI 10.1111/j.1365-2745.2001.00615.x,
  checked on Crossref on 17 Oct 2026 (title, first author Harms). Support:
  (a) others use the method; it is the standard habitat-association test of
  the ForestGEO plots. The paper's full text was NOT read: the procedure
  above is taken from Kyle Harms's R script torus_2011.txt (14 Jan 2011,
  faculty.lsu.edu/kharms, read 17 Oct 2026), which translates the habitat
  map over the fixed stem map by every 20 m quadrat step, with no rotations
  or reflections, and from the fgeo.analyze reference page for tt_test (read
  17 Oct 2026).

UNVERIFIED, and a question for the evaluation stage (not a finding): whether
the 2001 paper also used rotated and mirrored copies of the habitat map
beside the translations (the 2011 script does not). `orientations` therefore
defaults to the translations alone, and the other three orientations of a
rectangle are available only when asked for by name, each adding `h * w`
maps. On a map shifted in every direction they change the null's size, not
its idea.

Nothing here knows about any site; nothing is tuned.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from fmu.evaluation._common import (
    P_VALUE_ATOL,
    P_VALUE_RTOL,
    Alternative,
    IntArray,
    as_codes,
    permutation_p_value,
)

#: The orientations of the stand map that may be shifted. "identity" is the
#: verified method; the others are UNVERIFIED as Harms et al. (2001)'s.
ORIENTATIONS = ("identity", "rotate_180", "flip_rows", "flip_cols")

#: statistic(field_values, stand_codes) -> float, called with the quadrats that
#: have both a field value and a stand, in row-major order.
GridStatistic = Callable[[np.ndarray, IntArray], float]


@dataclass(frozen=True)
class TorusShiftResult:
    """`observed`: the statistic on the real map. `null`: on every other map,
    shape `(n_maps - 1,)`, in the order of `maps` (NaN where the statistic is
    not defined). `maps`: `(orientation, row shift, column shift)` per null
    value. `n_greater`, `n_less`, `n_equal`: ForestGEO's counts over all
    `n_maps` maps (the real one in `n_equal`; NaN null values in none).
    `p_value`: `(b + 1) / (n + 1)` for `alternative`. `n_quadrats_used`: the
    quadrats the real map scores."""

    observed: float
    null: np.ndarray
    maps: list[tuple[str, int, int]]
    n_maps: int
    n_greater: int
    n_less: int
    n_equal: int
    p_value: float
    alternative: str
    n_quadrats_used: int

    def summary(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if k not in ("null", "maps")}


def _oriented(stands: IntArray, orientation: str) -> IntArray:
    if orientation == "identity":
        return stands
    if orientation == "rotate_180":
        return stands[::-1, ::-1]
    if orientation == "flip_rows":
        return stands[::-1, :]
    if orientation == "flip_cols":
        return stands[:, ::-1]
    raise ValueError(f"orientation must be one of {ORIENTATIONS}, got {orientation!r}")


def torus_shift_test(
    field: npt.ArrayLike,
    stands: npt.ArrayLike,
    statistic: GridStatistic,
    *,
    field_missing: Any = None,
    alternative: Alternative = "greater",
    orientations: Sequence[str] = ("identity",),
) -> TorusShiftResult:
    """Place `statistic` on the real stand map among every torus-shifted map.

    `field` is a 2-D array with one value per quadrat (a field-type code, a
    measurement); a quadrat with no field value holds `field_missing` (or NaN
    for a float array when `field_missing` is None). `stands` is a 2-D integer
    array of the same shape, the stand of each quadrat, -1 for none. The field
    grid stays fixed and the stand map moves: the quadrat at `(r, c)` reads
    `stands[(r - dr) mod h, (c - dc) mod w]`. `statistic` sees only the
    quadrats with both a field value and a stand.

    `orientations`: which orientations of the stand map are shifted (see
    `ORIENTATIONS` and the module docstring; the default is the verified
    method). Raises `ValueError` on grids of different shapes or of one
    quadrat, or on an unknown orientation.
    """
    f = np.asarray(field)
    s_raw = np.asarray(stands)
    if f.ndim != 2 or f.shape != s_raw.shape:
        raise ValueError(f"field and stands must be 2-D arrays of one shape, got {f.shape} and {s_raw.shape}")
    h, w = f.shape
    if h * w < 2:
        raise ValueError("a grid of one quadrat has no shift to compare with")
    s = as_codes(s_raw.ravel(), "stands").reshape(h, w)
    orients = list(dict.fromkeys(orientations))
    if "identity" not in orients:
        raise ValueError("orientations must include 'identity' (the real map is its unshifted copy)")
    orients = ["identity", *[o for o in orients if o != "identity"]]
    for o in orients:
        if o not in ORIENTATIONS:
            raise ValueError(f"orientation must be one of {ORIENTATIONS}, got {o!r}")
    if field_missing is None:
        has_field = ~np.isnan(f) if np.issubdtype(f.dtype, np.floating) else np.ones(f.shape, bool)
    else:
        has_field = f != field_missing
        if np.issubdtype(f.dtype, np.floating):
            has_field &= ~np.isnan(f)

    def score(m: IntArray) -> tuple[float, int]:
        use = has_field & (m >= 0)
        if not use.any():
            return float("nan"), 0
        return float(statistic(f[use], m[use])), int(use.sum())

    observed, n_used = score(s)
    values: list[float] = []
    maps: list[tuple[str, int, int]] = []
    for o in orients:
        base = _oriented(s, o)
        for dr in range(h):
            rolled = np.roll(base, dr, axis=0)
            for dc in range(w):
                if o == "identity" and dr == 0 and dc == 0:
                    continue
                values.append(score(np.roll(rolled, dc, axis=1))[0])
                maps.append((o, dr, dc))
    null = np.asarray(values, dtype=np.float64)
    defined = null[~np.isnan(null)]
    if np.isnan(observed):
        n_gt = n_lt = n_eq = 0
    else:
        # ties within the tolerance permutation_p_value uses, so the counts and p agree on what a tie is
        # (none for an infinite value: inf - inf is NaN, and every map would count as a tie)
        tol = 0.0 if np.isinf(observed) else P_VALUE_ATOL + P_VALUE_RTOL * abs(observed)
        n_gt = int(np.count_nonzero(defined < observed - tol))
        n_lt = int(np.count_nonzero(defined > observed + tol))
        n_eq = int(defined.size) - n_gt - n_lt + 1
    return TorusShiftResult(
        observed=observed,
        null=null,
        maps=maps,
        n_maps=len(maps) + 1,
        n_greater=n_gt,
        n_less=n_lt,
        n_equal=n_eq,
        p_value=permutation_p_value(observed, null, alternative),
        alternative=alternative,
        n_quadrats_used=n_used,
    )
