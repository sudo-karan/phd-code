"""
Live integration tests for fmu.utils.gee.

These tests make REAL Earth Engine API calls. They:
  - Are excluded from the default `pytest` run via the `not live_gee` marker.
  - Run only with `pytest -m live_gee`.
  - Need a real GEE_PROJECT_ID in .env (or the environment).
  - Skip cleanly if authentication isn't set up.

Why a separate file (not just markers in test_gee_utils.py)?
  - Makes the boundary between "fast unit tests" and "slow real tests"
    obvious at the file level.
  - Future stages will have their own _live test files following the same
    pattern (test_data_load_live.py, test_features_optical_live.py, ...).

Cost: roughly 10-20 seconds total when run, plus a trivial amount of GEE
compute quota. Don't run on every save.
"""

from __future__ import annotations

from pathlib import Path

import ee
import pytest

# Mark ALL tests in this file as live_gee.
pytestmark = pytest.mark.live_gee


# ---------- Fixture: real GEE initialization ----------


@pytest.fixture(scope="module")
def real_gee():
    """
    Initialize GEE once for the entire test module. Skip all live tests if
    auth or project ID isn't set up.
    """
    import fmu.utils.gee as gee_mod
    from fmu.settings import get_settings

    # Reset cached state so init runs fresh
    gee_mod._initialized = False
    get_settings(force_reload=True)

    settings = get_settings()
    if not settings.gee_project_id:
        pytest.skip(
            "GEE_PROJECT_ID not set in environment or .env; cannot run live tests."
        )

    try:
        gee_mod.init_gee()
    except ee.EEException as e:
        msg = str(e).lower()
        if "authenticate" in msg or "credentials" in msg:
            pytest.skip(
                f"GEE not authenticated on this machine. Run "
                f"`earthengine authenticate` then retry. Underlying error: {e}"
            )
        raise

    yield


# ---------- init_gee live ----------


def test_init_gee_actually_authenticates(real_gee):
    """If we got past the fixture, GEE is initialized for real."""
    from fmu.utils.gee import is_initialized

    assert is_initialized()


def test_init_gee_can_make_trivial_call(real_gee):
    """A trivial GEE computation should succeed end-to-end."""
    # ee.Number is one of the lightest possible operations
    n = ee.Number(2).add(2)
    assert n.getInfo() == 4


# ---------- safe_get_info live ----------


def test_safe_get_info_works_against_real_gee(real_gee):
    """safe_get_info should return real .getInfo() results unchanged."""
    from fmu.utils.gee import safe_get_info

    n = ee.Number(7).multiply(6)
    result = safe_get_info(n, context="trivial multiplication")
    assert result == 42


def test_safe_get_info_appends_context_on_real_error(real_gee):
    """A real GEE error should still come back with context attached."""
    from fmu.utils.gee import safe_get_info

    # Reference a nonexistent asset; guaranteed to fail
    bad_img = ee.Image("users/this_user/does_not_exist_12345")
    with pytest.raises(ee.EEException) as exc_info:
        safe_get_info(bad_img, context="loading nonexistent asset")
    assert "loading nonexistent asset" in str(exc_info.value)


# ---------- load_roi_geometry live ----------


def test_load_real_geojson_produces_usable_geometry(real_gee):
    """The Sanjay Van GeoJSON should load into an ee.Geometry that GEE accepts."""
    from fmu.utils.gee import load_roi_geometry, safe_get_info

    repo_root = Path(__file__).parent.parent
    roi_file = repo_root / "aois" / "sanjay_van.geojson"
    assert roi_file.exists(), f"Missing test fixture: {roi_file}"

    geom = load_roi_geometry(roi_file)
    # Force materialization; if the geometry is malformed, this will fail.
    bounds = safe_get_info(geom.bounds(), context="getting bounds of loaded ROI")
    assert bounds["type"] == "Polygon"

    # Sanity-check the bounds are in Delhi (lon ~77, lat ~28)
    coords = bounds["coordinates"][0]
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    assert 77.0 < min(lons) < 78.0
    assert 28.0 < min(lats) < 29.0


def test_loaded_roi_can_filter_a_real_collection(real_gee):
    """The loaded geometry should work in a real .filterBounds() call."""
    from fmu.utils.gee import load_roi_geometry, safe_get_info

    repo_root = Path(__file__).parent.parent
    roi_file = repo_root / "aois" / "sanjay_van.geojson"
    geom = load_roi_geometry(roi_file)

    # Tiny query: count S2 images in Jan 2023 over our ROI.
    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(geom)
        .filterDate("2023-01-01", "2023-02-01")
    )
    count = safe_get_info(col.size(), context="counting Jan 2023 S2 images")
    assert isinstance(count, int)
    # Sanjay Van has S2 coverage; expect at least a few images in a month.
    assert count > 0


# ---------- asset_path live ----------


def test_asset_path_format_is_valid_for_gee(real_gee):
    """
    asset_path() output should be acceptable to GEE's asset namespace API,
    even if the asset itself doesn't exist yet.
    """
    from fmu.settings import get_settings
    from fmu.utils.gee import asset_path

    pid = get_settings().gee_project_id
    p = asset_path("does_not_exist_yet", subdir="test")

    # Path should be well-formed
    assert p.startswith("projects/")
    assert pid in p
    assert p.endswith("/does_not_exist_yet")

    # Try to query asset info; should fail with "not found", NOT with
    # "malformed path". That distinguishes "GEE rejected the format" from
    # "GEE accepted the format but the asset doesn't exist."
    try:
        ee.data.getAsset(p)
        # If it exists, that's fine too; no assertion needed
    except ee.EEException as e:
        # "Asset 'projects/.../does_not_exist_yet' not found" is the GOOD failure
        # "Invalid asset id" would be the BAD failure
        msg = str(e).lower()
        assert "not found" in msg or "does not exist" in msg, (
            f"GEE rejected the asset path format: {e}"
        )
