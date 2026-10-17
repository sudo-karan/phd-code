"""The k elbow, as a cached step (round 9, 17 Oct 2026).

What it computes. k-means on the rows the clustering stage fits its stand types on
(one row per stand: the scaled features k-means sees), for every k from
`k_elbow.k_min` to `k_elbow.k_max`, and the within-cluster sum of squares
(inertia) of each fit. The elbow is the k farthest from the chord joining the
first and the last point. Method, range and fit are those of the elbows run so
far (odisha_script/odisha_phase3_2_stand_k_elbow.py, scripts/remerge_demo_set.py):
scikit-learn's KMeans, seed 42, 25 starts, k from 2 to 12, and the same `knee`.

Why a cached step of its own. What determines the elbow is the set of rows and
the sweep's settings, not the k a config fits. Its cache key
(fmu.utils.caching.STEP_SETTINGS["k_elbow"]) covers the clustering settings but
`k`, the steps upstream of clustering, and the k_elbow block, so a
configuration's elbow is computed once and read back by every later run of it,
whatever its k. It is cached in the per-step layout only: under the legacy one
its key would be the config's fingerprint, which leaves the k_elbow block out,
so the stage refuses to run there.

It is in no default run and nothing reads it: k stays as each config sets it.
`fmu.pipeline.default_stage_names(config, through="k_elbow")` gives a run that
ends with it.

The rows. The clustering stage's `feature_stack`, masked to the habitat mask, one
point per unit (`_sample_one_point_per_unit`, with clustering.seed as the
clustering stage calls it), and, with clustering.fit_excludes_stands_below_min_area
on, without the stands the merge left below merge.min_area_ha
(`_leave_out_of_fit`): the rows k-means is trained on. They are read back (a few
hundred to a few thousand rows, a page at a time) and the sweep runs here.

Output. `k_elbow`: a FeatureCollection with one feature per k and no geometry,
with properties k, inertia, n_rows, n_bands, elbow_k (the same on every feature;
null if there are too few rows for three values of k) and is_elbow. Read it with
`read_k_elbow`.
"""

from __future__ import annotations

from typing import Any

import ee
import numpy as np

from fmu.config import Config
from fmu.stages.base import PipelineContext, Stage, StageResult, register_stage
from fmu.stages.clustering import (
    _leave_out_of_fit,
    _sample_one_point_per_unit,
    _stands_below_min_area,
)
from fmu.utils.caching import LEGACY_LAYOUT, active_layout
from fmu.utils.gee import safe_call, safe_get_info
from fmu.utils.logging import get_logger

log = get_logger(__name__)

# Rows read per request: Earth Engine stops a request at 5,000 elements.
_PAGE = 2500
# The merge outputs that say which stands are below merge.min_area_ha.
_BELOW_MIN_AREA_INPUTS: frozenset[str] = frozenset({"stand_provenance", "stand_attributes"})


@register_stage("k_elbow")
class KElbowStage(Stage):
    name = "k_elbow"
    # The unit labels (stands or superpixels) and, with the fit leaving out the
    # stands below the minimum, the merge's records of them, are checked in
    # validate(): which exist depends on the config.
    required_inputs = {"roi", "habitat_mask", "feature_stack"}
    produces = {"k_elbow"}
    cacheable_outputs = {"k_elbow"}
    table_outputs = {"k_elbow"}

    def validate(self, ctx: PipelineContext, config: Config) -> None:
        needed = set(self.required_inputs) | {config.unit_label_key()}
        if config.clustering.fit_excludes_stands_below_min_area:
            needed |= _BELOW_MIN_AREA_INPUTS
        missing = needed - ctx.keys()
        if missing:
            raise KeyError(
                f"{self.name}: missing required context inputs: {sorted(missing)}. "
                f"Context has: {sorted(ctx.keys())}"
            )

    @safe_call("k elbow")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        if active_layout(config) == LEGACY_LAYOUT:
            raise ValueError(
                "k_elbow is cached in the per-step layout only: in the legacy layout "
                "its key would be the config's fingerprint, which leaves the k_elbow "
                "settings out. Run it on a config whose cache is in the per-step "
                "layout, or with use_cache=False."
            )
        params = config.k_elbow
        rows, bands = training_rows(ctx, config)
        sweep = elbow_sweep(
            rows, k_min=params.k_min, k_max=params.k_max, seed=params.seed, n_init=params.n_init
        )
        log.info(
            "  k elbow: %d row(s) x %d band(s), k %d to %d: elbow at k = %s",
            sweep["n_rows"], len(bands), params.k_min, params.k_max, sweep["elbow_k"],
        )
        table = ee.FeatureCollection(
            [ee.Feature(None, props) for props in elbow_table(sweep, n_bands=len(bands))]
        )
        return StageResult(
            outputs={"k_elbow": table},
            metadata={
                "n_rows": sweep["n_rows"],
                "n_bands": len(bands),
                "bands": bands,
                "ks": sweep["ks"],
                "inertia": sweep["inertia"],
                "elbow_k": sweep["elbow_k"],
                "k_min": params.k_min,
                "k_max": params.k_max,
                "seed": params.seed,
                "n_init": params.n_init,
            },
        )


def training_rows(ctx: PipelineContext, config: Config) -> tuple[np.ndarray, list[str]]:
    """The clustering stage's k-means training rows, read back: (rows, band names).

    The same sample calls the clustering stage makes (`_train_and_apply_kmeans`),
    on its cached scaled feature image.
    """
    feature_stack: ee.Image = ctx.get("feature_stack")
    unit_key = config.unit_label_key()
    unit_labels: ee.Image = ctx.get(unit_key)
    roi = ctx.get("roi")
    scale = config.export.analysis_scale_m
    seed = config.clustering.seed
    bands = [str(b) for b in safe_get_info(feature_stack.bandNames(), context="k elbow bands")]
    training_input = feature_stack.updateMask(ctx.get("habitat_mask"))
    sample = _sample_one_point_per_unit(
        training_input, unit_labels, roi, scale, seed=seed,
        context=f"k elbow rows per {unit_key}",
    )
    if config.clustering.fit_excludes_stands_below_min_area:
        below_min = _stands_below_min_area(ctx.get("stand_provenance"), ctx.get("stand_attributes"))
        n_rows = int(safe_get_info(sample.size(), context="k elbow row count"))
        sample, _n_fit, _report = _leave_out_of_fit(
            training_input=training_input,
            training_sample=sample,
            n_rows=n_rows,
            unit_labels=unit_labels,
            roi=roi,
            scale=scale,
            seed=seed,
            unit_key=unit_key,
            below_min=below_min,
        )
    features = _read_rows(sample, context="k elbow rows")
    return rows_matrix(features, bands), bands


def _read_rows(fc: ee.FeatureCollection, *, context: str) -> list[dict[str, Any]]:
    """Every feature of a collection, a page at a time."""
    n = int(safe_get_info(fc.size(), context=f"{context}: count"))
    if n <= _PAGE:
        return list(safe_get_info(fc, context=context)["features"]) if n else []
    out: list[dict[str, Any]] = []
    for start in range(0, n, _PAGE):
        page = ee.FeatureCollection(fc.toList(_PAGE, start))
        out.extend(safe_get_info(page, context=f"{context}: {start} to {start + _PAGE}")["features"])
    return out


# ---------------------------------------------------------------------
# Pure helpers (no Earth Engine): tests/test_k_elbow.py
# ---------------------------------------------------------------------


def rows_matrix(features: list[dict[str, Any]], bands: list[str]) -> np.ndarray:
    """The rows as a matrix, one column per band in `bands`' order.

    A row without a value in a band cannot come from the sample (it drops nulls),
    so one is an error rather than something to fill.
    """
    out = np.empty((len(features), len(bands)), dtype=float)
    for i, f in enumerate(features):
        props = f.get("properties") or {}
        for j, b in enumerate(bands):
            value = props.get(b)
            if value is None:
                raise ValueError(f"k elbow: row {i} has no value in band {b!r}")
            out[i, j] = float(value)
    return out


def knee(ks: list[int], inertia: list[float]) -> int | None:
    """The k at the elbow: the point farthest from the chord between the first and last.

    The definition of odisha_script/odisha_phase3_2_stand_k_elbow.py and
    scripts/remerge_demo_set.py, kept identical. None when the inertia does not
    change over the range (no chord to measure from).
    """
    x, y = np.array(ks, float), np.array(inertia, float)
    if len(x) < 3 or x.max() == x.min() or y.max() == y.min():
        return None
    x = (x - x.min()) / (x.max() - x.min())
    y = (y - y.min()) / (y.max() - y.min())
    num = np.abs((y[-1] - y[0]) * x - (x[-1] - x[0]) * y + x[-1] * y[0] - y[-1] * x[0])
    return int(ks[int(np.argmax(num / np.hypot(y[-1] - y[0], x[-1] - x[0])))])


def elbow_sweep(
    rows: np.ndarray, *, k_min: int, k_max: int, seed: int, n_init: int
) -> dict[str, Any]:
    """k-means for k = k_min..k_max (each k below the number of rows), and the elbow."""
    from sklearn.cluster import KMeans

    ks: list[int] = []
    inertia: list[float] = []
    for k in range(k_min, k_max + 1):
        if k >= len(rows):
            break
        ks.append(k)
        fit = KMeans(n_clusters=k, random_state=seed, n_init=n_init).fit(rows)
        inertia.append(round(float(fit.inertia_), 6))
    return {"n_rows": int(len(rows)), "ks": ks, "inertia": inertia, "elbow_k": knee(ks, inertia)}


def elbow_table(sweep: dict[str, Any], *, n_bands: int) -> list[dict[str, Any]]:
    """The properties of the output's features, one per k."""
    return [
        {
            "k": k,
            "inertia": v,
            "n_rows": sweep["n_rows"],
            "n_bands": n_bands,
            "elbow_k": sweep["elbow_k"],
            "is_elbow": int(k == sweep["elbow_k"]),
        }
        for k, v in zip(sweep["ks"], sweep["inertia"], strict=True)
    ]


def read_k_elbow(table: ee.FeatureCollection) -> dict[str, Any]:
    """A k_elbow output (just computed, or read from the cache) as plain numbers."""
    features = safe_get_info(table.sort("k"), context="k elbow table")["features"]
    props = [f["properties"] for f in features]
    if not props:
        return {"n_rows": 0, "ks": [], "inertia": [], "elbow_k": None}
    return {
        "n_rows": int(props[0]["n_rows"]),
        "n_bands": int(props[0]["n_bands"]),
        "ks": [int(p["k"]) for p in props],
        "inertia": [float(p["inertia"]) for p in props],
        "elbow_k": props[0].get("elbow_k"),
    }
