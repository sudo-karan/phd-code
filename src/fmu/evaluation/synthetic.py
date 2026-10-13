"""Planted data with known answers, for checking the evaluation methods.

Everything here is generated from a seed. Nothing is read from a site. The
caller says how many plots each group (village) has and which super-group
(district) each group is in; every other number is a parameter with a stated
default. No default was chosen by looking at a result.

What is generated (`make_dataset`):

- **Plots.** Each group's plots lie in a square whose area is proportional to
  the number of plots, no two closer than a minimum spacing. Groups are far
  apart, super-groups farther.
- **A planted stand map**, one raster per group. Stands are the cells nearest
  to the seeds of a jittered square grid (Voronoi cells), so they are compact
  and of similar size. The grid sits at a random place in each map. Each stand gets one of a few types at random.
  `raster_to_polygons` gives the same map as polygons.
- **An unrelated map**: a second map made the same way from an independent
  random stream. It has the same size distribution and nothing else in common.
- **Field attributes** of each plot. With `g` the plot's group, `d` its
  super-group, `s` its planted stand and `t` the type of that stand,

      x = group_shift[g] + smooth[g](plot) + nugget + effect * signal
      signal = sqrt(type_share) * mu[d, t] + sqrt(1 - type_share) * u[s]

  `group_shift` is one random shift per group and attribute (villages differ).
  `smooth` is a Gaussian random field with covariance
  `smooth_var * exp(-distance / smooth_range)`, drawn per group at the plots:
  nearby plots are alike whatever the map says. `nugget` is independent noise.
  `mu[d, t]` and `u[s]` are standard normal vectors: a type mean drawn
  separately in each super-group (so a type code means a different forest in
  each one), and a stand's own departure from it.

  **`effect = 0` means the map is unrelated to the field**: the attributes are
  then the background alone, which is drawn from a random stream that never
  sees the map. They are still spatially smooth and still differ between
  groups. The planted signal has variance `effect^2` per attribute, against
  `group_var + smooth_var + nugget_var` for the background.
- **Field types**: k-means on the robust-scaled attributes of all plots.

Degraded copies of the planted map (`shifted_maps`, `merged_maps`,
`split_maps`) move its boundaries, merge its stands or split them, so that a
metric can be shown to prefer the planted map to a damaged one.

Randomness: `make_dataset` derives eight independent streams from the seed
(plots, planted map, unrelated map, type means, stand effects, background,
field types, layer noise), so that, for example, the plots and the background
are the same whatever the map parameters are. Same seed, same data set.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import shapely
from scipy.spatial import cKDTree
from sklearn.cluster import KMeans

from fmu.evaluation._common import (
    FloatArray,
    IntArray,
    Seed,
    robust_scale,
)
from fmu.evaluation.spatial_null import RasterStandMap

__all__ = [
    "DEFAULT_PARAMS",
    "StandSeeds",
    "SyntheticDataset",
    "SyntheticParams",
    "make_dataset",
    "make_layer",
    "merged_maps",
    "planted_signal_share",
    "raster_to_polygons",
    "rasterise",
    "read_stands",
    "shifted_maps",
    "split_maps",
]

# Rings of extra seeds round the raster, so that a shifted or merged map still
# has seeds on every side of every pixel.
_SEED_MARGIN = 2


@dataclass(frozen=True)
class SyntheticParams:
    """The numbers the generator uses. None was tuned on any result.

    Lengths are metres, areas square metres, variances are per attribute.
    """

    area_per_plot: float = 40_000.0  # a group's plots lie in a square of side sqrt(n * this)
    min_plot_spacing: float = 30.0  # no two plots of a group closer than this
    group_spacing: float = 20_000.0  # offset between the squares of groups
    super_group_spacing: float = 200_000.0  # offset between super-groups
    region_buffer: float = 300.0  # region = convex hull of the plots, buffered by this
    pixel_size: float = 20.0  # pixel of the stand rasters
    stand_spacing: float = 160.0  # spacing of the grid of stand seeds
    stand_jitter: float = 50.0  # each seed is moved by up to this in x and in y
    n_types: int = 5  # stand types; each stand gets one uniformly at random
    n_attributes: int = 4  # columns of the attribute matrix
    group_var: float = 0.5  # variance of the per-group shift
    smooth_var: float = 0.5  # variance of the smooth field
    smooth_range: float = 200.0  # its covariance is smooth_var * exp(-distance / this)
    nugget_var: float = 0.5  # variance of the independent noise
    type_share: float = 0.5  # share of the planted signal that comes from the type
    n_field_types: int = 5  # field types = k-means with this many clusters

    def __post_init__(self) -> None:
        positive = (
            "area_per_plot",
            "group_spacing",
            "super_group_spacing",
            "pixel_size",
            "stand_spacing",
            "smooth_range",
        )
        for name in positive:
            if not getattr(self, name) > 0:
                raise ValueError(f"{name} must be positive, got {getattr(self, name)}")
        for name in (
            "min_plot_spacing",
            "region_buffer",
            "stand_jitter",
            "group_var",
            "smooth_var",
            "nugget_var",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must not be negative, got {getattr(self, name)}")
        for name in ("n_types", "n_attributes", "n_field_types"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be at least 1, got {getattr(self, name)}")
        if not 0.0 <= self.type_share <= 1.0:
            raise ValueError(f"type_share must lie in [0, 1], got {self.type_share}")
        if self.min_plot_spacing**2 * 4 > self.area_per_plot:
            raise ValueError("min_plot_spacing is too large for area_per_plot: plots would not fit")


DEFAULT_PARAMS = SyntheticParams()


def planted_signal_share(effect: float, params: SyntheticParams = DEFAULT_PARAMS) -> float:
    """Share of an attribute's variance that the planted map accounts for.

    Formula: `effect^2 / (effect^2 + group_var + smooth_var + nugget_var)`.
    0 at `effect = 0`; `NaN` if both the effect and the background are 0.
    """
    background = params.group_var + params.smooth_var + params.nugget_var
    total = effect**2 + background
    return float(effect**2 / total) if total > 0 else float("nan")


@dataclass(frozen=True, eq=False)
class StandSeeds:
    """The seeds a stand map of one group is made from.

    The raster frame is `shape = (rows, columns)` pixels of `pixel_size`, with
    `origin = (x of the left edge, y of the top edge)`. `xy` holds the seed
    points (some lie outside the frame, in a margin). `grid_row` and
    `grid_col` say where each seed sits in the seed grid, `seed_type` is its
    stand type and `split_angle` the direction (radians) of the line that
    `split_maps` cuts its stand along.
    """

    origin: tuple[float, float]
    shape: tuple[int, int]
    pixel_size: float
    xy: FloatArray
    grid_row: IntArray
    grid_col: IntArray
    seed_type: IntArray
    split_angle: FloatArray


@dataclass(frozen=True, eq=False)
class SyntheticDataset:
    """One generated data set. Arrays are in one fixed plot order.

    `coords` `(n, 2)` metres; `groups` and `super_group` codes `(n,)`;
    `attributes` `(n, k)`; `signal` `(n, k)` the planted signal at
    `effect = 1` (so `attributes = background + effect * signal`);
    `background` `(n, k)` the part that does not depend on the map;
    `field_type` codes `(n,)`; `stand_id` and `stand_type` `(n,)` read from the
    planted map with `read_stands`; `regions`, `planted`, `unrelated` map a
    group code to its region polygon and its two rasters; `planted_seeds` and
    `unrelated_seeds` hold what the degraded maps are built from.
    """

    effect: float
    params: SyntheticParams
    coords: FloatArray
    groups: IntArray
    super_group: IntArray
    attributes: FloatArray
    signal: FloatArray
    background: FloatArray
    field_type: IntArray
    stand_id: IntArray
    stand_type: IntArray
    regions: dict[int, Any]
    planted: dict[int, RasterStandMap]
    unrelated: dict[int, RasterStandMap]
    planted_seeds: dict[int, StandSeeds]
    unrelated_seeds: dict[int, StandSeeds]
    layer_seed: np.random.SeedSequence

    @property
    def n_plots(self) -> int:
        return int(self.coords.shape[0])

    @property
    def n_groups(self) -> int:
        return len(self.regions)


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------


def _check_layout(layout: Mapping[int, Sequence[int]]) -> dict[int, tuple[int, ...]]:
    if not isinstance(layout, Mapping) or not layout:
        raise ValueError("layout must be a non-empty mapping: super-group code -> group sizes")
    out: dict[int, tuple[int, ...]] = {}
    for key in sorted(layout):
        sizes = tuple(int(s) for s in layout[key])
        if int(key) < 0 or not sizes or min(sizes) < 1:
            raise ValueError(
                "layout needs super-group codes >= 0, each with at least one group of >= 1 plot"
            )
        out[int(key)] = sizes
    return out


def _place_plots(rng: np.random.Generator, n: int, side: float, min_spacing: float) -> FloatArray:
    """`n` points uniform in a square of side `side`, none closer than `min_spacing`.

    A point too close to an earlier one is drawn again (simple rejection).
    """
    points = np.empty((n, 2), dtype=np.float64)
    placed = 0
    while placed < n:
        candidate = rng.random(2) * side
        if placed:
            gap = np.hypot(*(points[:placed] - candidate).T)
            if gap.min() < min_spacing:
                continue
        points[placed] = candidate
        placed += 1
    return points


# ---------------------------------------------------------------------------
# Stand maps
# ---------------------------------------------------------------------------


def _draw_seeds(
    rng: np.random.Generator, bounds: tuple[float, float, float, float], params: SyntheticParams
) -> StandSeeds:
    """Seeds of a stand map whose raster covers `bounds` (x_min, y_min, x_max, y_max)."""
    pixel = params.pixel_size
    spacing = params.stand_spacing
    x_min, y_min, x_max, y_max = bounds
    x0 = float(np.floor(x_min / pixel) * pixel)
    y0 = float(np.floor(y_min / pixel) * pixel)
    x1 = float(np.ceil(x_max / pixel) * pixel)
    y1 = float(np.ceil(y_max / pixel) * pixel)
    w = max(int(round((x1 - x0) / pixel)), 1)
    h = max(int(round((y1 - y0) / pixel)), 1)
    n_col = int(np.ceil(w * pixel / spacing)) + 2 * _SEED_MARGIN
    n_row = int(np.ceil(h * pixel / spacing)) + 2 * _SEED_MARGIN
    grid_row, grid_col = np.divmod(np.arange(n_row * n_col, dtype=np.int64), n_col)
    # The grid sits at a random place relative to the raster. Without this,
    # two maps of the same frame would share one grid and differ only by the
    # jitter, and the "unrelated" map would agree with the planted one.
    phase = rng.uniform(0.0, spacing, size=2)
    sx = x0 + phase[0] + spacing * (grid_col - _SEED_MARGIN)
    sy = y1 - phase[1] - spacing * (grid_row - _SEED_MARGIN)
    jitter = rng.uniform(-params.stand_jitter, params.stand_jitter, size=(n_row * n_col, 2))
    seed_type = rng.integers(0, params.n_types, size=n_row * n_col).astype(np.int64)
    split_angle = rng.uniform(0.0, np.pi, size=n_row * n_col)
    return StandSeeds(
        origin=(x0, y1),
        shape=(h, w),
        pixel_size=float(pixel),
        xy=np.column_stack([sx + jitter[:, 0], sy + jitter[:, 1]]),
        grid_row=grid_row,
        grid_col=grid_col,
        seed_type=seed_type,
        split_angle=split_angle,
    )


def rasterise(
    seeds: StandSeeds,
    *,
    shift: tuple[float, float] = (0.0, 0.0),
    merge_block: int = 1,
    split: bool = False,
) -> RasterStandMap:
    """Turn seeds into a stand raster, optionally damaged in one of three ways.

    Each pixel belongs to the seed nearest to its centre (a Voronoi cell).

    - `shift = (dx, dy)`: every seed is moved by this first, so every boundary
      moves by it. Stands keep their types.
    - `merge_block = b > 1`: the seeds of each `b x b` block of the seed grid
      form one stand (about `b^2` times as large). It takes the type of the
      block's first seed (lowest row, then lowest column).
    - `split = True`: each stand is cut in two by a straight line through its
      seed, at that seed's `split_angle`. Both halves keep the stand's type.

    Stand codes run `0..k-1` over the stands that own at least one pixel, in
    no meaningful order. Every pixel has a stand. `merge_block < 1` raises
    `ValueError`.
    """
    if merge_block < 1:
        raise ValueError(f"merge_block must be at least 1, got {merge_block}")
    h, w = seeds.shape
    pixel = seeds.pixel_size
    px = seeds.origin[0] + pixel * (np.arange(w) + 0.5)
    py = seeds.origin[1] - pixel * (np.arange(h) + 0.5)
    cx, cy = np.meshgrid(px, py)
    centres = np.column_stack([cx.ravel(), cy.ravel()])
    xy = seeds.xy + np.asarray(shift, dtype=np.float64)
    _, nearest = cKDTree(xy).query(centres)
    nearest = np.asarray(nearest, dtype=np.int64)
    if merge_block > 1:
        n_block_col = int(seeds.grid_col.max()) // merge_block + 1
        block = (seeds.grid_row // merge_block) * n_block_col + seeds.grid_col // merge_block
        # the first seed of each block (seeds are in row, column order)
        first = np.full(int(block.max()) + 1, -1, dtype=np.int64)
        first[block[::-1]] = np.arange(block.shape[0] - 1, -1, -1)
        raw = block[nearest]
        type_of_raw = seeds.seed_type[first]
    elif split:
        dx = centres[:, 0] - xy[nearest, 0]
        dy = centres[:, 1] - xy[nearest, 1]
        angle = seeds.split_angle[nearest]
        side = (np.cos(angle) * dy - np.sin(angle) * dx > 0).astype(np.int64)
        raw = 2 * nearest + side
        type_of_raw = np.repeat(seeds.seed_type, 2)
    else:
        raw = nearest
        type_of_raw = seeds.seed_type
    present, labels = np.unique(raw, return_inverse=True)
    return RasterStandMap(
        np.asarray(labels, dtype=np.int64).reshape(h, w),
        seeds.origin,
        pixel,
        type_of_raw[present],
    )


def shifted_maps(
    dataset: SyntheticDataset, shift: tuple[float, float] | None = None
) -> dict[int, RasterStandMap]:
    """The planted map with every boundary moved by `shift` (metres, x and y).

    The default is half a stand spacing in each direction.
    """
    if shift is None:
        half = dataset.params.stand_spacing / 2.0
        shift = (half, half)
    return {g: rasterise(s, shift=shift) for g, s in dataset.planted_seeds.items()}


def merged_maps(dataset: SyntheticDataset, block: int = 2) -> dict[int, RasterStandMap]:
    """The planted map with stands merged in `block x block` groups of seeds."""
    return {g: rasterise(s, merge_block=block) for g, s in dataset.planted_seeds.items()}


def split_maps(dataset: SyntheticDataset) -> dict[int, RasterStandMap]:
    """The planted map with every stand cut in two; halves keep the stand's type."""
    return {g: rasterise(s, split=True) for g, s in dataset.planted_seeds.items()}


def read_stands(
    maps: Mapping[int, RasterStandMap], coords: Any, groups: Any
) -> tuple[IntArray, IntArray]:
    """Stand and stand type of every plot, read from one map per group.

    Stand codes are made unique over the whole data set by an offset per
    group: groups in increasing code order, each adding the number of stands
    of its map. This is the rule of `spatial_null.rotation_null`, so the
    result equals that null's `observed_id` and `observed_type`.

    A plot outside its group's raster gets `-1` for both. A plot whose group
    is `-1` or has no map raises `ValueError`.
    """
    xy = np.asarray(coords, dtype=np.float64)
    grp = np.asarray(groups, dtype=np.int64)
    stand_id = np.full(grp.shape[0], -1, dtype=np.int64)
    stand_type = np.full(grp.shape[0], -1, dtype=np.int64)
    codes = [int(g) for g in np.unique(grp)]
    if any(g < 0 or g not in maps for g in codes):
        raise ValueError("every plot needs a group code that has a map")
    offset = 0
    for g in codes:
        idx = np.flatnonzero(grp == g)
        stand_map = maps[g]
        local = stand_map.lookup(xy[idx])
        on = local >= 0
        stand_id[idx[on]] = local[on] + offset
        if stand_map.stand_type is not None:
            stand_type[idx[on]] = stand_map.stand_type[local[on]]
        offset += int(stand_map.n_stands)
    return stand_id, stand_type


def raster_to_polygons(stand_map: RasterStandMap) -> list[Any]:
    """The stands of a raster as polygons, one per stand code.

    The polygon of stand `c` is the union of the pixel squares labelled `c`,
    so polygons and raster are the same map exactly: a point strictly inside
    a pixel is in the polygon of that pixel's stand. Boundaries follow pixel
    edges. A stand in two separate patches gives a multipolygon; a code with
    no pixel gives an empty polygon. Pixels labelled `-1` are in no polygon.
    """
    labels = stand_map.labels
    h, w = labels.shape
    pixel = stand_map.pixel_size
    x0, y_top = stand_map.origin
    change = np.ones((h, w), dtype=bool)
    change[:, 1:] = labels[:, 1:] != labels[:, :-1]
    start = np.flatnonzero(change.ravel())
    end = np.append(start[1:], h * w)
    row, col0 = np.divmod(start, w)
    col1 = end - row * w
    code = labels[row, col0]
    keep = code >= 0
    boxes = shapely.box(
        x0 + col0[keep] * pixel,
        y_top - (row[keep] + 1) * pixel,
        x0 + col1[keep] * pixel,
        y_top - row[keep] * pixel,
    )
    code = code[keep]
    order = np.argsort(code, kind="stable")
    cuts = np.searchsorted(code[order], np.arange(stand_map.n_stands + 1))
    out: list[Any] = []
    for c in range(stand_map.n_stands):
        runs = boxes[order[cuts[c] : cuts[c + 1]]]
        out.append(shapely.union_all(runs) if runs.shape[0] else shapely.Polygon())
    return out


# ---------------------------------------------------------------------------
# A raster layer, for the measures that need no reference data
# ---------------------------------------------------------------------------


def make_layer(
    stand_map: RasterStandMap,
    seed: Seed,
    *,
    effect: float,
    n_bands: int = 1,
    noise_var: float = 1.0,
    trend_var: float = 0.0,
) -> FloatArray:
    """A raster layer that follows a stand map with a set strength.

    Formula, per band and pixel: `effect * m[stand] + sqrt(noise_var) * e +
    sqrt(trend_var) * z`, with `m` one standard normal value per stand, `e`
    independent standard normal noise per pixel, and `z` a smooth surface (a
    plane with a random direction, scaled to variance 1 over the raster) that
    ignores the stands. `effect = 0` gives a layer unrelated to the map.

    Returns an array of shape `(n_bands, rows, columns)`. Pixels in no stand
    get the noise and the trend only.
    """
    rng_stand, rng_noise, rng_trend = (
        np.random.default_rng(c) for c in _root_sequence(seed).spawn(3)
    )
    labels = stand_map.labels
    h, w = labels.shape
    means = rng_stand.normal(size=(n_bands, max(stand_map.n_stands, 1)))
    out = np.sqrt(noise_var) * rng_noise.normal(size=(n_bands, h, w))
    on = labels >= 0
    for b in range(n_bands):
        out[b][on] += effect * means[b][labels[on]]
        angle = rng_trend.uniform(0.0, 2.0 * np.pi)
        if trend_var > 0:
            rr, cc = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
            plane = np.cos(angle) * cc + np.sin(angle) * rr
            sd = plane.std()
            if sd > 0:
                out[b] += np.sqrt(trend_var) * (plane - plane.mean()) / sd
    return np.asarray(out, dtype=np.float64)


# ---------------------------------------------------------------------------
# The data set
# ---------------------------------------------------------------------------


def _root_sequence(seed: Seed) -> np.random.SeedSequence:
    """A fresh `SeedSequence` for a seed, so the same seed always gives the same children.

    An int gives `SeedSequence(int)` (the children `_common.child_generators`
    would give). A `SeedSequence` is copied, so the caller's object is left as
    it was however often it is used. A `Generator` supplies one integer.
    """
    if isinstance(seed, np.random.SeedSequence):
        return np.random.SeedSequence(
            seed.entropy, spawn_key=seed.spawn_key, pool_size=seed.pool_size
        )
    if isinstance(seed, np.random.Generator):
        return np.random.SeedSequence(int(seed.integers(0, 2**63 - 1)))
    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise TypeError(
            f"seed must be a non-negative int, a numpy Generator or a SeedSequence; got {seed!r}"
        )
    return np.random.SeedSequence(int(seed))


def make_dataset(
    seed: Seed,
    effect: float,
    layout: Mapping[int, Sequence[int]],
    params: SyntheticParams = DEFAULT_PARAMS,
) -> SyntheticDataset:
    """Generate one data set (see the module docstring for the model).

    `layout` maps a super-group code to the sizes of its groups, for example
    `{0: (10, 9), 1: (30,)}`: two super-groups, three groups, 49 plots. Group
    codes run `0, 1, ...` in the order of the layout (super-group code, then
    position). `effect` sets how strongly the attributes follow the planted
    map; 0 means not at all.

    Degenerate inputs: an empty layout, a group of no plots, a negative
    `effect`, or fewer plots than `params.n_field_types` raise `ValueError`.
    A group of one plot is allowed (its region is a disc of radius
    `region_buffer`).
    """
    if not np.isfinite(effect) or effect < 0:
        raise ValueError(f"effect must be a finite number >= 0, got {effect}")
    sizes = _check_layout(layout)
    n_total = sum(sum(s) for s in sizes.values())
    if n_total < params.n_field_types:
        raise ValueError(
            f"{n_total} plot(s) cannot be put in {params.n_field_types} field types; "
            "lower params.n_field_types or add plots"
        )
    children = _root_sequence(seed).spawn(8)
    streams = [np.random.default_rng(c) for c in children[:7]]
    layer_seed = children[7]
    r_plots, r_map, r_unrelated, r_means, r_stand, r_background, r_types = streams

    k = params.n_attributes
    coords_parts: list[FloatArray] = []
    groups_list: list[int] = []
    super_list: list[int] = []
    regions: dict[int, Any] = {}
    planted_seeds: dict[int, StandSeeds] = {}
    unrelated_seeds: dict[int, StandSeeds] = {}
    planted: dict[int, RasterStandMap] = {}
    unrelated: dict[int, RasterStandMap] = {}
    g = 0
    for d, group_sizes in sizes.items():
        for position, n in enumerate(group_sizes):
            side = float(np.sqrt(n * params.area_per_plot))
            points = _place_plots(r_plots, n, side, params.min_plot_spacing)
            points += np.array([params.group_spacing * position, params.super_group_spacing * d])
            coords_parts.append(points)
            groups_list += [g] * n
            super_list += [d] * n
            hull = shapely.convex_hull(shapely.multipoints(points))
            regions[g] = shapely.buffer(hull, max(params.region_buffer, 1e-6), quad_segs=16)
            x_lo, y_lo, x_hi, y_hi = (float(b) for b in shapely.bounds(regions[g]))
            bounds = (x_lo, y_lo, x_hi, y_hi)
            planted_seeds[g] = _draw_seeds(r_map, bounds, params)
            unrelated_seeds[g] = _draw_seeds(r_unrelated, bounds, params)
            planted[g] = rasterise(planted_seeds[g])
            unrelated[g] = rasterise(unrelated_seeds[g])
            g += 1
    coords = np.concatenate(coords_parts)
    groups = np.asarray(groups_list, dtype=np.int64)
    super_group = np.asarray(super_list, dtype=np.int64)
    stand_id, stand_type = read_stands(planted, coords, groups)

    # Planted signal: a type mean per super-group and a stand's own effect.
    super_codes = sorted(sizes)
    super_position = {d: p for p, d in enumerate(super_codes)}
    type_means = r_means.normal(size=(len(super_codes), params.n_types, k))
    n_stands_total = sum(int(m.n_stands) for m in planted.values())
    stand_effects = r_stand.normal(size=(n_stands_total, k))
    which_super = np.array([super_position[int(d)] for d in super_group], dtype=np.int64)
    signal = (
        np.sqrt(params.type_share) * type_means[which_super, stand_type]
        + np.sqrt(1.0 - params.type_share) * stand_effects[stand_id]
    )

    # Background: never sees the map.
    background = np.empty((coords.shape[0], k), dtype=np.float64)
    for code in range(g):
        idx = np.flatnonzero(groups == code)
        xy = coords[idx]
        dist = np.hypot(xy[:, None, 0] - xy[None, :, 0], xy[:, None, 1] - xy[None, :, 1])
        shift = np.sqrt(params.group_var) * r_background.normal(size=k)
        white = r_background.normal(size=(idx.shape[0], k))
        if params.smooth_var > 0:
            cov = params.smooth_var * np.exp(-dist / params.smooth_range)
            cov[np.diag_indices_from(cov)] += 1e-10 * max(params.smooth_var, 1.0)
            smooth = np.linalg.cholesky(cov) @ white
        else:
            smooth = np.zeros_like(white)
        nugget = np.sqrt(params.nugget_var) * r_background.normal(size=(idx.shape[0], k))
        background[idx] = shift + smooth + nugget
    attributes = background + float(effect) * signal

    kmeans = KMeans(
        n_clusters=params.n_field_types,
        n_init=10,
        random_state=int(r_types.integers(0, 2**31 - 1)),
    ).fit(robust_scale(attributes))
    field_type = np.asarray(kmeans.labels_, dtype=np.int64)

    return SyntheticDataset(
        effect=float(effect),
        params=params,
        coords=coords,
        groups=groups,
        super_group=super_group,
        attributes=attributes,
        signal=signal,
        background=background,
        field_type=field_type,
        stand_id=stand_id,
        stand_type=stand_type,
        regions=regions,
        planted=planted,
        unrelated=unrelated,
        planted_seeds=planted_seeds,
        unrelated_seeds=unrelated_seeds,
        layer_seed=layer_seed,
    )
