"""Live integration tests for the features_static stage."""

from __future__ import annotations

from pathlib import Path

import ee
import pytest

from fmu.config import load_config
from fmu.stages.base import PipelineContext
from fmu.stages.features_static import FeaturesStaticStage
from fmu.stages.masking import MaskingStage
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
def ctx_with_water_mask(real_gee):
    """Context with roi and water_mask populated (from masking stage)."""
    repo_root = Path(__file__).parent.parent
    config = load_config(repo_root / "configs" / "sanjay_van_baseline.yaml")
    roi = load_roi_geometry(repo_root / "aois" / "sanjay_van.geojson")
    ctx = PipelineContext()
    ctx.set("roi", roi)

    masking_result = MaskingStage().run(ctx, config)
    for key, value in masking_result.outputs.items():
        ctx.set(key, value)

    return ctx, config


def test_runs_end_to_end(ctx_with_water_mask):
    ctx, config = ctx_with_water_mask
    result = FeaturesStaticStage().run(ctx, config)
    assert set(result.outputs.keys()) == {"static_features"}
    assert isinstance(result.outputs["static_features"], ee.Image)


def test_band_names_with_climate(ctx_with_water_mask):
    """With include_climate=True (the default), 5 bands."""
    ctx, config = ctx_with_water_mask
    result = FeaturesStaticStage().run(ctx, config)
    band_names = safe_get_info(
        result.outputs["static_features"].bandNames(),
        context="static_features band names",
    )
    expected = {
        "elevation",
        "slope",
        "aspect",
        "distance_to_water",
        "annual_rainfall",
    }
    assert set(band_names) == expected, f"Got: {band_names}"


def test_band_names_without_climate(ctx_with_water_mask):
    """With include_climate=False, 4 bands (no annual_rainfall)."""
    ctx, config = ctx_with_water_mask
    config_no_climate = config.model_copy(deep=True)
    config_no_climate.features_static.include_climate = False

    result = FeaturesStaticStage().run(ctx, config_no_climate)
    band_names = safe_get_info(
        result.outputs["static_features"].bandNames(),
        context="static_features band names (no climate)",
    )
    assert set(band_names) == {
        "elevation",
        "slope",
        "aspect",
        "distance_to_water",
    }, f"Got: {band_names}"


def test_elevation_in_plausible_range(ctx_with_water_mask):
    """Sanjay Van is on Delhi Ridge; elevation ~210-260 m above sea level."""
    ctx, config = ctx_with_water_mask
    roi = ctx.get("roi")
    result = FeaturesStaticStage().run(ctx, config)
    stats = safe_get_info(
        result.outputs["static_features"].select("elevation").reduceRegion(
            reducer=ee.Reducer.mean(), geometry=roi, scale=30, maxPixels=1e7
        ),
        context="elevation mean over ROI",
    )
    elev = stats.get("elevation")
    assert elev is not None
    assert 100 < elev < 400, f"elevation mean over Delhi: {elev} m"


def test_slope_non_negative(ctx_with_water_mask):
    """Slope in degrees is non-negative by definition."""
    ctx, config = ctx_with_water_mask
    roi = ctx.get("roi")
    result = FeaturesStaticStage().run(ctx, config)
    stats = safe_get_info(
        result.outputs["static_features"].select("slope").reduceRegion(
            reducer=ee.Reducer.min(), geometry=roi, scale=30, maxPixels=1e7
        ),
        context="slope min",
    )
    min_slope = stats.get("slope")
    assert min_slope is not None and min_slope >= 0, f"min slope: {min_slope}"


def test_aspect_in_valid_range(ctx_with_water_mask):
    """Aspect is 0-360 degrees. Allow small floating-point slack."""
    ctx, config = ctx_with_water_mask
    roi = ctx.get("roi")
    result = FeaturesStaticStage().run(ctx, config)
    stats = safe_get_info(
        result.outputs["static_features"].select("aspect").reduceRegion(
            reducer=ee.Reducer.minMax(), geometry=roi, scale=30, maxPixels=1e7
        ),
        context="aspect minMax",
    )
    amin = stats.get("aspect_min")
    amax = stats.get("aspect_max")
    assert amin is not None and amax is not None
    assert amin >= -0.01, f"aspect min: {amin}"
    assert amax <= 360.01, f"aspect max: {amax}"


def test_distance_to_water_non_negative(ctx_with_water_mask):
    """Distance is non-negative; water pixels themselves have distance 0."""
    ctx, config = ctx_with_water_mask
    roi = ctx.get("roi")
    result = FeaturesStaticStage().run(ctx, config)
    stats = safe_get_info(
        result.outputs["static_features"].select("distance_to_water").reduceRegion(
            reducer=ee.Reducer.min(), geometry=roi, scale=30, maxPixels=1e7
        ),
        context="distance min",
    )
    min_d = stats.get("distance_to_water")
    assert min_d is not None and min_d >= 0, f"min distance: {min_d}"


def test_annual_rainfall_positive(ctx_with_water_mask):
    """Delhi gets ~600-900 mm/year. CHIRPS should reflect that."""
    ctx, config = ctx_with_water_mask
    roi = ctx.get("roi")
    result = FeaturesStaticStage().run(ctx, config)
    stats = safe_get_info(
        result.outputs["static_features"].select("annual_rainfall").reduceRegion(
            reducer=ee.Reducer.mean(), geometry=roi, scale=5000, maxPixels=1e6
        ),
        context="annual_rainfall mean",
    )
    rain = stats.get("annual_rainfall")
    assert rain is not None
    # Delhi climatology; wide tolerance for sanity check
    assert 300 < rain < 1500, f"Delhi annual rainfall: {rain} mm/year"
