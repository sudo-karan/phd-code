"""features_optical.mean_over_window: `<index>_mean` is the fitted curve's mean over the window.

Round 14, Task 2, item 3 (review C9; round 13's question 31, answered (c)); register entry
spec-optical-mean-over-the-window. With the setting on, the band is the mean of the fitted
curve a + b cos(2 pi t) + c sin(2 pi t) [+ d cos(4 pi t) + e sin(4 pi t)] [+ f t] over the
dates window [start, end + 1 day), computed analytically, whatever `time_reference` is; for a
window of a whole number of years it is a + f x the window's middle. Off, the band is the
intercept a, as before (tests/test_features_optical_off_golden.py). The weights are checked
here against a numerical integral of the curve, and the stage's calls on the recorder of
tests/_ee_recorder.py.
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import numpy as np
import pytest
import yaml
from pydantic import ValidationError

import fmu.stages.features_optical as optical
from _ee_recorder import Rec, calls, made_by
from fmu.config import Config, load_config
from fmu.stages.base import PipelineContext
from fmu.utils.caching import config_fingerprint, step_keys

REPO = Path(__file__).resolve().parent.parent
BASELINE = REPO / "configs" / "sanjay_van_baseline.yaml"
DUAL = REPO / "configs" / "sanjay_van_nirv_dual.yaml"


def test_the_year_is_earth_engines():
    """ee.Date.difference(..., "year") on Earth Engine, 26 Oct 2026 (read-only)."""
    ref = date(2017, 1, 1)
    assert optical.years_since(date(2023, 1, 1), ref) == pytest.approx(5.99875425231182, rel=1e-14)
    assert optical.years_since(date(2018, 1, 1), ref) == pytest.approx(0.9993360575508052, rel=1e-14)
    assert optical.years_since(date(2021, 1, 1), date(2020, 1, 1)) == pytest.approx(
        1.0020739645577939, rel=1e-14
    )


def test_the_window_runs_from_its_first_day_to_the_day_after_its_last():
    t0, t1 = optical.window_years(date(2017, 1, 1), date(2022, 12, 31), date(2017, 1, 1))
    assert t0 == 0.0 and t1 == pytest.approx(5.99875425231182, rel=1e-14)


def _curve(t, coef):
    a, b, c, d, e, f = coef
    w = 2 * math.pi
    return a + b * np.cos(w * t) + c * np.sin(w * t) + d * np.cos(2 * w * t) + e * np.sin(2 * w * t) + f * t


def _weighted(weights, coef):
    a, b, c, d, e, f = coef
    named = {"constant": a, "cos_annual": b, "sin_annual": c, "cos_semi": d, "sin_semi": e, "t": f}
    return sum(named[k] * w for k, w in weights.items())


@pytest.mark.parametrize("harmonic_mode", ["single", "dual"])
@pytest.mark.parametrize("include_trend", [True, False])
@pytest.mark.parametrize("window", [(0.0, 5.99875425231182), (0.37, 2.81), (-1.2, 4.0)])
def test_the_weights_give_the_mean_of_the_fitted_curve_over_the_window(harmonic_mode, include_trend, window):
    rng = np.random.default_rng(3)
    coef = list(rng.normal(0, 1, 6))
    if harmonic_mode == "single":
        coef[3] = coef[4] = 0.0
    if not include_trend:
        coef[5] = 0.0
    t0, t1 = window
    weights = optical.window_mean_weights(t0, t1, harmonic_mode=harmonic_mode, include_trend=include_trend)
    t = np.linspace(t0, t1, 400_001)
    y = _curve(t, coef)
    numerical = float(np.sum((y[1:] + y[:-1]) / 2 * np.diff(t)) / (t1 - t0))
    assert _weighted(weights, coef) == pytest.approx(numerical, abs=1e-9)
    assert ("cos_semi" in weights) == (harmonic_mode == "dual")
    assert ("t" in weights) == include_trend


def test_for_a_whole_number_of_years_it_is_the_intercept_plus_the_trend_at_the_middle():
    w = optical.window_mean_weights(0.0, 6.0, harmonic_mode="dual", include_trend=True)
    assert w["t"] == 3.0
    for k in ("cos_annual", "sin_annual", "cos_semi", "sin_semi"):
        assert abs(w[k]) < 1e-15, k


def test_the_mean_does_not_depend_on_the_reference_date():
    """Moving the reference by D years gives a' = a + f D and the harmonics' coefficients
    rotated, and t shifted by -D: the window mean is the same."""
    rng = np.random.default_rng(9)
    a, b, c, f = rng.normal(0, 1, 4)
    start, end = date(2017, 1, 1), date(2022, 12, 31)
    means = []
    for ref in (date(2017, 1, 1), date(2019, 3, 15), date(2020, 1, 1)):
        d = optical.years_since(ref, date(2017, 1, 1))  # the shift, in years
        w = 2 * math.pi
        # The same curve written about the new reference: y(t') with t' = t - d.
        a2 = a + f * d
        b2 = b * math.cos(w * d) + c * math.sin(w * d)
        c2 = -b * math.sin(w * d) + c * math.cos(w * d)
        t0, t1 = optical.window_years(start, end, ref)
        weights = optical.window_mean_weights(t0, t1, harmonic_mode="single", include_trend=True)
        means.append(_weighted(weights, [a2, b2, c2, 0.0, 0.0, f]))
    assert means[1] == pytest.approx(means[0], abs=1e-12)
    assert means[2] == pytest.approx(means[0], abs=1e-12)


def _config(path: Path, **optical_settings) -> Config:
    raw = yaml.safe_load(path.read_text())
    raw["features_optical"] = {**raw.get("features_optical", {}), **optical_settings}
    return Config.model_validate(raw)


def _run(config: Config):
    log: list = []
    real_ee, real_info = optical.ee, optical.safe_get_info
    try:
        optical.ee = Rec("ee", log)
        optical.safe_get_info = lambda obj, context="": ["x"]
        ctx = PipelineContext()
        ctx.set("s2_collection", Rec("s2_collection", log))
        ctx.set("roi", Rec("roi", log))
        result = optical.FeaturesOpticalStage().run(ctx, config)
    finally:
        optical.ee, optical.safe_get_info = real_ee, real_info
    return result, log


def test_off_by_default():
    assert load_config(BASELINE).features_optical.mean_over_window is False


@pytest.mark.parametrize("path", [BASELINE, DUAL], ids=["ndvi_single", "nirv_dual"])
def test_on_the_mean_band_is_the_weighted_sum_of_the_coefficients(path):
    config = _config(path, mean_over_window=True)
    result, log = _run(config)
    params = config.features_optical
    t0, t1 = optical.window_years(config.dates.phenology.start, config.dates.phenology.end,
                                  params.time_reference)
    weights = optical.window_mean_weights(
        t0, t1, harmonic_mode=params.harmonic_mode, include_trend=params.include_trend
    )
    (named,) = [c for c in calls(log, ".rename") if c.args == (f"{params.index}_mean",)]
    # rename(sum) <- add(...) chain: walk it back, collecting each term's band and weight.
    terms = {}
    node = made_by(log, named.owner)
    while node.attr == "add":
        (term,) = node.args
        mult = made_by(log, term)
        assert mult.attr == "multiply"
        band = made_by(log, mult.owner)
        assert band.attr == "select"
        terms[band.args[0]] = mult.args[0]
        node = made_by(log, node.owner)
    assert node.attr == "select" and node.args == ("constant",)
    assert terms == {k: pytest.approx(v, rel=1e-15) for k, v in weights.items() if k != "constant"}
    assert result.metadata["mean_over_window"] is True
    assert result.metadata["mean_window"] == (
        f"{config.dates.phenology.start.isoformat()} to {config.dates.phenology.end.isoformat()}"
    )


def test_off_no_key_moves_and_on_the_optical_key_and_those_after_it_move(monkeypatch):
    monkeypatch.chdir(REPO)
    base = load_config(BASELINE)
    written = _config(BASELINE, mean_over_window=False)
    on = _config(BASELINE, mean_over_window=True)
    assert step_keys(written) == step_keys(base)
    assert config_fingerprint(written) == config_fingerprint(base)
    keys, keys_on = step_keys(base), step_keys(on)
    moved = {s for s in keys if keys[s] != keys_on[s]}
    assert "features_optical" in moved and "data_load" not in moved and "masking" not in moved
    assert config_fingerprint(on) != config_fingerprint(base)


def test_an_unknown_setting_is_still_refused():
    with pytest.raises(ValidationError):
        _config(BASELINE, mean_over_windows=True)
