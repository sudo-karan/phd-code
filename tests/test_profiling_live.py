"""Live integration tests for the profiling stage."""

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
from fmu.stages.profiling import ProfilingStage
from fmu.stages.segmentation import SegmentationStage
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
    yield


@pytest.fixture(scope="module")
def ctx_ready_for_profiling(real_gee):
    """Run the full upstream pipeline so context has cluster_labels + features."""
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


def test_runs_end_to_end(ctx_ready_for_profiling):
    ctx, config = ctx_ready_for_profiling
    result = ProfilingStage().run(ctx, config)
    assert "cluster_profiles" in result.outputs
    profiles = result.outputs["cluster_profiles"]
    assert isinstance(profiles, list)
    assert len(profiles) == config.clustering.k


def test_profile_has_expected_fields(ctx_ready_for_profiling):
    """Each cluster profile must have id, count, area, and per-band stats."""
    ctx, config = ctx_ready_for_profiling
    result = ProfilingStage().run(ctx, config)
    profiles = result.outputs["cluster_profiles"]
    for profile in profiles:
        assert "cluster_id" in profile
        assert "pixel_count" in profile
        assert "area_ha" in profile
        # The reducer name in GEE result is the band suffixed by stat
        # (mean/p25/p50/p75). Just check that at least one such key exists
        # for a known band:
        keys = set(profile.keys())
        has_canopy = any(k.startswith("canopy_height") for k in keys)
        assert has_canopy, f"canopy_height stats missing for cluster {profile['cluster_id']}"


def test_pixel_counts_sum_to_habitat(ctx_ready_for_profiling):
    """Total pixels across clusters should be > 0 and reasonable for the ROI."""
    ctx, config = ctx_ready_for_profiling
    result = ProfilingStage().run(ctx, config)
    profiles = result.outputs["cluster_profiles"]
    total = sum(p["pixel_count"] for p in profiles)
    # Sanjay Van ~13 km² to ~130k pixels at 10m. Habitat masking removes water
    # and built-up; expect 40-80% habitat. Habitat pixels at superpixel
    # resolution should be in the tens of thousands.
    assert total > 5000, f"only {total} pixels total; habitat mask too aggressive?"
    assert total < 150000, f"{total} pixels; exceeds ROI pixel count?"


def test_area_ha_matches_count(ctx_ready_for_profiling):
    """area_ha should equal pixel_count × scale² / 10000."""
    ctx, config = ctx_ready_for_profiling
    result = ProfilingStage().run(ctx, config)
    profiles = result.outputs["cluster_profiles"]
    scale = config.export.analysis_scale_m
    expected_factor = (scale * scale) / 10000.0
    for profile in profiles:
        expected_area = profile["pixel_count"] * expected_factor
        assert abs(profile["area_ha"] - expected_area) < 0.01, (
            f"cluster {profile['cluster_id']} area mismatch: "
            f"{profile['area_ha']} vs {expected_area}"
        )
