"""
Tests for fmu.utils.gee.

These tests do NOT make real GEE calls. They mock the `ee` module so the
test suite runs without authentication. Real-GEE tests will live elsewhere
and run manually, not in CI.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import ee
import pytest


@pytest.fixture(autouse=True)
def reset_gee_init_state():
    """Reset the module's _initialized flag before each test."""
    import fmu.utils.gee as gee_mod

    gee_mod._initialized = False
    yield
    gee_mod._initialized = False


# ---------- init_gee ----------


def test_init_gee_requires_project_id(monkeypatch, tmp_path):
    """If no project ID is configured anywhere, init_gee should fail cleanly."""
    # Move to a directory with no .env file so pydantic-settings can't load one
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GEE_PROJECT_ID", raising=False)
    from fmu.settings import get_settings
    from fmu.utils.gee import init_gee

    get_settings(force_reload=True)

    with pytest.raises(RuntimeError, match="project ID is not set"):
        init_gee()


def test_init_gee_calls_ee_initialize_with_project(monkeypatch):
    monkeypatch.setenv("GEE_PROJECT_ID", "test-proj-abc")
    from fmu.settings import get_settings
    from fmu.utils.gee import init_gee, is_initialized

    get_settings(force_reload=True)

    with patch.object(ee, "Initialize") as mock_init:
        init_gee()
        mock_init.assert_called_once_with(project="test-proj-abc")
        assert is_initialized()


def test_init_gee_override_project_id(monkeypatch):
    monkeypatch.setenv("GEE_PROJECT_ID", "from-env")
    from fmu.settings import get_settings
    from fmu.utils.gee import init_gee

    get_settings(force_reload=True)

    with patch.object(ee, "Initialize") as mock_init:
        init_gee(project_id="explicit-override")
        mock_init.assert_called_once_with(project="explicit-override")


def test_init_gee_is_idempotent(monkeypatch):
    monkeypatch.setenv("GEE_PROJECT_ID", "test-proj")
    from fmu.settings import get_settings
    from fmu.utils.gee import init_gee

    get_settings(force_reload=True)

    with patch.object(ee, "Initialize") as mock_init:
        init_gee()
        init_gee()
        init_gee()
        # Initialize should only be called once
        assert mock_init.call_count == 1


def test_init_gee_translates_auth_error(monkeypatch):
    """Authentication errors should produce a helpful message."""
    monkeypatch.setenv("GEE_PROJECT_ID", "test-proj")
    from fmu.settings import get_settings
    from fmu.utils.gee import init_gee

    get_settings(force_reload=True)

    with patch.object(
        ee,
        "Initialize",
        side_effect=ee.EEException("not authenticated: no credentials found"),
    ), pytest.raises(ee.EEException, match="earthengine authenticate"):
        init_gee()


def test_init_gee_passes_through_other_errors(monkeypatch):
    """Non-auth GEE errors should bubble up unchanged."""
    monkeypatch.setenv("GEE_PROJECT_ID", "test-proj")
    from fmu.settings import get_settings
    from fmu.utils.gee import init_gee

    get_settings(force_reload=True)

    with patch.object(
        ee,
        "Initialize",
        side_effect=ee.EEException("Quota exceeded"),
    ), pytest.raises(ee.EEException, match="Quota exceeded"):
        init_gee()


# ---------- safe_get_info ----------


def test_safe_get_info_returns_result_on_success():
    from fmu.utils.gee import safe_get_info

    mock_obj = MagicMock()
    mock_obj.getInfo.return_value = {"value": 42}

    result = safe_get_info(mock_obj, context="testing")
    assert result == {"value": 42}


def test_safe_get_info_appends_context_on_error():
    from fmu.utils.gee import safe_get_info

    mock_obj = MagicMock()
    mock_obj.getInfo.side_effect = ee.EEException("collection query aborted")

    with pytest.raises(ee.EEException, match="collection query aborted"):
        safe_get_info(mock_obj, context="loading S2 stack")
    # Run again to inspect message
    try:
        safe_get_info(mock_obj, context="loading S2 stack")
    except ee.EEException as e:
        assert "loading S2 stack" in str(e)


def test_safe_get_info_rejects_non_gee_objects():
    from fmu.utils.gee import safe_get_info

    with pytest.raises(TypeError, match="expected a GEE object"):
        safe_get_info("just a string")


# ---------- safe_call decorator ----------


def test_safe_call_decorator_adds_context_to_gee_errors():
    from fmu.utils.gee import safe_call

    @safe_call("doing the thing")
    def boom():
        raise ee.EEException("original error")

    with pytest.raises(ee.EEException) as exc_info:
        boom()
    assert "original error" in str(exc_info.value)
    assert "doing the thing" in str(exc_info.value)


def test_safe_call_decorator_passes_through_non_gee_errors():
    """A regular ValueError should NOT be wrapped — only ee.EEException."""
    from fmu.utils.gee import safe_call

    @safe_call("doing the thing")
    def boom():
        raise ValueError("not a GEE error")

    with pytest.raises(ValueError, match="not a GEE error"):
        boom()


# ---------- load_roi_geometry ----------


def test_load_roi_from_feature_collection(tmp_path):
    from fmu.utils.gee import load_roi_geometry

    gj = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "x"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                },
            }
        ],
    }
    p = tmp_path / "x.geojson"
    p.write_text(json.dumps(gj))

    with patch.object(ee, "Geometry") as mock_geom:
        load_roi_geometry(p)
        # Should have called ee.Geometry with the polygon dict
        assert mock_geom.called


def test_load_roi_from_feature(tmp_path):
    from fmu.utils.gee import load_roi_geometry

    gj = {
        "type": "Feature",
        "properties": {},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
        },
    }
    p = tmp_path / "feat.geojson"
    p.write_text(json.dumps(gj))

    with patch.object(ee, "Geometry") as mock_geom:
        load_roi_geometry(p)
        assert mock_geom.called


def test_load_roi_missing_file_raises(tmp_path):
    from fmu.utils.gee import load_roi_geometry

    with pytest.raises(FileNotFoundError):
        load_roi_geometry(tmp_path / "nope.geojson")


def test_load_roi_empty_feature_collection_raises(tmp_path):
    from fmu.utils.gee import load_roi_geometry

    p = tmp_path / "empty.geojson"
    p.write_text(json.dumps({"type": "FeatureCollection", "features": []}))

    with pytest.raises(ValueError, match="no features"):
        load_roi_geometry(p)


def test_load_roi_unrecognized_type_raises(tmp_path):
    from fmu.utils.gee import load_roi_geometry

    p = tmp_path / "weird.geojson"
    p.write_text(json.dumps({"type": "Topology", "objects": {}}))

    with pytest.raises(ValueError, match="unrecognized GeoJSON type"):
        load_roi_geometry(p)


def test_load_real_sanjay_van_geojson():
    """Make sure the actual baseline ROI file at least parses."""
    from fmu.utils.gee import load_roi_geometry

    repo_root = Path(__file__).parent.parent
    roi_file = repo_root / "aois" / "sanjay_van.geojson"
    assert roi_file.exists()

    with patch.object(ee, "Geometry") as mock_geom:
        load_roi_geometry(roi_file)
        assert mock_geom.called


# ---------- asset_path ----------


def test_asset_path_with_subdir(monkeypatch):
    monkeypatch.setenv("GEE_PROJECT_ID", "myproj")
    monkeypatch.delenv("GEE_ASSET_ROOT", raising=False)
    from fmu.settings import get_settings
    from fmu.utils.gee import asset_path

    get_settings(force_reload=True)
    p = asset_path("cluster_map", subdir="sanjay_van")
    assert p == "projects/myproj/assets/fmu/sanjay_van/cluster_map"


def test_asset_path_without_subdir(monkeypatch):
    monkeypatch.setenv("GEE_PROJECT_ID", "myproj")
    monkeypatch.delenv("GEE_ASSET_ROOT", raising=False)
    from fmu.settings import get_settings
    from fmu.utils.gee import asset_path

    get_settings(force_reload=True)
    p = asset_path("globalthing")
    assert p == "projects/myproj/assets/fmu/globalthing"


def test_asset_path_with_explicit_root(monkeypatch):
    monkeypatch.setenv("GEE_PROJECT_ID", "myproj")
    monkeypatch.setenv("GEE_ASSET_ROOT", "projects/myproj/assets/custom_root")
    from fmu.settings import get_settings
    from fmu.utils.gee import asset_path

    get_settings(force_reload=True)
    p = asset_path("x")
    assert p == "projects/myproj/assets/custom_root/x"


def test_asset_path_rejects_bad_names():
    from fmu.utils.gee import asset_path

    with pytest.raises(ValueError, match="must not contain"):
        asset_path("has/slash")
    with pytest.raises(ValueError, match="must not contain"):
        asset_path("has space")
