"""Non-live tests for the embedding feature arm (AlphaEarth / Tessera).

Covers the parts that need no Earth Engine:
  - config schema: clustering.feature_source, FeaturesEmbeddingParams,
    datasets.embedding, and the two shipped embedding configs;
  - ClusteringStage.validate() requiring the right context keys per source
    (the sanctioned hook, since required_inputs is a static class attribute);
  - default_stage_names() picking the handcrafted vs embedding stage list.

The live server-side behaviour (loading AlphaEarth/Tessera, clustering the
embedding, the confidence roll-up) has no dedicated *_live test yet — the
existing live fixtures all load hand-crafted configs. Covering it needs a
GEE-authed run of an embedding config, e.g.
`python scripts/inspect_metrics.py --config configs/sanjay_van_alphaearth.yaml`;
these non-live tests are the current automated coverage.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from fmu.config import (
    ClusteringParams,
    DatasetIDs,
    FeaturesEmbeddingParams,
    load_config,
)
from fmu.pipeline import default_stage_names
from fmu.stages.base import PipelineContext
from fmu.stages.clustering import ClusteringStage

REPO_ROOT = Path(__file__).parent.parent
ALPHAEARTH_YAML = REPO_ROOT / "configs" / "sanjay_van_alphaearth.yaml"
TESSERA_YAML = REPO_ROOT / "configs" / "sanjay_van_tessera.yaml"
BASELINE_YAML = REPO_ROOT / "configs" / "sanjay_van_baseline.yaml"
NIRV_DUAL_YAML = REPO_ROOT / "configs" / "sanjay_van_nirv_dual.yaml"


# ---------- config schema ----------


def test_feature_source_defaults_to_handcrafted():
    assert ClusteringParams().feature_source == "handcrafted"


def test_feature_source_accepts_embedding():
    assert ClusteringParams(feature_source="embedding").feature_source == "embedding"


def test_feature_source_rejects_unknown():
    with pytest.raises(ValidationError):
        ClusteringParams(feature_source="pretrained")  # type: ignore[arg-type]


def test_embedding_dataset_default_is_alphaearth():
    assert DatasetIDs().embedding == "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"


def test_embedding_params_defaults():
    p = FeaturesEmbeddingParams()
    assert p.collapse_reducer == "mean"
    assert p.band_names is None


def test_embedding_params_reject_bad_reducer():
    with pytest.raises(ValidationError):
        FeaturesEmbeddingParams(collapse_reducer="p90")  # type: ignore[arg-type]


def test_embedding_params_reject_unknown_field():
    with pytest.raises(ValidationError):
        FeaturesEmbeddingParams(bands=64)  # type: ignore[call-arg]


# ---------- shipped embedding configs ----------


def test_alphaearth_config_loads():
    cfg = load_config(ALPHAEARTH_YAML)
    assert cfg.name == "sanjay_van_alphaearth"
    assert cfg.clustering.feature_source == "embedding"
    assert cfg.datasets.embedding == "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"
    # Compares against the hand-crafted baseline.
    assert cfg.metrics.reference_config_name == "sanjay_van_baseline"


def test_alphaearth_segments_on_the_embedding():
    """Each arm segments on its OWN feature space.

    This deliberately reverses the earlier design, which held SNIC identical
    across arms and called that the experiment's control. Under the merge
    design SNIC+merge *produces the stand*, so a shared segmentation would have
    reduced the embedding arm to "which labels does k-means give inside
    boundaries the hand-crafted stack drew" — never putting the delineation
    question, which is the thesis question, to the embedding at all.
    """
    emb = load_config(ALPHAEARTH_YAML)
    assert [(b.source, b.band) for b in emb.segmentation.input_bands] == [
        ("embedding_features", "*")
    ]
    assert emb.segmentation.input_sources() == {"embedding_features"}


def test_alphaearth_holds_non_feature_hyperparameters_fixed():
    """What IS controlled: everything that is not the feature representation."""
    emb = load_config(ALPHAEARTH_YAML)
    base = load_config(BASELINE_YAML)
    for knob in (
        "size",
        "compactness",
        "connectivity",
        "neighborhood_size",
        "normalize_inputs",
        "normalize_distance_scale",
    ):
        assert getattr(emb.segmentation, knob) == getattr(base.segmentation, knob), knob
    assert emb.clustering.k == base.clustering.k
    assert emb.clustering.seed == base.clustering.seed
    assert emb.export.analysis_scale_m == base.export.analysis_scale_m


def test_both_arms_normalize_the_snic_distance_scale():
    """6 bands vs 64: without this, `compactness` is not comparable across arms.

    SNIC trades summed squared colour distance against a spatial term, and that
    sum grows with the number of effective axes. Equal `compactness` in a 6-band
    and a 64-band arm would buy very different spatial weights, which would
    confound the comparison the whole experiment rests on.
    """
    for path in (BASELINE_YAML, ALPHAEARTH_YAML, TESSERA_YAML, NIRV_DUAL_YAML):
        assert load_config(path).segmentation.normalize_distance_scale is True, path


def test_tessera_config_loads():
    cfg = load_config(TESSERA_YAML)
    assert cfg.name == "sanjay_van_tessera"
    assert cfg.clustering.feature_source == "embedding"
    assert cfg.metrics.reference_config_name == "sanjay_van_baseline"


# ---------- ClusteringStage.validate() ----------


def _ctx_with(keys: set[str]) -> PipelineContext:
    ctx = PipelineContext()
    for k in keys:
        ctx.set(k, f"<{k}>")  # dummy; validate() only inspects keys, not values
    return ctx


# `stand_clusters`, not `snic_clusters`: clustering labels the unit the merge
# produced. See Config.unit_label_key().
_HANDCRAFTED_KEYS = {
    "roi", "stand_clusters", "habitat_mask",
    "optical_features", "radar_features", "structure_features", "static_features",
}
_EMBEDDING_KEYS = {"roi", "stand_clusters", "habitat_mask", "embedding_features"}


def test_validate_handcrafted_passes_with_full_stack():
    cfg = load_config(BASELINE_YAML)
    ClusteringStage().validate(_ctx_with(_HANDCRAFTED_KEYS), cfg)  # no raise


def test_validate_handcrafted_missing_optical_raises():
    cfg = load_config(BASELINE_YAML)
    ctx = _ctx_with(_HANDCRAFTED_KEYS - {"optical_features"})
    with pytest.raises(KeyError, match="optical_features"):
        ClusteringStage().validate(ctx, cfg)


def test_validate_embedding_passes_with_embedding_features():
    cfg = load_config(ALPHAEARTH_YAML)
    ClusteringStage().validate(_ctx_with(_EMBEDDING_KEYS), cfg)  # no raise


def test_validate_embedding_missing_embedding_features_raises():
    cfg = load_config(ALPHAEARTH_YAML)
    ctx = _ctx_with({"roi", "stand_clusters", "habitat_mask"})
    with pytest.raises(KeyError, match="embedding_features"):
        ClusteringStage().validate(ctx, cfg)


def test_validate_embedding_does_not_require_handcrafted_stack():
    """An embedding run must NOT be forced to produce the optical/static images."""
    cfg = load_config(ALPHAEARTH_YAML)
    # Only the embedding inputs present — no optical/radar/structure/static.
    ClusteringStage().validate(_ctx_with(_EMBEDDING_KEYS), cfg)  # no raise


# ---------- default_stage_names() ----------


def test_stage_names_handcrafted():
    cfg = load_config(BASELINE_YAML)
    stages = default_stage_names(cfg)
    assert stages == [
        "masking", "data_load", "features_optical", "features_radar",
        "features_structure", "features_static", "segmentation", "merge",
        "clustering", "metrics",
    ]


def test_merge_sits_between_segmentation_and_clustering():
    """SNIC + merge produces the stand; clustering only labels it."""
    for path in (BASELINE_YAML, ALPHAEARTH_YAML, NIRV_DUAL_YAML, TESSERA_YAML):
        stages = default_stage_names(load_config(path))
        assert stages.index("segmentation") < stages.index("merge")
        assert stages.index("merge") < stages.index("clustering")


def test_disabling_merge_drops_the_stage():
    import yaml as _yaml

    from fmu.config import Config

    raw = _yaml.safe_load(BASELINE_YAML.read_text())
    raw["merge"] = {"enabled": False}
    cfg = Config.model_validate(raw)
    assert "merge" not in default_stage_names(cfg)
    # ...and downstream stages fall back to labelling raw superpixels
    assert cfg.unit_label_key() == "snic_clusters"


def test_stage_names_embedding_swaps_feature_stages():
    """The embedding replaces the hand-crafted stack as the *feature vector*,
    so features_radar and features_static drop out.

    features_optical and features_structure stay — not for the feature vector,
    but because the **merge criteria** are held identical across arms and read
    canopy_height, canopy_height_std and ndvi_amplitude_annual. That is what
    leaves delineation as the only thing differing between the arms.
    """
    cfg = load_config(ALPHAEARTH_YAML)
    stages = default_stage_names(cfg)
    assert "features_embedding" in stages
    for dropped in ("features_static", "features_radar"):
        assert dropped not in stages, dropped
    assert stages == [
        "masking", "data_load", "features_optical", "features_structure",
        "features_embedding", "segmentation", "merge", "clustering", "metrics",
    ]


def test_embedding_arm_runs_hand_crafted_stages_only_for_the_merge_gate():
    """Pin the reason: the criteria sources are exactly the extra stages."""
    cfg = load_config(ALPHAEARTH_YAML)
    assert cfg.clustering.feature_source == "embedding"
    assert cfg.segmentation.input_sources() == {"embedding_features"}
    assert cfg.merge.input_sources() == {"structure_features", "optical_features"}


def test_disabling_merge_leaves_the_embedding_arm_fully_independent():
    """With no merge gate, nothing in the arm reads a hand-crafted band."""
    import yaml as _yaml

    from fmu.config import Config

    raw = _yaml.safe_load(ALPHAEARTH_YAML.read_text())
    raw["merge"] = {"enabled": False}
    stages = default_stage_names(Config.model_validate(raw))
    assert stages == [
        "masking", "data_load", "features_embedding", "segmentation",
        "clustering", "metrics",
    ]


def test_stage_names_embedding_feeds_clustering_and_snic():
    """The embedding must be produced before both consumers that read it."""
    stages = default_stage_names(load_config(ALPHAEARTH_YAML))
    assert stages.index("features_embedding") < stages.index("segmentation")
    assert stages.index("features_embedding") < stages.index("clustering")


def test_stage_names_follow_snic_input_bands():
    """The stage list is the union of what clustering AND segmentation ask for.

    Pinned because it is the one place the two consumers could silently
    disagree: a config that clusters on the embedding but segments on
    hand-crafted bands must still run those feature stages.
    """
    import yaml as _yaml

    from fmu.config import Config

    raw = _yaml.safe_load(ALPHAEARTH_YAML.read_text())
    raw["segmentation"]["input_bands"] = [
        {"source": "radar_features", "band": "vv_minus_vh_median"},
        {"source": "structure_features", "band": "canopy_height"},
    ]
    stages = default_stage_names(Config.model_validate(raw))
    # clustering still wants the embedding; SNIC now pulls radar back in
    assert "features_embedding" in stages
    assert "features_radar" in stages
    assert "features_structure" in stages
    # nothing reads static, so it stays out
    assert "features_static" not in stages
    for needed in ("features_radar", "features_structure"):
        assert stages.index(needed) < stages.index("segmentation")


# ---------- default_stage_names(through=...) ----------


def test_stage_names_through_clustering_stops_at_clustering():
    """inspect_clustering asks for the clustering tail (no profiling/export/metrics)."""
    for yaml_path in (BASELINE_YAML, ALPHAEARTH_YAML):
        stages = default_stage_names(load_config(yaml_path), through="clustering")
        assert stages[-1] == "clustering"
        assert not ({"profiling", "export", "metrics"} & set(stages))


def test_stage_names_through_export_runs_profiling_then_export():
    """inspect_export needs profiling (dissolved layer) before export, no metrics."""
    stages = default_stage_names(load_config(ALPHAEARTH_YAML), through="export")
    assert stages[-2:] == ["profiling", "export"]
    assert "metrics" not in stages
    # embedding feature stage still swapped in
    assert "features_embedding" in stages
    assert "features_static" not in stages


def test_stage_names_through_profiling():
    stages = default_stage_names(load_config(BASELINE_YAML), through="profiling")
    assert stages[-1] == "profiling"
    assert "export" not in stages and "metrics" not in stages


def test_stage_names_through_metrics_is_default():
    cfg = load_config(BASELINE_YAML)
    assert default_stage_names(cfg) == default_stage_names(cfg, through="metrics")
    assert default_stage_names(cfg)[-1] == "metrics"
    # metrics tail does NOT run profiling/export (only needs cluster_labels)
    assert "profiling" not in default_stage_names(cfg)


def test_stage_names_rejects_unknown_through():
    with pytest.raises(ValueError, match="through must be one of"):
        default_stage_names(load_config(BASELINE_YAML), through="segmentation")


# ---------- ProfilingStage / ExportStage validate() (feature-source-aware) ----------

_PROFILING_INVARIANT = {"roi", "cluster_labels"}
# `stand_clusters` because export vectorises the merged stands as stands_merged
# whenever merge is enabled, which both shipped configs have it.
_EXPORT_INVARIANT = {
    "roi",
    "cluster_labels",
    "feature_stack",
    "snic_clusters",
    "stand_clusters",
    "cluster_profiles",
}
_HANDCRAFTED_FEATURES = {
    "optical_features", "radar_features", "structure_features", "static_features",
}


def test_profiling_validate_handcrafted_needs_four_images():
    from fmu.stages.profiling import ProfilingStage

    cfg = load_config(BASELINE_YAML)
    ProfilingStage().validate(_ctx_with(_PROFILING_INVARIANT | _HANDCRAFTED_FEATURES), cfg)
    with pytest.raises(KeyError, match="optical_features"):
        ProfilingStage().validate(_ctx_with(_PROFILING_INVARIANT), cfg)


def test_profiling_validate_embedding_needs_only_embedding_features():
    from fmu.stages.profiling import ProfilingStage

    cfg = load_config(ALPHAEARTH_YAML)
    # embedding run has no optical/static — must still validate
    ProfilingStage().validate(_ctx_with(_PROFILING_INVARIANT | {"embedding_features"}), cfg)
    with pytest.raises(KeyError, match="embedding_features"):
        ProfilingStage().validate(_ctx_with(_PROFILING_INVARIANT), cfg)


def test_export_validate_handcrafted_needs_four_images():
    from fmu.stages.export import ExportStage

    cfg = load_config(BASELINE_YAML)
    ExportStage().validate(_ctx_with(_EXPORT_INVARIANT | _HANDCRAFTED_FEATURES), cfg)
    with pytest.raises(KeyError, match="optical_features"):
        ExportStage().validate(_ctx_with(_EXPORT_INVARIANT), cfg)


def test_export_validate_embedding_needs_only_embedding_features():
    from fmu.stages.export import ExportStage

    cfg = load_config(ALPHAEARTH_YAML)
    ExportStage().validate(_ctx_with(_EXPORT_INVARIANT | {"embedding_features"}), cfg)
    with pytest.raises(KeyError, match="embedding_features"):
        ExportStage().validate(_ctx_with(_EXPORT_INVARIANT), cfg)
