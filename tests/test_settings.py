"""
Module 2 tests: environment Settings.

These verify the .env / environment-variable layer works correctly:
  - Defaults apply when env vars are not set
  - Env vars override defaults
  - Asset root resolution falls back sensibly
"""

from __future__ import annotations

import pytest

from fmu.settings import Settings


def test_settings_loads_with_defaults(monkeypatch):
    """If no GEE_PROJECT_ID is set in env, gee_project_id is empty string."""
    monkeypatch.delenv("GEE_PROJECT_ID", raising=False)
    monkeypatch.delenv("GEE_ASSET_ROOT", raising=False)
    # Construct without reading any .env (tmp dir as cwd)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.gee_project_id == ""
    assert s.gee_asset_root == ""
    assert s.log_level == "INFO"


def test_settings_reads_env_var(monkeypatch):
    monkeypatch.setenv("GEE_PROJECT_ID", "test-project-123")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.gee_project_id == "test-project-123"


def test_resolved_asset_root_uses_explicit_value(monkeypatch):
    monkeypatch.setenv("GEE_PROJECT_ID", "test-proj")
    monkeypatch.setenv("GEE_ASSET_ROOT", "projects/test-proj/assets/custom")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.resolved_asset_root() == "projects/test-proj/assets/custom"


def test_resolved_asset_root_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("GEE_PROJECT_ID", "test-proj")
    monkeypatch.delenv("GEE_ASSET_ROOT", raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.resolved_asset_root() == "projects/test-proj/assets/fmu"


def test_resolved_asset_root_fails_without_project_id(monkeypatch):
    monkeypatch.delenv("GEE_PROJECT_ID", raising=False)
    monkeypatch.delenv("GEE_ASSET_ROOT", raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="GEE_PROJECT_ID not set"):
        s.resolved_asset_root()
