"""scripts/copy_run_results.py, offline, on a stand-in run tree."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "copy_run_results.py"
RUN = "odisha_v120_3ha_squares_x_keptland_s1desc"


@pytest.fixture
def mod():
    spec = importlib.util.spec_from_file_location("copy_run_results", SCRIPT)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _tree(tmp_path: Path, big: int) -> Path:
    tree = tmp_path / "tree"
    vec = tree / "odisha_script" / "phase2_vectors"
    vec.mkdir(parents=True)
    (vec / f"{RUN}_stands_merged.geojson").write_text('{"type":"FeatureCollection","features":[]}')
    (vec / f"{RUN}_stands_snic.geojson").write_text('{"x":"' + "a" * big + '"}')
    (vec / f"{RUN}_stands_dissolved.geojson").write_text('{"type":"FeatureCollection","features":[]}')
    (vec / f"{RUN}_raster_at_plots.csv").write_text("plot_key,stand_clusters\n1_2,3\n")
    (vec / f"{RUN}_run.json").write_text(json.dumps({"run_dir": "runs/x_20261015_134106", "fingerprint": "f"}))
    # A pass that failed before writing its manifest: a folder with only its log.
    failed = tree / "runs" / f"{RUN}_20261015_134000"
    failed.mkdir(parents=True)
    (failed / "fmu.log").write_text("User memory limit exceeded.\n")
    for i, last in enumerate(["segmentation", "clustering", "export", "profiling"]):
        d = tree / "runs" / f"{RUN}_20261015_1341{i:02d}"
        d.mkdir(parents=True)
        stages = [{"name": last, "elapsed_sec": 1.5, "metadata": {"n": i}}]
        if last == "export":
            stages[0]["export_tasks"] = [{"task_id": "T", "submitted_at": "2026-10-15T13:41:00"}]
        (d / "manifest.json").write_text(json.dumps({"run_dir": str(d), "total_elapsed_sec": 9,
                                                     "run_timestamp": "x", "stages": stages,
                                                     "config": {"dates": {"radar": "2017"}}}))
    return tree


def test_small_files_go_in_the_repo_without_timings(mod, tmp_path):
    dest, off = tmp_path / "dest", tmp_path / "off"
    done = mod.copy(_tree(tmp_path, 10), RUN, dest, off)
    assert done["off_git"] == [] and not (dest / f"{RUN}_files_off_git.json").exists()
    names = {p.name for p in dest.iterdir()}
    # Round 14: the raster at the plots and every run folder's log (here the failed pass's) too.
    assert names == {f"{RUN}_{n}" for n in ("stands_merged.geojson", "stands_snic.geojson",
                                            "stands_dissolved.geojson", "run.json",
                                            "manifest_segmentation.json", "manifest_clustering.json",
                                            "manifest_export.json", "raster_at_plots.csv",
                                            "log_failed_1.txt")}
    assert "run_dir" not in json.loads((dest / f"{RUN}_run.json").read_text())
    exp = json.loads((dest / f"{RUN}_manifest_export.json").read_text())
    assert "submitted_at" not in json.dumps(exp) and "elapsed_sec" not in json.dumps(exp)
    assert exp["config"]["dates"] == {"radar": "2017"}  # a setting, kept
    # The read-back's own folder (ending at profiling) is not a pass.
    assert json.loads((dest / f"{RUN}_manifest_export.json").read_text())["stages"][0]["metadata"]["n"] == 2


def test_a_file_over_5_mb_stays_off_git_with_its_size_and_sha256(mod, tmp_path):
    dest, off = tmp_path / "dest", tmp_path / "off"
    done = mod.copy(_tree(tmp_path, mod.LIMIT + 1), RUN, dest, off)
    (f,) = done["off_git"]
    assert f["file"] == f"{RUN}_stands_snic.geojson" and not (dest / f["file"]).exists()
    data = (off / f["file"]).read_bytes()
    assert f["bytes"] == len(data) > mod.LIMIT and f["sha256"] == hashlib.sha256(data).hexdigest()
    record = json.loads((dest / f"{RUN}_files_off_git.json").read_text())
    assert record["files"] == [f] and Path(f["where"]) == (off / f["file"]).resolve()


def test_a_date_left_in_a_result_is_refused(mod, tmp_path):
    tree = _tree(tmp_path, 10)
    vec = tree / "odisha_script" / "phase2_vectors"
    (vec / f"{RUN}_run.json").write_text(json.dumps({"made": "2026-10-15T13:41:00"}))
    with pytest.raises(SystemExit, match="date and time"):
        mod.copy(tree, RUN, tmp_path / "dest", tmp_path / "off")


def test_a_recorded_drive_copy_survives_a_new_copy_of_the_same_file(mod, tmp_path):
    dest, off = tmp_path / "dest", tmp_path / "off"
    tree = _tree(tmp_path, mod.LIMIT + 1)
    mod.copy(tree, RUN, dest, off)
    record = dest / f"{RUN}_files_off_git.json"
    rec = json.loads(record.read_text())
    rec["files"][0]["drive"] = "phd-code_off_git/x/" + rec["files"][0]["file"]
    record.write_text(json.dumps(rec))
    mod.copy(tree, RUN, dest, off)  # the same file again: the Drive copy stays recorded
    assert json.loads(record.read_text())["files"][0]["drive"].startswith("phd-code_off_git/x/")
    vec = tree / "odisha_script" / "phase2_vectors"
    (vec / f"{RUN}_stands_snic.geojson").write_text('{"x":"' + "b" * (mod.LIMIT + 1) + '"}')
    mod.copy(tree, RUN, dest, off)  # another file: its Drive copy is not that one
    assert "drive" not in json.loads(record.read_text())["files"][0]


def test_a_pass_kind_run_twice_keeps_both_manifests(mod, tmp_path):
    """Review C35: a config needs a second wrapper pass when a later stage raised, and its retry
    writes a second segmentation manifest (every asset a hit, no task). Only the last of each kind
    was copied, so the manifest of the pass that computed the cache, with its export tasks and
    miss-exported statuses, stayed off git."""
    tree = _tree(tmp_path, big=10)
    computing = {"name": "segmentation", "elapsed_sec": 2.0, "metadata": {"distance_scale": 1.25},
                 "cache_status": {"snic_clusters": "miss-exported"}, "export_tasks": [{"task_id": "T1"}]}
    retry = {"name": "segmentation", "elapsed_sec": 1.0, "metadata": {"source": "cache"},
             "cache_status": {"snic_clusters": "hit"}, "export_tasks": []}
    # After _tree's own segmentation pass (134100): three manifests of the kind, in this order.
    for folder, stage in (("20261015_134120", computing), ("20261015_134150", retry)):
        d = tree / "runs" / f"{RUN}_{folder}"
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps({"run_dir": str(d), "stages": [stage]}))
    dest = tmp_path / "dest"
    done = mod.copy(tree, RUN, dest, tmp_path / "off")
    names = [n for n in done["in_repo"] if "_manifest_segmentation" in n]
    assert names == [f"{RUN}_manifest_segmentation.json", f"{RUN}_manifest_segmentation_1.json",
                     f"{RUN}_manifest_segmentation_2.json"]
    copied = {n: json.loads((dest / n).read_text())["stages"][0] for n in names}
    # The last one under the name it always had; the earlier ones numbered in the order they ran.
    assert copied[f"{RUN}_manifest_segmentation.json"]["cache_status"] == {"snic_clusters": "hit"}
    assert copied[f"{RUN}_manifest_segmentation_2.json"]["metadata"] == {"distance_scale": 1.25}
    assert copied[f"{RUN}_manifest_segmentation_2.json"]["export_tasks"] == [{"task_id": "T1"}]
    assert copied[f"{RUN}_manifest_segmentation_1.json"]["metadata"] == {"n": 0}  # _tree's own pass
    # A kind run once is copied as before, under its one name.
    assert [n for n in done["in_repo"] if "_manifest_clustering" in n] == [f"{RUN}_manifest_clustering.json"]


def test_the_read_back_tools_comparison_is_copied_when_there_is_one(mod, tmp_path):
    """Since round 13 (review C30) the read-back tool writes <run>_read_back.json beside a run
    record the run wrote itself."""
    tree = _tree(tmp_path, big=10)
    dest = tmp_path / "dest"
    assert f"{RUN}_read_back.json" not in mod.copy(tree, RUN, dest, tmp_path / "off")["in_repo"]
    vec = tree / "odisha_script" / "phase2_vectors"
    (vec / f"{RUN}_read_back.json").write_text(json.dumps({"config": RUN, "read_back": {"by": "tool"}}))
    assert f"{RUN}_read_back.json" in mod.copy(tree, RUN, dest, tmp_path / "off")["in_repo"]
    assert json.loads((dest / f"{RUN}_read_back.json").read_text())["read_back"] == {"by": "tool"}


def test_the_features_pass_of_a_round_9_run_is_copied_too(mod, tmp_path):
    """Since round 9 a run's first pass caches the feature stages and ends at one of them."""
    tree = _tree(tmp_path, big=10)
    d = tree / "runs" / f"{RUN}_20261017_120000"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({
        "run_dir": str(d), "total_elapsed_sec": 3,
        "stages": [{"name": "masking", "elapsed_sec": 1.0}, {"name": "features_static", "elapsed_sec": 2.0}],
        "config": {"dates": {"radar": "2017"}}}))
    dest = tmp_path / "dest"
    done = mod.copy(tree, RUN, dest, tmp_path / "off")
    assert f"{RUN}_manifest_features.json" in done["in_repo"]
    copied = json.loads((dest / f"{RUN}_manifest_features.json").read_text())
    assert [s["name"] for s in copied["stages"]] == ["masking", "features_static"]
    assert "elapsed_sec" not in copied["stages"][0]



# ---------- round 14: what the brief asks kept, and a batch that stopped after the k elbow ----------


def _add_round_14_files(tree: Path) -> None:
    vec = tree / "odisha_script" / "phase2_vectors"
    for name in ("clustering_fit_rows.csv", "k_elbow.csv", "k_elbow_fit_rows.csv"):
        (vec / f"{RUN}_{name}").write_text("stand_lbl,in_fit\n1,1\n")
    (vec / f"{RUN}_drive_exports.json").write_text(json.dumps({"files": {"x": "COMPLETED"}}))
    (vec / f"{RUN}_drive_exports_run.json").write_text(json.dumps({"read_at": "2026-10-27T10:00:00Z"}))
    for d in sorted((tree / "runs").glob(f"{RUN}_2*")):
        (d / "fmu.log").write_text("2026-10-27 10:00:00 stage x done\n")
        (d / "input_images.json").write_text(json.dumps({"s2": ["20170103T050211_20170103T050848_T44QPF"]}))


def test_the_stage_files_the_logs_the_image_lists_and_the_drive_states_are_kept(mod, tmp_path):
    tree = _tree(tmp_path, 10)
    _add_round_14_files(tree)
    dest, off = tmp_path / "dest", tmp_path / "off"
    done = mod.copy(tree, RUN, dest, off)
    names = set(done["in_repo"])
    for n in ("clustering_fit_rows.csv", "k_elbow.csv", "k_elbow_fit_rows.csv", "drive_exports.json",
              "drive_exports_run.json", "log_segmentation.txt", "log_clustering.txt", "log_export.txt",
              "log_failed_1.txt", "input_images_segmentation.json"):
        assert f"{RUN}_{n}" in names, n
    # The read-back tool's own folder is no pass: its log is not kept.
    assert not any("profiling" in n for n in names)
    assert (dest / f"{RUN}_log_export.txt").read_text().startswith("2026-10-27")  # a log keeps its times


def test_a_batch_through_the_k_elbow_keeps_its_elbow_files_and_needs_no_layers(mod, tmp_path):
    tree = tmp_path / "tree"
    vec = tree / "odisha_script" / "phase2_vectors"
    vec.mkdir(parents=True)
    for name in ("k_elbow.csv", "k_elbow_stand_table.csv", "k_elbow_fit_rows.csv", "k_elbow_types.csv",
                 "k_elbow_preprocessing.json"):
        (vec / f"{RUN}_{name}").write_text("{}" if name.endswith(".json") else "k,wcss\n2,1.0\n")
    (vec / f"{RUN}_k_elbow_run.json").write_text(json.dumps({"run_dir": "runs/x_20261027_100000", "k_elbow": {}}))
    for i, last in enumerate(["features_static", "segmentation", "k_elbow"]):
        d = tree / "runs" / f"{RUN}_20261027_1000{i:02d}"
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps({"stages": [{"name": last}], "config": {}}))
    dest, off = tmp_path / "dest", tmp_path / "off"
    done = mod.copy(tree, RUN, dest, off, through="k_elbow")
    names = set(done["in_repo"])
    assert {f"{RUN}_manifest_{k}.json" for k in ("features", "segmentation", "k_elbow")} <= names
    assert f"{RUN}_k_elbow_fit_rows.csv" in names and f"{RUN}_k_elbow_run.json" in names
    assert "run_dir" not in json.loads((dest / f"{RUN}_k_elbow_run.json").read_text())
    assert not any(n.endswith(".geojson") for n in names)


def test_a_batch_through_the_k_elbow_without_its_elbow_pass_is_refused(mod, tmp_path):
    tree = tmp_path / "tree"
    vec = tree / "odisha_script" / "phase2_vectors"
    vec.mkdir(parents=True)
    (vec / f"{RUN}_k_elbow_run.json").write_text("{}")
    (vec / f"{RUN}_k_elbow_fit_rows.csv").write_text("stand_lbl\n")
    d = tree / "runs" / f"{RUN}_20261027_100000"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({"stages": [{"name": "segmentation"}], "config": {}}))
    with pytest.raises(SystemExit, match="k_elbow"):
        mod.copy(tree, RUN, tmp_path / "dest", tmp_path / "off", through="k_elbow")
