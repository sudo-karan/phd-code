"""Spatial null models: chance that keeps the map and the plot layout intact.

A permutation of plots throws away two things that are true of any real site:
nearby plots are alike, and stands are compact pieces of ground. The null
models here keep both. The map stays as it is and the plots keep their layout;
only where the layout sits on the map is random.

  - `rotation_null`: the plots of each group (village) are moved as one rigid
    shape, by a random rotation and a random shift, to another place inside
    the group's region, and the map is read at the new positions.
  - `torus_translation_null`: for a gridded map, the map is slid under the
    plots by a random whole number of pixels and wraps round at the edges
    (Harms et al. 2001).

Both return `permutation.NullDraws`: for every draw, which stand (and type)
each plot gets. **They return no score.** A number only appears when a named,
established statistic is computed on the draws with `permutation.run_test`.
There is no such thing here as a "rotation score".

Nothing here knows about any site. Coordinates are x, y in metres in one
projected coordinate system.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import numpy.typing as npt
import shapely

from ._common import (
    BoolArray,
    FloatArray,
    IntArray,
    Seed,
    as_codes,
    as_coords,
    child_generators,
)
from .permutation import NullDraws

# Proposals are drawn in blocks of this size (part of the definition of the
# draws: changing it changes which placements a seed gives).
_BLOCK = 256
# Extra proposals allowed on top of `max_proposals_per_draw * n_draws`.
_PROPOSAL_SLACK = 50_000
# The torus translation uses the same cap as the default of the rotation null.
_TORUS_MAX_PROPOSALS_PER_DRAW = 2000


class NullNotEstimable(RuntimeError):  # noqa: N818 - the name is fixed by the specification
    """A spatial null could not produce the draws asked for.

    Raised when a group's plots cannot be placed often enough under the rule
    (inside the region, on stands). No group is dropped and no rule is relaxed
    to get a result.
    """


# ---------------------------------------------------------------------------
# Stand maps
# ---------------------------------------------------------------------------


def _as_xy(xy: npt.ArrayLike) -> FloatArray:
    arr = np.asarray(xy, dtype=np.float64)
    if arr.ndim < 1 or arr.shape[-1] != 2:
        raise ValueError(f"xy must have shape (..., 2), got {arr.shape}")
    return arr


def _as_stand_types(stand_type: npt.ArrayLike | None, n_stands: int) -> IntArray | None:
    if stand_type is None:
        return None
    return as_codes(stand_type, "stand_type", n=n_stands)


class RasterStandMap:
    """A stand map on a north-up grid of square pixels.

    `labels` is a 2-D integer array, row 0 at the top. A value is a stand code
    `0..k-1`; `-1` means no stand. `origin = (x of the left edge, y of the top
    edge)` and `pixel_size` are in metres. A point `(x, y)` falls in
    `col = floor((x - x0) / pixel_size)`, `row = floor((y_top - y) /
    pixel_size)`.

    `stand_type`, if given, has one type code per stand (the type of stand `c`
    at index `c`, `-1` for a stand without a type). `n_stands` is
    `max(labels) + 1` (0 for a map with no stand).

    Malformed input raises `ValueError`: labels that are not 2-D whole numbers
    `>= -1`, a pixel size that is not positive, a `stand_type` of the wrong
    length.
    """

    def __init__(
        self,
        labels: npt.ArrayLike,
        origin: tuple[float, float],
        pixel_size: float,
        stand_type: npt.ArrayLike | None = None,
    ) -> None:
        arr = np.asarray(labels)
        if arr.ndim != 2 or arr.size == 0:
            raise ValueError(f"labels must be a non-empty 2-D array, got shape {arr.shape}")
        self.labels: IntArray = as_codes(arr.ravel(), "labels").reshape(arr.shape)
        x0, y_top = float(origin[0]), float(origin[1])
        if not (np.isfinite(x0) and np.isfinite(y_top)):
            raise ValueError("origin must be two finite numbers")
        self.origin: tuple[float, float] = (x0, y_top)
        self.pixel_size = float(pixel_size)
        if not (np.isfinite(self.pixel_size) and self.pixel_size > 0):
            raise ValueError(f"pixel_size must be positive, got {pixel_size}")
        self.n_stands = int(self.labels.max()) + 1
        self.stand_type: IntArray | None = _as_stand_types(stand_type, self.n_stands)

    @property
    def shape(self) -> tuple[int, int]:
        """`(rows, columns)` of the raster."""
        return int(self.labels.shape[0]), int(self.labels.shape[1])

    def rowcol(self, xy: npt.ArrayLike) -> tuple[IntArray, IntArray]:
        """Row and column of each point; may lie outside the raster.

        `xy` has shape `(..., 2)`. Returns `(row, col)`, each of shape `(...)`.
        """
        pts = _as_xy(xy)
        col = np.floor((pts[..., 0] - self.origin[0]) / self.pixel_size).astype(np.int64)
        row = np.floor((self.origin[1] - pts[..., 1]) / self.pixel_size).astype(np.int64)
        return row, col

    def inside(self, row: IntArray, col: IntArray) -> BoolArray:
        """True where `(row, col)` is a pixel of the raster."""
        h, w = self.shape
        return np.asarray((row >= 0) & (row < h) & (col >= 0) & (col < w), dtype=np.bool_)

    def lookup(self, xy: npt.ArrayLike) -> IntArray:
        """Stand code at each point of `xy` (shape `(..., 2)`).

        Returns `-1` for a point outside the raster or on a no-stand pixel.
        """
        row, col = self.rowcol(xy)
        ok = self.inside(row, col)
        out = np.full(row.shape, -1, dtype=np.int64)
        out[ok] = self.labels[row[ok], col[ok]]
        return out


class PolygonStandMap:
    """A stand map given as polygons.

    `geometries` is a sequence of shapely polygons (or multipolygons) in
    projected metres. The stand code is the position in the sequence.
    `stand_types`, if given, has one type code per geometry (`-1` for none).
    `n_stands` is the number of geometries.

    A point on the boundary of a polygon counts as inside it. A point covered
    by several polygons gets the smallest of their codes; a point covered by
    none gets `-1`. An empty geometry covers nothing. A `stand_types` of the
    wrong length raises `ValueError`.
    """

    def __init__(self, geometries: Sequence[Any], stand_types: npt.ArrayLike | None = None) -> None:
        self.geometries = np.asarray(list(geometries), dtype=object)
        if self.geometries.ndim != 1:
            raise ValueError("geometries must be a flat sequence of shapely geometries")
        if not all(isinstance(g, shapely.Geometry) for g in self.geometries):
            raise ValueError("geometries must hold shapely geometries")
        self.n_stands = int(self.geometries.shape[0])
        self.stand_type: IntArray | None = _as_stand_types(stand_types, self.n_stands)
        self._tree = shapely.STRtree(self.geometries)

    def lookup(self, xy: npt.ArrayLike) -> IntArray:
        """Stand code at each point of `xy` (shape `(..., 2)`); `-1` for none."""
        pts = _as_xy(xy)
        flat = pts.reshape(-1, 2)
        out = np.full(flat.shape[0], self.n_stands, dtype=np.int64)
        if flat.shape[0] and self.n_stands:
            points = shapely.points(flat[:, 0], flat[:, 1])
            hit_point, hit_stand = self._tree.query(points, predicate="intersects")
            np.minimum.at(out, hit_point, hit_stand)
        out[out == self.n_stands] = -1
        return out.reshape(pts.shape[:-1])


StandMap = RasterStandMap | PolygonStandMap


def _types_of(stand_map: StandMap, codes: IntArray) -> IntArray:
    """Type of each stand code (`-1` for no stand or no type)."""
    out = np.full(codes.shape, -1, dtype=np.int64)
    if stand_map.stand_type is not None:
        on = codes >= 0
        out[on] = stand_map.stand_type[codes[on]]
    return out


# ---------------------------------------------------------------------------
# Rigid motion
# ---------------------------------------------------------------------------


def _rigid_moves(offsets: FloatArray, angles: FloatArray, centres: FloatArray) -> FloatArray:
    """Rotate `offsets` (m, 2) by each angle and add each centre: (B, m, 2)."""
    cos, sin = np.cos(angles)[:, None], np.sin(angles)[:, None]
    ox, oy = offsets[None, :, 0], offsets[None, :, 1]
    out = np.empty((angles.shape[0], offsets.shape[0], 2), dtype=np.float64)
    out[..., 0] = cos * ox - sin * oy + centres[:, 0][:, None]
    out[..., 1] = sin * ox + cos * oy + centres[:, 1][:, None]
    return out


def rigid_move(xy: npt.ArrayLike, angle: float, centre: tuple[float, float]) -> FloatArray:
    """Move a set of points as one rigid shape.

    Formula: with `m` the mean of the points and `o_i = xy_i - m`, the moved
    point is `centre + R(angle) o_i`, where `R` is the rotation by `angle`
    radians counter-clockwise, `R o = (o_x cos a - o_y sin a, o_x sin a +
    o_y cos a)`. So the points turn about their own mean and the mean lands on
    `centre`. All distances between the points are kept. This is the move the
    rotation null makes; its closest published relative is the torus
    translation of Harms et al. (2001), which slides the map. Kyle Harms's own
    script of 2011 slides it without turning; whether the 2001 paper also
    turned or mirrored it is UNVERIFIED (review C5, 20 Oct 2026; see
    `fmu.evaluation.torus_shift`).

    Returns an array of shape `(n, 2)`.

    Degenerate inputs: one point simply lands on `centre`. No points, or a
    missing coordinate, raise `ValueError`. `angle = 0` with `centre` equal to
    the mean returns the points where they were.
    """
    pts = as_coords(xy, "xy")
    if pts.shape[0] == 0:
        raise ValueError("xy holds no point")
    if not np.isfinite(angle) or not np.isfinite(centre[0]) or not np.isfinite(centre[1]):
        raise ValueError("angle and centre must be finite numbers")
    offsets = pts - pts.mean(axis=0)
    moved = _rigid_moves(
        offsets, np.array([float(angle)]), np.array([[float(centre[0]), float(centre[1])]])
    )
    return np.asarray(moved[0], dtype=np.float64)


# ---------------------------------------------------------------------------
# Shared machinery of the two nulls
# ---------------------------------------------------------------------------


def _check_n_draws(n_draws: int) -> int:
    if isinstance(n_draws, (bool, np.bool_)) or not isinstance(n_draws, (int, np.integer)):
        raise ValueError(f"n_draws must be a whole number, got {n_draws!r}")
    if n_draws < 1:
        raise ValueError(f"n_draws must be at least 1, got {n_draws}")
    return int(n_draws)


def _per_group(thing: Any, group_codes: list[int], what: str) -> dict[int, Any]:
    """One object per group, from a single object or a mapping by group code."""
    if isinstance(thing, Mapping):
        by_code = {int(key): value for key, value in thing.items()}
        missing = [g for g in group_codes if g not in by_code]
        if missing:
            raise ValueError(f"{what} has no entry for group(s) {missing}")
        return {g: by_code[g] for g in group_codes}
    return dict.fromkeys(group_codes, thing)


def _code_offsets(maps: dict[int, Any], shared: bool) -> dict[int, int]:
    """Offset that makes stand codes unique across the maps of the groups.

    Groups are taken in increasing code order and each distinct map adds its
    number of stands. Groups that were given the very same map object share
    one offset (a stand is the same stand whichever group reads it). A single
    map for all groups has no offset.
    """
    offsets: dict[int, int] = {}
    if shared:
        return dict.fromkeys(maps, 0)
    seen: dict[int, int] = {}
    total = 0
    for g in sorted(maps):
        key = id(maps[g])
        if key not in seen:
            seen[key] = total
            total += int(maps[g].n_stands)
        offsets[g] = seen[key]
    return offsets


class _Setup:
    """Validated inputs shared by the two spatial nulls."""

    def __init__(
        self,
        coords: npt.ArrayLike,
        groups: npt.ArrayLike,
        stand_maps: Any,
        n_draws: int,
        require_type: bool,
        allowed: tuple[type, ...],
    ) -> None:
        self.xy = as_coords(coords)
        n = self.xy.shape[0]
        self.groups = as_codes(groups, "groups", n=n)
        self.n_draws = _check_n_draws(n_draws)
        self.require_type = bool(require_type)
        self.codes = [int(g) for g in np.unique(self.groups[self.groups >= 0])]
        self.shared = not isinstance(stand_maps, Mapping)
        self.maps: dict[int, Any] = _per_group(stand_maps, self.codes, "stand_maps")
        every = list(self.maps.values()) if self.codes else ([stand_maps] if self.shared else [])
        for m in every:
            if not isinstance(m, allowed):
                names = " or ".join(t.__name__ for t in allowed)
                raise TypeError(f"a stand map must be a {names}, got {type(m).__name__}")
        typed = {m.stand_type is not None for m in every}
        if len(typed) > 1:
            raise ValueError("some stand maps have stand types and some do not")
        self.has_types = typed == {True}
        if self.require_type and not self.has_types:
            raise ValueError("require_type=True needs stand maps with stand types")
        self.offsets = _code_offsets(self.maps, self.shared)

        # Observed labels, read from the maps by the same lookup as the draws.
        self.observed_id = np.full(n, -1, dtype=np.int64)
        self.observed_type = np.full(n, -1, dtype=np.int64)
        ungrouped = self.groups < 0
        if self.shared and ungrouped.any():
            local = stand_maps.lookup(self.xy[ungrouped])
            self.observed_id[ungrouped] = local
            self.observed_type[ungrouped] = _types_of(stand_maps, local)
        self.members: dict[int, IntArray] = {}
        self.local_observed: dict[int, IntArray] = {}
        for g in self.codes:
            idx = np.flatnonzero(self.groups == g)
            local = np.asarray(self.maps[g].lookup(self.xy[idx]), dtype=np.int64)
            self.members[g] = idx
            self.local_observed[g] = local
            self.observed_id[idx] = np.where(local >= 0, local + self.offsets[g], -1)
            self.observed_type[idx] = _types_of(self.maps[g], local)
        self.ids = np.tile(self.observed_id, (self.n_draws, 1))
        self.types = np.tile(self.observed_type, (self.n_draws, 1))
        self.acceptance: dict[int, float] = {}

    def accept(self, g: int, local: IntArray) -> BoolArray:
        """Which proposals keep the set of scored plots as it is.

        `local` has shape `(B, m)`: the stand code each plot of group `g`
        would get under each proposal. A proposal passes if every plot that is
        on a stand at its real position lands on a stand, and, with
        `require_type`, every plot whose real stand has a type lands on a
        stand that has a type.
        """
        observed = self.local_observed[g]
        on_stand = observed >= 0
        ok = np.asarray((local[:, on_stand] >= 0).all(axis=1), dtype=np.bool_)
        if self.require_type:
            stand_map = self.maps[g]
            typed = _types_of(stand_map, observed) >= 0
            ok &= (_types_of(stand_map, local[:, typed]) >= 0).all(axis=1)
        return ok

    def store(self, g: int, local: IntArray) -> None:
        """Write the accepted draws `local` (n_draws, m) of group `g`.

        A plot that is in no stand at its real position stays in no stand in
        every draw, and with `require_type` a plot whose real stand has no
        type stays without a type, so every draw scores the same plots as the
        observed map does.
        """
        idx = self.members[g]
        stand_map = self.maps[g]
        observed = self.local_observed[g]
        ids = np.where(local >= 0, local + self.offsets[g], -1)
        types = _types_of(stand_map, local)
        ids[:, observed < 0] = -1
        types[:, observed < 0] = -1
        if self.require_type:
            types[:, _types_of(stand_map, observed) < 0] = -1
        self.ids[:, idx] = ids
        self.types[:, idx] = types

    def draws(self, name: str, info: dict[str, Any]) -> NullDraws:
        base: dict[str, Any] = {
            "n_groups": len(self.codes),
            "acceptance": dict(self.acceptance),
            "require_type": self.require_type,
        }
        base.update(info)
        return NullDraws(
            name=name,
            observed_id=self.observed_id,
            observed_type=self.observed_type if self.has_types else None,
            ids=self.ids,
            types=self.types if self.has_types else None,
            info=base,
        )


def _too_many(name: str, g: int, accepted: int, proposed: int, n_draws: int) -> NullNotEstimable:
    return NullNotEstimable(
        f"{name}: group {g} has {accepted} accepted placement(s) out of {proposed} proposed "
        f"(acceptance {accepted / max(proposed, 1):.2e}), and {n_draws} are needed. The plots of "
        "this group cannot be moved while staying inside the region and on stands. No group is "
        "dropped and no rule is relaxed."
    )


# ---------------------------------------------------------------------------
# The rotation null
# ---------------------------------------------------------------------------


def rotation_null(
    coords: npt.ArrayLike,
    groups: npt.ArrayLike,
    stand_maps: StandMap | Mapping[int, StandMap],
    regions: Any | Mapping[int, Any],
    n_draws: int,
    seed: Seed,
    *,
    require_type: bool = False,
    max_proposals_per_draw: int = 2000,
) -> NullDraws:
    """Relabel plots by moving each group's plots rigidly over the stand map.

    This is a way of drawing relabelled plots for a statistic chosen by the
    caller. It is not a metric and returns no score.

    Procedure, for each group (village) on its own: the group's plots are
    moved as one rigid shape (`rigid_move`): turned by an angle drawn
    uniformly from `[0, 2 pi)` and shifted so that their mean lands on a point
    drawn uniformly from the bounding box of the group's region. The placement
    is kept if

      (a) every moved plot is inside the region (the boundary counts);
      (b) every plot that is on a stand at its real position lands on a stand;
      (c) with `require_type`, every plot whose real stand has a type lands on
          a stand that has a type.

    The first `n_draws` placements kept are the draws, so they are uniform
    over the rigid placements that satisfy the rule. The stand map is then
    read at the moved positions. The spacing of the plots, the field values
    and the map itself are untouched; only where the layout sits on the map is
    random. Moving the plots over a fixed map is the same as moving the map
    under fixed plots by the inverse motion. The closest published relative is
    the torus translation of Harms et al. (2001); this version turns the layout,
    which Kyle Harms's own 2011 script does not (whether the 2001 paper turned or
    mirrored the map is UNVERIFIED), and does not wrap the map round.

    Arguments: `coords` `(n, 2)` in metres; `groups` integer codes (`-1`: in
    no group); `stand_maps` one map for all groups or a mapping from group
    code to map; `regions` one shapely polygon or a mapping from group code to
    polygon, in the same coordinate system. Each group has its own random
    stream (`_common.child_generators`), so with an integer seed adding a
    group with a higher code does not change the draws of the others.

    Returns `NullDraws` named `"rotation"`. `observed_id` and `observed_type`
    are read from the map at the real coordinates by the same lookup as the
    draws; compare them with the stand ids joined by other means. With one map
    per group, stand codes are made unique by an offset per map (in
    increasing group-code order, each map adding its number of stands; groups
    given the very same map object share an offset). `info` holds `n_groups`,
    `acceptance` (per group, draws kept divided by placements proposed up to
    the last one kept) and `require_type`.

    Degenerate inputs: plots with `groups == -1` keep their observed labels
    in every draw (read from the single map, or `-1` when maps are per group).
    A plot that is in no stand at its real position stays in no stand in
    every draw, and with `require_type` a plot whose real stand has no type
    stays without one, so every draw scores the same plots as the observed
    map. If a group has used more than `max_proposals_per_draw * n_draws +
    50,000` proposals without reaching `n_draws`, `NullNotEstimable` is
    raised. A missing map or region, an empty region, `n_draws < 1` or
    `require_type` without stand types raise `ValueError`.
    """
    setup = _Setup(
        coords, groups, stand_maps, n_draws, require_type, (RasterStandMap, PolygonStandMap)
    )
    if max_proposals_per_draw < 1:
        raise ValueError(f"max_proposals_per_draw must be at least 1, got {max_proposals_per_draw}")
    region_of = _per_group(regions, setup.codes, "regions")
    cap = int(max_proposals_per_draw) * setup.n_draws + _PROPOSAL_SLACK
    generators = child_generators(seed, len(setup.codes))
    for g, rng in zip(setup.codes, generators, strict=True):
        region = region_of[g]
        if not isinstance(region, shapely.Geometry) or shapely.is_empty(region):
            raise ValueError(f"the region of group {g} must be a non-empty shapely geometry")
        shapely.prepare(region)
        x_min, y_min, x_max, y_max = shapely.bounds(region)
        stand_map = setup.maps[g]
        xy = setup.xy[setup.members[g]]
        offsets = xy - xy.mean(axis=0)
        kept: list[IntArray] = []
        n_kept = 0
        proposed = 0
        used = 0
        while n_kept < setup.n_draws:
            if proposed >= cap:
                raise _too_many("rotation", g, n_kept, proposed, setup.n_draws)
            angles = rng.uniform(0.0, 2.0 * np.pi, _BLOCK)
            centres = np.column_stack(
                [rng.uniform(x_min, x_max, _BLOCK), rng.uniform(y_min, y_max, _BLOCK)]
            )
            moved = _rigid_moves(offsets, angles, centres)
            inside = np.asarray(
                shapely.intersects_xy(region, moved[..., 0], moved[..., 1]), dtype=np.bool_
            ).all(axis=1)
            candidates = np.flatnonzero(inside)
            if candidates.shape[0]:
                local = np.asarray(stand_map.lookup(moved[candidates]), dtype=np.int64)
                passed = setup.accept(g, local)
                take = np.flatnonzero(passed)[: setup.n_draws - n_kept]
                if take.shape[0]:
                    kept.append(local[take])
                    n_kept += int(take.shape[0])
                    used = proposed + int(candidates[take[-1]]) + 1
            proposed += _BLOCK
        setup.store(g, np.concatenate(kept, axis=0))
        setup.acceptance[g] = setup.n_draws / used
    return setup.draws("rotation", {})


# ---------------------------------------------------------------------------
# The torus translation
# ---------------------------------------------------------------------------


def torus_translation_null(
    coords: npt.ArrayLike,
    groups: npt.ArrayLike,
    stand_maps: RasterStandMap | Mapping[int, RasterStandMap],
    n_draws: int,
    seed: Seed,
    *,
    require_type: bool = False,
) -> NullDraws:
    """Relabel plots by sliding a gridded stand map under them, with wrap-round.

    This is a way of drawing relabelled plots for a statistic chosen by the
    caller. It is not a metric and returns no score.

    Procedure, for each group on its own, with a raster of `h` rows and `w`
    columns: a shift `(dr, dc)` is drawn uniformly from the `h * w - 1` shifts
    other than `(0, 0)`, with replacement, and the plot in pixel `(row, col)`
    reads `labels[(row - dr) mod h, (col - dc) mod w]`: the map slides under
    the plots and what leaves one edge comes back at the opposite one. Only
    translations are used (no mirror images or rotations of the map). A shift
    is kept under the same rules (b) and (c) as `rotation_null`, and the first
    `n_draws` kept are the draws. Reference: Harms et al. (2001).

    The wrap joins opposite edges of the raster, a seam that is not in the
    real map. With a raster not much larger than the plot layout this
    matters, so this null is offered for comparison with the published method
    and the rotation null is the default.

    Arguments as `rotation_null`, with raster maps only and no regions.

    Returns `NullDraws` named `"torus_translation"`; observed labels, code
    offsets and `info` as in `rotation_null`, plus `info["n_shifts"]`
    (`h * w - 1` per group).

    Degenerate inputs: plots with `groups == -1` keep their observed labels.
    A plot outside the raster, or on a no-stand pixel, at its real position
    stays in no stand in every draw (and with `require_type` an untyped plot
    stays untyped). A raster of one pixel has no shift to draw, and a group
    whose shifts are almost never kept runs into the cap of
    `2000 * n_draws + 50,000` proposals: both raise `NullNotEstimable`.
    """
    setup = _Setup(coords, groups, stand_maps, n_draws, require_type, (RasterStandMap,))
    cap = _TORUS_MAX_PROPOSALS_PER_DRAW * setup.n_draws + _PROPOSAL_SLACK
    generators = child_generators(seed, len(setup.codes))
    n_shifts: dict[int, int] = {}
    for g, rng in zip(setup.codes, generators, strict=True):
        stand_map: RasterStandMap = setup.maps[g]
        h, w = stand_map.shape
        n_shifts[g] = h * w - 1
        if n_shifts[g] == 0:
            raise _too_many("torus_translation", g, 0, 0, setup.n_draws)
        row, col = stand_map.rowcol(setup.xy[setup.members[g]])
        on_raster = stand_map.inside(row, col)
        kept: list[IntArray] = []
        n_kept = 0
        proposed = 0
        used = 0
        while n_kept < setup.n_draws:
            if proposed >= cap:
                raise _too_many("torus_translation", g, n_kept, proposed, setup.n_draws)
            shift = rng.integers(1, h * w, size=_BLOCK)
            dr, dc = shift // w, shift % w
            local = np.full((_BLOCK, row.shape[0]), -1, dtype=np.int64)
            local[:, on_raster] = stand_map.labels[
                (row[on_raster][None, :] - dr[:, None]) % h,
                (col[on_raster][None, :] - dc[:, None]) % w,
            ]
            take = np.flatnonzero(setup.accept(g, local))[: setup.n_draws - n_kept]
            if take.shape[0]:
                kept.append(local[take])
                n_kept += int(take.shape[0])
                used = proposed + int(take[-1]) + 1
            proposed += _BLOCK
        setup.store(g, np.concatenate(kept, axis=0))
        setup.acceptance[g] = setup.n_draws / used
    return setup.draws("torus_translation", {"n_shifts": n_shifts})
