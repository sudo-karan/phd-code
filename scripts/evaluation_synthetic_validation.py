"""Check the evaluation methods of `fmu.evaluation` on planted data with known answers.

Everything is generated (`fmu.evaluation.synthetic`). No site data is read.
The only numbers that come from a site are how many plots each group has
(`PLOTS_PER_GROUP`): design numbers, not measurements.

Five experiments, all declared here before anything is run:

1. **recovery**: with a strong planted effect, each of the twelve statistics
   is computed on the planted map and on four damaged or unrelated maps. A
   statistic recovers the map if it scores the planted map above the others,
   and each test should reject "no agreement".
2. **size**: with NO planted effect (the map is unrelated to the field, which
   is still spatially smooth), how often does each statistic x null model give
   `p <= 0.05`? A valid test does so 5% of the time.
3. **power**: the same rates with a planted effect of four strengths.
4. **reference_polygons**: the segmentation-accuracy measures, with the
   planted polygons as the reference, on the planted map and the four others.
5. **no_reference**: the measures that need no reference data, on a raster
   layer that follows the planted map, for the same five maps.

Run from the repo root:

    .venv/bin/python scripts/evaluation_synthetic_validation.py            # full
    .venv/bin/python scripts/evaluation_synthetic_validation.py --quick    # small

It writes `synthetic_validation.csv` and `synthetic_validation.md` into
`--out-dir` (default `docs/evaluation/`). The files hold results only: no run
times, no dates. Timings go to the log (standard error). The run is
deterministic: the same arguments give the same two files byte for byte,
whatever `--jobs` and `--cache-dir` are. Beside them goes
`synthetic_validation_run.json`, the run's record: the command, the date, the
git block (`fmu.utils.provenance.git_state`, read before the run starts) and
the Python environment (`environment_state`), as the pipeline's manifests and
the Odisha scripts' run records have. Before round 13 it wrote no record of its
own (review C37).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import shapely

from fmu.evaluation import agreement, pairs, permutation, spatial_null, synthetic
from fmu.evaluation import segmentation_accuracy as segacc
from fmu.evaluation import unsupervised as unsup
from fmu.evaluation._common import Statistic

# Plots per group (village), by super-group (district): 267 plots, 20 groups,
# 4 super-groups. Counted from the district and village columns of a plot
# table: how the plots are spread, not anything measured on them.
PLOTS_PER_GROUP: dict[int, tuple[int, ...]] = {
    0: (10, 10, 10, 9),
    1: (12, 12, 11, 10, 8, 8, 7, 7),
    2: (8,),
    3: (49, 31, 20, 11, 10, 10, 14),
}

ROOT_SEED = 20261013
ALPHA = 0.05
POWER_TARGET = 0.8  # the usual convention for "detected reliably"; used only to read the table
RECOVERY_SHARE = 0.9  # "recovers" = planted above the other map in at least this share

# Distance bands of the pair comparison, metres. A property of the synthetic
# layout (plots about 200 m apart). They say nothing about a real site.
BAND_EDGES: tuple[float, ...] = (0.0, 100.0, 200.0, 400.0, 800.0, math.inf)

STATISTICS: tuple[str, ...] = (
    "ari_drawing",
    "ari_labelling",
    "pair_stand",
    "pair_type",
    "mantel_stand",
    "mantel_type",
    "partial_mantel_stand",
    "partial_mantel_type",
    "anosim_stand",
    "anosim_type",
    "permanova_stand",
    "permanova_type",
)
STAND_STATISTICS = tuple(s for s in STATISTICS if s.endswith(("_stand", "_drawing")))
NULLS: tuple[str, ...] = (
    "free_permutation",
    "within_group_permutation",
    "rotation",
    "torus_translation",
)
MAPS: tuple[str, ...] = ("planted", "shifted", "merged", "split", "unrelated")

# Experiment numbers, used in the seed of every data set.
E_RECOVERY, E_SIZE, E_POWER, E_REFERENCE, E_NO_REFERENCE = 0, 1, 2, 3, 4


@dataclass(frozen=True)
class Design:
    """How much is run. Counts are data sets; draws are relabellings per test."""

    name: str
    n_recovery: int
    n_size: int
    n_power: int
    recovery_draws: int
    test_draws: int
    recovery_effect: float
    power_effects: tuple[float, ...]
    recovery_nulls: tuple[str, ...] = ("within_group_permutation", "rotation")
    layer_effect: float = 1.0  # the raster layer of experiment 5 follows the map this strongly
    layer_bands: int = 2
    boundary_tolerance_pixels: float = 1.0  # tolerance of the boundary match, in pixels
    # Experiments 4 and 5 score maps, not plots, so the plot layout does not
    # matter to them. They use the first few villages of each data set, which
    # keeps their cost (the boundary match above all) small.
    n_map_groups: int = 4


FULL = Design(
    name="full",
    n_recovery=10,
    n_size=300,
    n_power=80,
    recovery_draws=999,
    test_draws=99,
    recovery_effect=2.0,
    power_effects=(0.25, 0.5, 1.0, 2.0),
)
QUICK = Design(
    name="quick",
    n_recovery=2,
    n_size=6,
    n_power=4,
    recovery_draws=99,
    test_draws=19,
    recovery_effect=2.0,
    power_effects=(2.0,),
)


def scaled(design: Design, scale: float) -> Design:
    """The design with every number of data sets multiplied by one common factor.

    Draws and effects are not changed. Counts are rounded up, so none is 0.
    """
    if not 0 < scale <= 1:
        raise ValueError(f"scale must lie in (0, 1], got {scale}")
    return replace(
        design,
        n_recovery=max(1, math.ceil(design.n_recovery * scale - 1e-9)),
        n_size=max(1, math.ceil(design.n_size * scale - 1e-9)),
        n_power=max(1, math.ceil(design.n_power * scale - 1e-9)),
    )


# ---------------------------------------------------------------------------
# One data set
# ---------------------------------------------------------------------------


def build_statistics(
    attributes: Any, coords: Any, field_type: Any, groups: Any, super_group: Any
) -> list[Statistic]:
    """The twelve statistics, in the order of `STATISTICS`.

    The pair comparison, Mantel, ANOSIM and PERMANOVA all work inside groups;
    type comparisons are made inside a super-group.
    """
    field = pairs.field_distance(attributes)
    geo = pairs.geographic_distance(coords)
    comparison = pairs.PairComparison(
        field, coords, BAND_EDGES, groups=groups, super_group=super_group
    )
    stats = [
        agreement.drawing_statistic(field_type),
        agreement.labelling_statistic(field_type, super_group),
        comparison.statistic("stand"),
        comparison.statistic("type"),
        permutation.mantel_statistic(field, kind="stand", groups=groups),
        permutation.mantel_statistic(field, kind="type", groups=groups, super_group=super_group),
        permutation.mantel_statistic(field, kind="stand", groups=groups, geo_dist=geo),
        permutation.mantel_statistic(
            field, kind="type", groups=groups, super_group=super_group, geo_dist=geo
        ),
        permutation.anosim_statistic(field, by="stand", strata=groups),
        permutation.anosim_statistic(field, by="type", strata=groups),
        permutation.permanova_statistic(field, by="stand", strata=groups),
        permutation.permanova_statistic(field, by="type", strata=groups),
    ]
    names = tuple(s.name for s in stats)
    if names != STATISTICS:
        raise RuntimeError(f"statistic names differ from the declared list: {names}")
    return stats


def dataset_seed(root: int, key: tuple[int, ...]) -> np.random.SeedSequence:
    """Seed of one data set: the root seed with the data set's own key."""
    return np.random.SeedSequence(root, spawn_key=key)


def _num(x: float) -> float | None:
    """A float for JSON: `None` for NaN, so files compare byte for byte."""
    x = float(x)
    if math.isnan(x):
        return None
    return x


def _draw(
    null: str, ds: synthetic.SyntheticDataset, n_draws: int, seed: np.random.SeedSequence
) -> permutation.NullDraws | None:
    """Relabellings from one null model; `None` if the null cannot be drawn."""
    try:
        if null == "free_permutation":
            return permutation.free_permutation(ds.stand_id, ds.stand_type, n_draws, seed)
        if null == "within_group_permutation":
            return permutation.within_group_permutation(
                ds.stand_id, ds.stand_type, ds.groups, n_draws, seed
            )
        if null == "rotation":
            return spatial_null.rotation_null(
                ds.coords, ds.groups, ds.planted, ds.regions, n_draws, seed
            )
        if null == "torus_translation":
            return spatial_null.torus_translation_null(
                ds.coords, ds.groups, ds.planted, n_draws, seed
            )
    except spatial_null.NullNotEstimable:
        return None
    raise ValueError(f"unknown null {null!r}")


def run_test_dataset(
    root: int,
    key: tuple[int, ...],
    effect: float,
    n_draws: int,
    nulls: Sequence[str],
    layout: Mapping[int, Sequence[int]],
    params: synthetic.SyntheticParams,
    other_maps: bool,
) -> dict[str, Any]:
    """Generate one data set and test every statistic under the given nulls.

    Returns plain numbers: the observed value of each statistic on the
    planted map, the p-value per null and statistic (`None` where no p-value
    is given), and, with `other_maps`, the value on the four other maps.
    """
    data_seed, null_seed = dataset_seed(root, key).spawn(2)
    ds = synthetic.make_dataset(data_seed, effect, layout, params)
    stats = build_statistics(ds.attributes, ds.coords, ds.field_type, ds.groups, ds.super_group)
    null_seeds = dict(zip(NULLS, null_seed.spawn(len(NULLS)), strict=True))
    out: dict[str, Any] = {
        "observed": {s.name: _num(s(ds.stand_id, ds.stand_type)) for s in stats},
        "p": {},
        "identity": {},
    }
    for null in nulls:
        draws = _draw(null, ds, n_draws, null_seeds[null])
        if draws is None:
            out["p"][null] = dict.fromkeys(STATISTICS)
            continue
        if draws.observed_type is None:
            raise RuntimeError("the null returned no stand types")
        # The null must test the labels the statistic was observed on.
        out["identity"][null] = bool(
            np.array_equal(draws.observed_id, ds.stand_id)
            and np.array_equal(draws.observed_type, ds.stand_type)
        )
        out["p"][null] = {s.name: _num(permutation.run_test(s, draws).p_value) for s in stats}
    drawing = agreement.agreement(ds.field_type, ds.stand_id)
    counts = np.bincount(ds.stand_id)
    out["describe"] = {
        "same_stand_pairs": int(drawing.counts.b_only + drawing.counts.both),
        "stands_with_two_plots": int((counts >= 2).sum()),
        "stands_with_a_plot": int((counts >= 1).sum()),
        "ari_drawing_ceiling": _num(drawing.adjusted_rand_max),
    }
    if other_maps:
        candidates = {
            "shifted": synthetic.shifted_maps(ds),
            "merged": synthetic.merged_maps(ds),
            "split": synthetic.split_maps(ds),
            "unrelated": ds.unrelated,
        }
        out["maps"] = {"planted": dict(out["observed"])}
        for name, maps in candidates.items():
            sid, typ = synthetic.read_stands(maps, ds.coords, ds.groups)
            out["maps"][name] = {s.name: _num(s(sid, typ)) for s in stats}
    return out


def _five_maps(ds: synthetic.SyntheticDataset) -> dict[str, dict[int, Any]]:
    return {
        "planted": ds.planted,
        "shifted": synthetic.shifted_maps(ds),
        "merged": synthetic.merged_maps(ds),
        "split": synthetic.split_maps(ds),
        "unrelated": ds.unrelated,
    }


REFERENCE_MEASURES = ("over", "under", "d", "boundary_precision", "boundary_recall", "boundary_f")
NO_REFERENCE_MEASURES = (
    "r2",
    "weighted_variance",
    "morans_i",
    "global_score",
    "n_segments",
    "pixel_ari_with_planted",
)


def run_reference_dataset(
    root: int,
    key: tuple[int, ...],
    design: Design,
    layout: Mapping[int, Sequence[int]],
    params: synthetic.SyntheticParams,
) -> dict[str, Any]:
    """Segmentation accuracy of five maps against the planted polygons.

    Per group: the planted map's polygons are the reference; each candidate
    map's polygons are scored against them. The value reported for a data set
    is the plain mean over its groups.
    """
    data_seed, _ = dataset_seed(root, key).spawn(2)
    ds = synthetic.make_dataset(data_seed, design.recovery_effect, layout, params)
    tolerance = design.boundary_tolerance_pixels * params.pixel_size
    sums = {m: dict.fromkeys(REFERENCE_MEASURES, 0.0) for m in MAPS}
    maps = _five_maps(ds)
    used = sorted(ds.planted)[: design.n_map_groups]
    for g in used:
        reference = synthetic.raster_to_polygons(ds.planted[g])
        frame = shapely.union_all(np.asarray(reference, dtype=object))
        # The outer edge of the raster is shared by every map and would match
        # trivially, so it is left out of the boundary match.
        edge = shapely.buffer(shapely.boundary(frame), tolerance)
        for name in MAPS:
            stands = synthetic.raster_to_polygons(maps[name][g])
            acc = segacc.segmentation_accuracy(stands, reference).summary
            match = segacc.boundary_match(stands, reference, tolerance, ignore=edge)
            values = (acc["over"], acc["under"], acc["d"], match.precision, match.recall, match.f)
            for measure, value in zip(REFERENCE_MEASURES, values, strict=True):
                sums[name][measure] += float(value)
    n_groups = len(used)
    return {"maps": {m: {k: _num(v / n_groups) for k, v in sums[m].items()} for m in MAPS}}


def run_no_reference_dataset(
    root: int,
    key: tuple[int, ...],
    design: Design,
    layout: Mapping[int, Sequence[int]],
    params: synthetic.SyntheticParams,
) -> dict[str, Any]:
    """The no-reference measures of five maps on a layer that follows the planted map.

    Per group: a raster layer is generated from the planted map
    (`synthetic.make_layer`), and explained variance, area-weighted variance,
    Moran's I between adjacent stands and the Global Score are computed for
    the five maps as one declared set of candidates. Values are means over
    bands, then over groups. The adjusted Rand index between each map and the
    planted map, pixel against pixel, is reported beside them.
    """
    data_seed, _ = dataset_seed(root, key).spawn(2)
    ds = synthetic.make_dataset(data_seed, design.recovery_effect, layout, params)
    maps = _five_maps(ds)
    sums = {m: dict.fromkeys(NO_REFERENCE_MEASURES, 0.0) for m in MAPS}
    used = sorted(ds.planted)[: design.n_map_groups]
    layer_seeds = ds.layer_seed.spawn(len(used))
    for g, layer_seed in zip(used, layer_seeds, strict=True):
        layer = synthetic.make_layer(
            ds.planted[g], layer_seed, effect=design.layer_effect, n_bands=design.layer_bands
        )
        candidates = {name: maps[name][g].labels for name in MAPS}
        score = unsup.global_score(candidates, layer)
        mean_rows = score[score["band"] == "mean"].set_index("segmentation")
        for name in MAPS:
            r2 = unsup.explained_variance(candidates[name], layer)
            sums[name]["r2"] += float(r2["r2"].mean())
            sums[name]["n_segments"] += float(r2["n_segments"].mean())
            sums[name]["pixel_ari_with_planted"] += agreement.adjusted_rand_index(
                candidates[name].ravel(), candidates["planted"].ravel()
            )
            for measure in ("weighted_variance", "morans_i", "global_score"):
                sums[name][measure] += float(mean_rows.loc[name, measure])
    n_groups = len(used)
    return {"maps": {m: {k: _num(v / n_groups) for k, v in sums[m].items()} for m in MAPS}}


# ---------------------------------------------------------------------------
# Running all data sets
# ---------------------------------------------------------------------------


def _tasks(design: Design) -> list[tuple[str, tuple[int, ...], float]]:
    """Every data set of the design: (experiment, seed key, effect)."""
    tasks: list[tuple[str, tuple[int, ...], float]] = []
    tasks += [("recovery", (E_RECOVERY, k), design.recovery_effect) for k in range(design.n_recovery)]
    tasks += [("size", (E_SIZE, k), 0.0) for k in range(design.n_size)]
    for effect in design.power_effects:
        # An effect of the full design keeps its number, so --quick is a part of the full run.
        position = (
            FULL.power_effects.index(effect)
            if effect in FULL.power_effects
            else len(FULL.power_effects) + design.power_effects.index(effect)
        )
        tasks += [("power", (E_POWER, position, k), effect) for k in range(design.n_power)]
    tasks += [
        ("reference_polygons", (E_REFERENCE, k), design.recovery_effect)
        for k in range(design.n_recovery)
    ]
    tasks += [
        ("no_reference", (E_NO_REFERENCE, k), design.recovery_effect)
        for k in range(design.n_recovery)
    ]
    return tasks


def _work(job: tuple[Any, ...]) -> tuple[dict[str, Any], float]:
    experiment, key, effect, design, root, layout, params, cache_dir = job
    started = time.process_time()
    path = None
    if cache_dir is not None:
        path = Path(cache_dir) / ("_".join([experiment, *map(str, key)]) + ".json")
        if path.exists():
            return json.loads(path.read_text()), 0.0
    if experiment == "recovery":
        result = run_test_dataset(
            root, key, effect, design.recovery_draws, design.recovery_nulls, layout, params, True
        )
    elif experiment in ("size", "power"):
        result = run_test_dataset(root, key, effect, design.test_draws, NULLS, layout, params, False)
    elif experiment == "reference_polygons":
        result = run_reference_dataset(root, key, design, layout, params)
    else:
        result = run_no_reference_dataset(root, key, design, layout, params)
    if path is not None:
        tmp = path.with_suffix(f".tmp{key[-1]}")
        tmp.write_text(json.dumps(result, sort_keys=True))
        tmp.replace(path)
    return result, time.process_time() - started


def _source_files() -> list[tuple[str, Path]]:
    """The code a cached data set depends on: this script (the workers) and every module of
    `fmu.evaluation` (the only part of `fmu` it imports), each with a name for the hash."""
    package = Path(agreement.__file__).parent
    return [("script", Path(__file__))] + [
        (f"fmu/evaluation/{f.name}", f) for f in sorted(package.glob("*.py"))
    ]


def _source_hash() -> str:
    digest = hashlib.sha256()
    for name, path in _source_files():
        digest.update(name.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def _fingerprint(design: Design, root: int, layout: Any, params: Any) -> str:
    # the sources' hash keys the cache by the code too: a run resumed after any change to the
    # workers or to fmu.evaluation recomputes every data set instead of reading the old results
    payload = json.dumps(
        [_source_hash(), asdict(design), root, sorted(layout.items()), asdict(params), BAND_EDGES],
        sort_keys=True,
        default=str,
    )
    return hashlib.sha1(payload.encode()).hexdigest()[:12]


def run_validation(
    design: Design,
    *,
    seed: int = ROOT_SEED,
    layout: Mapping[int, Sequence[int]] = PLOTS_PER_GROUP,
    params: synthetic.SyntheticParams = synthetic.DEFAULT_PARAMS,
    jobs: int = 1,
    cache_dir: Path | None = None,
    log: Any = None,
) -> dict[str, Any]:
    """Run every data set of `design` and return the raw results, in a fixed order.

    The result does not depend on `jobs` or `cache_dir`. `cache_dir` keeps one
    file per finished data set, so a run that was cut off continues where it
    stopped; the files of a different design, seed, layout or parameter set,
    or of different code (this script or any module of `fmu.evaluation`), go
    to a different folder.
    """
    layout = {int(k): tuple(int(s) for s in v) for k, v in layout.items()}
    tasks = _tasks(design)
    # The counts do not enter the cache key: a data set is the same whatever
    # the number of others, so a small run is a prefix of a larger one.
    per_set = replace(design, name="", n_recovery=0, n_size=0, n_power=0, power_effects=())
    folder = None
    if cache_dir is not None:
        folder = Path(cache_dir) / _fingerprint(per_set, seed, layout, params)
        folder.mkdir(parents=True, exist_ok=True)
    job_list = [(e, key, effect, design, seed, layout, params, folder) for e, key, effect in tasks]
    results: list[dict[str, Any]] = []
    cpu = 0.0
    started = time.perf_counter()

    def note(done: int) -> None:
        if log is not None and (done % 10 == 0 or done == len(job_list)):
            print(
                f"  {done}/{len(job_list)} data sets, {cpu:.0f} s of processor time, "
                f"{time.perf_counter() - started:.0f} s elapsed",
                file=log,
                flush=True,
            )

    if jobs <= 1:
        for job in job_list:
            result, seconds = _work(job)
            results.append(result)
            cpu += seconds
            note(len(results))
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            for result, seconds in pool.map(_work, job_list, chunksize=1):
                results.append(result)
                cpu += seconds
                note(len(results))
    grouped: dict[str, Any] = {
        "recovery": [],
        "size": [],
        "power": {e: [] for e in design.power_effects},
        "reference_polygons": [],
        "no_reference": [],
    }
    for (experiment, _key, effect), result in zip(tasks, results, strict=True):
        if experiment == "power":
            grouped["power"][effect].append(result)
        else:
            grouped[experiment].append(result)
    return {"design": design, "seed": seed, "layout": layout, "params": params, "raw": grouped}


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """The 95% Wilson interval of a proportion; `(nan, nan)` when `n == 0`."""
    if n == 0:
        return float("nan"), float("nan")
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


COLUMNS = (
    "experiment",
    "effect",
    "statistic",
    "null",
    "map",
    "quantity",
    "value",
    "std_error",
    "wilson_low",
    "wilson_high",
    "n_replicates",
    "n_draws",
    "n_no_p_value",
)


def _rate_row(
    experiment: str, effect: float, statistic: str, null: str, flags: list[bool | None], n_draws: int
) -> dict[str, Any]:
    """A rejection rate. A data set without a p-value counts as "not rejected"."""
    m = len(flags)
    hits = sum(1 for f in flags if f)
    rate = hits / m if m else float("nan")
    low, high = wilson_interval(hits, m)
    return {
        "experiment": experiment,
        "effect": effect,
        "statistic": statistic,
        "null": null,
        "map": "planted",
        "quantity": "rejection_rate",
        "value": rate,
        "std_error": math.sqrt(rate * (1 - rate) / m) if m else float("nan"),
        "wilson_low": low,
        "wilson_high": high,
        "n_replicates": m,
        "n_draws": n_draws,
        "n_no_p_value": sum(1 for f in flags if f is None),
    }


def _share_row(
    experiment: str, effect: float, statistic: str, map_name: str, quantity: str, flags: list[bool]
) -> dict[str, Any]:
    m = len(flags)
    hits = sum(flags)
    share = hits / m if m else float("nan")
    low, high = wilson_interval(hits, m)
    return {
        "experiment": experiment,
        "effect": effect,
        "statistic": statistic,
        "null": "",
        "map": map_name,
        "quantity": quantity,
        "value": share,
        "std_error": math.sqrt(share * (1 - share) / m) if m else float("nan"),
        "wilson_low": low,
        "wilson_high": high,
        "n_replicates": m,
        "n_draws": "",
        "n_no_p_value": "",
    }


def _mean_row(
    experiment: str, effect: float, statistic: str, map_name: str, values: list[float | None]
) -> dict[str, Any]:
    """Mean of a score over data sets; its standard error is `sd / sqrt(m)`."""
    kept = np.array([v for v in values if v is not None], dtype=np.float64)
    m = int(kept.shape[0])
    return {
        "experiment": experiment,
        "effect": effect,
        "statistic": statistic,
        "null": "",
        "map": map_name,
        "quantity": "mean_value",
        "value": float(kept.mean()) if m else float("nan"),
        "std_error": float(kept.std(ddof=1) / math.sqrt(m)) if m > 1 else float("nan"),
        "wilson_low": "",
        "wilson_high": "",
        "n_replicates": m,
        "n_draws": "",
        "n_no_p_value": "",
    }


def _rejected(p: float | None) -> bool | None:
    return None if p is None else bool(p <= ALPHA)


def _above(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and a > b


def _equal(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and a == b


def summarise(results: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn the raw results into the rows of the result table, in a fixed order."""
    design: Design = results["design"]
    raw = results["raw"]
    rows: list[dict[str, Any]] = []

    recovery = raw["recovery"]
    effect = design.recovery_effect
    for s in STATISTICS:
        for name in MAPS:
            rows.append(_mean_row("recovery", effect, s, name, [r["maps"][name][s] for r in recovery]))
        for name in MAPS[1:]:
            pairs_ = [(r["maps"]["planted"][s], r["maps"][name][s]) for r in recovery]
            rows.append(
                _share_row(
                    "recovery", effect, s, name, "share_planted_above", [_above(a, b) for a, b in pairs_]
                )
            )
            rows.append(
                _share_row(
                    "recovery", effect, s, name, "share_planted_equal", [_equal(a, b) for a, b in pairs_]
                )
            )
        for null in design.recovery_nulls:
            flags = [_rejected(r["p"][null][s]) for r in recovery]
            rows.append(_rate_row("recovery", effect, s, null, flags, design.recovery_draws))
    for key in ("same_stand_pairs", "stands_with_two_plots", "stands_with_a_plot", "ari_drawing_ceiling"):
        rows.append(
            _mean_row("recovery", effect, key, "planted", [r["describe"][key] for r in recovery])
        )

    for experiment, effect, sets in [("size", 0.0, raw["size"])] + [
        ("power", e, raw["power"][e]) for e in design.power_effects
    ]:
        for s in STATISTICS:
            rows.append(_mean_row(experiment, effect, s, "planted", [r["observed"][s] for r in sets]))
            for null in NULLS:
                flags = [_rejected(r["p"][null][s]) for r in sets]
                rows.append(_rate_row(experiment, effect, s, null, flags, design.test_draws))

    for experiment, measures in (
        ("reference_polygons", REFERENCE_MEASURES),
        ("no_reference", NO_REFERENCE_MEASURES),
    ):
        sets = raw[experiment]
        for measure in measures:
            for name in MAPS:
                rows.append(
                    _mean_row(
                        experiment,
                        design.recovery_effect,
                        measure,
                        name,
                        [r["maps"][name][measure] for r in sets],
                    )
                )
    return rows


def identity_failures(results: dict[str, Any]) -> int:
    """Data sets in which a null did not start from the labels that were scored."""
    raw = results["raw"]
    sets = raw["recovery"] + raw["size"] + [r for e in raw["power"].values() for r in e]
    return sum(1 for r in sets for ok in r["identity"].values() if not ok)


def _cell(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if math.isnan(value):
        return ""
    return f"{value:.6g}"


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    lines = [",".join(COLUMNS)]
    lines += [",".join(_cell(row[c]) for c in COLUMNS) for row in rows]
    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------


def chance_of_too_high(n: int) -> float:
    """How often a SOUND test (true rate 0.05) is marked too high on `n` data sets.

    The rule marks a cell when the whole Wilson interval lies above 0.05. This
    is the binomial probability of a count large enough for that.
    """
    if n <= 0:
        return float("nan")
    smallest = next((k for k in range(n + 1) if wilson_interval(k, n)[0] > ALPHA), n + 1)
    below = sum(math.comb(n, k) * ALPHA**k * (1 - ALPHA) ** (n - k) for k in range(smallest))
    return max(0.0, 1.0 - below)


def size_verdict(low: float, high: float) -> str:
    """Declared rule: too high only if the whole 95% interval is above 0.05."""
    if low > ALPHA:
        return "too high"
    if high < ALPHA:
        return "below 0.05"
    return "acceptable"


def _pick(rows: list[dict[str, Any]], **where: Any) -> list[dict[str, Any]]:
    return [r for r in rows if all(r[k] == v for k, v in where.items())]


def _one(rows: list[dict[str, Any]], **where: Any) -> dict[str, Any]:
    found = _pick(rows, **where)
    if len(found) != 1:
        raise KeyError(f"{len(found)} rows match {where}")
    return found[0]


def _f(x: float, digits: int = 3) -> str:
    return "n/a" if (isinstance(x, float) and math.isnan(x)) else f"{x:.{digits}f}"


def _table(header: list[str], body: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(line) + " |" for line in body]
    return out


def _met(flag: bool) -> str:
    return "met" if flag else "NOT met"


def command_line(design: Design, scale: float, seed: int) -> str:
    parts = [".venv/bin/python scripts/evaluation_synthetic_validation.py"]
    if design.name == "quick":
        parts.append("--quick")
    if scale != 1.0:
        parts.append(f"--scale {scale:g}")
    if seed != ROOT_SEED:
        parts.append(f"--seed {seed}")
    return " ".join(parts)


def render_markdown(results: dict[str, Any], rows: list[dict[str, Any]], command: str) -> str:
    design: Design = results["design"]
    params: synthetic.SyntheticParams = results["params"]
    layout = results["layout"]
    n_plots = sum(sum(v) for v in layout.values())
    n_groups = sum(len(v) for v in layout.values())
    sizes = sorted((s for v in layout.values() for s in v), reverse=True)
    rec = design.recovery_effect
    L: list[str] = []  # noqa: N806 - the lines of the document
    add = L.append

    # ---- size verdicts, used throughout
    verdict: dict[tuple[str, str], str] = {}
    for s in STATISTICS:
        for null in NULLS:
            r = _one(rows, experiment="size", statistic=s, null=null, quantity="rejection_rate")
            verdict[(s, null)] = size_verdict(r["wilson_low"], r["wilson_high"])
    readable = {n: [s for s in STATISTICS if verdict[(s, n)] != "too high"] for n in NULLS}
    too_high = {n: [s for s in STATISTICS if verdict[(s, n)] == "too high"] for n in NULLS}

    add("# Synthetic validation of the evaluation metrics")
    add("")
    add(
        "This file is written by `scripts/evaluation_synthetic_validation.py`. Do not edit it by "
        "hand: run the script again. It holds results only, no run times and no dates."
    )
    add("")
    if design.name == "quick":
        add(
            "**This is the `--quick` run.** It is far too small to read rates from. It exists to "
            "check that the script runs and repeats."
        )
        add("")
    add("## The answer in short")
    add("")
    def size_rate(statistic: str, null: str) -> float:
        row = _one(rows, experiment="size", statistic=statistic, null=null, quantity="rejection_rate")
        return float(row["value"])

    def power_rate(statistic: str, null: str, effect: float) -> float:
        row = _one(
            rows,
            experiment="power",
            effect=effect,
            statistic=statistic,
            null=null,
            quantity="rejection_rate",
        )
        return float(row["value"])

    column_mean = {n: float(np.mean([size_rate(s, n) for s in STATISTICS])) for n in NULLS}
    fewest = min(len(too_high[n]) for n in NULLS)
    best = [n for n in NULLS if len(too_high[n]) == fewest]
    add(
        f"- **False alarms.** The map was made unrelated to the field data, the field data were "
        f"left spatially smooth (nearby plots alike), and each test was run at the 0.05 level on "
        f"{design.n_size} data sets. A sound test gives a false alarm in about 5% of them. What "
        "was measured, per way of simulating chance:"
    )
    for null in NULLS:
        rates = [size_rate(s, null) for s in STATISTICS]
        head = (
            f"  - `{null}`: false-alarm rates from {_f(min(rates))} to {_f(max(rates))}, "
            f"{_f(column_mean[null])} on average over the twelve statistics. "
        )
        if too_high[null]:
            add(
                head
                + f"Too high for {len(too_high[null])} of {len(STATISTICS)}: "
                + ", ".join(f"`{s}` ({_f(size_rate(s, null))})" for s in too_high[null])
                + "."
            )
        else:
            add(head + "Too high for none.")
    add(
        "  - Fewest failures: "
        + ", ".join(f"`{n}`" for n in best)
        + f" ({fewest} of {len(STATISTICS)}). A small p-value from a statistic x null pair marked "
        "too high does not mean the map agrees with the field: with these data it turns up that "
        "often when the map is unrelated to the field."
    )
    unmet = []
    for s in STATISTICS:
        for m in ("unrelated", "shifted", "merged"):
            r = _one(rows, experiment="recovery", statistic=s, map=m, quantity="share_planted_above")
            if r["value"] < RECOVERY_SHARE:
                unmet.append(f"`{s}` does not put the planted map above the {m} one")
    for s in STAND_STATISTICS:
        r = _one(rows, experiment="recovery", statistic=s, map="split", quantity="share_planted_above")
        if r["value"] < RECOVERY_SHARE:
            unmet.append(f"`{s}` does not put the planted map above the split one")
    add(
        f"- **Recovery.** With a strong planted effect (effect {rec:g}: the map accounts for "
        f"{synthetic.planted_signal_share(rec, params):.0%} of the variance of each measurement), "
        + (
            "every statistic scores the planted map above every damaged map it was expected to."
            if not unmet
            else "not every statistic prefers the planted map: " + "; ".join(unmet) + ". Section 1 "
            "says why."
        )
    )
    if "rotation" in NULLS:
        parts = []
        for e in design.power_effects:
            reach = [
                s
                for s in STATISTICS
                if verdict[(s, "rotation")] != "too high" and power_rate(s, "rotation", e) >= POWER_TARGET
            ]
            parts.append(
                f"at effect {e:g} (the map accounts for "
                f"{synthetic.planted_signal_share(e, params):.0%} of the variance) "
                f"{len(reach)} of the {len(readable['rotation'])} readable statistics reach a power "
                f"of {POWER_TARGET:g}"
            )
        add(
            f"- **Power** with this layout, under `rotation`, on {design.n_power} data sets per "
            "effect: " + "; ".join(parts) + ". Section 3 has every cell."
        )
    def map_value(experiment: str, measure: str, name: str) -> float:
        return float(_one(rows, experiment=experiment, statistic=measure, map=name)["value"])

    d_best = all(
        map_value("reference_polygons", "d", "planted") < map_value("reference_polygons", "d", m)
        for m in MAPS[1:]
    )
    score_best = all(
        map_value("no_reference", "global_score", "planted") < map_value("no_reference", "global_score", m)
        for m in MAPS[1:]
    )
    r2_fooled = map_value("no_reference", "r2", "split") >= map_value("no_reference", "r2", "planted")
    add(
        "- **Reference polygons** (section 4): the combined over- and under-segmentation measure D "
        + ("is best for the planted map." if d_best else "is NOT best for the planted map.")
        + " **No reference data** (section 5): the Global Score "
        + ("is best for the planted map" if score_best else "is NOT best for the planted map")
        + "; explained variance alone "
        + (
            "does not tell the planted map from one with every stand cut in two."
            if r2_fooled
            else "is higher for the planted map than for one with every stand cut in two."
        )
    )
    add(
        "- The parameters of the generator and the rules for reading the tables were fixed before "
        "the pilot and the full run and were not changed after seeing a result. One fault in the "
        "generator was corrected before those runs; the last section says what and why."
    )
    add("")

    add("## What was run")
    add("")
    add("Command, from the repo root:")
    add("")
    add("```")
    add(command)
    add("```")
    add("")
    add(
        "`--jobs N` and `--cache-dir DIR` may be added. They change how long the run takes and "
        "nothing in the two result files."
    )
    add("")
    add(
        f"- **Root seed**: {results['seed']}. Data set `k` of an experiment is seeded with "
        "`numpy.random.SeedSequence(root, spawn_key=(experiment, k))` (for power: "
        "`(experiment, effect number, k)`), experiments numbered recovery 0, size 1, power 2, "
        "reference polygons 3, no reference 4. A data set is therefore the same whatever else is "
        "run, and a smaller run is the first part of a larger one."
    )
    add(
        f"- **Layout**: {n_plots} plots in {n_groups} groups (villages) in {len(layout)} "
        f"super-groups (districts). Plots per group, largest first: "
        + ", ".join(str(s) for s in sizes)
        + ". These counts are the only thing taken from a real site: they are how many plots each "
        "village has, counted from the district and village columns of the plot table. No "
        "measurement, stand or polygon of a real site was read."
    )
    add(
        f"- **Numbers of data sets used**: recovery {design.n_recovery} (effect {rec:g}, "
        f"{design.recovery_draws} relabellings per test); size {design.n_size} (effect 0, "
        f"{design.test_draws} relabellings); power {design.n_power} at each of the effects "
        + ", ".join(f"{e:g}" for e in design.power_effects)
        + f" ({design.test_draws} relabellings); reference polygons {design.n_recovery}; "
        f"no reference {design.n_recovery}."
    )
    if design.name == "full" and (design.n_size, design.n_power, design.n_recovery) != (
        FULL.n_size,
        FULL.n_power,
        FULL.n_recovery,
    ):
        add(
            f"  The design declared {FULL.n_recovery}, {FULL.n_size} and {FULL.n_power}. All three "
            "were cut by one common factor to fit the time available. The factor was chosen from "
            "the measured cost of a data set, before any rate was looked at. The price is a wider "
            "Monte Carlo error, shown beside every rate."
        )
    add(
        "- **Statistics** (twelve, all one-sided: larger means the map agrees better with the "
        "field): the adjusted Rand index of field type against stand (`ari_drawing`) and against "
        "stand type within district (`ari_labelling`); the pair comparison within village and "
        "distance band (`pair_stand`, `pair_type`; bands "
        + ", ".join(f"{a:g}" for a in BAND_EDGES[:-1])
        + " m and beyond, a property of this synthetic layout only); Mantel and partial Mantel "
        "(distance held fixed) on within-village pairs; ANOSIM and PERMANOVA within villages. "
        '"stand" statistics test where the boundaries are drawn; "type" statistics test the types '
        "given to the stands."
    )
    add(
        "- **Null models** (what \"chance\" means): `free_permutation` shuffles the stand labels "
        "over all plots; `within_group_permutation` shuffles them inside each village; `rotation` "
        "moves each village's plots as one rigid shape to a random place and angle over the map; "
        "`torus_translation` slides the map under the plots and wraps it round at the edges. "
        "The last two keep the plots' spacing and the map's shapes; the first two do not. "
        "p = (b + 1) / (R + 1), with b of R relabellings at least as large as the observed value."
    )
    add("")
    add("### The generated data")
    add("")
    add(
        f"Each village's plots lie in a square of {params.area_per_plot / 10_000:g} ha per plot, at "
        f"least {params.min_plot_spacing:g} m apart. The village forest is the convex hull of its "
        f"plots widened by {params.region_buffer:g} m. The planted stand map is a raster of "
        f"{params.pixel_size:g} m pixels: stands are the cells nearest to the points of a "
        f"{params.stand_spacing:g} m grid, each point moved at random by up to "
        f"{params.stand_jitter:g} m (stands of about "
        f"{params.stand_spacing**2 / 10_000:.1f} ha). Each stand gets one of {params.n_types} types "
        "at random."
    )
    add("")
    add(
        f"Each plot has {params.n_attributes} attributes: a shift shared by its village (variance "
        f"{params.group_var:g}), a spatially smooth part (variance {params.smooth_var:g}, "
        f"correlation falling to 37% at {params.smooth_range:g} m), independent noise (variance "
        f"{params.nugget_var:g}), and `effect` times a planted signal of variance 1. "
        f"{params.type_share:.0%} of the signal comes from the stand's type (type means are drawn "
        "separately in each district, so a type number means a different forest in each) and the "
        "rest from the stand itself. At effect 0 the attributes do not depend on the map at all, "
        "but nearby plots are still alike and villages still differ. The share of an attribute's "
        "variance that the map accounts for is: "
        + ", ".join(
            f"{synthetic.planted_signal_share(e, params):.2f} at effect {e:g}"
            for e in FULL.power_effects
        )
        + f". Field types are k-means with {params.n_field_types} clusters on the robust-scaled "
        "attributes."
    )
    add("")
    add(
        "The four other maps: **shifted** (every boundary moved by half a stand spacing in x and "
        "y), **merged** (stands joined four at a time), **split** (every stand cut in two by a "
        "straight line; both halves keep the type), **unrelated** (a second map made the same way "
        "from an independent random stream)."
    )
    add("")
    describe = {
        key: _one(rows, experiment="recovery", statistic=key, quantity="mean_value")["value"]
        for key in ("same_stand_pairs", "stands_with_two_plots", "stands_with_a_plot", "ari_drawing_ceiling")
    }
    add(
        f"**How little the plots say about stands.** On average over the recovery data sets the "
        f"{n_plots} plots fall in {describe['stands_with_a_plot']:.0f} stands; only "
        f"{describe['stands_with_two_plots']:.0f} stands hold two or more plots, which gives "
        f"{describe['same_stand_pairs']:.0f} pairs of plots in the same stand out of "
        f"{n_plots * (n_plots - 1) // 2:,} pairs. Everything a \"stand\" statistic knows comes "
        f"from those pairs. The highest value `ari_drawing` could reach with these group sizes is "
        f"{describe['ari_drawing_ceiling']:.3f} (not 1), because stands are much finer than field "
        "types."
    )
    add("")

    # ---- recovery
    add("## 1. Recovery: does each statistic prefer the planted map?")
    add("")
    add(
        f"Effect {rec:g}, {design.n_recovery} data sets. Mean value of each statistic on each map "
        "(standard error over data sets in brackets)."
    )
    add("")
    body = []
    for s in STATISTICS:
        line = [f"`{s}`"]
        for name in MAPS:
            r = _one(rows, experiment="recovery", statistic=s, map=name, quantity="mean_value")
            line.append(f"{r['value']:.4g} ({_f(r['std_error'], 4)})")
        body.append(line)
    L.extend(_table(["statistic", *MAPS], body))
    add("")
    add(
        "Share of data sets in which the planted map scores strictly above each other map, and "
        f"share in which the planted map is rejected at {ALPHA} (\"no agreement\" is rejected, "
        f"{design.recovery_draws} relabellings)."
    )
    add("")
    body = []
    share: dict[tuple[str, str], float] = {}
    equal: dict[tuple[str, str], float] = {}
    reject: dict[tuple[str, str], float] = {}
    for s in STATISTICS:
        line = [f"`{s}`"]
        for name in MAPS[1:]:
            share[(s, name)] = _one(
                rows, experiment="recovery", statistic=s, map=name, quantity="share_planted_above"
            )["value"]
            equal[(s, name)] = _one(
                rows, experiment="recovery", statistic=s, map=name, quantity="share_planted_equal"
            )["value"]
            line.append(_f(share[(s, name)], 2))
        for null in design.recovery_nulls:
            reject[(s, null)] = _one(
                rows, experiment="recovery", statistic=s, null=null, quantity="rejection_rate"
            )["value"]
            line.append(_f(reject[(s, null)], 2))
        body.append(line)
    L.extend(
        _table(
            ["statistic", *(f"above {m}" for m in MAPS[1:]), *(f"rejected, {n}" for n in design.recovery_nulls)],
            body,
        )
    )
    add("")
    add(
        f"Expectations, declared before the run. \"Above\" means in at least {RECOVERY_SHARE:.0%} "
        "of the data sets."
    )
    add("")
    e1 = [(s, m) for s in STATISTICS for m in ("unrelated", "shifted", "merged") if share[(s, m)] < RECOVERY_SHARE]
    e2 = [s for s in STAND_STATISTICS if share[(s, "split")] < RECOVERY_SHARE]
    e3 = equal[("ari_labelling", "split")] == 1.0
    e4 = [(s, n) for s in STATISTICS for n in design.recovery_nulls if reject[(s, n)] < RECOVERY_SHARE]
    add(
        f"1. Planted above unrelated, shifted and merged, for all twelve statistics: **{_met(not e1)}**."
        + (
            " Not above: " + "; ".join(f"`{s}` against {m} ({_f(share[(s, m)], 2)})" for s, m in e1) + "."
            if e1
            else ""
        )
    )
    add(
        f"2. Planted above split, for the six \"stand\" statistics: **{_met(not e2)}**."
        + (
            " Not above: " + ", ".join(f"`{s}` ({_f(share[(s, 'split')], 2)})" for s in e2) + "."
            if e2
            else ""
        )
    )
    add(
        "3. `ari_labelling` exactly equal on planted and split (splitting a stand leaves every "
        f"plot's type as it was): **{_met(e3)}**. The other \"type\" statistics are not expected "
        "to separate planted from split either; that is not a failure."
    )
    add(
        f"4. The planted map rejected in at least {RECOVERY_SHARE:.0%} of data sets, every "
        f"statistic, both nulls: **{_met(not e4)}**."
        + (
            " Below: " + "; ".join(f"`{s}` under {n} ({_f(reject[(s, n)], 2)})" for s, n in e4) + "."
            if e4
            else ""
        )
    )
    add("")

    def mean_on(statistic: str, name: str) -> float:
        row = _one(rows, experiment="recovery", statistic=statistic, map=name, quantity="mean_value")
        return float(row["value"])

    notes = []
    if ("ari_drawing", "merged") in e1:
        notes.append(
            "`ari_drawing` scores the merged map (stands four times too large) ABOVE the planted "
            f"one in every data set ({mean_on('ari_drawing', 'merged'):.4f} against "
            f"{mean_on('ari_drawing', 'planted'):.4f}). This is a property of the adjusted Rand "
            "index, not a fault in the code (the index is checked against scikit-learn's in the "
            "unit tests). The index compares the stands and the field types as two groupings of "
            "equal standing. With stands far finer than field types, its size is set mostly by "
            "how many pairs of plots share a stand. Larger stands put more pairs together, a "
            "fair number of them are of one field type, and the index goes up although "
            f"{1 - map_value('reference_polygons', 'boundary_recall', 'merged'):.0%} of the "
            "planted boundary length is gone (section 4). So `ari_drawing` must not be used to compare maps with "
            "different stand sizes, and its value says little on its own. As a test against "
            "chance it still works (expectation 4 and section 3)."
        )
    purity = [s for s in ("anosim_stand", "permanova_stand") if s in e2]
    if purity:
        notes.append(
            ", ".join(f"`{s}`" for s in purity)
            + " do not score the planted map above the split one ("
            + "; ".join(f"{mean_on(s, 'planted'):.3f} against {mean_on(s, 'split'):.3f}" for s in purity)
            + "). This too is a property of the statistics. They ask whether plots in the same "
            "stand are more alike than plots in different stands of the village. Cutting a stand "
            "in two leaves each half as pure as the whole, so they lose nothing. They cannot see "
            "a boundary that should not be there (over-segmentation). `pair_stand` and the Mantel "
            "statistics do fall under splitting, because the two halves of a stand now count as "
            "\"different stands\" and are alike."
        )
    others = [f"`{s}` against {m}" for s, m in e1 if (s, m) != ("ari_drawing", "merged")] + [
        f"`{s}` against split" for s in e2 if s not in purity
    ]
    if others:
        notes.append(
            "Not explained: " + "; ".join(others) + ". These are open and are not to be read as "
            "properties of the methods until someone has looked into them."
        )
    if notes:
        add("Why, for the expectations not met:")
        add("")
        for note in notes:
            add(f"- {note}")
        add("")

    # ---- size
    add("## 2. Size: false alarms when the map is unrelated to the field")
    add("")
    add(
        f"Effect 0, {design.n_size} data sets, {design.test_draws} relabellings per test. Each "
        f"cell is the share of data sets with p <= {ALPHA}, with its 95% Wilson interval. A sound "
        f"test gives {ALPHA}. Declared rule: **too high** if the whole interval lies above "
        f"{ALPHA}; otherwise acceptable (marked \"below\" if the whole interval lies under "
        f"{ALPHA}: the test is then cautious, which costs power but not honesty)."
    )
    add("")
    body = []
    no_p_notes = []
    for s in STATISTICS:
        line = [f"`{s}`"]
        for null in NULLS:
            r = _one(rows, experiment="size", statistic=s, null=null, quantity="rejection_rate")
            mark = {"too high": " **too high**", "below 0.05": " below", "acceptable": ""}[verdict[(s, null)]]
            line.append(f"{_f(r['value'])} [{_f(r['wilson_low'])}, {_f(r['wilson_high'])}]{mark}")
            if r["n_no_p_value"]:
                no_p_notes.append(f"`{s}` under `{null}`: {r['n_no_p_value']} of {r['n_replicates']}")
        body.append(line)
    L.extend(_table(["statistic", *NULLS], body))
    add("")
    se = math.sqrt(ALPHA * (1 - ALPHA) / design.n_size)
    add(
        f"Monte Carlo error: a true rate of {ALPHA} measured on {design.n_size} data sets has a "
        f"standard error of {se:.3f}. A sound test is marked too high by this rule in "
        f"{chance_of_too_high(design.n_size):.1%} of runs. So if all {len(STATISTICS) * len(NULLS)} "
        f"tests were sound, about {len(STATISTICS) * len(NULLS) * chance_of_too_high(design.n_size):.1f} "
        f"marks would be expected in the whole table and about "
        f"{len(STATISTICS) * chance_of_too_high(design.n_size):.1f} in one column (fewer than these "
        "counts suggest are independent, because the twelve statistics share data sets). One "
        "isolated \"too high\" among acceptable neighbours is weak evidence; a whole column is not."
    )
    if no_p_notes:
        add("")
        add(
            "Data sets in which no p-value could be given (the statistic was undefined in more "
            "than 10% of the relabellings, or the null could not be drawn); they count as \"not "
            "rejected\": " + "; ".join(no_p_notes) + "."
        )
    add("")
    add("Reading:")
    add("")
    for null in NULLS:
        if too_high[null]:
            add(
                f"- `{null}`: **not sound** for "
                + ", ".join(f"`{s}`" for s in too_high[null])
                + (
                    "; acceptable for " + ", ".join(f"`{s}`" for s in readable[null]) + "."
                    if readable[null]
                    else ". No statistic is acceptable under it."
                )
            )
        else:
            add(f"- `{null}`: acceptable for all twelve statistics.")
    add("")
    add(
        "Average false-alarm rate over the twelve statistics: "
        + ", ".join(f"`{n}` {_f(column_mean[n])}" for n in NULLS)
        + ". (The twelve are computed on the same data sets, so they rise and fall together and "
        f"this average is not twelve times as precise as one cell; its standard error is "
        f"somewhere between {se / math.sqrt(len(STATISTICS)):.3f} and {se:.3f}.)"
    )
    add("")
    add(
        "What lies behind these numbers. The first five points are reasoning from how the data "
        "were generated and how the statistics are defined; no separate experiment was run to "
        "prove each one."
    )
    add("")
    add(
        "- **Shuffling over all plots** treats a plot in one village as interchangeable with a "
        "plot in another. Villages differ, and a stand lies in one village, so any statistic "
        "that looks across villages finds \"agreement\" that is only the village difference "
        f"(`ari_drawing`: {_f(size_rate('ari_drawing', 'free_permutation'))}). For the "
        "stand statistics that work inside villages it fails the other way "
        f"(`pair_stand` {_f(size_rate('pair_stand', 'free_permutation'))}, `anosim_stand` "
        f"{_f(size_rate('anosim_stand', 'free_permutation'))}): after such a shuffle hardly any two "
        "plots of a village share a stand, the shuffled values swing wildly, and the real value "
        "almost never stands out. Neither is a usable test."
    )
    add(
        "- **Shuffling inside villages** removes the village difference but not the smoothness. "
        "Two plots in the same stand are close together, and close plots are alike whatever the "
        "map says. The shuffle breaks that link, so the real map looks better than chance: "
        f"`mantel_stand` {_f(size_rate('mantel_stand', 'within_group_permutation'))}, "
        f"`anosim_stand` {_f(size_rate('anosim_stand', 'within_group_permutation'))}, "
        f"`permanova_stand` {_f(size_rate('permanova_stand', 'within_group_permutation'))}."
    )
    add(
        "- **Holding distance fixed does not cure it.** The partial Mantel statistic still gives "
        f"{_f(size_rate('partial_mantel_stand', 'within_group_permutation'))} under the "
        "within-village shuffle, and the pair comparison inside distance bands "
        f"{_f(size_rate('pair_stand', 'within_group_permutation'))}: better, not sound. Inside a "
        "distance band the same-stand pairs are still the closer ones. This is the warning of "
        "Guillot and Rousset (2013, doi:10.1111/2041-210x.12018) about Mantel tests on spatially "
        "smooth data, seen here for the other statistics as well."
    )
    add(
        "- **Type statistics** built from Mantel, ANOSIM and PERMANOVA also fail under the "
        f"within-village shuffle (`mantel_type` {_f(size_rate('mantel_type', 'within_group_permutation'))}, "
        f"`anosim_type` {_f(size_rate('anosim_type', 'within_group_permutation'))}, `permanova_type` "
        f"{_f(size_rate('permanova_type', 'within_group_permutation'))}), because their \"same "
        "type\" pairs include the pairs in the same stand, which are the close ones. `pair_type` "
        "leaves same-stand pairs out and holds "
        f"({_f(size_rate('pair_type', 'within_group_permutation'))}); `ari_labelling` gives "
        f"{_f(size_rate('ari_labelling', 'within_group_permutation'))}."
    )
    add(
        "- **The torus translation** wraps the map round at the edges of each village's raster. "
        "The raster is not much larger than the plot layout, so many shifts put the seam through "
        "the plots, and plots that are neighbours on the ground are read from opposite edges of "
        "the map. That is the likely reason it gives "
        f"{_f(size_rate('ari_drawing', 'torus_translation'))} for `ari_drawing`. It is offered for "
        "comparison with the published method (Harms et al. 2001, "
        "doi:10.1111/j.1365-2745.2001.00615.x), not as the default."
    )
    add(
        "- **The rotation null** moves each village's plots as one rigid shape, so close plots "
        "stay close and land in the same stand about as often as they really do. Its rates run "
        f"from {_f(min(size_rate(s, 'rotation') for s in STATISTICS))} to "
        f"{_f(max(size_rate(s, 'rotation') for s in STATISTICS))}"
        + (
            ", and by the declared rule "
            + ", ".join(f"`{s}` ({_f(size_rate(s, 'rotation'))})" for s in too_high["rotation"])
            + " is marked too high. If the rotation null were exactly sound, about "
            f"{len(STATISTICS) * chance_of_too_high(design.n_size):.1f} such marks would be expected "
            "among its twelve cells, so one mark is not surprising but is not nothing either. The "
            "other statistics under this null are within error of 0.05, and this run "
            "cannot say whether that excess is real. The rotation null is not exact in theory: the "
            "placements it may use are crowded round the real one, so the real placement is not "
            "just one more draw, and a small excess of false alarms is possible. The average over the twelve "
            f"({_f(column_mean['rotation'])}) is a little above 0.05 and the same caution applies. "
            "It is reported as measured; more data sets under this null alone would settle it."
            if too_high["rotation"]
            else f", none marked too high; the average over the twelve is {_f(column_mean['rotation'])}."
        )
    )
    add("")

    # ---- power
    add("## 3. Power: how much planted agreement is needed")
    add("")
    add(
        f"{design.n_power} data sets per effect, {design.test_draws} relabellings per test. Each "
        f"cell is the share of data sets with p <= {ALPHA}. A cell in brackets belongs to a "
        "statistic whose false-alarm rate under that null was too high in section 2: its "
        "\"power\" is partly false alarms and must not be read as power."
    )
    add("")
    for null in NULLS:
        add(f"### `{null}`")
        add("")
        body = []
        for s in STATISTICS:
            line = [f"`{s}`"]
            for e in design.power_effects:
                r = _one(
                    rows, experiment="power", effect=e, statistic=s, null=null, quantity="rejection_rate"
                )
                text = _f(r["value"], 2)
                line.append(f"({text})" if verdict[(s, null)] == "too high" else text)
            first = next(
                (
                    e
                    for e in design.power_effects
                    if _one(
                        rows, experiment="power", effect=e, statistic=s, null=null, quantity="rejection_rate"
                    )["value"]
                    >= POWER_TARGET
                ),
                None,
            )
            if verdict[(s, null)] == "too high":
                line.append("not read")
            else:
                line.append(f"{first:g}" if first is not None else "not reached")
            body.append(line)
        L.extend(
            _table(
                [
                    "statistic",
                    *(f"effect {e:g}" for e in design.power_effects),
                    f"smallest effect with power >= {POWER_TARGET:g}",
                ],
                body,
            )
        )
        add("")
    worst = 0.5 / math.sqrt(design.n_power)
    add(
        f"Monte Carlo error: with {design.n_power} data sets the standard error of a power is at "
        f"most {worst:.3f} (at a power of 0.5), so differences between two cells of less than "
        f"about {2.8 * worst:.2f} are not established."
    )
    add("")
    add(
        "For scale, the share of an attribute's variance that the planted map accounts for is "
        + ", ".join(
            f"{synthetic.planted_signal_share(e, params):.0%} at effect {e:g}" for e in design.power_effects
        )
        + ". That share counts the differences between villages. The pair comparison, Mantel, "
        "ANOSIM and PERMANOVA statistics work inside villages, where the village shift plays no "
        "part; inside a village the map's share is "
        + ", ".join(
            f"{e**2 / (e**2 + params.smooth_var + params.nugget_var):.0%} at effect {e:g}"
            for e in design.power_effects
        )
        + "."
    )
    add("")

    # ---- reference polygons
    add("## 4. Reference polygons: segmentation accuracy against the planted polygons")
    add("")
    add(
        f"{design.n_recovery} data sets; in each, the planted map (as polygons) of each of the first "
        f"{design.n_map_groups} villages is the reference and each of the five maps is scored "
        "against it; the figure is the mean over those villages, then over data sets. (These "
        "measures look at maps, not plots, so the plot layout does not matter to them; a few "
        "villages keep the cost down.) Over- and under-segmentation and their combination D are "
        "0 for a perfect match (lower is better). Boundary precision, recall and F are 1 for a "
        f"perfect match (higher is better), with a tolerance of "
        f"{design.boundary_tolerance_pixels * params.pixel_size:g} m (one pixel) and the outer "
        "edge of the raster left out."
    )
    add("")
    body = []
    for measure in REFERENCE_MEASURES:
        line = [f"`{measure}`"]
        for name in MAPS:
            r = _one(rows, experiment="reference_polygons", statistic=measure, map=name)
            line.append(_f(r["value"]))
        body.append(line)
    L.extend(_table(["measure", *MAPS], body))
    add("")

    def ref(measure: str, name: str) -> float:
        return float(_one(rows, experiment="reference_polygons", statistic=measure, map=name)["value"])

    perfect = (
        ref("over", "planted") == 0
        and ref("under", "planted") == 0
        and ref("d", "planted") == 0
        and ref("boundary_f", "planted") == 1
    )
    best = all(ref("d", "planted") < ref("d", m) and ref("boundary_f", "planted") > ref("boundary_f", m) for m in MAPS[1:])
    add("Expectations, declared before the run:")
    add("")
    add(f"1. The planted map scores a perfect match (0, 0, 0 and F = 1): **{_met(perfect)}**.")
    add(f"2. Every other map has a worse D and a worse boundary F: **{_met(best)}**.")
    add(
        f"   Note the unrelated map: boundary F {_f(ref('boundary_f', 'unrelated'))}, D "
        f"{_f(ref('d', 'unrelated'))}. A map that has nothing to do with the reference still gets "
        "these, because with stands this small a good share of any boundary lies within one pixel "
        "of some reference boundary. These measures need that baseline beside them; 0 and 1 are "
        "not the values of a useless map."
    )
    add(
        "3. Splitting shows as over-segmentation and not as under-segmentation: "
        f"**{_met(ref('over', 'split') > 0.2 and ref('under', 'split') < 0.01)}**. Merging shows "
        "as under-segmentation and not as over-segmentation: "
        f"**{_met(ref('under', 'merged') > 0.2 and ref('over', 'merged') < 0.01)}**."
    )
    add("")

    # ---- no reference
    add("## 5. No reference data: likeness inside stands")
    add("")
    add(
        f"{design.n_recovery} data sets; in each of the first {design.n_map_groups} villages a "
        f"raster layer of {design.layer_bands} bands is generated that follows the planted map (stand means of variance "
        f"{design.layer_effect**2:g}, pixel noise of variance 1), and the five maps are scored on "
        "it as one declared set of candidates. Explained variance (`r2`): higher is better. "
        "Area-weighted variance, Moran's I between adjacent stands and the Global Score: lower "
        "is better. `n_segments` is the mean number of stands per village raster."
    )
    add("")
    body = []
    for measure in NO_REFERENCE_MEASURES:
        line = [f"`{measure}`"]
        for name in MAPS:
            r = _one(rows, experiment="no_reference", statistic=measure, map=name)
            line.append(_f(r["value"]))
        body.append(line)
    L.extend(_table(["measure", *MAPS], body))
    add("")

    def nor(measure: str, name: str) -> float:
        return float(_one(rows, experiment="no_reference", statistic=measure, map=name)["value"])

    add("Expectations, declared before the run:")
    add("")
    gs_best = all(nor("global_score", "planted") < nor("global_score", m) for m in MAPS[1:])
    r2_three = all(nor("r2", "planted") > nor("r2", m) for m in ("shifted", "merged", "unrelated"))
    add(f"1. The Global Score is best (lowest) for the planted map: **{_met(gs_best)}**.")
    add(
        "2. Explained variance is higher for the planted map than for the shifted, merged and "
        f"unrelated maps: **{_met(r2_three)}**."
    )
    split_r2 = nor("r2", "split") >= nor("r2", "planted")
    pixel_unrelated = nor("pixel_ari_with_planted", "unrelated")
    add(
        "3. Explained variance does NOT prefer the planted map to the split one (cutting stands "
        "in two can only raise it, because it rises with the number of stands whatever the "
        f"layer): **{_met(split_r2)}**. This is a property of the measure and the reason it is "
        "never read without the number of stands. Moran's I is what catches the split: the two "
        f"halves of a stand are alike ({_f(nor('morans_i', 'split'))} against "
        f"{_f(nor('morans_i', 'planted'))} for the planted map)."
    )
    add(
        "4. `pixel_ari_with_planted` is the adjusted Rand index between each map and the planted "
        "map, pixel against pixel. It is 1 for the planted map against itself: "
        f"**{_met(nor('pixel_ari_with_planted', 'planted') == 1.0)}**. Note the unrelated map: "
        f"{_f(pixel_unrelated)}, not 0. Two maps of compact stands of the same size share many "
        "pairs of neighbouring pixels by geometry alone, and the index's allowance for chance "
        "knows nothing about geometry. When two stand maps are compared pixel by pixel with this "
        "index, the value to beat is the one an unrelated map of the same grain gets, not 0."
    )
    add("")

    # ---- limits
    add("## What this does and does not show")
    add("")
    bad_identity = identity_failures(results)
    add(
        "- **Checked in every data set**: each null model starts from exactly the stand and type "
        "labels the statistic was observed on. "
        + (
            "This held throughout."
            if bad_identity == 0
            else f"**This FAILED in {bad_identity} case(s): the nulls and the statistics read different labels.**"
        )
    )
    add(
        "- **Nothing was tuned.** The generator, its parameters, the distance bands, the numbers "
        "of relabellings and the rules used to read the tables (too high, recovered, power of "
        f"{POWER_TARGET:g}) were fixed before the run. Where an expectation is marked NOT met, "
        "that is reported as a finding; the generator was not changed to make it go away."
    )
    add(
        "- **One fault in the generator was corrected, before the pilot and the full run.** In "
        "the first draft the planted map and the \"unrelated\" map of a village were built on the "
        "same grid of seed points and differed only by the random jitter of each point, so the "
        "unrelated map was not unrelated. It was noticed while writing a unit test that compares "
        "the two rasters. Each map's "
        "grid now sits at its own random place. The change was made because the map did not "
        "mean what its name says, not because of any score, and the small trial run made before "
        "it is used nowhere in this file."
    )
    add(
        "- **One synthetic world.** The rates hold for this layout, this stand size, this "
        "smoothness and this mix of village, smooth and noise variance. A real site with stands "
        "much larger or smaller than the plot spacing, or smoother field data, can behave "
        "differently. Sensitivity to those parameters was not run."
    )
    add(
        "- **The village forest is generous here.** It is the hull of the plots widened by "
        f"{params.region_buffer:g} m, and every pixel in it has a stand. A real village forest "
        "can be thin or full of holes, which leaves the rotation null few places to move the "
        "plots to. How the rotation null behaves then was not tested."
    )
    add(
        f"- **{design.test_draws} relabellings** per test in the size and power experiments. That "
        "puts 0.05 exactly on a possible p-value (the 5 largest of 100), so no rate here is off "
        "because of rounding; whether a test is sound still depends on its null model. A real "
        "analysis would use more, and its power would be slightly higher."
    )
    add(
        "- **Not validated here**: Holm's correction across several tests; the Spearman form of "
        "the Mantel statistics; ANOSIM with equal village weights; the all-pairs Mantel test "
        "(without villages); polygon stand maps under the rotation null (rasters were used); "
        "plots that fall outside any stand; missing measurements. These are covered by unit "
        "tests with known answers, not by this study."
    )
    add(
        "- **Not a result about any real site.** No metric was run on real data, and nothing "
        "here says whether a real map agrees with real field data."
    )
    add("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def write_outputs(results: dict[str, Any], out_dir: Path, command: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = summarise(results)
    csv_path = out_dir / "synthetic_validation.csv"
    md_path = out_dir / "synthetic_validation.md"
    write_csv(rows, csv_path)
    md_path.write_text(render_markdown(results, rows, command))
    return csv_path, md_path


def write_run_record(out_dir: Path, result_files: Sequence[Path], argv: Sequence[str],
                     git: dict[str, Any]) -> Path:
    """`synthetic_validation_run.json` beside the results: what made them (review C37)."""
    import datetime
    import shlex

    from fmu.utils.provenance import environment_state

    path = out_dir / "synthetic_validation_run.json"
    command = ["scripts/evaluation_synthetic_validation.py", *argv]
    path.write_text(json.dumps({
        "result_files": [p.name for p in result_files],
        "command_line": "python " + " ".join(shlex.quote(a) for a in command),
        "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "git": git,
        "environment": environment_state(),
    }, indent=1) + "\n")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    from fmu.utils.provenance import git_state

    # Which code ran: read before the run, which takes long enough for the tree to change.
    started = {k: v for k, v in git_state().items() if k != "root"}
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--quick", action="store_true", help="a small run, to check the script")
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="multiply every number of data sets by this common factor (0 to 1)",
    )
    parser.add_argument("--seed", type=int, default=ROOT_SEED, help="root seed")
    parser.add_argument("--out-dir", type=Path, default=Path("docs/evaluation"))
    parser.add_argument("--jobs", type=int, default=1, help="processes; does not change results")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="keep finished data sets here so a cut-off run can continue; does not change results",
    )
    args = parser.parse_args(argv)
    design = scaled(QUICK if args.quick else FULL, args.scale)
    command = command_line(design, args.scale, args.seed)
    print(f"design: {design}", file=sys.stderr)
    results = run_validation(
        design, seed=args.seed, jobs=args.jobs, cache_dir=args.cache_dir, log=sys.stderr
    )
    csv_path, md_path = write_outputs(results, args.out_dir, command)
    record = write_run_record(args.out_dir, (csv_path, md_path),
                              list(sys.argv[1:] if argv is None else argv), started)
    print(f"wrote {csv_path} and {md_path}, and their run record {record}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
