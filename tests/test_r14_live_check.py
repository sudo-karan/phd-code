"""odisha_script/r14_live_check.py, offline: round 14's live check of two runs made from scratch.

The round 14 brief, Task 4: run _r14_check_a and _r14_check_b from scratch in one batch; the check
passes only if the two runs give the same stands and types, feature values within 1e-9 relative
and identical elbows, distance_to_water no longer 10,000 m everywhere, 189 Sentinel-1 scenes,
slope and aspect with decimals, and the four new settings on.

The records of the two runs are made up here, small, in the form scripts/copy_run_results.py
copies them: the three stand layers, every pass's manifest (with the stage lists and the cache keys
fmu gives the two check configs), the tables of units, the scaled rows, the elbow and the types
written by fmu's own writers. Identical records pass every criterion; each criterion fails when
one of its inputs is changed in run b (distance_to_water in both runs, so that the two still
agree), and only that criterion. Earth Engine is a stand-in reader handed to main(); one test
checks that the script's own reader forbids writes before it reads. No Earth Engine call and no
network; the one test marked live_gee (not run by default) reads Earth Engine.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "odisha_script" / "r14_live_check.py"
RUN_A = "odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_a"
RUN_B = "odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_b"
# The second live check (Jaskaran's answer to question 11 of the round 14 record, 27 Oct 2026):
# the first stopped in the merge, so the check runs again from scratch as two more copies.
RUN_C = "odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_c"
RUN_D = "odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_d"
# The third (his answer to question 13, 27 Oct 2026): the second stopped in the k elbow's table
# export, so the check runs again from scratch as two more copies.
RUN_E = "odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_e"
RUN_F = "odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_f"
CONFIG_A = REPO / "configs" / f"{RUN_A}.yaml"
CONFIG_B = REPO / "configs" / f"{RUN_B}.yaml"
CONFIG_C = REPO / "configs" / f"{RUN_C}.yaml"
CONFIG_D = REPO / "configs" / f"{RUN_D}.yaml"
CONFIG_E = REPO / "configs" / f"{RUN_E}.yaml"
CONFIG_F = REPO / "configs" / f"{RUN_F}.yaml"
KINDS = ("features", "segmentation", "k_elbow", "clustering", "export")
OFFLINE = ("0_both_runs_from_scratch", "1_same_stands_and_types", "3_distance_to_water",
           "4_sentinel1_scenes", "6_four_settings_on")
GRID = {"crs": "EPSG:32645", "transform": [10.0, 0.0, 300000.0, 0.0, -10.0, 2300000.0]}


@pytest.fixture(autouse=True)
def _a_project(monkeypatch):
    """Asset paths name a project; this checkout has no .env, so one is set, and unset after."""
    from fmu.settings import get_settings

    monkeypatch.setenv("GEE_PROJECT_ID", "test-project")
    get_settings(force_reload=True)
    yield
    monkeypatch.delenv("GEE_PROJECT_ID", raising=False)
    get_settings(force_reload=True)


@pytest.fixture(scope="module")
def mod() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("r14_live_check", SCRIPT)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def configs() -> dict[str, Any]:
    from fmu.config import load_config

    return {run: load_config(REPO / "configs" / f"{run}.yaml")
            for run in (RUN_A, RUN_B, RUN_C, RUN_D, RUN_E, RUN_F)}


# ---------------------------------------------------------------------------
# Made-up records of the two runs
# ---------------------------------------------------------------------------


def _square(x0: float, y0: float, d: float = 0.001) -> dict[str, Any]:
    return {"type": "Polygon",
            "coordinates": [[[x0, y0], [x0 + d, y0], [x0 + d, y0 + d], [x0, y0 + d], [x0, y0]]]}


def _merged() -> dict[str, Any]:
    """Four polygons of three stands (stand 14 in two pieces), as the export pass reads them."""
    features = []
    for i, (label, cluster, water) in enumerate(((9, 2, 812.5), (14, 0, 10000.0), (14, 0, 10000.0),
                                                  (21, None, 431.25))):
        props = {
            "stand_lbl": label, "stand_id": i + 1, "cluster_id": cluster, "n_pixels": 10 + i,
            "area_ha": (10 + i) / 100, "perim_m": 120.5 + i, "centroid_lat": 20.8005 + i * 1e-3,
            "centroid_lon": 84.6005 + i * 2e-3, "n_superpx": 1 + i, "n_pass1": i, "n_relaxed": 0,
            "n_fallback": 0, "below_min": int(i == 3), "below_why": "isolated" if i == 3 else "",
            "ndvi_mean": 0.61 + i / 100, "ndvi_trend": -0.0183 * (i + 1), "slope": 3.25 + i,
            "aspect": 181.5 + i, "distance_to_water": water, "vv_p50": -13.5 + i,
        }
        features.append({"type": "Feature", "id": f"+{25 + i}+1020",
                         "geometry": _square(84.6 + i * 0.002, 20.8), "properties": props})
    return {"type": "FeatureCollection", "columns": [], "features": features}


def _snic() -> dict[str, Any]:
    features = []
    for i, label in enumerate((435526858, 435526990, 435527001)):
        props = {"snic_label": label, "stand_id": i + 1, "cluster_id": i % 2, "n_pixels": 9 + i,
                 "area_ha": (9 + i) / 100, "perim_m": 139.95, "centroid_lat": 20.83, "centroid_lon": 84.64,
                 "ndvi_mean": 0.69 - i / 50, "slope": 6.8 + i}
        features.append({"type": "Feature", "id": f"+{46 + i}+1024",
                         "geometry": _square(84.64 + i * 0.001, 20.83, 0.0005), "properties": props})
    return {"type": "FeatureCollection", "columns": [], "features": features}


def _dissolved() -> dict[str, Any]:
    features = []
    for i in range(2):
        props = {"unit_id": i + 1, "cluster_id": i, "n_pixels": 178 + i, "area_ha": (178 + i) / 100,
                 "perim_m": 1139.6, "centroid_lat": 20.83, "centroid_lon": 84.65,
                 "profile_ndvi_mean_p50": 0.6465 + i / 10}
        features.append({"type": "Feature", "id": f"+{108 + i}+1023",
                         "geometry": _square(84.648 + i * 0.01, 20.829, 0.004), "properties": props})
    return {"type": "FeatureCollection", "columns": [], "features": features}


def _stage_files() -> dict[str, str]:
    """The tables, rows, elbow and types, by fmu's own writers."""
    from fmu.stages.k_elbow import _elbow_csv, _types_csv
    from fmu.utils import stand_table as st

    table = st.StandTable(
        labels=np.array([9, 14, 21], dtype=np.int64), bands=["canopy_height", "ndvi_mean", "vv_p50"],
        values=np.array([[4.0, 0.0989449275732470, -13.509690292746992],
                         [18.25, 0.6908220017698279, -10.674951695643813],
                         [11.5, 0.6465022305105478, -8.407843901203725]]),
        in_fit=np.array([True, True, False]))
    pre = st.Preprocessed(bands=["canopy_height", "ndvi_mean"],
                          values=np.array([[-1.0, -1.12], [0.85, 0.27], [0.0, 0.0]]), record={})
    sweep = {"ks": [2, 3, 4], "inertia": [10.5, 6.25, 5.0], "ari_median": [1.0, 0.875, 0.75],
             "ari_min": [1.0, 0.5, 0.25], "elbow_k": 3, "types": [[0, 1, 0], [0, 1, 2], [3, 1, 2]]}
    return {
        "k_elbow.csv": _elbow_csv(sweep),
        "k_elbow_stand_table.csv": st.table_csv(table),
        "k_elbow_fit_rows.csv": st.rows_csv(table, pre),
        "k_elbow_types.csv": _types_csv(table, sweep, label_name="stand_lbl"),
        "clustering_stand_table.csv": st.table_csv(table),
        "clustering_fit_rows.csv": st.rows_csv(table, pre, types=np.array([1, 0, 1])),
    }


def _stage_names(cfg: Any, kind: str) -> list[str]:
    """The stages of a pass, as odisha_script/odisha_phase2_2_run_pipeline.py's stage_names."""
    from fmu.pipeline import default_stage_names, feature_stage_names, segmentation_stage_names

    if kind == "features":
        return feature_stage_names(cfg)
    if kind == "segmentation":
        return segmentation_stage_names(cfg)
    return default_stage_names(cfg, through=kind)


def _manifests(mod: types.ModuleType, cfg: Any) -> dict[str, dict[str, Any]]:
    """One manifest of each kind, as a batch from scratch writes them: each stage computed and
    exported in the first pass that runs it, read from the cache after."""
    from fmu.utils.caching import cache_key

    seen: set[str] = set()
    out = {}
    for kind in KINDS:
        stages = []
        for name in _stage_names(cfg, kind):
            outputs = sorted(mod.cacheable_outputs(name))
            new = name not in seen
            seen.add(name)
            entry: dict[str, Any] = {
                "name": name, "produced": outputs, "warnings": [], "metadata": {},
                "cache_status": {o: "miss-exported" if new else "hit" for o in outputs},
                "cache_key": cache_key(cfg, name, "per_step") if outputs else None,
                "export_tasks": [], "transparency": {}, "input_images": {},
            }
            if name == "features_radar":
                entry["input_images"] = {"radar_features": {
                    "source": "computed in this run" if new else "the cached asset",
                    "collections": {"s1": {"count": 189, "sha256": "4f2a", "ids": None}}}}
            stages.append(entry)
        out[kind] = {"config_name": cfg.name, "use_cache": True, "submit_exports": True,
                     "summaries": True, "cache_layout": "per_step",
                     "cache_layout_reason": "its cache holds no asset of the legacy layout",
                     "git": {"commit": "55cc992", "dirty": False}, "stages": stages,
                     "config": cfg.model_dump(mode="json")}
    return out


def _write(folder: Path, mod: types.ModuleType, configs: dict[str, Any],
           runs: tuple[str, str] = (RUN_A, RUN_B)) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    files = _stage_files()
    for run in runs:
        for layer, build in (("stands_merged", _merged), ("stands_snic", _snic),
                             ("stands_dissolved", _dissolved)):
            (folder / f"{run}_{layer}.geojson").write_text(json.dumps(build()))
        for name, text in files.items():
            (folder / f"{run}_{name}").write_text(text)
        for kind, manifest in _manifests(mod, configs[run]).items():
            (folder / f"{run}_manifest_{kind}.json").write_text(json.dumps(manifest, indent=1) + "\n")
        (folder / f"{run}_log_features.txt").write_text("a log of a pass that did not fail\n")
    return folder


@pytest.fixture
def records(tmp_path: Path, mod, configs) -> Path:
    return _write(tmp_path / "live_check", mod, configs)


def _edit_json(path: Path, change: Callable[[Any], None]) -> None:
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))


def _b(records: Path, name: str) -> Path:
    return records / f"{RUN_B}_{name}"


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    (entry,) = [s for s in manifest["stages"] if s["name"] == name]
    return entry


def _run(mod, records: Path, *extra: str, reader: Any = None) -> tuple[int, dict[str, Any] | None]:
    argv = ["--records", str(records), "--config-a", str(CONFIG_A), "--config-b", str(CONFIG_B), *extra]
    if reader is None:
        argv.append("--offline")
        code = mod.main(argv)
    else:
        code = mod.main(argv, reader=lambda: reader)
    out = records / "r14_live_check.json"
    return code, (json.loads(out.read_text()) if out.exists() else None)


def _passes(result: dict[str, Any]) -> dict[str, Any]:
    return {name: c["passes"] for name, c in result["criteria"].items()}


# ---------------------------------------------------------------------------
# Identical records
# ---------------------------------------------------------------------------


def test_identical_records_pass_every_offline_criterion(mod, records):
    code, result = _run(mod, records)
    assert result is not None
    assert code == 2 and result["passes"] == "not run"
    passes = _passes(result)
    assert {name: passes[name] for name in OFFLINE} == dict.fromkeys(OFFLINE, True)
    # The Earth Engine parts are not run offline; criterion 2's other parts pass.
    assert passes["5_slope_and_aspect_decimals"] == "not run"
    values = result["criteria"]["2_feature_values_and_elbows"]
    assert values["passes"] == "not run" and values["iii_cached_assets"] == {"passes": "not run"}
    assert all(values[p]["passes"] is True for p in ("i_tables_of_units",
                                                     "ii_feature_means_of_stands_merged", "elbows"))
    # What the numbers say.
    stands = result["criteria"]["1_same_stands_and_types"]["stands_merged"]
    assert stands["polygons"] == [4, 4] and stands["distinct_stand_lbl"] == [3, 3]
    assert stands["pairs"] == 4 and stands["canonical_sha256"][0] == stands["canonical_sha256"][1]
    water = result["criteria"]["3_distance_to_water"]["runs"][RUN_A]
    assert (water["exactly_10000"], water["distinct_values"], water["least"], water["greatest"]) == (
        2, 3, 431.25, 10000.0)
    scratch = result["criteria"]["0_both_runs_from_scratch"]["runs"][RUN_A]["first_manifests"]
    assert scratch["segmentation"]["stages_it_adds"] == ["segmentation"]
    assert scratch["k_elbow"]["stages_it_adds"] == ["merge", "k_elbow"]
    assert scratch["clustering"]["computed_in_it"] == ["clustering/cluster_labels",
                                                       "clustering/feature_stack"]
    assert "masking/habitat_mask" in scratch["features"]["computed_in_it"]
    assert result["criteria"]["2_feature_values_and_elbows"]["elbows"]["k_elbow.csv"]["knee"] == [3, 3]


def test_the_second_live_check_judges_check_c_and_check_d_by_the_same_rules(mod, tmp_path, configs):
    """The first live check stopped in the merge, and by Jaskaran's answer to question 11 of the
    round 14 record (27 Oct 2026) it runs again from scratch as _r14_check_c and _r14_check_d.
    The script judges them by the same rules, given with --config-a and --config-b and a records
    folder of their own: identical records under their names pass every offline criterion, and
    the results name the two runs."""
    records = _write(tmp_path / "live_check_cd", mod, configs, runs=(RUN_C, RUN_D))
    argv = ["--records", str(records), "--config-a", str(CONFIG_C), "--config-b", str(CONFIG_D),
            "--offline"]
    assert mod.main(argv) == 2
    result = json.loads((records / "r14_live_check.json").read_text())
    assert result["runs"] == [RUN_C, RUN_D]
    passes = _passes(result)
    assert {name: passes[name] for name in OFFLINE} == dict.fromkeys(OFFLINE, True)
    assert set(result["criteria"]["0_both_runs_from_scratch"]["runs"]) == {RUN_C, RUN_D}


def test_the_third_live_check_judges_check_e_and_check_f_by_the_same_rules(mod, tmp_path, configs):
    """The second live check stopped in the k elbow's table export, and by Jaskaran's answer to
    question 13 of the round 14 record (27 Oct 2026) it runs again from scratch as _r14_check_e
    and _r14_check_f, judged as the second was."""
    records = _write(tmp_path / "live_check_ef", mod, configs, runs=(RUN_E, RUN_F))
    argv = ["--records", str(records), "--config-a", str(CONFIG_E), "--config-b", str(CONFIG_F),
            "--offline"]
    assert mod.main(argv) == 2
    result = json.loads((records / "r14_live_check.json").read_text())
    assert result["runs"] == [RUN_E, RUN_F]
    passes = _passes(result)
    assert {name: passes[name] for name in OFFLINE} == dict.fromkeys(OFFLINE, True)
    assert set(result["criteria"]["0_both_runs_from_scratch"]["runs"]) == {RUN_E, RUN_F}


def test_the_smoke_tests_records_fail_criterion_0_and_only_it(mod, tmp_path, configs):
    """The smoke test before the third live check (his answer to question 13) finishes _check_c and
    _check_d from the features and segmentation the second batch cached: every output of their
    passes is a hit, so criterion 0 (both runs from scratch) fails, as the smoke test's declaration
    says it must, and the check with it. Identical records still pass every other offline
    criterion, which is what the smoke test reads of them."""
    records = _write(tmp_path / "smoke_test", mod, configs, runs=(RUN_C, RUN_D))
    for run in (RUN_C, RUN_D):
        for kind in ("features", "segmentation"):
            def read_back(manifest: dict[str, Any]) -> None:
                for stage in manifest["stages"]:
                    stage["cache_status"] = dict.fromkeys(stage["cache_status"], "hit")
                    for record in stage["input_images"].values():
                        record["source"] = "the cached asset"
            _edit_json(records / f"{run}_manifest_{kind}.json", read_back)
    argv = ["--records", str(records), "--config-a", str(CONFIG_C), "--config-b", str(CONFIG_D),
            "--offline"]
    assert mod.main(argv) == 1
    result = json.loads((records / "r14_live_check.json").read_text())
    assert result["passes"] is False
    passes = _passes(result)
    assert passes["0_both_runs_from_scratch"] is False
    assert {name: passes[name] for name in OFFLINE[1:]} == dict.fromkeys(OFFLINE[1:], True)
    first = result["criteria"]["0_both_runs_from_scratch"]["runs"][RUN_C]["first_manifests"]
    assert "masking/habitat_mask" not in first["features"]["computed_in_it"]


def test_the_results_hold_no_times_and_the_run_record_says_how_it_was_made(mod, records):
    _run(mod, records)
    out = records / "r14_live_check.json"
    mod.results_only(json.loads(out.read_text()))  # raises on a time key or a date and time
    run = json.loads((records / "r14_live_check_run.json").read_text())
    assert run["result_file"] == "r14_live_check.json"
    assert run["command_line"].startswith("python odisha_script/r14_live_check.py --records ")
    assert run["ran_at"].endswith("Z") and run["offline"] is True
    assert set(run["git"]) >= {"commit", "dirty"} and "root" not in run["git"]
    assert f"{RUN_B}_stands_merged.geojson" in run["files_read_sha256"]
    with pytest.raises(SystemExit, match="times"):
        mod.results_only({"criteria": {"started": 1}})


def test_an_existing_result_is_refused_unless_overwrite_and_a_second_check_writes_the_same(mod, records):
    argv = ["--records", str(records), "--config-a", str(CONFIG_A), "--config-b", str(CONFIG_B),
            "--offline"]
    assert mod.main(argv) == 2
    out, run = records / "r14_live_check.json", records / "r14_live_check_run.json"
    first = out.read_text()
    out.write_text("an earlier result\n")
    assert mod.main(argv) == 3 and out.read_text() == "an earlier result\n"
    assert mod.main([*argv, "--overwrite"]) == 2 and out.read_text() == first
    # The run record alone there is refused too.
    out.unlink()
    assert mod.main(argv) == 3 and not out.exists() and run.exists()


def test_no_records_folder_is_refused(mod, tmp_path):
    code = mod.main(["--records", str(tmp_path / "none"), "--offline"])
    assert code == 3 and not (tmp_path / "none").exists()


# ---------------------------------------------------------------------------
# Each criterion fails when its input is changed, and only it
# ---------------------------------------------------------------------------


def _move_a_vertex(records: Path) -> None:
    def change(gj):
        gj["features"][1]["geometry"]["coordinates"][0][2][0] += 1e-9
    _edit_json(_b(records, "stands_merged.geojson"), change)


def _retype_a_stand(records: Path) -> None:
    def change(gj):
        gj["features"][0]["properties"]["cluster_id"] = 3
    _edit_json(_b(records, "stands_merged.geojson"), change)


def _retype_a_fit_row(records: Path) -> None:
    path = _b(records, "clustering_fit_rows.csv")
    lines = path.read_text().splitlines()
    head, first = lines[0].split(","), lines[1].split(",")
    first[head.index("type")] = "4"
    lines[1] = ",".join(first)
    path.write_text("\n".join(lines) + "\n")


def _a_band_value_in_a_table(records: Path) -> None:
    path = _b(records, "k_elbow_stand_table.csv")
    lines = path.read_text().splitlines()
    row = lines[2].split(",")
    row[3] = format(float(row[3]) * (1 + 1e-6), ".17g")
    lines[2] = ",".join(row)
    path.write_text("\n".join(lines) + "\n")


def _a_feature_mean(records: Path) -> None:
    def change(gj):
        gj["features"][2]["properties"]["ndvi_mean"] *= 1 + 1e-6
    _edit_json(_b(records, "stands_merged.geojson"), change)


def _a_byte_of_the_elbow(records: Path) -> None:
    path = _b(records, "k_elbow.csv")
    text = path.read_text()
    assert "0.875" in text
    path.write_text(text.replace("0.875", "0.876"))


def _every_stand_at_the_cap(records: Path) -> None:
    """In both runs, so that the two still agree (criterion 2 ii) and only criterion 3 fails."""
    def change(gj):
        for f in gj["features"]:
            f["properties"]["distance_to_water"] = 10000
    for run in (RUN_A, RUN_B):
        _edit_json(records / f"{run}_stands_merged.geojson", change)


def _188_scenes(records: Path) -> None:
    def change(m):
        _stage(m, "features_radar")["input_images"]["radar_features"]["collections"]["s1"]["count"] = 188
    _edit_json(_b(records, "manifest_features.json"), change)


def _a_setting_off(records: Path) -> None:
    def change(m):
        m["config"]["k_elbow"]["in_fit_space"] = False
    _edit_json(_b(records, "manifest_export.json"), change)


def _a_hit_in_a_first_pass(records: Path) -> None:
    def change(m):
        _stage(m, "segmentation")["cache_status"]["snic_clusters"] = "hit"
    _edit_json(_b(records, "manifest_segmentation.json"), change)


PERTURBED = {
    "a polygon's geometry": (_move_a_vertex, "1_same_stands_and_types"),
    "a stand's cluster_id": (_retype_a_stand, "1_same_stands_and_types"),
    "a type in the fit rows": (_retype_a_fit_row, "1_same_stands_and_types"),
    "a band value of a table, 1e-6 relative": (_a_band_value_in_a_table, "2_feature_values_and_elbows"),
    "a feature mean of a stand, 1e-6 relative": (_a_feature_mean, "2_feature_values_and_elbows"),
    "a byte of k_elbow.csv": (_a_byte_of_the_elbow, "2_feature_values_and_elbows"),
    "every distance_to_water 10000": (_every_stand_at_the_cap, "3_distance_to_water"),
    "an s1 count of 188": (_188_scenes, "4_sentinel1_scenes"),
    "a setting off": (_a_setting_off, "6_four_settings_on"),
    "a hit in a first pass": (_a_hit_in_a_first_pass, "0_both_runs_from_scratch"),
}


@pytest.mark.parametrize("what", list(PERTURBED))
def test_each_criterion_fails_when_its_input_is_changed_and_only_it(mod, records, what):
    perturb, failing = PERTURBED[what]
    perturb(records)
    code, result = _run(mod, records)
    assert result is not None
    assert code == 1 and result["passes"] is False
    passes = _passes(result)
    assert passes[failing] is False, what
    others = {n: passes[n] for n in OFFLINE if n != failing}
    assert others == dict.fromkeys(others, True), what
    if failing != "2_feature_values_and_elbows":
        assert passes["2_feature_values_and_elbows"] == "not run", what


def test_the_failures_are_said_where_they_are(mod, records):
    _a_band_value_in_a_table(records)
    _a_hit_in_a_first_pass(records)
    _188_scenes(records)
    _a_setting_off(records)
    _, result = _run(mod, records)
    assert result is not None
    table = result["criteria"]["2_feature_values_and_elbows"]["i_tables_of_units"]["k_elbow_stand_table.csv"]
    assert table["values_not_agreeing"] == 1 and table["in_band"] == "ndvi_mean"
    assert table["largest_relative_difference"] == pytest.approx(1e-6, rel=1e-3)
    # The clustering stage's table was not changed.
    assert result["criteria"]["2_feature_values_and_elbows"]["i_tables_of_units"][
        "clustering_stand_table.csv"]["passes"] is True
    seg = result["criteria"]["0_both_runs_from_scratch"]["runs"][RUN_B]["first_manifests"]["segmentation"]
    assert seg["not_computed_in_it"] == [{"output": "segmentation/snic_clusters", "cache_status": "hit"}]
    s1 = result["criteria"]["4_sentinel1_scenes"]["runs"][RUN_B]
    assert s1["counts"] == [188, 189]
    off = result["criteria"]["6_four_settings_on"]["runs"][RUN_B]["settings_not_on"]
    assert off == [{"manifest": f"{RUN_B}_manifest_export.json", "setting": "k_elbow.in_fit_space",
                    "value": False}]


def test_stands_snic_and_dissolved_are_reported_and_not_part_of_the_pass(mod, records):
    def change(gj):
        gj["features"][0]["geometry"]["coordinates"][0][1][0] += 1e-9
    _edit_json(_b(records, "stands_snic.geojson"), change)
    _edit_json(_b(records, "stands_dissolved.geojson"), change)
    code, result = _run(mod, records)
    assert result is not None and code == 2
    stands = result["criteria"]["1_same_stands_and_types"]
    assert stands["passes"] is True
    for layer in ("stands_snic", "stands_dissolved"):
        assert stands[layer]["geometry_differs"] == 1 and stands[layer]["passes"] is False
        assert stands[layer]["part_of_the_pass"] is False


# ---------------------------------------------------------------------------
# 1: a geometry is compared in normal form
# ---------------------------------------------------------------------------


def _ring(points: list[tuple[float, float]]) -> list[list[float]]:
    return [list(p) for p in points] + [list(points[0])]


OUTER = [(84.6, 20.8), (84.61, 20.8), (84.61, 20.81), (84.6, 20.81)]
HOLE_1 = [(84.601, 20.801), (84.601, 20.802), (84.602, 20.802), (84.602, 20.801)]
HOLE_2 = [(84.605, 20.805), (84.605, 20.806), (84.606, 20.806), (84.606, 20.805)]
APART = [(84.62, 20.8), (84.63, 20.8), (84.63, 20.81), (84.62, 20.81)]
WITH_HOLES = {"type": "Polygon", "coordinates": [_ring(OUTER), _ring(HOLE_1), _ring(HOLE_2)]}
IN_PARTS = {"type": "MultiPolygon", "coordinates": [[_ring(OUTER), _ring(HOLE_1)], [_ring(APART)]]}
LISTED_OTHERWISE = {
    "the holes in another order": (
        WITH_HOLES, {"type": "Polygon", "coordinates": [_ring(OUTER), _ring(HOLE_2), _ring(HOLE_1)]}),
    "a ring started at another vertex": (
        WITH_HOLES, {"type": "Polygon", "coordinates": [_ring(OUTER[2:] + OUTER[:2]), _ring(HOLE_1),
                                                        _ring(HOLE_2)]}),
    "a ring turned the other way": (
        WITH_HOLES, {"type": "Polygon", "coordinates": [_ring(OUTER[::-1]), _ring(HOLE_1), _ring(HOLE_2)]}),
    "the parts in another order": (
        IN_PARTS, {"type": "MultiPolygon", "coordinates": [[_ring(APART)], [_ring(OUTER), _ring(HOLE_1)]]}),
}


def _set_geometry(path: Path, index: int, geometry: dict[str, Any]) -> None:
    def change(gj):
        gj["features"][index]["geometry"] = copy.deepcopy(geometry)
    _edit_json(path, change)


@pytest.mark.parametrize("what", list(LISTED_OTHERWISE))
def test_one_polygon_listed_otherwise_in_the_two_runs_is_the_same_stand(mod, records, what):
    """Earth Engine lists a polygon's holes, and a multipolygon's parts, in an order that differs
    between two from-scratch runs (round 9's two runs, below): a geometry is compared in normal
    form, which changes no coordinate."""
    in_a, in_b = LISTED_OTHERWISE[what]
    _set_geometry(records / f"{RUN_A}_stands_merged.geojson", 1, in_a)
    _set_geometry(_b(records, "stands_merged.geojson"), 1, in_b)
    code, result = _run(mod, records)
    assert result is not None and code == 2
    stands = result["criteria"]["1_same_stands_and_types"]
    merged = stands["stands_merged"]
    assert stands["passes"] is True and merged["passes"] is True
    assert (merged["geometry_differs"], merged["geometry_differs_as_read"]) == (0, 1)
    assert merged["same_canonical_sha256"] is True


def test_a_moved_vertex_of_a_hole_is_another_stand(mod, records):
    moved = copy.deepcopy(WITH_HOLES)
    moved["coordinates"][2][1][1] += 1e-9
    _set_geometry(records / f"{RUN_A}_stands_merged.geojson", 1, WITH_HOLES)
    _set_geometry(_b(records, "stands_merged.geojson"), 1, moved)
    code, result = _run(mod, records)
    assert result is not None and code == 1
    merged = result["criteria"]["1_same_stands_and_types"]["stands_merged"]
    assert merged["geometry_differs"] == 1 and merged["same_canonical_sha256"] is False
    assert merged["passes"] is False


ROUND9 = REPO / "docs" / "reproducibility" / "round9_cache_test"
R9 = "odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r9"


@pytest.mark.parametrize("layer, listed_otherwise", [("stands_merged", 4), ("stands_dissolved", 9)])
def test_round_9s_two_runs_from_scratch_have_the_same_polygons_in_normal_form(mod, layer, listed_otherwise):
    """Round 9's two from-scratch runs of one Kendujhar config, their labels the same pixel for
    pixel (docs/reproducibility/round9_cache_test/): as read, a few polygons list their holes or
    parts in another order; in normal form none differs, and the merged layers are the same stands.
    (Their dissolved layers' area_ha came from the geometry's area() then, and differ by up to
    1.02e-8 relative; since round 13 it is the pixel count's.)"""
    a = json.loads((ROUND9 / f"{R9}_{layer}.geojson").read_text())
    b = json.loads((ROUND9 / f"{R9}_check_{layer}.geojson").read_text())
    got = mod.compare_layer(a, b, layer)
    assert got["geometry_differs_as_read"] == listed_otherwise
    assert got["geometry_differs"] == 0 and got["same_canonical_sha256"] is True
    assert got["n_pixels_differs"] == got["cluster_id_differs"] == 0
    if layer == "stands_merged":
        assert got["pairs"] == 547 and got["area_ha_differs"] == 0 and got["passes"] is True


# ---------------------------------------------------------------------------
# 0: the first pass of each kind
# ---------------------------------------------------------------------------


def _first_features_with_masking_hits(records: Path) -> None:
    """Run b's features pass ran twice: the first failed (no manifest) after exporting masking's
    outputs, the second read them back and computed the rest."""
    def change(m):
        masking = _stage(m, "masking")
        masking["cache_status"] = dict.fromkeys(masking["cache_status"], "hit")
    _edit_json(_b(records, "manifest_features.json"), change)


def _failed_log(records: Path, configs: dict[str, Any], outputs: list[str]) -> None:
    from fmu.utils.caching import cache_key

    key = cache_key(configs[RUN_B], "masking", "per_step")
    lines = ["2026-10-27 10:00:00 INFO stage: masking"]
    lines += [f"2026-10-27 10:00:01 INFO Started cache export to projects/test-project/assets/fmu/"
              f"{RUN_B}/masking/{o}__{key} (task T{i}). Check progress at "
              f"https://code.earthengine.google.com/tasks" for i, o in enumerate(outputs)]
    lines.append("2026-10-27 10:05:00 ERROR stage features_optical FAILED after 3.00 sec: timeout")
    _b(records, "log_failed_1.txt").write_text("\n".join(lines) + "\n")


def test_a_hit_on_an_asset_a_failed_pass_of_the_run_exported_is_accepted(mod, records, configs):
    _first_features_with_masking_hits(records)
    outputs = ["habitat_mask", "landcover_summary", "mask_provenance", "water_mask"]
    _failed_log(records, configs, outputs)
    _, result = _run(mod, records)
    assert result is not None
    run_b = result["criteria"]["0_both_runs_from_scratch"]["runs"][RUN_B]
    assert run_b["passes"] is True
    assert [h["output"] for h in run_b["hits_made_by_a_failed_pass"]] == [f"masking/{o}" for o in outputs]
    assert {h["exported_by"] for h in run_b["hits_made_by_a_failed_pass"]} == {f"{RUN_B}_log_failed_1.txt"}


def test_a_hit_with_no_failed_pass_that_exported_it_fails(mod, records, configs):
    _first_features_with_masking_hits(records)
    _failed_log(records, configs, ["habitat_mask", "landcover_summary", "mask_provenance"])
    _, result = _run(mod, records)
    assert result is not None
    run_b = result["criteria"]["0_both_runs_from_scratch"]["runs"][RUN_B]
    assert run_b["passes"] is False
    assert run_b["first_manifests"]["features"]["not_computed_in_it"] == [
        {"output": "masking/water_mask", "cache_status": "hit"}]


def test_the_first_manifest_of_a_kind_is_the_first_numbered_one(mod, records):
    """A pass run twice: the records keep the earlier as _1 and the last without a number."""
    first = _b(records, "manifest_clustering.json")
    retry = json.loads(first.read_text())
    _stage(retry, "clustering")["cache_status"] = {"cluster_labels": "hit", "feature_stack": "hit"}
    first.rename(_b(records, "manifest_clustering_1.json"))
    first.write_text(json.dumps(retry))
    _, result = _run(mod, records)
    assert result is not None
    run_b = result["criteria"]["0_both_runs_from_scratch"]["runs"][RUN_B]
    assert run_b["passes"] is True
    assert run_b["first_manifests"]["clustering"]["manifest"] == f"{RUN_B}_manifest_clustering_1.json"
    # Swapped, the first one read its outputs from the cache: not from scratch.
    swapped = json.loads(_b(records, "manifest_clustering_1.json").read_text())
    _b(records, "manifest_clustering_1.json").write_text(json.dumps(retry))
    _b(records, "manifest_clustering.json").write_text(json.dumps(swapped))
    _, result = _run(mod, records, "--overwrite")
    assert result is not None
    assert result["criteria"]["0_both_runs_from_scratch"]["runs"][RUN_B]["passes"] is False


def test_a_missing_pass_or_a_second_cache_key_fails(mod, records):
    _b(records, "manifest_k_elbow.json").unlink()
    _, result = _run(mod, records)
    assert result is not None
    run_b = result["criteria"]["0_both_runs_from_scratch"]["runs"][RUN_B]
    assert run_b["first_manifests"]["k_elbow"] == {"manifest": None, "passes": False}
    assert run_b["passes"] is False

    def change(m):
        _stage(m, "data_load")["cache_key"] = "s0000000000"
    _edit_json(records / f"{RUN_A}_manifest_export.json", change)
    _, result = _run(mod, records, "--overwrite")
    assert result is not None
    run_a = result["criteria"]["0_both_runs_from_scratch"]["runs"][RUN_A]
    assert run_a["passes"] is False and run_a["one_layout_and_one_key_per_stage"] is False
    assert run_a["stages_with_more_than_one_cache_key"][0]["stage"] == "data_load"


def test_a_missing_cache_status_fails(mod, records):
    """A stage of the pass that records no status for an output fmu says it caches."""
    def change(m):
        _stage(m, "segmentation")["cache_status"] = {}
    _edit_json(_b(records, "manifest_segmentation.json"), change)
    _, result = _run(mod, records)
    assert result is not None
    seg = result["criteria"]["0_both_runs_from_scratch"]["runs"][RUN_B]["first_manifests"]["segmentation"]
    assert seg["not_computed_in_it"] == [{"output": "segmentation/snic_clusters", "cache_status": None},
                                         {"output": "segmentation/snic_means", "cache_status": None}]


# ---------------------------------------------------------------------------
# Missing and off-git files
# ---------------------------------------------------------------------------


def test_a_missing_file_fails_the_criteria_that_need_it(mod, records):
    _b(records, "stands_merged.geojson").unlink()
    code, result = _run(mod, records)
    assert result is not None and code == 1
    passes = _passes(result)
    assert passes["1_same_stands_and_types"] is False
    assert passes["2_feature_values_and_elbows"] is False
    assert passes["3_distance_to_water"] is False
    assert "not in the records" in result["criteria"]["3_distance_to_water"]["runs"][RUN_B]["missing"]
    assert passes["0_both_runs_from_scratch"] is True and passes["6_four_settings_on"] is True


def test_a_layer_off_git_is_read_from_where_its_record_says_and_checked(mod, records, tmp_path):
    import hashlib

    name = f"{RUN_B}_stands_merged.geojson"
    off = tmp_path / "off_git"
    off.mkdir()
    data = (records / name).read_bytes()
    (off / name).write_bytes(data)
    (records / name).unlink()
    record = {"what": "made up", "files": [{"file": name, "bytes": len(data),
                                            "sha256": hashlib.sha256(data).hexdigest(),
                                            "where": str((off / name).resolve())}]}
    (records / f"{RUN_B}_files_off_git.json").write_text(json.dumps(record))
    code, result = _run(mod, records)
    assert result is not None and code == 2
    assert _passes(result)["1_same_stands_and_types"] is True
    # Not the file its record names: the criteria that need it fail.
    (off / name).write_bytes(data.replace(b"812.5", b"812.6"))
    code, result = _run(mod, records, "--overwrite")
    assert result is not None and code == 1
    assert "not the one its off-git record names" in (
        result["criteria"]["3_distance_to_water"]["runs"][RUN_B]["missing"])


# ---------------------------------------------------------------------------
# The rule for two numbers, at its edges
# ---------------------------------------------------------------------------


def test_the_relative_rule_at_its_edge(mod):
    # 1e9 and 1e9 + 1 differ by 1, within 1e-9 x (1e9 + 1); 1e9 + 2 by 2, outside.
    assert mod.agree(1e9, 1e9 + 1) and mod.agree(1e9 + 1, 1e9)
    assert not mod.agree(1e9, 1e9 + 2)
    # 1e-9 relative on a value of 1, just inside and just outside.
    assert mod.agree(1.0, 1.0 + 0.999e-9) and not mod.agree(1.0, 1.0 + 1.001e-9)
    assert not mod.agree(-3.5, -3.5 * (1 + 1e-6))
    assert mod.relative_difference(1e9, 1e9 + 2) == pytest.approx(2 / (1e9 + 2))


def test_the_absolute_floor_at_its_edge(mod):
    # Near 0 the relative rule alone fails any difference; the floor is 1e-12.
    assert mod.agree(0.0, 1e-12) and mod.agree(5e-13, -5e-13) and mod.agree(-1e-15, 1e-15)
    assert not mod.agree(0.0, 1.01e-12) and not mod.agree(0.0, 2e-12)
    assert mod.relative_difference(0.0, 1e-12) == 0.0 and mod.relative_difference(0.0, 2e-12) == 1.0


def test_nulls_nans_and_other_values(mod):
    assert mod.agree(None, None) and not mod.agree(None, 0.0) and not mod.agree(0, None)
    assert mod.agree(float("nan"), float("nan")) and not mod.agree(float("nan"), 1.0)
    assert mod.agree(3, 3.0) and mod.agree("isolated", "isolated") and not mod.agree("", "isolated")
    assert not mod.agree(True, 1)  # a bool is not a number here


def test_combine_is_false_then_not_run_then_true(mod):
    assert mod.combine([True, True]) is True
    assert mod.combine([True, "not run"]) == "not run"
    assert mod.combine(["not run", False, True]) is False
    assert [mod.exit_code(v) for v in (True, False, "not run")] == [0, 1, 2]


# ---------------------------------------------------------------------------
# The Earth Engine parts, with a stand-in reader
# ---------------------------------------------------------------------------


class StandIn:
    """A stand-in for EarthEngineReader: every pair of assets alike, unless told otherwise."""

    def __init__(self, *, layout: str = "per_step", change: dict[str, Callable[[dict], None]] | None = None,
                 values: list[list[Any]] | None = None):
        self.layout = layout
        self.change = change or {}
        self.values = values if values is not None else [[3.25, 181.5]] * 5000
        self.compared: list[tuple[str, str, str, bool]] = []
        self.sampled: list[tuple[Any, ...]] = []
        self.forbidden = ["ee.batch.Task.start"]

    def cache_layout(self, config: Any) -> str:
        return self.layout

    def compare(self, path_a: str, path_b: str, *, roi_file: str, label_like: bool) -> dict[str, Any]:
        self.compared.append((path_a, path_b, roi_file, label_like))
        bands = ["b1", "b2"]
        per: dict[str, dict[str, Any]]
        if label_like:
            per = {b: {"n_compared": 100, "n_differ": 0, "n_mask_differs": 0} for b in bands}
        else:
            per = {b: {"n_compared": 100, "n_not_agreeing": 0, "largest_relative_difference": 0.0,
                       "largest_abs_difference": 0.0, "n_mask_differs": 0} for b in bands}
        got = {"bands_a": bands, "bands_b": list(bands), "grid_a": dict(GRID),
               "grid_b": copy.deepcopy(GRID), "per_band": per}
        stage, leaf = path_a.split("/")[-2:]
        output = f"{stage}/{leaf.split('__')[0]}"
        if output in self.change:
            self.change[output](got)
        return got

    def sample(self, path: str, *, roi_file: str, bands: Any, n: int, asked: int, seed: int) -> list[list[Any]]:
        self.sampled.append((path, tuple(bands), n, asked, seed))
        return self.values


def test_with_earth_engine_alike_the_check_passes(mod, records, configs):
    from fmu.utils.caching import cache_key, cached_asset_path

    reader = StandIn()
    code, result = _run(mod, records, reader=reader)
    assert result is not None
    assert code == 0 and result["passes"] is True
    assert set(_passes(result).values()) == {True}
    # fmu's paths of the two configs' assets, every asset of 2 iii, on config a's ROI.
    expected = [
        tuple(cached_asset_path(configs[run].name, stage, key, cache_key(configs[run], stage, "per_step"))
              for run in (RUN_A, RUN_B)) + (configs[RUN_A].roi.roi_file, label_like)
        for stage, key, label_like in mod.ASSETS
    ]
    assert reader.compared == expected
    assert len(expected) == 13 and expected[0][0].startswith(f"projects/test-project/assets/fmu/{RUN_A}/")
    # 5: check_a's static features, 5,000 of 10,000 pixels asked for, a fixed seed.
    static = cached_asset_path(RUN_A, "features_static", "static_features",
                               cache_key(configs[RUN_A], "features_static", "per_step"))
    assert reader.sampled == [(static, ("slope", "aspect"), 5000, 10_000, 42)]
    five = result["criteria"]["5_slope_and_aspect_decimals"]
    assert (five["pixels_with_slope_above_0"], five["slope_with_decimals"]) == (5000, 5000)
    assert five["aspect_with_decimals"] == 5000
    run = json.loads((records / "r14_live_check_run.json").read_text())
    assert run["offline"] is False and run["earth_engine_writes_forbidden"] == ["ee.batch.Task.start"]


def _set(name: str, value: Any, band: str = "b2") -> Callable[[dict], None]:
    def change(got: dict) -> None:
        got["per_band"][band][name] = value
    return change


def _other_grid(got: dict) -> None:
    got["grid_b"]["transform"][2] += 5.0


def _other_bands(got: dict) -> None:
    got["bands_b"] = ["b1", "b3"]


def _not_cached(got: dict) -> None:
    got.clear()
    got["missing"] = ["projects/test-project/assets/fmu/x"]


def _nothing_compared(got: dict) -> None:
    for per in got["per_band"].values():
        per["n_compared"] = 0


EARTH_ENGINE_FAILURES = {
    "a value outside the tolerance": ("features_static/static_features", _set("n_not_agreeing", 1)),
    "a pixel whose mask differs": ("data_load/s2_composite", _set("n_mask_differs", 3, "b1")),
    "a label that differs": ("segmentation/snic_clusters", _set("n_differ", 1)),
    "a mask that differs, of labels": ("masking/habitat_mask", _set("n_mask_differs", 1)),
    "another grid": ("clustering/feature_stack", _other_grid),
    "other bands": ("features_radar/radar_features", _other_bands),
    "an asset not cached": ("clustering/cluster_labels", _not_cached),
    "no pixel compared": ("segmentation/snic_means", _nothing_compared),
}


@pytest.mark.parametrize("what", list(EARTH_ENGINE_FAILURES))
def test_2_iii_fails_on_one_asset(mod, records, what):
    output, change = EARTH_ENGINE_FAILURES[what]
    code, result = _run(mod, records, reader=StandIn(change={output: change}))
    assert result is not None
    assert code == 1 and result["passes"] is False
    passes = _passes(result)
    assert passes["2_feature_values_and_elbows"] is False
    assert {n: p for n, p in passes.items() if n != "2_feature_values_and_elbows"} == dict.fromkeys(
        [n for n in passes if n != "2_feature_values_and_elbows"], True)
    rows = result["criteria"]["2_feature_values_and_elbows"]["iii_cached_assets"]["assets"]
    failed = [f"{r['stage']}/{r['key']}" for r in rows if r["passes"] is not True]
    assert failed == [output], what


def test_the_largest_relative_difference_is_reported_with_its_band(mod, records):
    change = {"features_optical/optical_features": _set("largest_relative_difference", 3e-10)}
    _, result = _run(mod, records, reader=StandIn(change=change))
    assert result is not None
    rows = result["criteria"]["2_feature_values_and_elbows"]["iii_cached_assets"]["assets"]
    (row,) = [r for r in rows if r["key"] == "optical_features"]
    assert (row["largest_relative_difference"], row["in_band"], row["passes"]) == (3e-10, "b2", True)
    assert [b["band"] for b in row["per_band"]] == ["b1", "b2"]


def test_an_asset_that_is_not_the_one_the_run_recorded_fails(mod, records):
    # fmu finds the cache in the legacy layout, and the manifests record the per-step one.
    code, result = _run(mod, records, reader=StandIn(layout="legacy"))
    assert result is not None and code == 1
    rows = result["criteria"]["2_feature_values_and_elbows"]["iii_cached_assets"]["assets"]
    assert all(r["passes"] is False and "legacy" in r["not_the_recorded_asset"][0] for r in rows)
    assert result["criteria"]["5_slope_and_aspect_decimals"]["passes"] is False


CARDINAL = [[1.5, a] for a in (0.0, 90.0, 180.0, 270.0)]
DIAGONAL = [[2.25, a] for a in (45.0, 135.0, 225.0, 315.0)]


@pytest.mark.parametrize("values, passes", [
    ([[3.0 + i, 180.5] for i in range(5000)], False),            # slope whole numbers
    ([[3.5, 180.0 + i] for i in range(5000)], False),            # aspect whole numbers
    ([[1.5, float(a)] for a in range(360)] * 10, False),          # aspect rounded to whole degrees
    ([[0.0, 0.0]] * 4000 + [[1.5, 90.5]] * 1000, True),           # slope 0 is left out
    ([[1.5, 90.5]] * 99 + [[2.0, 90.5]], True),                   # 99 of 100: at the share
    ([[1.5, 90.5]] * 98 + [[2.0, 90.0]] * 2, False),              # slope 98 of 100: below it
    ([[1.5, 90.5]] * 98 + [[1.5, 91.0]] * 2, False),              # aspect 98 of 100: below it
    # A correct run on a DEM of whole metres: a gradient component exactly 0 gives an aspect of
    # exactly 0, 90, 180 or 270, and equal components on a grid of equal spacings 45, 135, ...
    ([[1.5, 90.5]] * 850 + CARDINAL * 38, True),
    ([[1.5, 90.5]] * 300 + CARDINAL * 150 + DIAGONAL * 25, True),
    ([[1.5, 90.0]] * 100, False),                                 # every aspect set aside
    # A value has decimals only when it is finite (the declared words, 27 Oct 2026).
    ([[1.5, 90.5]] * 98 + [[1.5, float("inf")]] * 2, False),      # aspect: 98 of 100
    ([[1.5, 90.5]] * 98 + [[1.5, float("nan")]] * 2, False),      # aspect: 98 of 100
    ([[1.5, 90.5]] * 98 + [[float("inf"), 90.5]] * 2, False),     # slope: 98 of 100
    ([[0.0, 12.5]] * 10, False),                                  # no pixel with slope above 0
    ([], False),
])
def test_5_slope_and_aspect_decimals(mod, records, values, passes):
    _, result = _run(mod, records, reader=StandIn(values=values))
    assert result is not None
    assert result["criteria"]["5_slope_and_aspect_decimals"]["passes"] is passes


def test_5_counts_the_aspects_set_aside_and_the_pixels_the_sample_gave(mod, records):
    values = [[1.5, 90.5]] * 300 + CARDINAL * 150 + DIAGONAL * 25 + [[0.0, 0.0]] * 37
    _, result = _run(mod, records, reader=StandIn(values=values))
    assert result is not None
    five = result["criteria"]["5_slope_and_aspect_decimals"]
    assert five["sample"] == {"asked": 10_000, "limit": 5000, "seed": 42}
    assert (five["pixels_sampled"], five["pixels_with_slope_above_0"]) == (1037, 1000)
    assert (five["slope_with_decimals"], five["aspect_at_a_multiple_of_45"]) == (1000, 700)
    assert (five["aspect_not_at_a_multiple_of_45"], five["aspect_with_decimals"]) == (300, 300)
    assert (five["share_slope_with_decimals"], five["share_aspect_with_decimals"]) == (1.0, 1.0)
    # The keys say what is counted: a value with decimals is a finite number that is not whole.
    assert not [k for k in five if "whole" in k]


def test_a_static_features_asset_not_on_earth_engine_fails_5_and_the_results_are_written(
        mod, records, monkeypatch):
    """The script's own reader, with no such asset: criterion 5 fails, naming it, as 2 iii does."""
    import fmu.utils.caching

    monkeypatch.setattr(fmu.utils.caching, "asset_exists", lambda path: False)
    real = mod.EarthEngineReader(None, [])

    class NotThere(StandIn):
        def sample(self, path: str, **kw: Any) -> list[list[Any]]:
            return real.sample(path, **kw)

    code, result = _run(mod, records, reader=NotThere())
    assert result is not None and code == 1
    five = result["criteria"]["5_slope_and_aspect_decimals"]
    assert five["passes"] is False and five["not_on_earth_engine"] == [five["asset"]]
    assert (records / "r14_live_check_run.json").exists()


def test_a_failure_to_read_earth_engine_writes_nothing(mod, records):
    def fails() -> Any:
        raise RuntimeError("no credentials")

    argv = ["--records", str(records), "--config-a", str(CONFIG_A), "--config-b", str(CONFIG_B)]
    assert mod.main(argv, reader=fails) == 4
    assert not (records / "r14_live_check.json").exists()
    assert not (records / "r14_live_check_run.json").exists()


def test_the_earth_engine_reader_forbids_writes_before_it_reads(mod, monkeypatch):
    import ee
    import ee_read_only

    import fmu.utils.gee

    calls: list[str] = []
    monkeypatch.setattr(fmu.utils.gee, "init_gee", lambda *a, **k: calls.append("init"))

    def forbid(ee_module: Any = None) -> list[str]:
        calls.append("forbid")
        return ["ee.batch.Task.start"]

    monkeypatch.setattr(ee_read_only, "forbid_writes", forbid)
    monkeypatch.setattr(ee.data, "setDeadline", lambda ms: calls.append(f"deadline {ms}"))
    reader = mod.earth_engine_reader()
    assert calls == ["init", "forbid", "deadline 420000"]
    assert isinstance(reader, mod.EarthEngineReader) and reader.forbidden == ["ee.batch.Task.start"]


@pytest.mark.live_gee
def test_live_the_earth_engine_reader_on_an_r9_run_s_own_assets(mod, monkeypatch):
    """Read-only, on Earth Engine (pytest -m live_gee tests/test_r14_live_check.py, from the repo
    root): the reader's reductions and sample on the cached assets of the Angul _r9 run, each asset
    against itself, so every count of a difference is 0. A few small requests; no task. The calls
    forbid_writes replaces are put back after."""
    import ee
    import ee_read_only

    import fmu.utils.gee as gee_mod
    from fmu.config import load_config
    from fmu.settings import get_settings
    from fmu.utils.caching import cache_key, cached_asset_path

    monkeypatch.delenv("GEE_PROJECT_ID", raising=False)  # this machine's .env, not the stand-in
    if not get_settings(force_reload=True).gee_project_id:
        pytest.skip("GEE_PROJECT_ID not set in .env")
    gee_mod._initialized = False
    saved = {"start": ee.batch.Task.start,
             **{n: getattr(ee.data, n) for n in ee_read_only._DATA_WRITES if hasattr(ee.data, n)}}
    try:
        try:
            reader = mod.earth_engine_reader()
        except ee.EEException as e:
            pytest.skip(f"Earth Engine is not set up on this machine: {e}")
        cfg = load_config(REPO / "configs" / "odisha_v120_3ha_squares_angul_keptland_s1desc_r9.yaml")
        layout = reader.cache_layout(cfg)
        assert layout == "per_step"
        # The assets the _r9 run made, by the cache keys its manifest recorded: round 13's fixes
        # moved some of its steps' keys (features_static's among them), so the key the config
        # gives today names no asset there (26 Oct 2026, the first run of this test).
        manifest = json.loads((REPO / "docs" / "reproducibility" / "r9_runs" /
                               f"{cfg.name}_manifest_features.json").read_text())
        recorded = {s["name"]: s["cache_key"] for s in manifest["stages"] if s.get("cache_key")}
        assert recorded["masking"] == cache_key(cfg, "masking", layout)  # unmoved since _r9

        def path(stage: str, key: str) -> str:
            return cached_asset_path(cfg.name, stage, key, recorded[stage])

        for stage, key, label_like in (("masking", "habitat_mask", True),
                                       ("features_static", "static_features", False)):
            p = path(stage, key)
            row = mod.judge_asset(stage, key, label_like, p, p,
                                  reader.compare(p, p, roi_file=cfg.roi.roi_file, label_like=label_like))
            assert row["passes"] is True and row["pixels_compared"] > 0, row
        values = reader.sample(path("features_static", "static_features"), roi_file=cfg.roi.roi_file,
                               bands=("slope", "aspect"), n=50, asked=100, seed=42)
        assert 0 < len(values) <= 50 and all(len(v) == 2 for v in values)
        with pytest.raises(ee_read_only.EarthEngineWriteError):
            ee.data.createFolder("projects/none/assets/fmu_live_check_not_made")
    finally:
        ee.batch.Task.start = saved.pop("start")
        for name, fn in saved.items():
            setattr(ee.data, name, fn)
        gee_mod._initialized = False
        get_settings(force_reload=True)


# ---------------------------------------------------------------------------
# The declaration
# ---------------------------------------------------------------------------


def test_the_docstring_declares_every_criterion_and_the_rule(mod):
    doc = mod.__doc__
    for heading in ("0. Both runs from scratch.", "1. The same stands, and the same type",
                    "2. The feature values agree within 1e-9 relative", "3. distance_to_water.",
                    "4. 189 Sentinel-1 scenes.", "5. Slope and aspect have decimals.",
                    "6. The four settings on.", "The check passes only if 0 to 6 all pass."):
        assert heading in doc, heading
    assert "|a - b| <= 1e-9 x max(|a|, |b|)" in doc and "|a - b| <= 1e-12" in doc
    # As amended on 27 Oct 2026, before the batch (the gate's review, part 3).
    words = " ".join(doc.split())
    assert "exactly equal in normal form (shapely.normalize" in words
    assert "whose aspect is not at a multiple of 45 degrees" in words
    assert (mod.RELATIVE, mod.FLOOR, mod.S1_SCENES, mod.DECIMALS_SHARE) == (1e-9, 1e-12, 189, 0.99)
    assert (mod.SAMPLE_PIXELS, mod.SAMPLE_ASKED, mod.SAMPLE_SEED) == (5000, 10_000, 42)


def test_the_four_settings_are_the_ones_the_check_configs_switch_on(mod, configs):
    for cfg in configs.values():
        dumped = cfg.model_dump(mode="json")
        assert all(dumped[block][field] == value for block, field, value in mod.SETTINGS)
    # And off by default, so that a manifest of a config that left one off would show it.
    from fmu.config import load_config

    dumped = load_config(REPO / "configs" / "odisha_v120_3ha_squares_angul_keptland_s1desc_r9.yaml").model_dump(
        mode="json")
    assert not any(dumped[block][field] == value for block, field, value in mod.SETTINGS)
