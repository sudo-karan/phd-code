"""Live integration test for the masking stage. Hits real GEE."""

from __future__ import annotations

from pathlib import Path

import ee
import pytest

from fmu.config import load_config
from fmu.stages.base import PipelineContext
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
            pytest.skip(f"GEE not authenticated. Run `earthengine authenticate`. {e}")
        raise
    yield


@pytest.fixture(scope="module")
def sanjay_van_ctx(real_gee):
    repo_root = Path(__file__).parent.parent
    roi = load_roi_geometry(repo_root / "aois" / "sanjay_van.geojson")
    ctx = PipelineContext()
    ctx.set("roi", roi)
    return ctx


@pytest.fixture(scope="module")
def baseline_config():
    repo_root = Path(__file__).parent.parent
    return load_config(repo_root / "configs" / "sanjay_van_baseline.yaml")


def test_masking_runs_against_sanjay_van(sanjay_van_ctx, baseline_config):
    """End to end: stage runs and returns the three declared outputs."""
    result = MaskingStage().run(sanjay_van_ctx, baseline_config)
    assert set(result.outputs.keys()) == {
        "habitat_mask",
        "water_mask",
        "landcover_summary",
    }
    for key, img in result.outputs.items():
        assert isinstance(img, ee.Image), f"{key} is not an ee.Image"


def test_habitat_mask_has_nonzero_coverage(sanjay_van_ctx, baseline_config):
    """Sanjay Van is mostly vegetation, so the habitat_mask should cover
    a meaningful fraction of pixels."""
    result = MaskingStage().run(sanjay_van_ctx, baseline_config)
    habitat = result.outputs["habitat_mask"]

    roi = sanjay_van_ctx.get("roi")
    mean = safe_get_info(
        habitat.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=roi, scale=10, maxPixels=1e7
        ),
        context="habitat mask coverage over Sanjay Van",
    )
    # habitat_mask is binary, so mean = fraction of pixels that are 1
    fraction = mean.get("habitat_mask", 0)
    assert 0.3 < fraction < 1.0, (
        f"Expected habitat to cover 30-100% of Sanjay Van; got {fraction:.2%}"
    )


def test_landcover_summary_has_expected_label_values(sanjay_van_ctx, baseline_config):
    """Labeled summary should contain at least one of the veg classes (10/20/30).
    Built (50) and water (80) may or may not appear depending on the ROI."""
    result = MaskingStage().run(sanjay_van_ctx, baseline_config)
    summary = result.outputs["landcover_summary"]

    roi = sanjay_van_ctx.get("roi")
    hist = safe_get_info(
        summary.reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=roi,
            scale=10,
            maxPixels=1e7,
        ),
        context="landcover_summary histogram",
    )
    values = hist.get("landcover_summary", {})
    keys_seen = {int(k) for k in values}
    # At least one veg class should be present
    assert keys_seen & {10, 20, 30}, (
        f"Expected at least one of 10/20/30 in landcover_summary, saw: {keys_seen}"
    )
    # All values should be from the expected set
    assert keys_seen <= {0, 10, 20, 30, 50, 80}, (
        f"Unexpected labels in landcover_summary: {keys_seen - {0, 10, 20, 30, 50, 80}}"
    )


def test_built_areas_appear_in_summary(sanjay_van_ctx, baseline_config):
    """Sanjay Van bbox includes surrounding colonies, so built-up (50)
    should be picked up by Open Buildings + VIIRS combined mask."""
    result = MaskingStage().run(sanjay_van_ctx, baseline_config)
    summary = result.outputs["landcover_summary"]
    roi = sanjay_van_ctx.get("roi")
    hist = safe_get_info(
        summary.reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=roi,
            scale=10,
            maxPixels=1e7,
        ),
        context="landcover_summary built-up presence",
    )
    values = hist.get("landcover_summary", {})
    built_count = values.get("50", 0)
    assert built_count > 0, (
        "Expected at least some built-up pixels (code 50) in the ROI; "
        "Open Buildings should cover colonies around Sanjay Van."
    )


def test_water_mask_is_binary(sanjay_van_ctx, baseline_config):
    """water_mask should only have values 0 and 1."""
    result = MaskingStage().run(sanjay_van_ctx, baseline_config)
    water = result.outputs["water_mask"]

    roi = sanjay_van_ctx.get("roi")
    minmax = safe_get_info(
        water.reduceRegion(
            reducer=ee.Reducer.minMax(), geometry=roi, scale=10, maxPixels=1e7
        ),
        context="water_mask min/max",
    )
    wmin = minmax.get("water_mask_min", 0)
    wmax = minmax.get("water_mask_max", 0)
    assert wmin in (0, 1)
    assert wmax in (0, 1)


def test_habitat_and_water_are_disjoint(sanjay_van_ctx, baseline_config):
    """A pixel should never be in both habitat_mask AND water_mask."""
    result = MaskingStage().run(sanjay_van_ctx, baseline_config)
    overlap = result.outputs["habitat_mask"].And(result.outputs["water_mask"])

    roi = sanjay_van_ctx.get("roi")
    s = safe_get_info(
        overlap.reduceRegion(
            reducer=ee.Reducer.sum(), geometry=roi, scale=10, maxPixels=1e7
        ),
        context="habitat ∩ water overlap",
    )
    # The reducer keys depend on input band name; just check the value
    val = next(iter(s.values()), 0) if s else 0
    assert val == 0, f"habitat and water should be disjoint, found {val} overlap pixels"
