"""Live integration tests for the features_radar stage. Hits real GEE."""

from __future__ import annotations

from pathlib import Path

import ee
import pytest

from fmu.config import load_config
from fmu.stages.base import PipelineContext
from fmu.stages.data_load import DataLoadStage
from fmu.stages.features_radar import FeaturesRadarStage
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
    """Context with s1_collection loaded, plus the baseline config."""
    repo_root = Path(__file__).parent.parent
    config = load_config(repo_root / "configs" / "sanjay_van_baseline.yaml")
    roi = load_roi_geometry(repo_root / "aois" / "sanjay_van.geojson")
    ctx = PipelineContext()
    ctx.set("roi", roi)

    # Run data_load so we have s1_collection in context
    data_result = DataLoadStage().run(ctx, config)
    for key, value in data_result.outputs.items():
        ctx.set(key, value)

    return ctx, config


def test_radar_features_runs_end_to_end(baseline_ctx_and_config):
    ctx, config = baseline_ctx_and_config
    result = FeaturesRadarStage().run(ctx, config)
    assert set(result.outputs.keys()) == {"radar_features"}
    assert isinstance(result.outputs["radar_features"], ee.Image)


def test_default_band_names(baseline_ctx_and_config):
    """Default config produces 9 bands: 3 percentiles × 2 pols + 2 IQR + 1 contrast."""
    ctx, config = baseline_ctx_and_config
    result = FeaturesRadarStage().run(ctx, config)
    band_names = safe_get_info(
        result.outputs["radar_features"].bandNames(), context="radar band names"
    )
    expected = {
        "vv_p10",
        "vv_p50",
        "vv_p90",
        "vh_p10",
        "vh_p50",
        "vh_p90",
        "vv_iqr",
        "vh_iqr",
        "vv_minus_vh_median",
    }
    assert set(band_names) == expected, f"Got: {band_names}"


def test_vv_median_in_db_range(baseline_ctx_and_config):
    """VV median over the ROI should fall in the typical SAR dB range."""
    ctx, config = baseline_ctx_and_config
    roi = ctx.get("roi")
    result = FeaturesRadarStage().run(ctx, config)
    stats = safe_get_info(
        result.outputs["radar_features"].select("vv_p50").reduceRegion(
            reducer=ee.Reducer.mean(), geometry=roi, scale=30, maxPixels=1e7
        ),
        context="vv_p50 mean over ROI",
    )
    vv_med = stats.get("vv_p50")
    assert vv_med is not None
    # Typical terrestrial VV in dB: -20 to -5. Urban surfaces can be higher.
    assert -25 < vv_med < 0, f"VV median over ROI unexpected: {vv_med} dB"


def test_vh_median_lower_than_vv(baseline_ctx_and_config):
    """VH backscatter is typically weaker than VV — co-pol > cross-pol."""
    ctx, config = baseline_ctx_and_config
    roi = ctx.get("roi")
    result = FeaturesRadarStage().run(ctx, config)
    stats = safe_get_info(
        result.outputs["radar_features"]
        .select(["vv_p50", "vh_p50"])
        .reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, scale=30, maxPixels=1e7),
        context="vv vs vh medians over ROI",
    )
    vv = stats.get("vv_p50")
    vh = stats.get("vh_p50")
    assert vv is not None and vh is not None
    assert vv > vh, f"VV ({vv}) should be > VH ({vh}) in typical terrestrial returns"


def test_cross_pol_contrast_positive_for_vegetation(baseline_ctx_and_config):
    """VV-VH median over the ROI should be positive (VV stronger than VH).
    Typical vegetation: 4-10 dB. The ROI mixes forest + urban, so range is wider."""
    ctx, config = baseline_ctx_and_config
    roi = ctx.get("roi")
    result = FeaturesRadarStage().run(ctx, config)
    stats = safe_get_info(
        result.outputs["radar_features"]
        .select("vv_minus_vh_median")
        .reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, scale=30, maxPixels=1e7),
        context="vv-vh median over ROI",
    )
    diff = stats.get("vv_minus_vh_median")
    assert diff is not None
    assert 0 < diff < 20, f"VV-VH median over ROI: {diff} dB (expected ~3-12)"


def test_iqr_is_non_negative(baseline_ctx_and_config):
    """IQR = p75 - p25, must be >= 0 by construction."""
    ctx, config = baseline_ctx_and_config
    roi = ctx.get("roi")
    result = FeaturesRadarStage().run(ctx, config)
    stats = safe_get_info(
        result.outputs["radar_features"].select("vv_iqr").reduceRegion(
            reducer=ee.Reducer.min(), geometry=roi, scale=30, maxPixels=1e7
        ),
        context="vv_iqr min",
    )
    min_iqr = stats.get("vv_iqr")
    assert min_iqr is not None and min_iqr >= 0, f"min vv_iqr: {min_iqr}"


def test_percentile_ordering(baseline_ctx_and_config):
    """p10 <= p50 <= p90 must hold per-pixel; check the ROI-mean inequality."""
    ctx, config = baseline_ctx_and_config
    roi = ctx.get("roi")
    result = FeaturesRadarStage().run(ctx, config)
    stats = safe_get_info(
        result.outputs["radar_features"]
        .select(["vv_p10", "vv_p50", "vv_p90"])
        .reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, scale=30, maxPixels=1e7),
        context="vv percentile means over ROI",
    )
    p10 = stats.get("vv_p10")
    p50 = stats.get("vv_p50")
    p90 = stats.get("vv_p90")
    assert p10 < p50 < p90, f"Percentile ordering failed: {p10} {p50} {p90}"
