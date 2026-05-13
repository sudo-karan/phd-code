"""Live integration test for the data_load stage. Hits real GEE."""

from __future__ import annotations

from pathlib import Path

import ee
import pytest

from fmu.config import load_config
from fmu.stages.base import PipelineContext
from fmu.stages.data_load import DataLoadStage
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


def test_data_load_runs_end_to_end(sanjay_van_ctx, baseline_config):
    """Stage runs and produces the three declared outputs."""
    result = DataLoadStage().run(sanjay_van_ctx, baseline_config)
    assert set(result.outputs.keys()) == {
        "s2_collection",
        "s1_collection",
        "s2_composite",
    }
    assert isinstance(result.outputs["s2_collection"], ee.ImageCollection)
    assert isinstance(result.outputs["s1_collection"], ee.ImageCollection)
    assert isinstance(result.outputs["s2_composite"], ee.Image)


def test_s2_collection_has_images(sanjay_van_ctx, baseline_config):
    """Phenology window should contain plenty of S2 images over Sanjay Van."""
    result = DataLoadStage().run(sanjay_van_ctx, baseline_config)
    n = safe_get_info(
        result.outputs["s2_collection"].size(), context="s2_collection size"
    )
    assert n > 100, f"Expected >100 S2 images in 2017-2024 window; got {n}"


def test_s1_collection_has_images(sanjay_van_ctx, baseline_config):
    """Radar window with ASCENDING orbit should have a healthy count."""
    result = DataLoadStage().run(sanjay_van_ctx, baseline_config)
    n = safe_get_info(
        result.outputs["s1_collection"].size(), context="s1_collection size"
    )
    assert n > 50, f"Expected >50 S1 ASCENDING images in 2017-2021; got {n}"

def test_s2_composite_is_single_image(sanjay_van_ctx, baseline_config):
    """The composite should be a single ee.Image with the expected band count."""
    result = DataLoadStage().run(sanjay_van_ctx, baseline_config)
    composite = result.outputs["s2_composite"]
    assert isinstance(composite, ee.Image)
    # S2 SR has ~12 bands; reduced composite should have at least the main ones
    bands = safe_get_info(composite.bandNames(), context="s2_composite band names")
    assert len(bands) > 5, f"Expected several bands in S2 composite; got {bands}"


def test_s2_composite_has_real_values(sanjay_van_ctx, baseline_config):
    """The composite should have non-null reflectance values over Sanjay Van."""
    result = DataLoadStage().run(sanjay_van_ctx, baseline_config)
    roi = sanjay_van_ctx.get("roi")
    composite = result.outputs["s2_composite"]
    # B4 (red) median should fall in S2 SR's typical range (roughly 0-3000)
    stats = safe_get_info(
        composite.select("B4_median").reduceRegion(
            reducer=ee.Reducer.mean(), geometry=roi, scale=10, maxPixels=1e7
        ),
        context="S2 composite B4 mean",
    )
    mean_b4 = next(iter(stats.values()), None)
    assert mean_b4 is not None and mean_b4 > 0, f"B4 mean: {mean_b4}"
