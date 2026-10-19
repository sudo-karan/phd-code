"""rebuild_cache.py against a fake Earth Engine: what it counts, when it fails, and when it
refuses (B32, review 2026-10-19).

The register (docs/decisions.yaml) and docs/running.md name this tool for forcing a
recompute, so a deletion it reports must have happened, and an export of the old code still
in the queue must not be left to write its asset after the deletion.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).parent.parent / "rebuild_cache.py"
ROOT = "projects/p/assets/fmu"


class FakeData:
    """`ee.data`: a folder tree of assets, a task list, and a record of the deletions."""

    def __init__(self, tree: dict[str, list[dict]], operations: list[dict] | None = None,
                 fail_delete: tuple[str, ...] = (), fail_list: tuple[str, ...] = ()):
        self.tree, self.operations = tree, operations or []
        self.fail_delete, self.fail_list = fail_delete, fail_list
        self.deleted: list[str] = []

    def listAssets(self, params: dict) -> dict:  # noqa: N802 - Earth Engine's name
        parent = params["parent"]
        if parent in self.fail_list:
            raise RuntimeError("Earth Engine said no")
        return {"assets": self.tree.get(parent, [])}

    def deleteAsset(self, asset_id: str) -> None:  # noqa: N802 - Earth Engine's name
        if asset_id in self.fail_delete:
            raise RuntimeError("Permission denied")
        self.deleted.append(asset_id)

    def listOperations(self) -> list[dict]:  # noqa: N802 - Earth Engine's name
        return self.operations


def _tree() -> dict[str, list[dict]]:
    return {
        f"{ROOT}/cfg": [{"name": f"{ROOT}/cfg/masking", "type": "FOLDER"}],
        f"{ROOT}/cfg/masking": [
            {"name": f"{ROOT}/cfg/masking/habitat_mask__abc", "type": "IMAGE"},
            {"name": f"{ROOT}/cfg/masking/water_mask__abc", "type": "IMAGE"},
        ],
    }


def _run(monkeypatch, data: FakeData, *argv: str) -> int:
    """Load the script with a fake `ee` (and without its chdir), run main(), return the exit code."""
    import fmu.settings  # noqa: F401  (imported with the real ee before the fake goes in)
    import fmu.utils.gee  # noqa: F401

    monkeypatch.setitem(sys.modules, "ee", SimpleNamespace(data=data))
    monkeypatch.setattr(os, "chdir", lambda path: None)
    spec = importlib.util.spec_from_file_location("rebuild_cache", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "init_gee", lambda *a, **k: None)
    monkeypatch.setattr(mod, "get_settings", lambda: SimpleNamespace(resolved_asset_root=lambda: ROOT))
    monkeypatch.setattr(sys, "argv", ["rebuild_cache.py", *argv])
    try:
        mod.main()
    except SystemExit as e:
        return int(e.code) if isinstance(e.code, int) else 1
    return 0


def test_a_failed_deletion_is_not_counted_and_the_exit_is_non_zero(monkeypatch, capsys):
    data = FakeData(_tree(), fail_delete=(f"{ROOT}/cfg/masking/water_mask__abc",))
    code = _run(monkeypatch, data, "--delete", "cfg")
    out = capsys.readouterr().out
    assert data.deleted == [f"{ROOT}/cfg/masking/habitat_mask__abc"]
    assert "Deleted 1 assets." in out
    assert code != 0


def test_a_failed_listing_makes_the_exit_non_zero(monkeypatch, capsys):
    data = FakeData(_tree(), fail_list=(f"{ROOT}/cfg/masking",))
    code = _run(monkeypatch, data, "--delete", "cfg")
    assert "list failed" in capsys.readouterr().out
    assert code != 0


def test_a_queued_task_of_the_config_refuses_before_anything_is_deleted(monkeypatch, capsys):
    """A queued export of the old code writes its asset after the deletion, and the next run
    reads it as a cache hit under unchanged keys."""
    ops = [{"metadata": {"description": "cfg_masking_habitat_mask", "state": "PENDING"}}]
    data = FakeData(_tree(), operations=ops)
    code = _run(monkeypatch, data, "--delete", "cfg")
    assert data.deleted == []
    assert code != 0
    assert "cfg_masking_habitat_mask" in capsys.readouterr().out


def test_an_unreadable_task_list_refuses_too(monkeypatch):
    data = FakeData(_tree())

    def no_list() -> list[dict]:
        raise RuntimeError("deadline exceeded")

    monkeypatch.setattr(data, "listOperations", no_list)
    code = _run(monkeypatch, data, "--delete", "cfg")
    assert data.deleted == [] and code != 0


def test_finished_tasks_and_other_configs_tasks_do_not_refuse(monkeypatch, capsys):
    ops = [
        {"metadata": {"description": "cfg_masking_habitat_mask", "state": "SUCCEEDED"}},
        {"metadata": {"description": "other_masking_habitat_mask", "state": "RUNNING"}},
    ]
    data = FakeData(_tree(), operations=ops)
    code = _run(monkeypatch, data, "--delete", "cfg")
    assert len(data.deleted) == 2 and code == 0
    assert "Deleted 2 assets." in capsys.readouterr().out


def test_a_dry_run_deletes_nothing_and_exits_zero(monkeypatch, capsys):
    data = FakeData(_tree())
    code = _run(monkeypatch, data, "cfg")
    assert data.deleted == [] and code == 0
    assert "Would delete 2 assets." in capsys.readouterr().out
