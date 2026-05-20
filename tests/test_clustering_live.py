"""Live integration tests for the clustering stage.

Upstream artifacts come from the GEE asset cache (populated by an earlier
inspect_*.py run). This matches the production cache-hit path and avoids
the per-call memory limit that re-running every upstream stage live used
to exhaust.

To populate the cache: `python scripts/inspect_clustering.py` once.
After that, all clustering tests run in seconds with no upstream compute.
"""

from __future__ import annotations

import json

import ee
import pytest

from _live_cache_fixtures import ctx_ready_for_downstream
from fmu.stages.clustering import ClusteringStage
from fmu.utils.gee import safe_get_info

pytestmark = pytest.mark.live_gee


@pytest.fixture(scope="module")
def ctx_ready_for_clustering():
    return ctx_ready_for_downstream("sanjay_van_baseline.yaml")


def test_runs_end_to_end(ctx_ready_for_clustering):
    ctx, config = ctx_ready_for_clustering
    result = ClusteringStage().run(ctx, config)
    assert set(result.outputs.keys()) == {"cluster_labels", "feature_stack"}
    assert isinstance(result.outputs["cluster_labels"], ee.Image)
    assert isinstance(result.outputs["feature_stack"], ee.Image)


def test_cluster_labels_in_valid_range(ctx_ready_for_clustering):
    """cluster_id values should be in [0, k-1] across the ROI."""
    ctx, config = ctx_ready_for_clustering
    roi = ctx.get("roi")
    result = ClusteringStage().run(ctx, config)

    stats = safe_get_info(
        result.outputs["cluster_labels"].reduceRegion(
            reducer=ee.Reducer.minMax(),
            geometry=roi,
            scale=config.export.analysis_scale_m,
            maxPixels=1e9,
            bestEffort=True,
        ),
        context="cluster id range",
    )
    cmin = stats.get("cluster_id_min")
    cmax = stats.get("cluster_id_max")
    assert cmin is not None and cmax is not None
    assert cmin >= 0, f"cluster_id_min={cmin}"
    assert cmax <= config.clustering.k - 1, (
        f"cluster_id_max={cmax} (k={config.clustering.k})"
    )


def test_all_k_clusters_present(ctx_ready_for_clustering):
    """K-means should produce all k cluster IDs (no empty clusters
    over a real ROI with thousands of superpixels).

    Mask cluster_labels to habitat-only before counting. The cluster_labels
    image is masked OUTSIDE the habitat (those pixels are null), but GEE's
    countDistinct treats the null/masked entity as a distinct value in some
    reduction paths — producing k+1 instead of k. Applying habitat_mask
    excludes those pixels from the reducer entirely.
    """
    ctx, config = ctx_ready_for_clustering
    roi = ctx.get("roi")
    habitat_mask = ctx.get("habitat_mask")
    result = ClusteringStage().run(ctx, config)

    count_stats = safe_get_info(
        result.outputs["cluster_labels"]
        .updateMask(habitat_mask)
        .reduceRegion(
            reducer=ee.Reducer.countDistinct(),
            geometry=roi,
            scale=config.export.analysis_scale_m,
            maxPixels=1e9,
            bestEffort=True,
        ),
        context="distinct cluster count",
    )
    n_distinct = count_stats.get("cluster_id")
    assert n_distinct is not None
    assert n_distinct == config.clustering.k, (
        f"got {n_distinct} distinct clusters, expected k={config.clustering.k}"
    )


def test_feature_stack_has_active_bands(ctx_ready_for_clustering):
    """feature_stack should expose only bands that survived scaling."""
    ctx, config = ctx_ready_for_clustering
    result = ClusteringStage().run(ctx, config)
    band_names = safe_get_info(
        result.outputs["feature_stack"].bandNames(), context="feature_stack bands"
    )
    assert len(band_names) > 0
    # Excluded bands must NOT appear in the active stack
    for excluded in ("ndvi_obs_count", "nirv_obs_count", "annual_rainfall"):
        assert excluded not in band_names, f"{excluded} should not be in feature_stack"
    # Cyclic bands must NOT appear; their sin/cos pair should
    for cyclic_raw in ("ndvi_phase_annual", "nirv_phase_annual", "aspect"):
        assert cyclic_raw not in band_names, (
            f"{cyclic_raw} should have been decomposed to sin/cos"
        )


def test_aspect_decomposed(ctx_ready_for_clustering):
    """aspect to aspect_sin + aspect_cos."""
    ctx, config = ctx_ready_for_clustering
    result = ClusteringStage().run(ctx, config)
    band_names = set(
        safe_get_info(
            result.outputs["feature_stack"].bandNames(),
            context="feature_stack bands",
        )
    )
    assert "aspect_sin" in band_names
    assert "aspect_cos" in band_names


def test_clustering_metadata_is_attached(ctx_ready_for_clustering):
    """The cluster_labels image should have a 'clustering_metadata' property
    holding a JSON blob with the preprocessing decisions."""
    ctx, config = ctx_ready_for_clustering
    result = ClusteringStage().run(ctx, config)
    raw = safe_get_info(
        result.outputs["cluster_labels"].get("clustering_metadata"),
        context="clustering_metadata property",
    )
    assert raw is not None, "clustering_metadata property is missing"
    parsed = json.loads(raw)
    for key in (
        "k",
        "seed",
        "normalization_method",
        "log_transformed_bands",
        "scaling",
        "active_bands",
        "dropped_constant_bands",
    ):
        assert key in parsed, f"missing key in metadata: {key}"
    assert parsed["k"] == config.clustering.k
    assert parsed["normalization_method"] == config.normalization.method
