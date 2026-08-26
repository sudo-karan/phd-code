"""Non-live tests for the merge stage's wiring.

The algorithm itself is covered in `test_region_merge.py` and the graph
extraction in `test_adjacency.py`. What is pinned here is the contract between
them and the rest of the pipeline: the stage declaration, the config-driven
dependency check, the unit key every downstream stage has to agree on, and the
diagnostics that turn a bad threshold choice into a legible warning rather than
a silently odd stand map.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from fmu.config import Config, load_config
from fmu.pipeline import default_stage_names
from fmu.stages.base import PipelineContext, get_stage_class
from fmu.stages.clustering import ClusteringStage
from fmu.stages.merge import MergeStage, _warnings_from
from fmu.stages.metrics import MetricsStage

REPO_ROOT = Path(__file__).parent.parent
CONFIG_DIR = REPO_ROOT / "configs"
BASELINE_YAML = CONFIG_DIR / "sanjay_van_baseline.yaml"
ALPHAEARTH_YAML = CONFIG_DIR / "sanjay_van_alphaearth.yaml"


def _ctx_with(keys: set[str]) -> PipelineContext:
    ctx = PipelineContext()
    for k in keys:
        ctx.set(k, f"<{k}>")
    return ctx


def _cfg(**merge_overrides) -> Config:
    raw = yaml.safe_load(BASELINE_YAML.read_text())
    if merge_overrides:
        raw["merge"] = {**raw.get("merge", {}), **merge_overrides}
    return Config.model_validate(raw)


# ---------- stage declaration ----------


def test_merge_is_registered():
    assert get_stage_class("merge") is MergeStage


def test_merge_produces_the_stand_layer():
    assert MergeStage.produces == {"stand_clusters", "stand_attributes"}


def test_merge_is_not_cached():
    """Deliberate. Caching it would need the merge config hashed into the key,
    and thresholds are the main thing being iterated on -- a stale cache would
    silently poison exactly the experiment being run. The image is a remap of a
    cached asset, so rebuilding it is cheap."""
    assert MergeStage.cacheable_outputs == set()


def test_required_inputs_is_the_invariant_subset_only():
    """The criteria bands' sources depend on `merge.criteria`, which a static
    class attribute cannot see."""
    assert MergeStage.required_inputs == {"roi", "snic_clusters"}


# ---------- validate() ----------


def test_validate_passes_with_the_configured_criterion_sources():
    cfg = _cfg()
    MergeStage().validate(
        _ctx_with({"roi", "snic_clusters"} | cfg.merge.input_sources()), cfg
    )


def test_validate_raises_on_a_missing_criterion_source():
    cfg = _cfg()
    ctx = _ctx_with(
        {"roi", "snic_clusters"} | cfg.merge.input_sources() - {"optical_features"}
    )
    with pytest.raises(KeyError, match="optical_features"):
        MergeStage().validate(ctx, cfg)


def test_validate_error_points_at_the_config_key():
    cfg = _cfg()
    with pytest.raises(KeyError, match="merge.criteria"):
        MergeStage().validate(_ctx_with({"roi", "snic_clusters"}), cfg)


def test_validate_follows_a_changed_criterion_source():
    """Swap in a radar criterion and the stage should demand radar_features."""
    cfg = _cfg(
        criteria=[
            {"source": "structure_features", "band": "canopy_height", "tolerance": 2.0},
            {
                "source": "radar_features",
                "band": "vv_minus_vh_median",
                "tolerance": 0.65,
            },
        ]
    )
    with pytest.raises(KeyError, match="radar_features"):
        MergeStage().validate(
            _ctx_with({"roi", "snic_clusters", "structure_features"}), cfg
        )


# ---------- the unit key every downstream stage shares ----------


def test_unit_key_is_stands_when_merge_runs():
    assert _cfg().unit_label_key() == "stand_clusters"


def test_unit_key_falls_back_to_superpixels_when_merge_is_off():
    assert _cfg(enabled=False).unit_label_key() == "snic_clusters"


def test_clustering_labels_stands_not_superpixels():
    """Clustering is demoted to attaching a type label to a finished stand, so
    it must reduce over `stand_clusters`."""
    cfg = _cfg()
    base = {"roi", "habitat_mask"} | {
        "optical_features",
        "radar_features",
        "structure_features",
        "static_features",
    }
    ClusteringStage().validate(_ctx_with(base | {"stand_clusters"}), cfg)
    with pytest.raises(KeyError, match="stand_clusters"):
        ClusteringStage().validate(_ctx_with(base | {"snic_clusters"}), cfg)


def test_clustering_falls_back_to_superpixels_when_merge_is_off():
    cfg = _cfg(enabled=False)
    base = {"roi", "habitat_mask"} | {
        "optical_features",
        "radar_features",
        "structure_features",
        "static_features",
    }
    ClusteringStage().validate(_ctx_with(base | {"snic_clusters"}), cfg)


def test_metrics_uses_the_same_unit_key():
    """A silhouette over stands and a profile over superpixels are not
    comparable, and nothing in the numbers would say so -- so every stage must
    read the same key."""
    cfg = _cfg()
    base = {"roi", "cluster_labels", "habitat_mask"}
    MetricsStage().validate(_ctx_with(base | {"stand_clusters"}), cfg)
    with pytest.raises(KeyError, match="stand_clusters"):
        MetricsStage().validate(_ctx_with(base | {"snic_clusters"}), cfg)


# ---------- pipeline placement ----------


def test_merge_sits_between_segmentation_and_clustering():
    stages = default_stage_names(_cfg())
    assert stages.index("segmentation") < stages.index("merge") < stages.index(
        "clustering"
    )


def test_disabling_merge_removes_it_from_every_tail():
    cfg = _cfg(enabled=False)
    for through in ("clustering", "profiling", "export", "metrics"):
        assert "merge" not in default_stage_names(cfg, through=through)


def test_merge_criteria_pull_in_their_feature_stages():
    """An embedding run still computes canopy height and NDVI amplitude, purely
    because the merge gate reads them -- the merge rule is held identical across
    arms so that delineation is the only thing differing."""
    stages = default_stage_names(load_config(ALPHAEARTH_YAML))
    assert "features_structure" in stages
    assert "features_optical" in stages
    for stage in ("features_structure", "features_optical"):
        assert stages.index(stage) < stages.index("merge")


# ---------- diagnostics -> warnings ----------


class _Params:
    min_area_ha = 1.0
    max_area_ha = 10.0
    min_frac_valid = 0.5
    max_pass2_iterations = 60


_CLEAN = {
    "orphans_area_blocked": 0,
    "orphans_isolated": 0,
    "orphans_no_attribute_match": 0,
    "stands_with_incomplete_criteria": 0,
    "pass2_fallback_merges": 0,
    "pass2_merges": 0,
    "n_stands": 100,
    "n_superpixels": 1000,
}


def test_clean_run_produces_no_warnings():
    assert _warnings_from(dict(_CLEAN), _Params()) == []


def test_area_blocked_orphans_name_the_right_cause():
    """The distinction that matters: area-blocked means max_area_ha is too
    tight, which is a config fix, not a fact about the forest."""
    w = _warnings_from({**_CLEAN, "orphans_area_blocked": 163}, _Params())
    assert len(w) == 1
    assert "max_area_ha" in w[0]
    assert "too tight" in w[0]


def test_isolated_orphans_are_reported_separately():
    w = _warnings_from({**_CLEAN, "orphans_isolated": 3}, _Params())
    assert len(w) == 1
    assert "no 4-connected neighbour" in w[0]


def test_iteration_cap_is_reported_as_such():
    w = _warnings_from({**_CLEAN, "orphans_no_attribute_match": 2}, _Params())
    assert "ran out of its 60 iterations" in w[0]


def test_incomplete_criteria_are_surfaced():
    w = _warnings_from({**_CLEAN, "stands_with_incomplete_criteria": 14}, _Params())
    assert "null rather than as a mean" in w[0]


def test_fallback_merges_are_surfaced():
    w = _warnings_from(
        {**_CLEAN, "pass2_fallback_merges": 40, "pass2_merges": 50}, _Params()
    )
    assert "shared-edge fallback" in w[0]


def test_no_merging_at_all_is_loud():
    """Silent identity is the failure mode most likely to be mistaken for a
    working run: every stand map looks plausible at 1249 units."""
    w = _warnings_from({**_CLEAN, "n_stands": 1000, "n_superpixels": 1000}, _Params())
    assert any("No superpixels merged" in x for x in w)


# ---------- k-means fits on units, not pixels ----------


def test_n_training_samples_is_retired():
    """It sampled 10,000 *pixels* -- ~37 per superpixel -- from a stack that is
    constant within a unit, so it drew each unit once per pixel and
    area-weighted every statistic computed from it. A config still carrying it
    now fails to load."""
    raw = yaml.safe_load(BASELINE_YAML.read_text())
    raw["clustering"]["n_training_samples"] = 10000
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError
        Config.model_validate(raw)


@pytest.mark.parametrize(
    "path", sorted(CONFIG_DIR.glob("sanjay_van_*.yaml")), ids=lambda p: p.stem
)
def test_shipped_configs_no_longer_carry_n_training_samples(path: Path):
    raw = yaml.safe_load(path.read_text())
    assert "n_training_samples" not in raw.get("clustering", {})


def test_sampler_stratifies_one_point_per_unit():
    """Pin the call shape: numPoints=1 with no classValues takes one point from
    every class present, so no unit is dropped for being small."""
    from fmu.stages.clustering import _sample_one_point_per_unit

    captured = {}

    class _Img:
        def addBands(self, other):
            return self

        def rename(self, name):
            return self

        def stratifiedSample(self, **kw):  # noqa: N802
            captured.update(kw)
            return "<fc>"

    _sample_one_point_per_unit(
        _Img(), _Img(), "<roi>", 10, seed=42, context="test"
    )
    assert captured["numPoints"] == 1
    assert captured["classBand"] == "_unit_label"
    assert captured["scale"] == 10
    assert captured["dropNulls"] is True
    # No classValues: every class present is sampled, small units included.
    assert "classValues" not in captured
