"""docs/demo/demo_set.json: the record of the 14 re-runs of 13 October 2026 (the demo set).

Offline. Whether the assets it lists exist on Earth Engine is checked when the file is built
(scripts/build_demo_set.py lists the asset folders); here the file is checked against the
configs, the cache layout, the register and the other committed records.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import fmu.stages.clustering  # noqa: F401  (importing registers the stages)
import fmu.stages.data_load  # noqa: F401
import fmu.stages.features_embedding  # noqa: F401
import fmu.stages.features_optical  # noqa: F401
import fmu.stages.features_radar  # noqa: F401
import fmu.stages.features_static  # noqa: F401
import fmu.stages.features_structure  # noqa: F401
import fmu.stages.masking  # noqa: F401
import fmu.stages.merge  # noqa: F401
import fmu.stages.segmentation  # noqa: F401
from fmu.config import load_config
from fmu.pipeline import Pipeline, default_stage_names
from fmu.stages.base import get_stage_class
from fmu.utils.caching import config_fingerprint

REPO = Path(__file__).parent.parent
DEMO = json.loads((REPO / "docs" / "demo" / "demo_set.json").read_text())
RUNS = {r["run_id"]: r for r in DEMO["runs"]}
DISTRICTS = ["Angul", "Dhenkanal", "Kendujhar", "Koraput"]


def test_the_runs_are_the_fourteen_repro_configs():
    assert len(DEMO["runs"]) == 14 == len(RUNS)
    assert set(RUNS) == {p.stem for p in (REPO / "configs").glob("*_repro.yaml")}
    assert DEMO["n_assets"] == sum(len(r["assets"]) for r in DEMO["runs"]) == 163


def test_the_design_is_the_one_the_brief_lists():
    """Sanjay Van with both arms at 10 ha; each district hand-crafted at 3 and at 10 ha, and
    AlphaEarth at 10 ha."""
    design = sorted((r["site"], r["district"], r["arm"], r["stand_ceiling_ha"], r["k"]) for r in DEMO["runs"])
    expected = [("Sanjay Van", None, "alphaearth", 10.0, 6), ("Sanjay Van", None, "feature_vector", 10.0, 6)]
    for d in DISTRICTS:
        expected += [("Odisha", d, "alphaearth", 10.0, 6), ("Odisha", d, "feature_vector", 3.0, 5),
                     ("Odisha", d, "feature_vector", 10.0, 6)]
    assert design == sorted(expected, key=lambda t: (t[0], t[1] or "", t[2], t[3], t[4]))


@pytest.mark.parametrize("run_id", sorted(RUNS))
def test_a_run_agrees_with_its_config(run_id: str):
    run = RUNS[run_id]
    cfg = load_config(REPO / run["config"])
    assert cfg.name == run_id
    assert run["stand_ceiling_ha"] == cfg.merge.max_area_ha
    assert run["stand_minimum_ha"] == cfg.merge.min_area_ha
    assert run["k"] == cfg.clustering.k
    assert run["segmentation_size"] == cfg.segmentation.size
    assert run["arm"] == ("alphaearth" if cfg.clustering.feature_source == "embedding" else "feature_vector")
    assert run["roi_file"] == str(cfg.roi.roi_file) and (REPO / run["roi_file"]).is_file()
    assert run["drive_folder"] == cfg.export.drive_folder
    assert run["area"] == (run["district"] or "Sanjay Van working area")


@pytest.mark.parametrize("run_id", sorted(RUNS))
def test_every_asset_path_is_the_cache_path_of_the_runs_fingerprint(run_id: str):
    """The paths were read from Earth Engine, not built from the config. They must still be the
    ones the config's fingerprint leads to, or the saved assets could not be found by name."""
    run = RUNS[run_id]
    cfg = load_config(REPO / run["config"])
    assert run["fingerprint"] == config_fingerprint(cfg)
    for asset in run["assets"]:
        assert asset["fingerprint"] == run["fingerprint"]
        assert asset["asset"] == (
            f"{DEMO['asset_root']}/{run_id}/{asset['stage']}/{asset['key']}__{asset['fingerprint']}"
        )


@pytest.mark.parametrize("run_id", sorted(RUNS))
def test_the_assets_are_what_the_pipeline_caches_for_that_config(run_id: str):
    """One asset per cacheable output of every stage through clustering, except the outputs
    listed as not cached (added to the code after these runs)."""
    run = RUNS[run_id]
    cfg = load_config(REPO / run["config"])
    expected = {
        f"{stage}/{key}"
        for stage in default_stage_names(cfg, through="clustering")
        for key in Pipeline._resolve_cacheable_outputs(get_stage_class(stage)())
    }
    listed = [f"{a['stage']}/{a['key']}" for a in run["assets"]]
    assert len(listed) == len(set(listed))
    assert set(run["not_cached"]) <= expected
    assert set(listed) == expected - set(run["not_cached"])


def test_the_segmentation_route_is_the_recorded_one():
    routes = {r["config"]: r for r in json.loads(
        (REPO / "docs" / "reproducibility" / "segmentation_route.json").read_text())}
    for run_id, run in RUNS.items():
        assert run["segmentation_route"] == routes[run_id]["route"] in ("cached", "live")
        assert run["segmentation_run"] == routes[run_id]["runs"][-1]["run"]


def test_the_label_names_the_commit_and_a_rule_that_is_in_the_register():
    register = yaml.safe_load((REPO / "docs" / "decisions.yaml").read_text())["decisions"]
    ids = {d["id"] for d in register}
    assert DEMO["merge_rule"] in ids
    assert f"`{DEMO['merge_rule']}`" in DEMO["label"]
    assert DEMO["source_commit"].startswith("df45350") and "commit df45350" in DEMO["label"]
    assert DEMO["label"].startswith("Demo set: Earth Engine runs of 13 Oct 2026")
    assert "question 1" in DEMO["label"] and DEMO["label"].endswith("The final re-run replaces it.")


def test_every_committed_file_it_names_exists():
    for run in DEMO["runs"]:
        assert (REPO / run["config"]).is_file()
        for what, path in run["committed"].items():
            assert (REPO / path).is_file(), f"{run['run_id']}: {what} {path}"


@pytest.mark.parametrize("run_id", sorted(RUNS))
def test_the_local_record_of_a_run_matches_when_it_is_on_this_machine(run_id: str):
    """outputs/ is ignored by git, so this runs only where the re-runs' files are kept."""
    run = RUNS[run_id]
    record_path = REPO / run["local"]["run_record"]
    if not record_path.is_file():
        pytest.skip("the re-runs' local files are not on this machine")
    record = json.loads(record_path.read_text())
    assert record["config"] == run_id and record["fingerprint"] == run["fingerprint"]
    assert sorted(e["filename"] for e in record["drive_exports"].values()) == run["drive"]["files"]
    assert run["counts"]["stands"] == record["merge_diagnostics"]["n_stands"]
    assert run["local"]["missing_here"] == []
    assert run["source_commit"] == DEMO["source_commit"] and run["source_tree_dirty"] is False
    # Every input of the pass that wrote the stands was read from the cache, so a re-merge from
    # the saved assets takes the same route as the run did.
    assert {state for keys in record["cache_status"].values() for state in keys.values()} == {"hit"}


# ---------------------------------------------------------------------------
# docs/demo/demo_set_boxes.json: the four box runs of task A0, recorded in the same form
# ---------------------------------------------------------------------------

BOXES = json.loads((REPO / "docs" / "demo" / "demo_set_boxes.json").read_text())
BOX_RUNS = {r["run_id"]: r for r in BOXES["runs"]}


def test_every_run_of_both_sets_says_what_its_roi_is():
    assert {r["roi"] for r in BOXES["runs"]} == {"boxes"}
    for run in DEMO["runs"]:
        assert run["roi"] == ("hulls" if run["site"] == "Odisha" else "rectangle"), run["run_id"]


def test_the_box_runs_are_the_four_box_configs_under_their_own_fingerprints():
    from fmu.config import load_config
    from fmu.utils.caching import config_fingerprint

    configs = sorted((REPO / "configs").glob("odisha_v120_3ha_squares_*.yaml"))
    assert sorted(BOX_RUNS) == [p.stem for p in configs] and len(configs) == 4
    assert BOXES["n_assets"] == sum(len(r["assets"]) for r in BOXES["runs"])
    for path in configs:
        cfg = load_config(path)
        run = BOX_RUNS[cfg.name]
        assert run["fingerprint"] == config_fingerprint(cfg), cfg.name
        assert run["arm"] == "feature_vector" and run["stand_ceiling_ha"] == 3.0 and run["k"] == 5
        assert cfg.merge.pass2_skip_at_min_area is True
        for asset in run["assets"]:
            assert asset["asset"] == (
                f"{BOXES['asset_root']}/{cfg.name}/{asset['stage']}/{asset['key']}__{run['fingerprint']}")


def test_a_box_run_whose_export_pass_ended_early_says_what_was_read_back():
    assert BOXES["merge_rule"] == DEMO["merge_rule"] and f"`{BOXES['merge_rule']}`" in BOXES["label"]
    for run_id, run in BOX_RUNS.items():
        assert "export_pass" in run, run_id
        if run["export_pass"] == "finished":
            assert "read_back" not in run, run_id
        else:
            # The local files the export pass did not write came from the cached assets.
            assert run["read_back"]["by"] == "odisha_script/odisha_read_back_export.py", run_id
            assert set(run["read_back"]["layers_read_back"]) | set(run["read_back"]["layers_the_run_wrote"]) == {
                "stands_merged", "stands_snic", "stands_dissolved"}, run_id
