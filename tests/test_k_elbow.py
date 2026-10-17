"""The k elbow step (round 9), offline: built and tested, not used this round.

The elbow rule is the one the Phase 3 and demo-set elbows used; the sweep finds
the planted number of groups in planted data; the stage refuses the legacy cache
layout; its output table holds one row per k; and its cache key does not move
with k (tests/test_cache_layout.py, test_k_moves_clustering_and_not_the_elbow).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from fmu.config import Config, load_config
from fmu.pipeline import default_stage_names
from fmu.stages import k_elbow
from fmu.stages.base import PipelineContext
from fmu.utils.caching import LEGACY_LAYOUT, layout_in_use

REPO = Path(__file__).resolve().parent.parent
KENDUJHAR = REPO / "configs" / "odisha_v120_3ha_squares_kendujhar_keptland_s1desc.yaml"


def _blobs(k: int, n: int = 60, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    centres = rng.normal(0, 10, size=(k, 4))
    return np.vstack([c + rng.normal(0, 0.3, size=(n, 4)) for c in centres])


def test_knee_is_the_rule_of_the_earlier_elbows():
    """The same k as scripts/remerge_demo_set.py's knee on the same curve."""
    spec = importlib.util.spec_from_file_location("remerge", REPO / "scripts" / "remerge_demo_set.py")
    assert spec and spec.loader
    remerge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(remerge)
    ks = list(range(2, 13))
    curves = [
        [21251.3, 17428.0, 15613.0, 14066.4, 13165.6, 12453.1, 11794.9, 11178.0, 10713.8, 10375.9, 10071.9],
        [100, 40, 20, 15, 12, 10, 9, 8, 7.5, 7, 6.8],
    ]
    for curve in curves:
        assert k_elbow.knee(ks, curve) == remerge.knee(ks, curve)
    # the Phase 3 pooled curve of the 3 ha arm: its elbow was 5
    assert k_elbow.knee(ks, curves[0]) == 5


def test_knee_without_a_curve_is_none():
    assert k_elbow.knee([2, 3], [5.0, 4.0]) is None
    assert k_elbow.knee([2, 3, 4], [5.0, 5.0, 5.0]) is None


def test_the_sweep_finds_planted_groups():
    sweep = k_elbow.elbow_sweep(_blobs(4), k_min=2, k_max=10, seed=42, n_init=5)
    assert sweep["ks"] == list(range(2, 11))
    assert sweep["elbow_k"] == 4
    assert all(a >= b for a, b in zip(sweep["inertia"], sweep["inertia"][1:], strict=False))


def test_the_sweep_stops_below_the_number_of_rows():
    sweep = k_elbow.elbow_sweep(_blobs(2, n=2), k_min=2, k_max=12, seed=42, n_init=2)
    assert sweep["ks"] == [2, 3] and sweep["elbow_k"] is None


def test_the_table_has_one_row_per_k_and_marks_the_elbow():
    sweep = {"n_rows": 9, "ks": [2, 3, 4], "inertia": [9.0, 3.0, 2.0], "elbow_k": 3}
    rows = k_elbow.elbow_table(sweep, n_bands=5)
    assert [r["k"] for r in rows] == [2, 3, 4]
    assert [r["is_elbow"] for r in rows] == [0, 1, 0]
    assert all(r["n_rows"] == 9 and r["n_bands"] == 5 and r["elbow_k"] == 3 for r in rows)


def test_rows_matrix_keeps_band_order_and_refuses_gaps():
    feats = [{"properties": {"b": 2.0, "a": 1.0}}, {"properties": {"a": 3.0, "b": 4.0}}]
    assert k_elbow.rows_matrix(feats, ["a", "b"]).tolist() == [[1.0, 2.0], [3.0, 4.0]]
    with pytest.raises(ValueError):
        k_elbow.rows_matrix([{"properties": {"a": 1.0}}], ["a", "b"])


def test_the_stage_refuses_the_legacy_layout():
    cfg = load_config(KENDUJHAR)
    with layout_in_use(cfg, LEGACY_LAYOUT), pytest.raises(ValueError, match="per-step layout"):
        k_elbow.KElbowStage().run(PipelineContext(), cfg)


def test_the_stage_sweeps_the_rows_it_reads_and_returns_a_table():
    cfg = load_config(KENDUJHAR)
    rows = _blobs(3, n=30)
    made: list[dict] = []

    class FakeFeature:
        def __init__(self, geom, props):
            made.append(props)

    with patch("fmu.stages.k_elbow.training_rows", return_value=(rows, ["a", "b", "c", "d"])), \
         patch("fmu.stages.k_elbow.ee.Feature", side_effect=FakeFeature), \
         patch("fmu.stages.k_elbow.ee.FeatureCollection", side_effect=lambda feats: ("FC", feats)):
        result = k_elbow.KElbowStage().run(PipelineContext(), cfg)
    assert result.outputs["k_elbow"][0] == "FC"
    assert [p["k"] for p in made] == list(range(cfg.k_elbow.k_min, cfg.k_elbow.k_max + 1))
    assert result.metadata["elbow_k"] == 3 and result.metadata["n_rows"] == 90


def test_the_validate_asks_for_the_merge_records_when_the_fit_leaves_stands_out():
    cfg = load_config(KENDUJHAR)
    assert cfg.clustering.fit_excludes_stands_below_min_area
    ctx = PipelineContext()
    for key in ("roi", "habitat_mask", "feature_stack", "stand_clusters"):
        ctx.set(key, key)
    with pytest.raises(KeyError, match="stand_provenance"):
        k_elbow.KElbowStage().validate(ctx, cfg)


def test_a_run_ending_with_the_elbow_is_one_stage_longer():
    cfg = load_config(KENDUJHAR)
    assert default_stage_names(cfg, through="k_elbow") == [
        *default_stage_names(cfg, through="clustering"), "k_elbow",
    ]


def test_the_elbow_settings_need_a_point_between_the_ends():
    raw = {"k_min": 2, "k_max": 3}
    with pytest.raises(ValueError):
        Config.model_validate(
            {
                "name": "x",
                "roi": {"name": "t", "roi_file": "x.geojson"},
                "dates": {
                    "phenology": {"start": "2020-01-01", "end": "2020-12-31"},
                    "radar": {"start": "2020-01-01", "end": "2020-12-31"},
                    "optical_composite": {"start": "2020-01-01", "end": "2020-12-31"},
                },
                "k_elbow": raw,
            }
        )
