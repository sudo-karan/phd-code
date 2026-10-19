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


def _write(runs: Path, folder: str, stages, name: str = "site", layout: str | None = None) -> None:
    (runs / folder).mkdir(parents=True)
    record = {"config_name": name, "stages": stages}
    if layout is not None:  # manifests since round 9 say which cache layout the run used
        record["cache_layout"] = layout
    (runs / folder / "manifest.json").write_text(json.dumps(record))


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


# ---------------------------------------------------------------------------
# The same question for the stage that made the stand types
# ---------------------------------------------------------------------------


def _clustering_stages(static: str, labels: str = "miss-exported", fingerprint: str = FP, name: str = "site"):
    tasks = []
    if labels == "miss-exported":
        tasks = [{"task_id": "T", "description": f"{name}_clustering_cluster_labels",
                  "asset_path": f"projects/p/assets/fmu/{name}/clustering/cluster_labels__{fingerprint}"}]
    return [
        {"name": "masking", "cache_status": {"habitat_mask": "hit"}},
        {"name": "features_optical", "cache_status": {"optical_features": "hit"}},
        {"name": "features_static", "cache_status": {"static_features": static}},
        {"name": "segmentation", "cache_status": {"snic_clusters": "hit"},
         "export_tasks": [{"asset_path": f"projects/p/assets/fmu/{name}/segmentation/snic_clusters__{fingerprint}"}]},
        # The merge is not cached: it has no status and is no input of its own.
        {"name": "merge"},
        {"name": "clustering", "cache_status": {"cluster_labels": labels, "feature_stack": labels},
         "export_tasks": tasks},
    ]


def test_the_clustering_route_says_which_feature_stage_was_computed_live():
    mod = _load()
    route, inputs = mod.route_of(_clustering_stages("miss-exported"), "clustering", "cluster_labels")
    assert route == "mixed"
    assert inputs["features_static/static_features"] == "miss-exported"
    assert inputs["segmentation/snic_clusters"] == "hit"
    assert mod.route_of(_clustering_stages("hit"), "clustering", "cluster_labels")[0] == "cached"
    # Asked about segmentation, this run made no superpixel asset: it read it back.
    assert mod.route_of(_clustering_stages("hit")) is None


def test_the_clustering_route_reads_the_fingerprint_of_the_labels_asset(tmp_path: Path):
    mod = _load()
    runs = tmp_path / "runs"
    _write(runs, "site_20260102_000001", _clustering_stages("miss-exported"))
    _write(runs, "site_20260102_000002", _clustering_stages("hit", labels="hit"))       # read the labels back
    _write(runs, "site_20260102_000003", _clustering_stages("hit", fingerprint="0000000000"))
    result = mod.routes("site", FP, [runs], "clustering", "cluster_labels")
    assert [r["run"] for r in result["runs"]] == ["site_20260102_000001"]
    assert result["route"] == "mixed" and result["stage"] == "clustering" and result["output"] == "cluster_labels"
    # The default question gives a record without the two extra keys, as before.
    assert "stage" not in mod.routes("site", FP, [runs])
    (line,) = mod.describe(mod.routes("other", FP, [runs], "clustering", "cluster_labels"))
    assert "not recorded" in line and "`cluster_labels`" in line


# ---------------------------------------------------------------------------
# Runs in the per-step cache layout (round 9 on): assets are named by step keys
# ---------------------------------------------------------------------------

STEP_KEY = "s0123456789"


def test_a_per_step_run_is_found_by_its_step_key_and_a_legacy_run_by_its_fingerprint(tmp_path: Path):
    """Review C42: every run in the per-step layout was reported "not recorded". The asset name
    was read as `__` and hex digits, and a step key is "s" and ten hex digits; and a run was
    matched against the legacy fingerprint, which no per-step asset carries."""
    mod = _load()
    assert mod.exported_fingerprint(_stages("hit", fingerprint=STEP_KEY)) == STEP_KEY
    runs = tmp_path / "runs"
    _write(runs, "site_20261018_000001", _stages("hit", fingerprint=STEP_KEY), layout="per_step")
    _write(runs, "site_20261018_000002", _stages("miss-exported", fingerprint="s9999999999"),
           layout="per_step")  # made under an earlier step key
    _write(runs, "site_20260102_000001", _stages("miss-exported"), layout="legacy")
    result = mod.routes("site", FP, [runs], step_key=STEP_KEY)
    assert [(r["run"], r["route"]) for r in result["runs"]] == [
        ("site_20260102_000001", "live"), ("site_20261018_000001", "cached")]
    assert result["route"] == "cached" and result["step_key"] == STEP_KEY
    (line, _) = mod.describe(result)
    assert FP in line and STEP_KEY in line
    # A legacy fingerprint never matches a per-step run, nor a step key a legacy run.
    assert mod.routes("site", STEP_KEY, [runs], step_key=FP)["runs"] == []


def test_a_folder_of_legacy_runs_gives_the_record_it_gave_before(tmp_path: Path):
    """The committed route files are of legacy runs; with no per-step run in the folders the
    record has no `step_key`, so they regenerate as before."""
    mod = _load()
    runs = tmp_path / "runs"
    _write(runs, "site_20260102_000001", _stages("hit"))
    assert set(mod.routes("site", FP, [runs], step_key=STEP_KEY)) == {
        "config", "fingerprint", "route", "runs", "unreadable_manifests"}


def test_the_command_reads_a_per_step_run_of_a_config(tmp_path: Path, monkeypatch, capsys):
    """The documented command, on a manifest that names the asset by the config's step key today."""
    import sys

    from fmu.config import load_config
    from fmu.utils.caching import step_key

    repo = Path(__file__).resolve().parent.parent
    config = repo / "configs" / "odisha_alphaearth_3ha_squares_angul_keptland_r9.yaml"
    monkeypatch.chdir(repo)  # the ROI file is read from the repo root, as the pipeline reads it
    cfg = load_config(config)
    key = step_key(cfg, "segmentation")
    runs = tmp_path / "runs"
    _write(runs, f"{cfg.name}_20261018_000001", _stages("hit", fingerprint=key, name=cfg.name),
           name=cfg.name, layout="per_step")
    monkeypatch.setattr(sys, "argv", ["segmentation_route.py", "--config", str(config),
                                      "--runs-dir", str(runs)])
    _load().main()
    out = capsys.readouterr().out
    assert f"cached in run {cfg.name}_20261018_000001" in out and key in out
