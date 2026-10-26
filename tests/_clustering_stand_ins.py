"""Stand-ins for what the clustering stage asks of Earth Engine, for the offline tests.

`answers()` gives a `safe_get_info` that answers every request `ClusteringStage.run()`
makes by the context it names, the same way every time: the band lists, the skewness and
minimum of each band and its column of values (whose exact quartiles the scaling takes; until
review B16 it asked Earth Engine's percentiles), the training row count and the label
histograms of `_count_units`. Each request is also written into the call log, so a recording shows what
was asked as well as what was built. `run_stage()` runs `ClusteringStage().run()` of a given
copy of the stage module on the stand-ins of tests/_ee_recorder.py. (Until round 13 the stage
also checked the labels with `assert_components_fit` and measured the unit extents for
reduceConnectedComponents; review B14 took both out, with their stand-ins here.)

tests/test_clustering_off_golden.py records the default path with these, and
tests/test_clustering_fit_excludes_stands.py runs the path with
clustering.fit_excludes_stands_below_min_area on. The answers are made up. They are chosen
to reach every branch of the default path: bands the stage drops, cyclic bands, skewed
bands (one with a negative skew), a band with no spread, and units inside the habitat mask
with no training row.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any

from _ee_recorder import Call, Rec

# The four hand-crafted feature images together, as ee.Image.cat stacks them: the bands of
# a baseline run (odisha_script/odisha_phase1_8_results.txt) and the three the stage drops.
HANDCRAFTED_BANDS = (
    "ndvi_mean",
    "ndvi_amplitude_annual",
    "ndvi_phase_annual",
    "ndvi_trend",
    "ndvi_obs_count",
    "ndvi_residual_variance",
    "vv_p10",
    "vh_p10",
    "vv_p50",
    "vh_p50",
    "vv_p90",
    "vh_p90",
    "vv_iqr",
    "vh_iqr",
    "vv_minus_vh_median",
    "canopy_height",
    "canopy_height_std",
    "canopy_height_max",
    "elevation",
    "slope",
    "aspect",
    "distance_to_water",
    "annual_rainfall",
)
_DROPPED = ("ndvi_obs_count", "ndvi_residual_variance", "annual_rainfall")
# What the stage keeps of them ("raw clustering bands") ...
HANDCRAFTED_KEPT = tuple(b for b in HANDCRAFTED_BANDS if b not in _DROPPED)
# ... and the same once the two cyclic bands are sin/cos pairs, at the end.
HANDCRAFTED_DECOMPOSED = (
    *(b for b in HANDCRAFTED_KEPT if b not in ("ndvi_phase_annual", "aspect")),
    "ndvi_phase_annual_sin",
    "ndvi_phase_annual_cos",
    "aspect_sin",
    "aspect_cos",
)
EMBEDDING_BANDS = tuple(f"A{i:02d}" for i in range(64))

# Bands whose |skew| is above the threshold of 1.0; every other band has a skew of 0.3.
SKEW = {"vh_iqr": 2.5, "canopy_height_max": 1.6, "slope": -1.8, "A03": 1.2, "A10": -2.0, "A42": 3.1}
# Bands with no spread, which the scaling drops.
NO_SPREAD = frozenset({"distance_to_water", "A63"})

UNITS_IN_ROI = 25
UNITS_IN_HABITAT = 22
# Units with a habitat pixel whose centre is inside the ROI (round 14, round 13's question 35):
# one of the 22 has none, so it can have no row; the other units without a row (one) have a
# band gap.
UNITS_WITH_A_CENTRE = 21
TRAINING_ROWS = 20  # so two units inside the habitat mask have no row: one per cause

# The two requests that only the path with the setting on makes.
FIT_ROW_COUNT = "k-means training row count without the stands below the minimum"
LEFT_OUT_ROWS = "stands below the minimum with a training row"
# The one request of the path with clustering.fit_outside_earth_engine on (round 14): the
# table of units, a row per unit with its label first. Its labels come in this order, not
# sorted, so a test can see the stage sort them.
TABLE_OF_UNITS = "the table of units"
TABLE_LABELS = (7, 3, 19, 0, 12, 5, 16, 1, 9, 14, 2, 18, 6, 11, 4, 17, 8, 13, 10, 15)


def table_value(band: str, label: int) -> float:
    """The made-up mean of a unit in a band: skewed where SKEW says so, flat where NO_SPREAD
    does, in [-1, 1] for an angle's sin and cos."""
    import math

    x = (label * 37 + sum(map(ord, band)) * 11) % 101 / 100.0  # 0.00 .. 1.00, spread
    if band in NO_SPREAD:
        return 5.0
    if band.endswith(("_sin", "_cos")):
        return math.sin(6.283185307179586 * x) if band.endswith("_sin") else math.cos(6.283185307179586 * x)
    if SKEW.get(band, 0.0) > 1.0:
        return math.exp(4.0 * x)  # a long right tail
    if SKEW.get(band, 0.0) < -1.0:
        return -math.exp(4.0 * x)  # a long left tail
    return x


def table_rows(bands: tuple[str, ...] | list[str]) -> list[list[float]]:
    """The table of units the stand-ins answer: [label, value of each band] per unit."""
    return [[float(lbl), *(table_value(b, lbl) for b in bands)] for lbl in TABLE_LABELS]


def answers(
    config: Any,
    log: list,
    *,
    fit_rows: int | None = None,
    left_out_rows: list[Any] | None = None,
) -> Callable[..., Any]:
    """A `safe_get_info` for `config`. `fit_rows` and `left_out_rows` answer the two
    requests of the path with the setting on; any request not listed here fails."""
    embedding = config.clustering.feature_source == "embedding"
    raw = EMBEDDING_BANDS if embedding else HANDCRAFTED_KEPT
    decomposed = EMBEDDING_BANDS if embedding else HANDCRAFTED_DECOMPOSED
    unit_band = config.unit_label_key()

    def answer(context: str) -> Any:
        if context == "combined feature bands":
            return list(HANDCRAFTED_BANDS)
        if context in ("raw clustering bands", "bands for cyclic check"):
            return list(raw)
        if context in ("post-decomposition bands", "bands"):
            return list(decomposed)
        if context.startswith("skew of "):
            return {"skew": SKEW.get(context.removeprefix("skew of "), 0.3)}
        if context.startswith("min of "):
            return {"min": -1.5}
        if context.startswith("values of "):
            if context.removeprefix("values of ") in NO_SPREAD:
                return [5.0] * 5
            return [0.0, 0.25, 0.5, 1.0, 1.5]  # quartiles 0.25, 0.5 and 1.0
        if context.startswith("mean/stdDev of "):
            flat = context.removeprefix("mean/stdDev of ") in NO_SPREAD
            return {"mean": 0.5, "stdDev": 0.0 if flat else 0.4}
        if context == "k-means training row count":
            return TRAINING_ROWS
        if context.endswith(" band name"):
            return [unit_band]
        if context.endswith(" in ROI label histogram"):
            return {unit_band: {str(i): 10.0 for i in range(UNITS_IN_ROI)}}
        if context.endswith(" in habitat label histogram"):
            return {unit_band: {str(i): 10.0 for i in range(UNITS_IN_HABITAT)}}
        if context.endswith(" in habitat by pixel centre label histogram"):
            # Unweighted, so it also counts the masked pixels, under "null" (adjacency.py).
            labels = {str(i): 10.0 for i in range(UNITS_WITH_A_CENTRE)}
            return {unit_band: {**labels, "null": 37.0}}
        if context == FIT_ROW_COUNT and fit_rows is not None:
            return fit_rows
        if context == LEFT_OUT_ROWS and left_out_rows is not None:
            return list(left_out_rows)
        if context == TABLE_OF_UNITS:
            return {"list": table_rows(decomposed)}
        raise AssertionError(f"unexpected request: {context}")

    def get_info(obj: Any, context: str = "") -> Any:
        log.append(Call("getInfo", None, None, (obj,), {"context": context}, None))
        return answer(context)

    return get_info


def inputs(config: Any) -> set[str]:
    """The context keys `run()` reads with the setting off."""
    if config.clustering.feature_source == "embedding":
        features = {"embedding_features"}
    else:
        features = {"optical_features", "radar_features", "structure_features", "static_features"}
    return {"roi", "habitat_mask", config.unit_label_key()} | features


def run_stage(
    module: ModuleType,
    config: Any,
    *,
    merge_outputs: dict[str, Any] | None = None,
    fit_rows: int | None = None,
    left_out_rows: list[Any] | None = None,
) -> tuple[Any, list, Any]:
    """`module.ClusteringStage().run()` on stand-ins: (result, call log, context).

    Every input in `inputs(config)` is a recorder named by its key; `merge_outputs`
    (stand_provenance and stand_attributes, for the setting on) go in as given. The
    module's `ee` and `safe_get_info` are swapped for the run and put back after it, so
    this works on another copy of the module as well.
    """
    from fmu.stages.base import PipelineContext

    log: list = []
    names = ("ee", "safe_get_info")
    saved = {name: getattr(module, name) for name in names}
    try:
        module.ee = Rec("ee", log)  # type: ignore[attr-defined]
        module.safe_get_info = answers(  # type: ignore[attr-defined]
            config, log, fit_rows=fit_rows, left_out_rows=left_out_rows
        )
        ctx = PipelineContext()
        for key in sorted(inputs(config)):
            ctx.set(key, Rec(key, log))
        for key, value in (merge_outputs or {}).items():
            ctx.set(key, value)
        result = module.ClusteringStage().run(ctx, config)
    finally:
        for name, value in saved.items():
            setattr(module, name, value)
    return result, log, ctx
