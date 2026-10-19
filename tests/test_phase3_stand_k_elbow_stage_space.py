"""odisha_script/odisha_phase3_2_stand_k_elbow.py: the clustering stage's space (review A7).

The script's own space (--space script), which wrote the two committed elbow files, departs from
the clustering stage in five ways (review A7, 19 Oct 2026). --space stage rebuilds the stage's
rows from a stand layer: the stage's bands, one row per typed stand, the stage's log rule and
offset over those rows, the bands with no spread dropped; then the elbow's two geometries, (i)
(x - median) / IQR and (ii) each band min-max normalised over the fit rows (review A2). The tests
of the stage space fail on the code before it, which had only the script's own space; the test
of the script's own space shows the departures and passes on both.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "odisha_script" / "odisha_phase3_2_stand_k_elbow.py"


def _script():
    spec = importlib.util.spec_from_file_location("odisha_phase3_2_stand_k_elbow", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


E = _script()

# Polygons 1 to 15. Stand 114 is in two pieces, polygons 14 (40 px) and 15 (300 px); polygons
# 12 and 13 have no type. The stage's rows are therefore polygons 1 to 11 and 15.
STAND_IDS = list(range(1, 16))
STAGE_ROWS = [*range(1, 12), 15]
VV_P10 = [-10.0, -10.2, -9.8, -10.1, -9.9, -10.3, -9.7, -10.05, -9.95, -30.0, -10.15, -12.0, -40.0, -9.0, -9.85]
CANOPY_STD = [0.5, 0.6, 0.55, 0.7, 0.45, 0.65, 0.5, 0.6, 9.0, 0.52, 0.58, 0.4, 0.3, 4.0, 0.62]
NDVI_MEAN = [0.30, 0.40, 0.50, 0.60, 0.35, 0.45, 0.55, 0.65, 0.42, 0.48, 0.52, 0.2, 0.9, 0.1, 0.38]
VH_IQR = [0, 0, 0, 0, 0, 0, 0, 0, 0, 2.5, 3.0, 1.0, 1.5, 2.0, 0]
SLOPE = [3.0, 5.0, 7.5, 2.0, 9.0, 4.0, 6.0, 8.0, 1.5, 5.5, 6.5, 12.0, 0.5, 3.5, 4.5]
ASPECT = [10.0, 350.0, 90.0, 180.0, 270.0, 45.0, 135.0, 225.0, 315.0, 200.0, 160.0, 5.0, 300.0, 100.0, 250.0]
PHASE = [-3.0, -2.5, -2.0, -1.0, 0.0, 1.0, 2.0, 2.5, 3.0, 0.5, -0.5, 1.5, -1.5, 2.8, 1.2]
# Over the twelve rows its skewness is 1.047 by G1 and 0.911 by g1.
TREND = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 0.5, 0.5, 0.5, 1.7]


def _layer(below_min: bool = False) -> pd.DataFrame:
    n = len(STAND_IDS)
    layer = pd.DataFrame({
        "stand_id": STAND_IDS,
        "stand_lbl": [100 + i for i in range(1, 14)] + [114, 114],
        "cluster_id": [i % 3 for i in range(11)] + [None, None, 1, 1],
        "n_pixels": [100 + i for i in range(13)] + [40, 300],
        "area_ha": [1.0] * n, "perim_m": [400.0] * n,
        "centroid_lat": [21.0] * n, "centroid_lon": [85.0] * n,
        "annual_rainfall": [1400.0 + 10 * i for i in range(n)],
        "ndvi_residual_variance": [0.01 * (i + 1) for i in range(n)],
        "distance_to_water": [463409.5] * n,
        "aspect": ASPECT, "ndvi_phase_annual": PHASE, "vv_p10": VV_P10,
        "canopy_height_std": CANOPY_STD, "ndvi_mean": NDVI_MEAN, "vh_iqr": VH_IQR, "slope": SLOPE,
        "ndvi_trend": TREND,
    })
    if below_min:
        layer["below_min"] = [0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
        layer["below_why"] = ["" if b == 0 else "area_blocked" for b in layer["below_min"]]
    return layer


def _stage_values(band: str) -> np.ndarray:
    values = dict(zip(STAND_IDS, _layer()[band], strict=True))
    return np.array([values[i] for i in STAGE_ROWS], float)


def _declared(s: dict, band: str) -> np.ndarray:
    return s["declared"][:, s["bands"].index(band)]


# ---------------------------------------------------------------------------
# --space stage: the stage's rows
# ---------------------------------------------------------------------------


def test_the_stage_bands_leave_out_what_the_stage_excludes():
    """annual_rainfall and ndvi_residual_variance are in clustering._EXCLUDE_BANDS; the merge's
    provenance and the layer's bookkeeping are not features."""
    assert E.stage_bands(_layer(below_min=True).columns) == [
        "aspect", "canopy_height_std", "distance_to_water", "ndvi_mean", "ndvi_phase_annual",
        "ndvi_trend", "slope", "vh_iqr", "vv_p10"]


def test_one_row_per_typed_stand_from_its_largest_piece():
    stands = E.stage_stands(_layer())
    assert stands["stand_id"].tolist() == STAGE_ROWS


def test_the_stage_space_logs_by_the_stages_rule_and_drops_the_bands_with_no_spread():
    layer = _layer()
    s = E.stage_space(E.stage_stands(layer), E.stage_bands(layer.columns), threshold=1.0)
    assert s["n_rows"] == s["n_fit"] == 12
    # the constant band and the band whose IQR over the twelve rows is 0 are dropped
    assert s["dropped"] == ["distance_to_water", "vh_iqr"]
    assert {"aspect_sin", "aspect_cos", "ndvi_phase_annual_sin", "ndvi_phase_annual_cos"} <= set(s["bands"])
    assert "aspect" not in s["bands"] and "ndvi_phase_annual" not in s["bands"]
    # a negative, left-skewed band is logged too, by log(x - min + 0.001), min over the rows
    for band in ("vv_p10", "canopy_height_std"):
        x = _stage_values(band)
        assert band in s["logged"]
        assert s["offsets"][band] == pytest.approx(-x.min() + 0.001)
        y = np.log(x - x.min() + 0.001)
        q25, q50, q75 = np.quantile(y, [0.25, 0.5, 0.75])
        np.testing.assert_allclose(_declared(s, band), (y - q50) / (q75 - q25))
    # an unskewed band is scaled as it is
    assert "ndvi_mean" not in s["logged"]
    x = _stage_values("ndvi_mean")
    q25, q50, q75 = np.quantile(x, [0.25, 0.5, 0.75])
    np.testing.assert_allclose(_declared(s, "ndvi_mean"), (x - q50) / (q75 - q25))


def test_the_two_geometries():
    layer = _layer()
    s = E.stage_space(E.stage_stands(layer), E.stage_bands(layer.columns), threshold=1.0)
    declared, fit_geometry = s["declared"], s["fit_geometry"]
    np.testing.assert_allclose(np.quantile(declared, 0.5, axis=0), 0.0, atol=1e-12)
    np.testing.assert_allclose(np.quantile(declared, 0.75, axis=0) - np.quantile(declared, 0.25, axis=0), 1.0)
    np.testing.assert_allclose(fit_geometry.min(axis=0), 0.0, atol=1e-12)
    np.testing.assert_allclose(fit_geometry.max(axis=0), 1.0)
    # min-max undoes any per-band scaling before it: what wekaKMeans fits in is the same whatever
    # the stage's centre and spread (review A2)
    lo, hi = declared.min(axis=0), declared.max(axis=0)
    np.testing.assert_allclose((declared - lo) / (hi - lo), fit_geometry, atol=1e-12)


def test_the_fit_leaves_out_the_stands_below_the_minimum_and_the_statistics_do_not():
    layer = _layer(below_min=True)
    stands = E.stage_stands(layer)
    fit = E.fit_rows(stands, True)
    assert fit.tolist() == [True, True, False, True, True, True, False, True, True, True, True, True]
    s = E.stage_space(stands, E.stage_bands(layer.columns), threshold=1.0, fit=fit)
    assert (s["n_rows"], s["n_fit"]) == (12, 10)
    x = _stage_values("ndvi_mean")
    q25, q50, q75 = np.quantile(x, [0.25, 0.5, 0.75])            # over every row
    np.testing.assert_allclose(_declared(s, "ndvi_mean"), (x[fit] - q50) / (q75 - q25))
    np.testing.assert_allclose(s["fit_geometry"].min(axis=0), 0.0, atol=1e-12)   # over the fit rows
    np.testing.assert_allclose(s["fit_geometry"].max(axis=0), 1.0)
    assert E.fit_rows(E.stage_stands(_layer()), False).all()
    with pytest.raises(ValueError, match="below_min"):
        E.fit_rows(E.stage_stands(_layer()), True)


def test_the_angles_are_the_layers_mean_angles():
    """The limit no rebuild from a layer removes (review C10): the layer holds the arithmetic mean
    of aspect, and the stage takes sin and cos per pixel before the mean."""
    layer = _layer()
    stands = E.stage_stands(layer)
    decomposed = E.decompose(stands, E.stage_bands(layer.columns))
    np.testing.assert_allclose(decomposed["aspect_sin"], np.sin(np.deg2rad(_stage_values("aspect"))))
    np.testing.assert_allclose(decomposed["ndvi_phase_annual_cos"], np.cos(_stage_values("ndvi_phase_annual")))


def test_skewness_estimators():
    x = np.array([1.0, 2.0, 2.0, 3.0, 10.0])
    d = x - x.mean()
    g1 = np.mean(d ** 3) / np.mean(d ** 2) ** 1.5
    assert E.skewness(x, adjusted=False) == pytest.approx(g1)
    assert E.skewness(x) == pytest.approx(pd.Series(x).skew())
    assert E.skewness(np.full(5, 463409.50001051987)) == 0.0


def test_elbow_of_is_the_knee_of_the_sweep():
    """elbow_of, which the two new spaces use for the rows in reverse order, is the knee of the
    sweep's own inertia curve; on well-separated groups the order of the rows does not matter."""
    rng = np.random.default_rng(3)
    centres = np.array([[0.0, 0.0], [10.0, 0.0], [0.0, 10.0], [10.0, 10.0]])
    rows = np.vstack([c + rng.normal(0, 0.3, size=(30, 2)) for c in centres])
    sweep = E.sweep_numbers(rows)
    assert E.elbow_of(rows) == sweep["elbow"] == E.knee(sweep["table"].k.tolist(), sweep["table"].inertia.tolist())
    assert E.elbow_of(rows[::-1]) == E.elbow_of(rows) == 4


def test_the_log_by_either_skewness_estimator():
    layer = _layer()
    stands, bands = E.stage_stands(layer), E.stage_bands(layer.columns)
    assert E.skewness(_stage_values("ndvi_trend")) == pytest.approx(1.0466, abs=1e-4)
    assert E.skewness(_stage_values("ndvi_trend"), adjusted=False) == pytest.approx(0.9110, abs=1e-4)
    by_adjusted = E.stage_space(stands, bands, threshold=1.0)
    by_moments = E.stage_space(stands, bands, threshold=1.0, adjusted=False)
    assert "ndvi_trend" in by_adjusted["logged"] and "ndvi_trend" not in by_moments["logged"]
    assert by_adjusted["skew_estimators_disagree"] == by_moments["skew_estimators_disagree"] == ["ndvi_trend"]


# ---------------------------------------------------------------------------
# --space stage-rows: the checks on the stage's own rows
# ---------------------------------------------------------------------------


def _saved_fit(row_of_114: int, not_logged: tuple[str, ...] = ()) -> dict:
    """Rows as scripts/remerge_demo_set.py saves them, made by the stage's rules from the layer,
    with stand 114's row from polygon `row_of_114`, and the bands `not_logged` left as they are
    whatever their skew."""
    layer = _layer()
    pieces = layer.set_index("stand_id")
    stands = pd.concat([pieces.loc[[i for i in STAGE_ROWS if i != 15]], pieces.loc[[row_of_114]]])
    decomposed = E.decompose(stands, ["canopy_height_std", "ndvi_mean", "slope", "vv_p10"])
    post, logged, offsets = E.log_skewed(decomposed, 1.0)
    for band in not_logged:
        post[band] = decomposed[band]
        logged.remove(band)
        del offsets[band]
    q = post.quantile([0.25, 0.5, 0.75])
    scaling = {b: {"center": float(q.loc[0.5, b]), "spread": float(q.loc[0.75, b] - q.loc[0.25, b])}
               for b in post.columns}
    scaled = np.column_stack([(post[b] - scaling[b]["center"]) / scaling[b]["spread"] for b in post.columns])
    return {"metadata": {"log_transformed_bands": logged, "log_offsets": offsets, "scaling": scaling,
                         "dropped_constant_bands": []},
            "bands": list(post.columns), "labels": [int(v) for v in stands["stand_lbl"]], "scaled": scaled}


def test_the_checks_reproduce_the_stages_decisions_on_rows_made_by_its_rules():
    stage = _saved_fit(15)
    pre = E.unlog(stage, E.unscale(stage))
    np.testing.assert_allclose(pre["vv_p10"], [VV_P10[i - 1] for i in STAGE_ROWS])
    check = E.check_stage_rules(stage, 1.0)
    assert check["G1"] == [] and check["offsets"] == []
    assert check["spread_ratio"] == pytest.approx((1.0, 1.0))
    # a band the stage did not log, and that the rule would: reported
    assert E.check_stage_rules(_saved_fit(15, not_logged=("canopy_height_std",)), 1.0)["G1"] == [
        "canopy_height_std"]


def test_which_piece_a_stage_row_came_from():
    assert E.which_piece(_saved_fit(15), _layer()) == {"largest": 1, "another": 0, "not_told_apart": 0}
    assert E.which_piece(_saved_fit(14), _layer()) == {"largest": 0, "another": 1, "not_told_apart": 0}


# ---------------------------------------------------------------------------
# --space script: the departures (the finding; true before and after round 13)
# ---------------------------------------------------------------------------


def test_the_scripts_own_space_departs_from_the_stage():
    layer = _layer()
    feats = sorted(set(layer.columns) - E.DROP)
    rows, cols = E.prep(layer[feats])
    # 1. the bands the stage excludes are kept
    assert "annual_rainfall" in cols and "ndvi_residual_variance" in cols
    # 2. every polygon is a row: the untyped stands and both pieces of stand 114
    assert rows.shape[0] == len(STAND_IDS)
    # 3. a band with no spread over the typed stands is kept
    assert "vh_iqr" in cols
    # 4. a negative band is never logged, however skewed
    x = np.array(VV_P10)
    q25, q50, q75 = np.quantile(x, [0.25, 0.5, 0.75])
    np.testing.assert_allclose(rows[:, cols.index("vv_p10")], (x - q50) / (q75 - q25))
    # 5. a skewed non-negative band is logged by log1p, not by log(x - min + 0.001)
    y = np.log1p(np.array(CANOPY_STD))
    q25, q50, q75 = np.quantile(y, [0.25, 0.5, 0.75])
    np.testing.assert_allclose(rows[:, cols.index("canopy_height_std")], (y - q50) / (q75 - q25))


# ---------------------------------------------------------------------------
# The committed files, written again (slow: minutes of k-means)
# ---------------------------------------------------------------------------


def _run_copy(tmp_path: Path, *args: str) -> Path:
    """Run a copy of the script beside links to the repo's inputs; return the copy's folder."""
    here = tmp_path / "odisha_script"
    here.mkdir()
    shutil.copy2(SCRIPT, here / SCRIPT.name)
    (here / "phase2_vectors").symlink_to(REPO / "odisha_script" / "phase2_vectors")
    for name in ("configs", "docs", "outputs"):
        if (REPO / name).exists():
            (tmp_path / name).symlink_to(REPO / name)
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(REPO / "src"), os.environ.get("PYTHONPATH", "")])}
    proc = subprocess.run([sys.executable, str(here / SCRIPT.name), *args], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=3600, check=False)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    return here


@pytest.mark.slow
@pytest.mark.parametrize("space,suffix", [("script", ""), ("stage", "_stage"), ("stage-rows", "_stage_rows")])
@pytest.mark.parametrize("arm", ["odisha_v120_handcrafted", "odisha_v120_3ha"])
def test_the_committed_elbow_files_are_written_again_byte_for_byte(tmp_path, arm, space, suffix):
    name = f"odisha_phase3_2_k_elbow_{arm}{suffix}.txt"
    committed = REPO / "odisha_script" / name
    if not committed.exists():
        pytest.skip(f"{name} is not committed")
    if space == "stage-rows" and not (REPO / "outputs" / "demo").exists():
        pytest.skip("the stage's own rows are off git, in outputs/demo")
    here = _run_copy(tmp_path, "--arm", arm, "--space", space)
    assert (here / name).read_bytes() == committed.read_bytes()
