"""odisha_script/odisha_phase2_5_stats.py, offline: which plots the rotation null is scored on (review A8, round 13).

The observed 6.1 statistics leave out a plot the observed stand map leaves unassigned (its stand id is NaN). The
rotation null forces only the observed-assigned plots onto a stand, so a realisation can still put an unassigned plot
on a stand. Scored on every plot, such a realisation measures a different plot set from the observed value it is the
null of (the review found it in the full set's v120 / stands_snic, 265 of 267 plots assigned). Phase 3 scores its
null on the observed-assigned plots (odisha_phase3_3_significance.py, `X.delin(rid[r], As)`); so must Phase 2.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import shapely
from shapely import STRtree
from shapely.geometry import box

REPO = Path(__file__).resolve().parent.parent
ODISHA = REPO / "odisha_script"
sys.path.insert(0, str(ODISHA))

import odisha_phase2_3_join as J  # noqa: E402, N812
import odisha_phase2_5_stats as S  # noqa: E402, N812

N_ROT = 101     # at least S.MIN_NULL, so every percentile is estimable
# observed: stands 0, 1 and 2 hold two plots each, stand 3 one; plot 7 is on no stand
OBS_IDS = np.array([0, 0, 1, 1, 2, 2, 3, np.nan])
Y = np.array([1.0, 1.2, 3.0, 3.1, 5.0, 5.4, 2.0, 9.0])
STRUCTURE = ("k (multi-plot stands)", "n (plots in them)", "same-stand within-part pairs")


def _ctx(xy: np.ndarray | None = None) -> S.Ctx:
    """Eight plots in one AOI part, every field variable equal to Y."""
    p = len(Y)
    plots = pd.DataFrame({v: Y for v in S.YVARS})
    plots["aoi_part"] = 0
    if xy is not None:
        plots["x"], plots["y"] = xy[:, 0], xy[:, 1]
    ctx = S.Ctx()
    ctx.plots, ctx.parts = plots, [{"name": "site"}]
    ctx.iu, ctx.ju = np.triu_indices(p, 1)
    ctx.same_part = np.ones(len(ctx.iu), bool)
    ctx.same_district = np.ones(len(ctx.iu), bool)
    ctx.d_geo = np.linspace(20.0, 700.0, len(ctx.iu))
    ctx.d_bc = np.abs(Y[ctx.iu] - Y[ctx.ju]) / 10.0
    ctx.d_lo = np.abs(Y[ctx.iu] - Y[ctx.ju])
    ctx.d_bc_first, ctx.first_keys = None, {}
    ctx.strict_null = False
    return ctx


class _Layer:
    """What analyse_partition reads of a Partition, for one secondary (snic) layer of one AOI part."""
    arm, short, layer_name, label = "v120", "snic", "stands_snic", "v120 / stands_snic"

    def __init__(self, ids: np.ndarray, layer=None):
        self.ids = np.asarray(ids, float)
        self.bdist = np.where(np.isnan(self.ids), np.nan, 100.0)
        self.cluster = np.where(np.isnan(self.ids), np.nan, 0.0)
        self.missing, self.missing_why, self.n_dropped_ids = [], {}, 0
        self.n_in_loaded = len(self.ids)
        keys = np.unique(self.ids[np.isfinite(self.ids)]) if layer is None else layer[2]
        self.polys = pd.DataFrame({"key": keys, "area_ha": 1.0, "cluster_id": 0.0})
        self._layer = layer

    def part_layer(self, q):
        return self._layer


@pytest.fixture
def fresh_output(monkeypatch):
    """The module's printed lines and summary rows, empty for this test and thrown away after it."""
    monkeypatch.setattr(S, "_lines", [])
    monkeypatch.setattr(S, "_rows", [])
    S._ROW_FLAGS.clear()
    yield
    S._ROW_FLAGS.clear()


def _structure_rows(lines: list[str]) -> dict[str, list[str]]:
    """The 6.1 null-structure rows as printed: observed, null median, p5, p95, percentile."""
    out = {}
    for line in lines:
        for name in STRUCTURE:
            if line.strip().startswith(name):
                out[name] = re.split(r"\s+", line.strip()[len(name):].strip())[:5]
    return out


# every realisation has the same null E here, so the E-slope bias estimate fits a line to one point, and says so
@pytest.mark.filterwarnings("ignore:Polyfit may be poorly conditioned")
def test_a_realisation_that_reproduces_the_observed_map_scores_the_observed_value(monkeypatch, fresh_output):
    """Every realisation puts the observed-assigned plots exactly where the observed map has them, and plot 7, which
    the observed map leaves on no stand, on stand 3 beside plot 6. Scored on the plots the observed statistic is
    computed on, each realisation IS the observed partition: null median = observed, excess 0, percentile 50 (all
    ties), and the null's structure is the observed one. Scored on every plot, stand 3 gains a second plot, so the
    null measures a different plot set and its median, excess, percentile and structure all move."""
    rid_one = np.where(np.isnan(OBS_IDS), 3.0, OBS_IDS)          # plot 7 lands on stand 3

    def fake_null(plots, parts, part_obj, observed_ok, n, rng, **kw):
        assert observed_ok.tolist() == [True] * 7 + [False]        # the null forces the observed-assigned plots only
        ids = np.tile(rid_one, (n, 1))
        return ids, np.zeros_like(ids), np.full_like(ids, 100.0), {"site": (1.0, "plain", 1.0)}, []

    monkeypatch.setattr(S, "rotation_null", fake_null)
    res = S.analyse_partition(_ctx(), _Layer(OBS_IDS), N_ROT, primary=False)

    rows = [r for r in S._rows if r.get("section") == "6.1"]
    assert len(rows) == len(S.YVARS)
    for r in rows:
        assert (r["k_restricted"], r["n_restricted"]) == (3, 6)      # observed: stands 0-2, plots 0-5
        assert r["null_median"] == r["r2_restricted"], r["variable"]
        assert r["excess"] == 0.0 and r["percentile"] == 50.0 and r["n_null"] == N_ROT, r
    for v in S.YVARS:
        np.testing.assert_array_equal(res["r2"][v]["null"], np.full(N_ROT, res["r2"][v]["obs"]))

    got = _structure_rows(S._lines)
    assert set(got) == set(STRUCTURE)
    for name, (obs, med, p5, p95, pct) in got.items():
        assert obs == med == p5 == p95, (name, got[name])
        assert pct == "50.0", (name, got[name])
    assert got["k (multi-plot stands)"][0] == "3.000" and got["n (plots in them)"][0] == "6.000"
    assert got["same-stand within-part pairs"][0] == "3.000"


def _grid_layer(gap: tuple[int, int]):
    """A 2 km AOI part tiled by 200 m stands, one tile missing (a gap in the stand map), as rotation_null reads a
    layer: prepared polygons, their tree, stand keys, cluster ids and bounds."""
    tiles = [(i, j) for i in range(10) for j in range(10) if (i, j) != gap]
    geoms = np.array([box(200 * i, 200 * j, 200 * (i + 1), 200 * (j + 1)) for i, j in tiles])
    shapely.prepare(geoms)
    key = np.arange(len(geoms), dtype=float)
    return geoms, STRtree(geoms), key, key % 3, shapely.bounds(geoms)


# plots 0-6 in four tiles around the gap (tile 4, 4: x and y 800 to 1000 m), plot 7 inside the gap
XY = np.array([[650, 850], [700, 950], [1050, 850], [1150, 950], [850, 1050], [950, 1150], [850, 700], [900, 900]],
              float)


def _observed_ids(layer) -> np.ndarray:
    geoms, _, key, _, _ = layer
    ids = np.full(len(XY), np.nan)
    for k, (x, y) in enumerate(XY):
        hit = [key[g] for g in range(len(geoms)) if geoms[g].covers(shapely.Point(x, y))]
        ids[k] = min(hit) if hit else np.nan
    return ids


def test_the_rotation_null_is_scored_on_the_plots_the_observed_statistic_is_computed_on(monkeypatch, fresh_output):
    """End to end with the real rotation_null on a small stand map with a gap: the plot in the gap is unassigned in
    the observed map, the null places it on a stand in most realisations and beside another plot in some, and every
    6.1 null value must be the restricted R2 of the realisation over the observed-assigned plots only."""
    layer = _grid_layer(gap=(4, 4))
    ids = _observed_ids(layer)
    assert np.isnan(ids[7]) and np.isfinite(ids[:7]).all()
    ctx = _ctx(XY)
    ctx.parts = [{"name": "site", "geom": box(0, 0, 2000, 2000)}]
    shapely.prepare(ctx.parts[0]["geom"])
    real, seen = S.rotation_null, {}

    def spy(*a, **kw):
        out = real(*a, **kw)
        seen["rid"] = out[0]
        return out

    monkeypatch.setattr(S, "rotation_null", spy)
    res = S.analyse_partition(ctx, _Layer(ids, layer), N_ROT, primary=False)

    rid = seen["rid"]
    assert rid.shape == (N_ROT, len(XY)) and np.isfinite(rid[:, :7]).all()
    shares = [(rid[r, :7] == rid[r, 7]).any() for r in range(N_ROT)]
    assert np.isfinite(rid[:, 7]).sum() > N_ROT // 2 and any(shares)   # the case is real: the null assigns plot 7
    scored = np.where(np.isfinite(ids), rid, np.nan)
    for v in S.YVARS:
        want = np.array([S.r2_partition(Y, scored[r], True)[0] for r in range(N_ROT)])
        np.testing.assert_array_equal(res["r2"][v]["null"], want, err_msg=v)


def test_with_every_plot_assigned_the_null_is_scored_on_every_plot(monkeypatch, fresh_output):
    """The pilot and every merged layer assign every plot: there the null is scored on all of them, as before."""
    layer = _grid_layer(gap=(9, 9))                                   # a gap far from the plots
    ids = _observed_ids(layer)
    assert np.isfinite(ids).all()
    ctx = _ctx(XY)
    ctx.parts = [{"name": "site", "geom": box(0, 0, 2000, 2000)}]
    real, seen = S.rotation_null, {}

    def spy(*a, **kw):
        out = real(*a, **kw)
        seen["rid"] = out[0]
        return out

    monkeypatch.setattr(S, "rotation_null", spy)
    res = S.analyse_partition(ctx, _Layer(ids, layer), N_ROT, primary=False)
    rid = seen["rid"]
    for v in S.YVARS:
        want = np.array([S.r2_partition(Y, rid[r], True)[0] for r in range(N_ROT)])
        np.testing.assert_array_equal(res["r2"][v]["null"], want, err_msg=v)


FIGURES = ("primary_r2_null", "arms_excess", "pairwise_bands")


def test_a_run_writes_beside_the_files_from_before_the_fix_never_over_them():
    """The fix moves committed numbers, so the files the script wrote before it stay as the record (CLAUDE.md: never
    overwrite a committed result) and a run with the defaults writes new names beside them."""
    for name, old in (("pilot", ""), ("districts", "_districts")):
        before = [f"odisha_phase2_5_results{old}.txt", f"odisha_phase2_5_summary{old}.csv",
                  *[f"odisha_phase2_5_{f}{old}.png" for f in FIGURES]]
        assert all((ODISHA / f).is_file() for f in before), name       # the committed record from before the fix
        suffix = S.output_suffix(J.set_spec(name))
        assert suffix == old + S.OUTPUT_TAG and S.OUTPUT_TAG
        now = [f"odisha_phase2_5_results{suffix}.txt", f"odisha_phase2_5_summary{suffix}.csv",
               f"odisha_phase2_5_results{suffix}.log", *[f"odisha_phase2_5_{f}{suffix}.png" for f in FIGURES]]
        assert not set(now) & set(before)
