"""scripts/segmentation_route.py: which inputs a run drew its superpixels from.

Offline: the manifests are written here, under tmp_path.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "segmentation_route.py"
FP = "abc123def0"


def _load():
    spec = importlib.util.spec_from_file_location("segmentation_route", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _stages(inputs: str, snic: str = "miss-exported", fingerprint: str = FP, name: str = "site"):
    tasks = []
    if snic == "miss-exported":
        tasks = [{"task_id": "T", "description": f"{name}_segmentation_snic_clusters",
                  "asset_path": f"projects/p/assets/fmu/{name}/segmentation/snic_clusters__{fingerprint}"}]
    return [
        {"name": "masking", "cache_status": {"habitat_mask": inputs, "water_mask": inputs}},
        {"name": "data_load", "cache_status": {"s2_composite": inputs}},
        {"name": "features_optical", "cache_status": {"optical_features": inputs}},
        {"name": "segmentation", "cache_status": {"snic_clusters": snic, "snic_means": snic},
         "export_tasks": tasks},
        # A stage after segmentation must not count as an input.
        {"name": "merge", "cache_status": {"stand_labels": "miss-exported"}},
    ]


def _write(runs: Path, folder: str, stages, name: str = "site") -> None:
    (runs / folder).mkdir(parents=True)
    (runs / folder / "manifest.json").write_text(json.dumps({"config_name": name, "stages": stages}))


def test_all_inputs_from_the_cache_is_cached_and_none_is_live():
    mod = _load()
    assert mod.route_of(_stages("hit"))[0] == "cached"
    assert mod.route_of(_stages("miss-exported"))[0] == "live"


def test_some_inputs_from_the_cache_is_mixed_and_lists_them():
    mod = _load()
    stages = _stages("hit")
    stages[2]["cache_status"]["optical_features"] = "miss-exported"
    route, inputs = mod.route_of(stages)
    assert route == "mixed"
    assert inputs["features_optical/optical_features"] == "miss-exported"
    assert inputs["data_load/s2_composite"] == "hit"


def test_a_run_that_did_not_make_the_asset_has_no_route():
    mod = _load()
    assert mod.route_of(_stages("hit", snic="hit")) is None  # read the asset back
    assert mod.route_of(_stages("miss", snic="miss")) is None  # computed it, exported nothing
    assert mod.route_of(_stages("hit")[:3]) is None  # stopped before segmentation


def test_mask_provenance_does_not_turn_a_cached_run_into_a_mixed_one():
    mod = _load()
    stages = _stages("hit")
    stages[0]["cache_status"]["mask_provenance"] = "miss-exported"
    assert mod.route_of(stages)[0] == "cached"


def test_the_fingerprint_is_read_from_the_exported_asset_name():
    mod = _load()
    assert mod.exported_fingerprint(_stages("hit", fingerprint="0123456789")) == "0123456789"
    assert mod.exported_fingerprint(_stages("hit", snic="hit")) is None


def test_routes_keeps_only_this_config_under_this_fingerprint(tmp_path: Path):
    mod = _load()
    runs = tmp_path / "runs"
    _write(runs, "site_20260101_000001", _stages("miss-exported", fingerprint="0ld0ld0ld0"))
    _write(runs, "site_20260102_000001", _stages("miss-exported"))
    _write(runs, "site_20260103_000001", _stages("hit", snic="hit"))
    _write(runs, "other_20260102_000002", _stages("hit", name="other"), name="other")
    (runs / "site_20260104_000001").mkdir()
    (runs / "site_20260104_000001" / "manifest.json").write_text("{ not json")
    result = mod.routes("site", FP, [runs])
    assert [r["run"] for r in result["runs"]] == ["site_20260102_000001"]
    assert result["route"] == "live"
    assert len(result["unreadable_manifests"]) == 1


def test_a_later_export_under_the_same_fingerprint_decides_the_route(tmp_path: Path):
    mod = _load()
    first, second = tmp_path / "a", tmp_path / "b"
    _write(first, "site_20260102_000001", _stages("miss-exported"))
    _write(second, "site_20260105_000001", _stages("hit"))
    result = mod.routes("site", FP, [second, first])
    assert [r["route"] for r in result["runs"]] == ["live", "cached"]
    assert result["route"] == "cached"


def test_no_run_is_reported_as_not_recorded(tmp_path: Path):
    mod = _load()
    (tmp_path / "runs").mkdir()
    result = mod.routes("site", FP, [tmp_path / "runs"])
    assert result["route"] == "not recorded" and result["runs"] == []
    (line,) = mod.describe(result)
    assert "not recorded" in line and "site" in line


def test_describe_names_the_run_and_the_route(tmp_path: Path):
    mod = _load()
    runs = tmp_path / "runs"
    _write(runs, "site_20260102_000001", _stages("hit"))
    (line,) = mod.describe(mod.routes("site", FP, [runs]))
    assert "cached" in line and "site_20260102_000001" in line and FP in line
