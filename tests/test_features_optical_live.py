"""Live integration tests for the features_optical stage. Hits real GEE.

Tests both the baseline (NDVI + single annual) and variant (NIRv + dual)
configs to verify config-driven behavior.
"""

from __future__ import annotations

from pathlib import Path

import ee
import pytest

from fmu.config import load_config
from fmu.stages.base import PipelineContext
from fmu.stages.data_load import DataLoadStage
from fmu.stages.features_optical import FeaturesOpticalStage
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
    """Context with s2_collection loaded, plus the baseline config."""
    repo_root = Path(__file__).parent.parent
    config = load_config(repo_root / "configs" / "sanjay_van_baseline.yaml")
    roi = load_roi_geometry(repo_root / "aois" / "sanjay_van.geojson")
    ctx = PipelineContext()
    ctx.set("roi", roi)

    # Run data_load so we have the s2_collection in context
    data_result = DataLoadStage().run(ctx, config)
    for key, value in data_result.outputs.items():
        ctx.set(key, value)

    return ctx, config


@pytest.fixture(scope="module")
def nirv_dual_ctx_and_config(real_gee):
    """Context with s2_collection loaded, plus the NIRv+dual variant config."""
    repo_root = Path(__file__).parent.parent
    config = load_config(repo_root / "configs" / "sanjay_van_nirv_dual.yaml")
    roi = load_roi_geometry(repo_root / "aois" / "sanjay_van.geojson")
    ctx = PipelineContext()
    ctx.set("roi", roi)

    data_result = DataLoadStage().run(ctx, config)
    for key, value in data_result.outputs.items():
        ctx.set(key, value)

    return ctx, config


def test_baseline_produces_optical_features(baseline_ctx_and_config):
    """Baseline (NDVI + single) end-to-end runs."""
    ctx, config = baseline_ctx_and_config
    result = FeaturesOpticalStage().run(ctx, config)
    assert set(result.outputs.keys()) == {"optical_features"}
    assert isinstance(result.outputs["optical_features"], ee.Image)


def test_baseline_band_names(baseline_ctx_and_config):
    """NDVI + single + trend → 6 bands with ndvi_ prefix and expected suffixes."""
    ctx, config = baseline_ctx_and_config
    result = FeaturesOpticalStage().run(ctx, config)
    band_names = safe_get_info(
        result.outputs["optical_features"].bandNames(), context="baseline band names"
    )
    expected = {
        "ndvi_mean",
        "ndvi_amplitude_annual",
        "ndvi_phase_annual",
        "ndvi_trend",
        "ndvi_residual_variance",
        "ndvi_obs_count",
    }
    assert set(band_names) == expected, f"Got: {band_names}"


def test_nirv_dual_band_names(nirv_dual_ctx_and_config):
    """NIRv + dual + trend → 8 bands with nirv_ prefix and both harmonics."""
    ctx, config = nirv_dual_ctx_and_config
    result = FeaturesOpticalStage().run(ctx, config)
    band_names = safe_get_info(
        result.outputs["optical_features"].bandNames(), context="nirv_dual band names"
    )
    expected = {
        "nirv_mean",
        "nirv_amplitude_annual",
        "nirv_phase_annual",
        "nirv_amplitude_semi",
        "nirv_phase_semi",
        "nirv_trend",
        "nirv_residual_variance",
        "nirv_obs_count",
    }
    assert set(band_names) == expected, f"Got: {band_names}"


def test_ndvi_mean_in_plausible_range(baseline_ctx_and_config):
    """NDVI mean over Sanjay Van bbox should sit in plausible range (mix of urban + forest)."""
    ctx, config = baseline_ctx_and_config
    roi = ctx.get("roi")
    result = FeaturesOpticalStage().run(ctx, config)
    stats = safe_get_info(
        result.outputs["optical_features"].select("ndvi_mean").reduceRegion(
            reducer=ee.Reducer.mean(), geometry=roi, scale=30, maxPixels=1e7
        ),
        context="ndvi_mean over ROI",
    )
    mean_ndvi = stats.get("ndvi_mean")
    assert mean_ndvi is not None
    # Sanjay Van bbox is ~40% forest + ~55% urban, so ROI mean NDVI should
    # be modestly positive (urban areas pull it down).
    assert 0.05 < mean_ndvi < 0.7, f"NDVI mean over ROI unexpected: {mean_ndvi}"


def test_nirv_mean_in_plausible_range(nirv_dual_ctx_and_config):
    """NIRv per Badgley et al. (2017) lives in [0, 1] — NDVI × NIR_reflectance.
    If this test fails with values >1, we've regressed back to the un-normalized
    NIRv (NIR stored-integer × NDVI, in thousands), which is the bug fixed
    2026-05-14.
    """
    ctx, config = nirv_dual_ctx_and_config
    roi = ctx.get("roi")
    result = FeaturesOpticalStage().run(ctx, config)
    stats = safe_get_info(
        result.outputs["optical_features"].select("nirv_mean").reduceRegion(
            reducer=ee.Reducer.mean(), geometry=roi, scale=30, maxPixels=1e7
        ),
        context="nirv_mean over ROI",
    )
    mean_nirv = stats.get("nirv_mean")
    assert mean_nirv is not None
    # NIRv ∈ [0, 1] in principle. ROI is mixed forest+urban so mean is small.
    assert 0.0 < mean_nirv < 0.5, (
        f"NIRv mean over ROI unexpected: {mean_nirv} "
        f"(expected 0-0.5 range; if >1, NIR_reflectance is not normalized)"
    )


def test_amplitude_is_non_negative(baseline_ctx_and_config):
    """Amplitude = sqrt(b² + c²), so it must be >= 0 everywhere."""
    ctx, config = baseline_ctx_and_config
    roi = ctx.get("roi")
    result = FeaturesOpticalStage().run(ctx, config)
    stats = safe_get_info(
        result.outputs["optical_features"].select("ndvi_amplitude_annual").reduceRegion(
            reducer=ee.Reducer.min(), geometry=roi, scale=30, maxPixels=1e7
        ),
        context="min amplitude_annual",
    )
    min_amp = stats.get("ndvi_amplitude_annual")
    assert min_amp is not None and min_amp >= 0, f"min amplitude: {min_amp}"


def test_phase_in_valid_range(baseline_ctx_and_config):
    """Phase from atan2 is in [-π, π]. Check both min and max."""
    ctx, config = baseline_ctx_and_config
    roi = ctx.get("roi")
    result = FeaturesOpticalStage().run(ctx, config)
    phase_band = result.outputs["optical_features"].select("ndvi_phase_annual")
    stats = safe_get_info(
        phase_band.reduceRegion(
            reducer=ee.Reducer.minMax(), geometry=roi, scale=30, maxPixels=1e7
        ),
        context="phase_annual minMax",
    )
    pmin = stats.get("ndvi_phase_annual_min")
    pmax = stats.get("ndvi_phase_annual_max")
    assert pmin is not None and pmax is not None
    assert pmin > -3.15 and pmax < 3.15, f"phase out of [-π, π]: min={pmin}, max={pmax}"


def test_obs_count_positive(baseline_ctx_and_config):
    """obs_count should be > 0 over the AOI (we know there are 255 phenology images)."""
    ctx, config = baseline_ctx_and_config
    roi = ctx.get("roi")
    result = FeaturesOpticalStage().run(ctx, config)
    stats = safe_get_info(
        result.outputs["optical_features"].select("ndvi_obs_count").reduceRegion(
            reducer=ee.Reducer.mean(), geometry=roi, scale=30, maxPixels=1e7
        ),
        context="mean obs_count",
    )
    mean_count = stats.get("ndvi_obs_count")
    assert mean_count is not None and mean_count > 50, (
        f"mean obs_count over ROI: {mean_count} (expected > 50)"
    )


def test_residual_variance_is_non_negative(baseline_ctx_and_config):
    """Residual RMS is non-negative by construction."""
    ctx, config = baseline_ctx_and_config
    roi = ctx.get("roi")
    result = FeaturesOpticalStage().run(ctx, config)
    stats = safe_get_info(
        result.outputs["optical_features"].select("ndvi_residual_variance").reduceRegion(
            reducer=ee.Reducer.min(), geometry=roi, scale=30, maxPixels=1e7
        ),
        context="min residual_variance",
    )
    min_resid = stats.get("ndvi_residual_variance")
    assert min_resid is not None and min_resid >= 0, f"min residual: {min_resid}"
