"""Live integration tests for the metrics stage.

These tests run against the variant config (sanjay_van_nirv_dual) so the
comparison path against the baseline reference is exercised. Requires
both configs' cluster_labels and feature_stack to be cached as GEE assets.
"""

from __future__ import annotations

from pathlib import Path

import ee
import pytest

from fmu.config import load_config
from fmu.stages.base import PipelineContext
from fmu.stages.clustering import ClusteringStage
from fmu.stages.data_load import DataLoadStage
from fmu.stages.features_optical import FeaturesOpticalStage
from fmu.stages.features_radar import FeaturesRadarStage
from fmu.stages.features_static import FeaturesStaticStage
from fmu.stages.features_structure import FeaturesStructureStage
from fmu.stages.masking import MaskingStage
from fmu.stages.metrics import MetricsStage
from fmu.stages.segmentation import SegmentationStage
from fmu.utils.caching import asset_exists, cached_asset_path
from fmu.utils.gee import load_roi_geometry

pytestmark = pytest.mark.live_gee


@pytest.fixture(scope="module")
def real_gee():
    import fmu.utils.gee as gee_mod
    from fmu.settings import get_settings

    gee_mod._initialized = False
    get_settings(force_reload=True)

    settings = get_settings()
    if not settings.gee_project_id:
        pytest.skip("GEE_PROJECT_ID not set in .env")

    try:
        gee_mod.init_gee()
    except ee.EEException as e:
        msg = str(e).lower()
        if "authenticate" in msg or "credentials" in msg:
            pytest.skip(f"GEE not authenticated. {e}")
        raise

    # Skip if baseline assets aren't cached (we need them as reference)
    baseline_labels = cached_asset_path(
        "sanjay_van_baseline", "clustering", "cluster_labels"
    )
    if not asset_exists(baseline_labels):
        pytest.skip(
            f"Baseline cluster_labels not cached at {baseline_labels}. "
            "Run inspect_clustering.py on baseline first."
        )

    yield


@pytest.fixture(scope="module")
def ctx_ready_for_metrics(real_gee):
    """Run the variant pipeline up through clustering, then we can run metrics."""
    repo_root = Path(__file__).parent.parent
    config = load_config(repo_root / "configs" / "sanjay_van_nirv_dual.yaml")
    roi = load_roi_geometry(repo_root / "aois" / "sanjay_van.geojson")
    ctx = PipelineContext()
    ctx.set("roi", roi)

    stages = [
        MaskingStage(),
        DataLoadStage(),
        FeaturesOpticalStage(),
        FeaturesRadarStage(),
        FeaturesStructureStage(),
        FeaturesStaticStage(),
        SegmentationStage(),
        ClusteringStage(),
    ]
    for stage in stages:
        result = stage.run(ctx, config)
        for key, value in result.outputs.items():
            if not ctx.has(key):
                ctx.set(key, value)
    return ctx, config


def test_runs_end_to_end(ctx_ready_for_metrics):
    ctx, config = ctx_ready_for_metrics
    result = MetricsStage().run(ctx, config)
    assert "comparison_metrics" in result.outputs
    # Agreement map should be present when comparison mode is active
    assert "agreement_map" in result.outputs


def test_metrics_has_required_keys(ctx_ready_for_metrics):
    ctx, config = ctx_ready_for_metrics
    result = MetricsStage().run(ctx, config)
    metrics = result.outputs["comparison_metrics"]
    # Comparison mode required keys
    for key in ("ari", "nmi", "agreement_rate", "correspondence",
                "confusion_matrix", "silhouette_current"):
        assert key in metrics, f"missing key: {key}"


def test_ari_nmi_in_valid_range(ctx_ready_for_metrics):
    """ARI ∈ [-1, 1] in theory; NMI ∈ [0, 1]."""
    ctx, config = ctx_ready_for_metrics
    result = MetricsStage().run(ctx, config)
    metrics = result.outputs["comparison_metrics"]
    assert -1.0 <= metrics["ari"] <= 1.0, f"ARI out of range: {metrics['ari']}"
    assert 0.0 <= metrics["nmi"] <= 1.0, f"NMI out of range: {metrics['nmi']}"


def test_silhouette_in_valid_range(ctx_ready_for_metrics):
    """Silhouette ∈ [-1, 1]."""
    ctx, config = ctx_ready_for_metrics
    result = MetricsStage().run(ctx, config)
    metrics = result.outputs["comparison_metrics"]
    silh = metrics["silhouette_current"]
    # nan also acceptable if feature_stack absent
    if silh == silh:  # not NaN
        assert -1.0 <= silh <= 1.0, f"silhouette out of range: {silh}"


def test_correspondence_is_one_to_one(ctx_ready_for_metrics):
    """Hungarian guarantees a 1-to-1 matching; verify."""
    ctx, config = ctx_ready_for_metrics
    result = MetricsStage().run(ctx, config)
    metrics = result.outputs["comparison_metrics"]
    correspondence = metrics["correspondence"]
    assert len(correspondence) == config.clustering.k
    keys = set(correspondence.keys())
    vals = set(correspondence.values())
    assert len(keys) == config.clustering.k, "duplicate current cluster IDs"
    assert len(vals) == config.clustering.k, "duplicate reference cluster IDs"


def test_confusion_matrix_shape(ctx_ready_for_metrics):
    ctx, config = ctx_ready_for_metrics
    result = MetricsStage().run(ctx, config)
    metrics = result.outputs["comparison_metrics"]
    cm = metrics["confusion_matrix"]
    k = config.clustering.k
    assert len(cm) == k
    for row in cm:
        assert len(row) == k


def test_agreement_map_is_image(ctx_ready_for_metrics):
    ctx, config = ctx_ready_for_metrics
    result = MetricsStage().run(ctx, config)
    agreement = result.outputs["agreement_map"]
    assert isinstance(agreement, ee.Image)


# ---------------------------------------------------------------------
# Baseline-mode tests: metrics.reference_config_name is null. The stage
# should compute intrinsic silhouette only and leave agreement_map as None.
# Importantly we ALSO exercise the orchestrator (not bare .run()) since
# the orchestrator's output-validation step is what catches contract
# violations.
# ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def ctx_ready_for_baseline_metrics(real_gee):
    """Same as ctx_ready_for_metrics but uses the baseline config (no reference)."""
    repo_root = Path(__file__).parent.parent
    config = load_config(repo_root / "configs" / "sanjay_van_baseline.yaml")
    roi = load_roi_geometry(repo_root / "aois" / "sanjay_van.geojson")
    ctx = PipelineContext()
    ctx.set("roi", roi)

    stages = [
        MaskingStage(),
        DataLoadStage(),
        FeaturesOpticalStage(),
        FeaturesRadarStage(),
        FeaturesStructureStage(),
        FeaturesStaticStage(),
        SegmentationStage(),
        ClusteringStage(),
    ]
    for stage in stages:
        result = stage.run(ctx, config)
        for key, value in result.outputs.items():
            if not ctx.has(key):
                ctx.set(key, value)
    return ctx, config


def test_baseline_mode_only_returns_intrinsic_metrics(ctx_ready_for_baseline_metrics):
    """In baseline mode (no reference_config_name), comparison metrics are absent
    but the silhouette is still computed."""
    ctx, config = ctx_ready_for_baseline_metrics
    # Sanity check the fixture
    assert config.metrics.reference_config_name is None

    result = MetricsStage().run(ctx, config)
    metrics = result.outputs["comparison_metrics"]

    # Intrinsic metric must be present
    assert "silhouette_current" in metrics

    # Comparison metrics must NOT be present (no reference to compare against)
    for key in ("ari", "nmi", "agreement_rate", "correspondence", "confusion_matrix"):
        assert key not in metrics, (
            f"baseline mode unexpectedly produced {key!r}; "
            "should only run when reference_config_name is set"
        )


def test_baseline_mode_still_produces_both_declared_outputs(ctx_ready_for_baseline_metrics):
    """The stage's `produces` declaration is invariant; baseline mode must
    still write both keys to outputs (with agreement_map = None).

    This is the regression test for the bug found 2026-05-19: the stage
    used to conditionally add agreement_map only in comparison mode,
    which the orchestrator rejects with `output mismatch` error.
    """
    ctx, config = ctx_ready_for_baseline_metrics
    result = MetricsStage().run(ctx, config)
    assert set(result.outputs.keys()) == {"comparison_metrics", "agreement_map"}
    assert result.outputs["agreement_map"] is None


def test_baseline_mode_passes_orchestrator_validation(ctx_ready_for_baseline_metrics):
    """The orchestrator's strict produced_keys==produces check must accept
    baseline-mode metrics output.

    Why this matters: the bare `MetricsStage().run(ctx, config)` calls in
    other tests bypass the orchestrator. This test routes through Pipeline,
    which means the framework's contract enforcement is exercised end-to-end.
    """
    import tempfile

    from fmu.pipeline import Pipeline

    ctx, config = ctx_ready_for_baseline_metrics
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        # use_cache=False so this is a pure framework-level test, not a
        # cache test; and so we don't pollute the user's GEE asset space.
        pipeline = Pipeline(stage_names=["metrics"], use_cache=False)
        result = pipeline.run(config=config, run_dir=run_dir, initial_context=ctx)

    # If the orchestrator hadn't accepted the output, .run() would have
    # raised a ValueError before getting here.
    assert any(s.name == "metrics" for s in result.stages)
    assert result.context.has("comparison_metrics")
    assert result.context.has("agreement_map")
    # agreement_map should be None in baseline mode
    assert result.context.get("agreement_map") is None
