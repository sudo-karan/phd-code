"""Live integration tests for the features_structure stage."""

from __future__ import annotations

from pathlib import Path

import ee
import pytest

from fmu.config import load_config
from fmu.stages.base import PipelineContext
from fmu.stages.features_structure import FeaturesStructureStage
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
def baseline_ctx_and_config(real_gee):
    """Context with roi loaded, baseline config (with neighborhood stats on)."""
    repo_root = Path(__file__).parent.parent
    config = load_config(repo_root / "configs" / "sanjay_van_baseline.yaml")
    roi = load_roi_geometry(repo_root / "aois" / "sanjay_van.geojson")
    ctx = PipelineContext()
    ctx.set("roi", roi)
    return ctx, config


def test_runs_end_to_end(baseline_ctx_and_config):
    ctx, config = baseline_ctx_and_config
    result = FeaturesStructureStage().run(ctx, config)
    assert set(result.outputs.keys()) == {"structure_features"}
    assert isinstance(result.outputs["structure_features"], ee.Image)


def test_band_names_with_neighborhood_stats(baseline_ctx_and_config):
    """With include_neighborhood_stats=True (the default), 3 bands."""
    ctx, config = baseline_ctx_and_config
    result = FeaturesStructureStage().run(ctx, config)
    band_names = safe_get_info(
        result.outputs["structure_features"].bandNames(),
        context="structure band names",
    )
    expected = {"canopy_height", "canopy_height_std", "canopy_height_max"}
    assert set(band_names) == expected, f"Got: {band_names}"


def test_band_names_without_neighborhood_stats(baseline_ctx_and_config):
    """With include_neighborhood_stats=False, only canopy_height."""
    ctx, config = baseline_ctx_and_config
    # Make a shallow copy of config with the flag flipped
    config_no_neighborhood = config.model_copy(deep=True)
    config_no_neighborhood.features_structure.include_neighborhood_stats = False

    result = FeaturesStructureStage().run(ctx, config_no_neighborhood)
    band_names = safe_get_info(
        result.outputs["structure_features"].bandNames(),
        context="structure band names (no neighborhood)",
    )
    assert set(band_names) == {"canopy_height"}, f"Got: {band_names}"


def test_canopy_height_in_plausible_range(baseline_ctx_and_config):
    """Mean canopy height over Sanjay Van bbox: forest+urban mix. Some trees,
    lots of zero-height non-vegetation. Mean roughly 1-15m feels right."""
    ctx, config = baseline_ctx_and_config
    roi = ctx.get("roi")
    result = FeaturesStructureStage().run(ctx, config)
    stats = safe_get_info(
        result.outputs["structure_features"].select("canopy_height").reduceRegion(
            reducer=ee.Reducer.mean(), geometry=roi, scale=30, maxPixels=1e7
        ),
        context="canopy_height mean over ROI",
    )
    mean_h = stats.get("canopy_height")
    assert mean_h is not None
    # Sanity bounds. Anything outside [0, 50] means the dataset isn't what we think.
    assert 0 < mean_h < 50, f"canopy_height mean over ROI: {mean_h} m"


def test_canopy_height_std_non_negative(baseline_ctx_and_config):
    """std-dev is non-negative by construction."""
    ctx, config = baseline_ctx_and_config
    roi = ctx.get("roi")
    result = FeaturesStructureStage().run(ctx, config)
    stats = safe_get_info(
        result.outputs["structure_features"].select("canopy_height_std").reduceRegion(
            reducer=ee.Reducer.min(), geometry=roi, scale=30, maxPixels=1e7
        ),
        context="canopy_height_std min",
    )
    min_std = stats.get("canopy_height_std")
    assert min_std is not None and min_std >= 0, f"min std: {min_std}"


def test_max_at_least_height(baseline_ctx_and_config):
    """For any pixel, neighborhood max >= the pixel's own height (the pixel is in
    its own neighborhood). Check the ROI-mean inequality."""
    ctx, config = baseline_ctx_and_config
    roi = ctx.get("roi")
    result = FeaturesStructureStage().run(ctx, config)
    stats = safe_get_info(
        result.outputs["structure_features"]
        .select(["canopy_height", "canopy_height_max"])
        .reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, scale=30, maxPixels=1e7),
        context="canopy_height vs max means",
    )
    mean_h = stats.get("canopy_height")
    mean_max = stats.get("canopy_height_max")
    assert mean_h is not None and mean_max is not None
    assert mean_max >= mean_h, f"max ({mean_max}) should be >= height ({mean_h})"
