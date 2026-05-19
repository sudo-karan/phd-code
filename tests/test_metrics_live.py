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
