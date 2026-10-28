"""`asset_exists` on Earth Engine: a cache asset that is not there is answered 404 (round 14).

Read-only: `ee.data.getAsset` on two paths that do not exist; nothing is written or submitted.
Run with `pytest -m live_gee tests/test_asset_exists_live.py` from the repo root.

Since round 14 (round 13 question 42) `asset_exists` takes a 404 as a missing asset and raises
for every other status. The first run of a new config asks for assets under folders that do not
exist yet: `fmu.pipeline.cache_layout_for` looks for each output's legacy asset, then each stage
looks for its cached outputs. If Earth Engine answered such a path with 403 ("does not exist or
doesn't allow this operation") rather than 404, every first run would now stop there, before any
task is submitted. The offline tests (`tests/test_asset_exists_http_status.py`) cannot say which
status Earth Engine gives; this does.
"""

from __future__ import annotations

import ee
import pytest

pytestmark = pytest.mark.live_gee


@pytest.fixture(scope="module")
def asset_root() -> str:
    """Initialise Earth Engine once; skip if this machine has no project or no credentials."""
    import fmu.utils.gee as gee_mod
    from fmu.settings import get_settings

    gee_mod._initialized = False
    settings = get_settings(force_reload=True)
    if not settings.gee_project_id:
        pytest.skip("GEE_PROJECT_ID not set in environment or .env; cannot run live tests.")
    try:
        gee_mod.init_gee()
    except ee.EEException as e:
        if "authenticate" in str(e).lower() or "credentials" in str(e).lower():
            pytest.skip(f"Earth Engine is not authenticated on this machine: {e}")
        raise
    return settings.resolved_asset_root()


@pytest.mark.parametrize(
    "below_root",
    [
        # a new config's first cache check: its folder does not exist yet
        "fmu_live_check_no_such_config/masking/habitat_mask__s0000000000",
        # a missing asset in the asset root, a folder that exists
        "fmu_live_check_no_such_asset__s0000000000",
    ],
    ids=["under a folder that does not exist", "in the asset root"],
)
def test_a_missing_asset_is_answered_404_and_reads_as_missing(asset_root, below_root):
    from fmu.utils.caching import _http_status, asset_exists

    path = f"{asset_root}/{below_root}"
    with pytest.raises(ee.EEException) as info:
        ee.data.getAsset(path)
    assert _http_status(info.value) == 404, f"{path}: {info.value}"
    assert asset_exists(path) is False
