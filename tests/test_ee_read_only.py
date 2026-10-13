"""scripts/ee_read_only.py: after forbid_writes() nothing can be submitted or changed.

Offline: the real `ee` client is patched in place and restored, and no call reaches Earth
Engine, because every patched function raises before doing anything.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "ee_read_only.py"


def _load():
    spec = importlib.util.spec_from_file_location("ee_read_only", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def locked(monkeypatch):
    """The installed client with its writing calls replaced, restored afterwards."""
    import ee

    mod = _load()
    monkeypatch.setattr(ee.batch.Task, "start", ee.batch.Task.start)
    for name in mod._DATA_WRITES:
        if hasattr(ee.data, name):
            monkeypatch.setattr(ee.data, name, getattr(ee.data, name))
    return mod, ee, mod.forbid_writes()


def test_the_calls_that_start_a_task_or_touch_an_asset_all_raise(locked):
    mod, ee, replaced = locked
    for name in ("ee.batch.Task.start", "ee.data.exportImage", "ee.data.exportTable",
                 "ee.data.createAsset", "ee.data.copyAsset", "ee.data.deleteAsset",
                 "ee.data.renameAsset", "ee.data.updateAsset", "ee.data.setAssetProperties"):
        assert name in replaced, name
    with pytest.raises(mod.EarthEngineWriteError, match="read-only"):
        ee.data.deleteAsset("projects/x/assets/y")
    with pytest.raises(mod.EarthEngineWriteError):
        ee.data.exportImage("id", {})
    with pytest.raises(mod.EarthEngineWriteError):
        ee.data.copyAsset("a", "b")


def test_every_call_the_client_uses_to_start_a_task_is_covered(locked):
    """The list is checked against the client itself: whatever `ee.batch` calls on `ee.data`
    to export must be replaced, so a client upgrade that adds a way to submit fails here."""
    import inspect
    import re

    _, ee, replaced = locked
    used = set(re.findall(r"data\.(export\w+|start\w+)\(", inspect.getsource(ee.batch)))
    assert used, "ee.batch no longer exports through ee.data: read it again"
    assert {f"ee.data.{name}" for name in used} <= set(replaced), used


def test_an_export_task_can_be_built_but_not_started(locked):
    """Building the task object makes no request; starting it is what submits."""
    mod, ee, _ = locked
    task = ee.batch.Task("id", ee.batch.Task.Type.EXPORT_IMAGE, ee.batch.Task.State.UNSUBMITTED)
    with pytest.raises(mod.EarthEngineWriteError, match="ee.batch.Task.start"):
        task.start()


def test_reading_calls_are_left_alone(locked):
    _, ee, replaced = locked
    for name in ("getInfo", "listAssets", "getAsset", "getDownloadId", "computeValue"):
        if hasattr(ee.data, name):
            assert f"ee.data.{name}" not in replaced
            assert not getattr(ee.data, name).__name__.startswith("forbidden_")


def test_calling_it_twice_is_harmless(locked):
    mod, ee, replaced = locked
    assert mod.forbid_writes() == replaced
    with pytest.raises(mod.EarthEngineWriteError):
        ee.data.deleteAsset("x")
