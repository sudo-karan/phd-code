"""Live integration tests for the segmentation (SNIC) stage."""

from __future__ import annotations

from pathlib import Path

import ee
import pytest

from fmu.config import load_config
from fmu.stages.base import PipelineContext
from fmu.stages.data_load import DataLoadStage
from fmu.stages.features_radar import FeaturesRadarStage
from fmu.stages.features_structure import FeaturesStructureStage
from fmu.stages.segmentation import SegmentationStage
from fmu.utils.gee import load_roi_geometry, safe_get_info

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
    yield


@pytest.fixture(scope="module")
def ctx_ready_for_snic(real_gee):
    """Build a context that has the three upstream cached inputs needed
    for segmentation: s2_composite, structure_features, radar_features."""
    repo_root = Path(__file__).parent.parent
    config = load_config(repo_root / "configs" / "sanjay_van_baseline.yaml")
    roi = load_roi_geometry(repo_root / "aois" / "sanjay_van.geojson")
    ctx = PipelineContext()
    ctx.set("roi", roi)

    # Run the upstream stages live (no caching for the test) so the context
    # is fully populated without depending on whether the user has cached assets.
    for stage in (DataLoadStage(), FeaturesStructureStage(), FeaturesRadarStage()):
        result = stage.run(ctx, config)
        for key, value in result.outputs.items():
            if not ctx.has(key):
                ctx.set(key, value)
    return ctx, config


def test_runs_end_to_end(ctx_ready_for_snic):
    ctx, config = ctx_ready_for_snic
    result = SegmentationStage().run(ctx, config)
    assert set(result.outputs.keys()) == {"snic_clusters", "snic_means"}
    assert isinstance(result.outputs["snic_clusters"], ee.Image)
    assert isinstance(result.outputs["snic_means"], ee.Image)


def test_snic_clusters_has_single_band(ctx_ready_for_snic):
    ctx, config = ctx_ready_for_snic
    result = SegmentationStage().run(ctx, config)
    band_names = safe_get_info(
        result.outputs["snic_clusters"].bandNames(),
        context="snic_clusters bands",
    )
    assert band_names == ["snic_clusters"], f"Got: {band_names}"


def test_snic_means_has_five_bands(ctx_ready_for_snic):
    """SNIC's per-cluster mean output should have one band per input; five total.
    Note: SNIC suffixes the input names with '_mean' internally; the stage
    strips that suffix so downstream code sees stable band names matching
    the inputs."""
    ctx, config = ctx_ready_for_snic
    result = SegmentationStage().run(ctx, config)
    band_names = safe_get_info(
        result.outputs["snic_means"].bandNames(),
        context="snic_means bands",
    )
    expected = {
        "B4_median",
        "B8_median",
        "composite_nirv",
        "canopy_height",
        "vv_minus_vh_median",
    }
    assert set(band_names) == expected, f"Got: {band_names}"


def test_cluster_count_in_plausible_range(ctx_ready_for_snic):
    """At size=10 on a ~13 km² ROI, expect roughly 1k-50k distinct superpixels.
    The notebook's reference numbers were ~10k-20k; allow generous bounds.

    SNIC numbers clusters with a spatial hash (not 0..N sequential), so we
    use countDistinct rather than max to get a real count."""
    ctx, config = ctx_ready_for_snic
    roi = ctx.get("roi")
    result = SegmentationStage().run(ctx, config)

    count_stats = safe_get_info(
        result.outputs["snic_clusters"].reduceRegion(
            reducer=ee.Reducer.countDistinct(),
            geometry=roi,
            scale=config.export.analysis_scale_m,
            maxPixels=1e9,
            bestEffort=True,
        ),
        context="distinct cluster count",
    )
    n_clusters = count_stats.get("snic_clusters")
    assert n_clusters is not None
    assert 500 < n_clusters < 200000, f"distinct superpixels: {n_clusters} (expected ~1k-50k)"


def test_means_are_finite_and_nonconstant(ctx_ready_for_snic):
    """Each means band should have real variation across the ROI (not constant)."""
    ctx, config = ctx_ready_for_snic
    roi = ctx.get("roi")
    result = SegmentationStage().run(ctx, config)
    stats = safe_get_info(
        result.outputs["snic_means"].reduceRegion(
            reducer=ee.Reducer.stdDev(),
            geometry=roi,
            scale=config.export.analysis_scale_m,
            maxPixels=1e9,
            bestEffort=True,
        ),
        context="snic_means stddev",
    )
    for band in ("B4_median", "B8_median", "composite_nirv", "canopy_height", "vv_minus_vh_median"):
        std = stats.get(band)
        assert std is not None, f"{band} stddev was None"
        assert std > 0, f"{band} stddev was {std} (constant?)"
