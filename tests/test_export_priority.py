"""The optional Earth Engine task priority for cache exports.

`gee_task_priority` decides when a cache-export task runs inside the project's
queue, never what it computes. Two properties matter and both are pinned here:

  - unset (the default), `start_export` must call Earth Engine exactly as it did
    before the setting existed -- no `priority` argument at all;
  - it is a per-machine setting, so it can never reach the experiment config and
    therefore never the cache fingerprint.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

import fmu.utils.caching as caching
from fmu.config import load_config
from fmu.settings import Settings
from fmu.utils.caching import config_fingerprint

REPO_ROOT = Path(__file__).parent.parent


class _FakeTask:
    id = "TASK123"

    def start(self) -> None:  # pragma: no cover - trivial
        pass


def _capture_export(monkeypatch, priority):
    seen: dict = {}

    def fake_to_asset(**kwargs):
        seen.update(kwargs)
        return _FakeTask()

    monkeypatch.setattr(caching.ee.batch.Export.image, "toAsset", fake_to_asset)
    monkeypatch.setattr(caching, "ensure_parent_folders", lambda path: None)
    monkeypatch.setattr(
        caching, "get_settings",
        lambda: Settings(_env_file=None, gee_task_priority=priority),  # type: ignore[call-arg]
    )
    caching.start_export(
        image=object(), asset_path="projects/p/assets/fmu/cfg/stage/key__abc", roi=object()
    )
    return seen


def test_priority_defaults_to_unset(monkeypatch):
    monkeypatch.delenv("GEE_TASK_PRIORITY", raising=False)
    assert Settings(_env_file=None).gee_task_priority is None  # type: ignore[call-arg]


def test_priority_read_from_environment(monkeypatch):
    monkeypatch.setenv("GEE_TASK_PRIORITY", "500")
    assert Settings(_env_file=None).gee_task_priority == 500  # type: ignore[call-arg]


@pytest.mark.parametrize("bad", ["-1", "10000"])
def test_priority_outside_earth_engine_range_is_rejected(monkeypatch, bad):
    monkeypatch.setenv("GEE_TASK_PRIORITY", bad)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_export_call_is_unchanged_when_priority_unset(monkeypatch):
    seen = _capture_export(monkeypatch, None)
    assert "priority" not in seen
    assert set(seen) == {"image", "description", "assetId", "region", "scale", "maxPixels"}


def test_export_call_carries_priority_when_set(monkeypatch):
    seen = _capture_export(monkeypatch, 500)
    assert seen["priority"] == 500


def test_priority_cannot_reach_the_cache_fingerprint(monkeypatch):
    cfg = REPO_ROOT / "configs" / "odisha_v120_3ha_kendujhar.yaml"
    monkeypatch.delenv("GEE_TASK_PRIORITY", raising=False)
    before = config_fingerprint(load_config(cfg))
    monkeypatch.setenv("GEE_TASK_PRIORITY", "500")
    assert config_fingerprint(load_config(cfg)) == before
