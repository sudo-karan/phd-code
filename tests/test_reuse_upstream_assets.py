"""scripts/reuse_upstream_assets.py, offline: what it would copy, and what it refuses.

The plan for the six kept-land configs of round 3, and for round 7's four descending-orbit
configs, is built from the committed configs and the asset records alone, so it is checked here
exactly as the dry run prints it. Earth Engine is replaced by
stand-ins for --check and --execute; nothing here talks to it.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "reuse_upstream_assets.py"
spec = importlib.util.spec_from_file_location("reuse_upstream_assets", SCRIPT)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod  # dataclasses look their module up while the class is built
spec.loader.exec_module(mod)

ROOT = "projects/replicating-paper/assets/fmu"
NEVER = {"segmentation", "merge", "clustering", "profiling", "export", "metrics"}
# config -> number of assets the records list for its source run, before segmentation
EXPECTED_COPIES = {
    "sanjay_van_baseline_keptland": 8,  # masking 3, data_load 1, features 4
    "sanjay_van_alphaearth_keptland": 7,  # masking 3, data_load 1, features 3
    # masking 4, data_load 1, features 3: not static_features, which reads the distance cap
    # (round 6, RECOMPUTE_KEYS) and is computed by the run
    **{f"odisha_v120_3ha_squares_{d}_keptland": 8
       for d in ("kendujhar", "angul", "dhenkanal", "koraput")},
    # Round 7: masking 4, data_load 1, features 3 (optical, structure, static): not radar, which
    # depends on the orbit (RECOMPUTE_VIA_CONTEXT) and is computed by the run.
    **{f"odisha_v120_3ha_squares_{d}_keptland_s1desc": 8
       for d in ("kendujhar", "angul", "dhenkanal", "koraput")},
}
BOXES = {f"odisha_v120_3ha_squares_{d}_keptland" for d in ("kendujhar", "angul", "dhenkanal",
                                                           "koraput")}
S1DESC = {f"{name}_s1desc" for name in BOXES}
# --config arguments for the six configs of rounds 3 to 6 (their sources are the box and _repro
# runs), and for the four of round 7 (their sources are the round-6 kept-land runs). The two sets
# are copied at different times: the round-7 sources are the round-6 destinations.
ROUND3 = [a for new, _, _ in mod.PAIRS if Path(new).stem not in S1DESC for a in ("--config", new)]
ROUND7 = [a for new, _, _ in mod.PAIRS if Path(new).stem in S1DESC for a in ("--config", new)]


@pytest.fixture(scope="module")
def plans():
    return {p.name: p for p in (mod.plan_for(*pair) for pair in mod.PAIRS)}


def test_the_pairs_are_the_kept_land_configs():
    names = {Path(new).stem for new, _, _ in mod.PAIRS}
    assert names == set(EXPECTED_COPIES)
    # The round 9 copies (*_r9*.yaml) run from scratch, with no copied assets.
    assert names == {p.stem for p in (REPO / "configs").glob("*_keptland*.yaml")
                     if "_r9" not in p.stem}
    # Round 7: each descending-orbit config reuses its district's round-6 kept-land run.
    for new, source, record in mod.PAIRS:
        if Path(new).stem in S1DESC:
            assert Path(source).stem == Path(new).stem.removesuffix("_s1desc")
            assert record == "docs/reproducibility/keptland_boxes_assets.json"


def test_each_plan_copies_what_its_source_run_cached_before_segmentation(plans):
    for name, plan in plans.items():
        assert len(plan.copies) == EXPECTED_COPIES[name], name
        assert {c.stage for c in plan.copies} <= set(mod.UPSTREAM_STAGES)
        assert not {c.stage for c in plan.copies} & NEVER
        rec = json.loads((REPO / plan.record).read_text())
        (run,) = [r for r in rec["runs"] if r["config"] == plan.source_config]
        fresh = ({"features_static"} if name in BOXES
                 else {"features_radar"} if name in S1DESC else set())
        listed = {a["asset"] for a in run["assets"] if a["stage"] not in NEVER | fresh}
        assert {c.source for c in plan.copies} == listed, name


def test_static_features_are_computed_by_the_box_runs_not_copied(plans):
    """The four box configs cap distance_to_water (round 6) and their sources do not: the static
    features differ, so they are not copied. The Sanjay Van configs do not cap, and copy theirs."""
    for name, plan in plans.items():
        stages = {c.stage for c in plan.copies}
        if name in BOXES:
            assert plan.computed_fresh == ["features_static/static_features"], name
            assert "features_static" not in stages, name
        elif name in S1DESC:
            assert plan.computed_fresh == ["features_radar/radar_features"], name
        else:
            assert plan.computed_fresh == [], name
    assert "features_static" in {c.stage for c in plans["sanjay_van_baseline_keptland"].copies}


def test_the_descending_orbit_runs_compute_their_radar_and_copy_the_rest(plans):
    """Round 7: the _s1desc configs differ from the round-6 kept-land configs in the orbit, which
    only the radar features depend on. Everything else before segmentation is copied, the
    capped static features of round 6 among it, and the S2 composite of data_load, which reads
    the orbit but caches nothing built from it."""
    for name in S1DESC:
        plan = plans[name]
        assert {c.stage for c in plan.copies} == {"masking", "data_load", "features_optical",
                                                 "features_structure", "features_static"}, name
        assert ("data_load", "s2_composite") in {(c.stage, c.key) for c in plan.copies}
        assert all(f"/{plan.source_name}/" in c.source for c in plan.copies)


def test_destinations_are_where_the_new_run_will_look(plans, monkeypatch):
    """Each destination is the path Pipeline._try_load_cache will look up for that config, built
    by the pipeline's own cached_asset_path under the records' asset root."""
    import fmu.utils.gee as gee
    from fmu.config import load_config
    from fmu.utils.caching import cached_asset_path, config_fingerprint

    monkeypatch.setattr(gee, "get_settings", lambda: _FakeSettings())
    for name, plan in plans.items():
        fp = config_fingerprint(load_config(REPO / plan.config))
        assert plan.fingerprint == fp
        for c in plan.copies:
            assert c.destination == cached_asset_path(name, c.stage, c.key, fp)
            assert c.source == cached_asset_path(plan.source_name, c.stage, c.key,
                                                 plan.source_fingerprint)


def test_the_sanjay_van_runs_never_cached_mask_provenance(plans):
    for name, plan in plans.items():
        expect = ["masking/mask_provenance"] if name.startswith("sanjay_van") else []
        assert plan.not_cached_in_source == expect, name


def test_the_configs_differ_from_their_sources_only_in_safe_keys(plans):
    round3 = {
        "name", "description", "export.drive_folder", "segmentation.mask_before_snic",
        "merge.pass2_soft_ceiling", "clustering.fit_excludes_stands_below_min_area",
    }
    # Round 4 (questions 6 and 7): the Sanjay Van configs also skip at the minimum, as the box
    # configs already do, and the AlphaEarth arm compares with the baseline on kept land.
    sanjay_van = round3 | {"merge.pass2_skip_at_min_area"}
    expect = {
        "sanjay_van_baseline_keptland": sanjay_van,
        "sanjay_van_alphaearth_keptland": sanjay_van | {"metrics.reference_config_name"},
        # Round 6: the box configs cap distance_to_water.
        **{name: round3 | {"features_static.cap_distance_to_water"} for name in BOXES},
        # Round 7: from the round-6 kept-land configs, the orbit and the names only.
        **{name: {"name", "description", "export.drive_folder", "data_load.s1_orbit"}
           for name in S1DESC},
    }
    for name, plan in plans.items():
        assert set(plan.differences) == expect.get(name, round3), name


def _upstream_modules() -> list[Path]:
    """The upstream stage modules and every fmu.utils module they import, recursively."""
    stages = [REPO / "src" / "fmu" / "stages" / f"{s}.py" for s in mod.UPSTREAM_STAGES]
    seen: set[Path] = set()
    todo = list(stages) + [REPO / "src" / "fmu" / "stages" / "base.py"]
    while todo:
        path = todo.pop()
        if path in seen or not path.exists():
            continue
        seen.add(path)
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            elif isinstance(node, ast.Import):
                names.extend(a.name for a in node.names)
            for n in names:
                if n.startswith("fmu.utils"):
                    todo.append(REPO / "src" / Path(*n.split(".")).with_suffix(".py"))
    return sorted(seen)


def test_no_stage_before_segmentation_reads_a_safe_key():
    """The guard's premise, checked rather than trusted: the names of the keys the configs may
    differ in appear in no upstream stage module, nor in any fmu.utils module those import; and no
    upstream stage reads the segmentation, merge or clustering block of the config at all."""
    keys = {k for _, k in mod.REUSE_SAFE_KEYS if k}
    modules = _upstream_modules()
    assert len(modules) > len(mod.UPSTREAM_STAGES)
    for path in modules:
        text = path.read_text()
        for k in keys:
            assert k not in text, f"{path.relative_to(REPO)} names {k}"
    # A key of RECOMPUTE_KEYS is read by the stage it names, and by no other module here.
    for (_, key), stage in mod.RECOMPUTE_KEYS.items():
        assert stage in mod.UPSTREAM_STAGES
        own = REPO / "src" / "fmu" / "stages" / f"{stage}.py"
        assert key in own.read_text(), f"{stage} does not read {key}"
        for path in modules:
            if path != own:
                assert key not in path.read_text(), f"{path.relative_to(REPO)} names {key}"
    for s in mod.UPSTREAM_STAGES:
        text = (REPO / "src" / "fmu" / "stages" / f"{s}.py").read_text()
        assert not re.search(r"config\.(segmentation|merge|clustering)\b", text), s
        # Nor the name or description, nor a Config method (max_component_pixels() reads
        # merge.pass2_soft_ceiling, kept_patch_min_pixels() reads drop_kept_patches_...).
        assert not re.search(r"config\.(name|description)\b", text), s
        assert not re.search(r"config\.\w+\(", text), s


def _reads_of(tree: ast.AST, attr: str) -> list[tuple[str, ast.AST]]:
    """(enclosing function, node) of each read of `.attr` in a module."""
    out = []
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            for node in ast.walk(fn):
                if isinstance(node, ast.Attribute) and node.attr == attr:
                    out.append((fn.name, node))
    return out


def test_a_context_key_reaches_only_the_stage_that_reads_its_value():
    """RECOMPUTE_VIA_CONTEXT, checked from the code rather than trusted. For each key: its name
    appears in no upstream module but the reading stage's; there it is read only in methods whose
    one use in run() is to make the context value, and in the stage's metadata; the stage makes
    the value but does not cache it, and builds its cached outputs without it; among the upstream
    stages only the one named reads the value."""
    import fmu.stages  # noqa: F401
    from fmu.stages.base import get_stage_class

    modules = _upstream_modules()
    for (_, key), (reader, value, dependent) in mod.RECOMPUTE_VIA_CONTEXT.items():
        assert reader in mod.UPSTREAM_STAGES and dependent in mod.UPSTREAM_STAGES
        own = REPO / "src" / "fmu" / "stages" / f"{reader}.py"
        for path in modules:
            if path != own:
                assert key not in path.read_text(), f"{path.relative_to(REPO)} names {key}"
        tree = ast.parse(own.read_text())
        (run,) = [f for f in ast.walk(tree) if isinstance(f, ast.FunctionDef) and f.name == "run"]
        # The StageResult run() returns: its outputs dict and its metadata.
        (result,) = [n for n in ast.walk(run) if isinstance(n, ast.Call)
                     and getattr(n.func, "id", None) == "StageResult"]
        kw = {k.arg: k.value for k in result.keywords}
        outputs = {k.value: v for k, v in zip(kw["outputs"].keys, kw["outputs"].values, strict=True)}
        metadata_nodes = set(map(id, ast.walk(kw["metadata"])))
        methods = set()
        for fn_name, node in _reads_of(tree, key):
            if fn_name == "run":
                assert id(node) in metadata_nodes, f"run() reads {key} outside its metadata"
            else:
                methods.add(fn_name)
        assert methods, f"{reader} does not read {key}"
        # Each such method is called once in run(), into a name that is the value's output and
        # is used nowhere else in run().
        for m in methods:
            calls = [n for n in ast.walk(run) if isinstance(n, ast.Assign)
                     and isinstance(n.value, ast.Call)
                     and getattr(n.value.func, "attr", None) == m]
            assert len(calls) == 1, m
            (target,) = calls[0].targets
            uses = [n for n in ast.walk(run) if isinstance(n, ast.Name) and n.id == target.id]
            assert len(uses) == 2, f"{target.id} is used elsewhere in run()"  # assigned, output
            assert isinstance(outputs[value], ast.Name) and outputs[value].id == target.id
        cls = get_stage_class(reader)
        assert value in cls.produces and value not in cls.cacheable_outputs
        readers = {s for s in mod.UPSTREAM_STAGES if value in get_stage_class(s).required_inputs}
        assert readers == {dependent}, readers


def _copy_pair(tmp_path: Path, edit) -> tuple[str, str, str]:
    """A pair under tmp_path: Kendujhar's box config, its kept-land copy with `edit` applied to
    the YAML text, and the boxes record."""
    for rel in ("configs/odisha_v120_3ha_squares_kendujhar.yaml",
                "configs/odisha_v120_3ha_squares_kendujhar_keptland.yaml",
                "docs/demo/demo_set_boxes.json"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, tmp_path / rel)
    new = tmp_path / "configs/odisha_v120_3ha_squares_kendujhar_keptland.yaml"
    new.write_text(edit(new.read_text()))
    return ("configs/odisha_v120_3ha_squares_kendujhar_keptland.yaml",
            "configs/odisha_v120_3ha_squares_kendujhar.yaml", "docs/demo/demo_set_boxes.json")


@pytest.mark.parametrize("edit", [
    lambda t: t.replace("  max_area_ha: 3.0", "  max_area_ha: 4.0"),  # changes pass 1 and every stand
    lambda t: t.replace("  size: 6", "  size: 8"),  # segmentation, but not a key the guard allows
    lambda t: t.replace("  indiasat_year_max: 2021", "  indiasat_year_max: 2022"),  # masking
    lambda t: t.replace("  k: 5", "  k: 4"),
])
def test_a_difference_outside_the_safe_keys_is_refused(tmp_path, edit):
    pair = _copy_pair(tmp_path, edit)
    with pytest.raises(mod.RefusedError, match="REUSE_SAFE_KEYS"):
        mod.plan_for(*pair, repo=tmp_path)


def test_a_record_whose_fingerprint_is_not_the_configs_is_refused(tmp_path):
    pair = _copy_pair(tmp_path, lambda t: t)
    rec_path = tmp_path / pair[2]
    rec = json.loads(rec_path.read_text())
    for r in rec["runs"]:
        r["fingerprint"] = "0000000000"
    rec_path.write_text(json.dumps(rec))
    with pytest.raises(mod.RefusedError, match="hashes to"):
        mod.plan_for(*pair, repo=tmp_path)


def test_the_dry_run_makes_no_earth_engine_call(monkeypatch, capsys):
    import fmu.utils.caching as caching
    import fmu.utils.gee as gee

    def boom(*a, **k):
        raise AssertionError("the dry run called Earth Engine")

    monkeypatch.setattr(gee, "init_gee", boom)
    monkeypatch.setattr(caching, "asset_exists", boom)
    assert mod.main([]) == 0
    out = capsys.readouterr().out
    assert "10 config(s), 79 asset(s) to copy; nothing copied (dry run)" in out
    assert "segmentation/" not in out
    assert mod.main(ROUND7) == 0
    out = capsys.readouterr().out
    assert "4 config(s), 32 asset(s) to copy; nothing copied (dry run)" in out
    assert out.count("computed by the new run (it depends on a key the configs differ in): "
                     "features_radar/radar_features") == 4


class _FakeSettings:
    def resolved_asset_root(self):
        return ROOT


def _fake_ee(monkeypatch, *, exists):
    import ee

    import fmu.settings as settings
    import fmu.utils.caching as caching
    import fmu.utils.gee as gee

    copies: list[tuple[str, str]] = []
    folders: list[str] = []
    monkeypatch.setattr(settings, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(gee, "init_gee", lambda: None)
    monkeypatch.setattr(caching, "asset_exists", exists)
    monkeypatch.setattr(caching, "ensure_parent_folders", folders.append)
    monkeypatch.setattr(ee.data, "copyAsset", lambda s, d: copies.append((s, d)))
    return copies, folders


def test_execute_copies_every_planned_asset_once_and_records_them(monkeypatch, capsys, tmp_path):
    copies, folders = _fake_ee(monkeypatch, exists=lambda p: "_keptland/" not in p)
    record = tmp_path / "keptland_reuse.json"
    assert mod.main(["--execute", "--record", str(record), *ROUND3]) == 0
    assert len(copies) == 47 == len(folders)
    assert len({d for _, d in copies}) == 47
    assert all("_keptland/" in d and "_keptland/" not in s for s, d in copies)
    assert not any(f"/{stage}/" in d for _, d in copies for stage in NEVER)
    out = capsys.readouterr().out
    assert "copied 47 asset(s); 47 recorded in" in out
    rec = json.loads(record.read_text())
    assert [(c["source"], c["destination"]) for c in rec["copies"]] == copies
    run = json.loads((tmp_path / "keptland_reuse_run.json").read_text())
    assert run["completed"] is True and run["result_file"] == "keptland_reuse.json"
    assert set(run["git"]) >= {"commit", "dirty"} and "date" in run


def test_a_copy_that_stops_part_way_leaves_a_true_record_and_can_be_resumed(monkeypatch, tmp_path):
    import ee

    record = tmp_path / "keptland_reuse.json"
    copied: set[str] = set()
    copies, _ = _fake_ee(monkeypatch, exists=lambda p: "_keptland/" not in p or p in copied)

    def copy_then_fail(src, dst):
        if len(copies) == 10:
            raise RuntimeError("network")
        copies.append((src, dst))
        copied.add(dst)

    monkeypatch.setattr(ee.data, "copyAsset", copy_then_fail)
    with pytest.raises(RuntimeError):
        mod.main(["--execute", "--record", str(record), *ROUND3])
    assert len(json.loads(record.read_text())["copies"]) == 10
    assert json.loads((tmp_path / "keptland_reuse_run.json").read_text())["completed"] is False
    # Without --resume the record is not overwritten.
    assert mod.main(["--execute", "--record", str(record), *ROUND3]) == 3
    monkeypatch.setattr(ee.data, "copyAsset", lambda s, d: (copies.append((s, d)), copied.add(d)))
    assert mod.main(["--execute", "--resume", "--record", str(record), *ROUND3]) == 0
    assert len(copies) == 47 and len({d for _, d in copies}) == 47
    assert len(json.loads(record.read_text())["copies"]) == 47
    assert json.loads((tmp_path / "keptland_reuse_run.json").read_text())["completed"] is True


def test_a_resume_with_other_configs_keeps_what_the_record_holds_for_the_others(monkeypatch, tmp_path):
    """Review C43: --execute --resume rebuilt the record from the configs of the call only, so a
    resume with another --config set (or with the default record, the committed round-5 one)
    dropped the copies recorded for the others, and the run record of the resume replaced the
    earlier one."""
    import ee

    record, run_record = tmp_path / "keptland_reuse.json", tmp_path / "keptland_reuse_run.json"
    copied: set[str] = set()
    copies, _ = _fake_ee(monkeypatch, exists=lambda p: "_keptland/" not in p or p in copied)
    monkeypatch.setattr(ee.data, "copyAsset", lambda s, d: (copies.append((s, d)), copied.add(d)))
    first, second = ROUND3[:4], ROUND3[4:6]  # the two Sanjay Van configs (8 and 7), then a box one
    assert mod.main(["--execute", "--record", str(record), *first]) == 0
    recorded_first = json.loads(record.read_text())["copies"]
    run_first = json.loads(run_record.read_text())
    assert len(recorded_first) == 15 and run_first["completed"] is True
    assert mod.main(["--execute", "--resume", "--record", str(record), *second]) == 0
    recorded = json.loads(record.read_text())["copies"]
    assert (len(recorded), len(copies)) == (23, 23)
    assert recorded[:15] == recorded_first
    assert [(c["source"], c["destination"]) for c in recorded] == copies
    run = json.loads(run_record.read_text())
    assert run_first.pop("earlier_runs") == []  # kept one level deep, not nested
    assert run["completed"] is True and run["earlier_runs"] == [run_first]
    assert "--resume" in run["command_line"] and "--resume" not in run_first["command_line"]


def test_execute_copies_the_round_7_assets_from_the_round_6_runs(monkeypatch, capsys, tmp_path):
    """Round 7: the round-6 kept-land assets exist (they are the sources), the _s1desc ones do not."""
    copies, folders = _fake_ee(monkeypatch, exists=lambda p: "_s1desc/" not in p)
    record = tmp_path / "keptland_reuse_s1desc.json"
    assert mod.main(["--execute", "--record", str(record), *ROUND7]) == 0
    assert len(copies) == 32 == len({d for _, d in copies})
    assert all("_keptland_s1desc/" in d and "_keptland/" in s for s, d in copies)
    assert not any("/features_radar/" in d for _, d in copies)
    assert "copied 32 asset(s); 32 recorded in" in capsys.readouterr().out


def test_resume_refuses_a_destination_the_record_does_not_hold(monkeypatch, tmp_path):
    there = f"{ROOT}/sanjay_van_baseline_keptland/masking/"
    copies, _ = _fake_ee(monkeypatch, exists=lambda p: "_keptland/" not in p or p.startswith(there))
    record = tmp_path / "keptland_reuse.json"
    record.write_text(json.dumps({"what": "", "copies": []}))
    assert mod.main(["--execute", "--resume", "--record", str(record)]) == 3
    assert copies == []


def test_execute_copies_nothing_if_any_destination_exists(monkeypatch, capsys, tmp_path):
    there = f"{ROOT}/sanjay_van_baseline_keptland/masking/"
    copies, _ = _fake_ee(monkeypatch,
                         exists=lambda p: "_keptland/" not in p or p.startswith(there))
    assert mod.main(["--execute", "--record", str(tmp_path / "r.json")]) == 3
    assert copies == []
    assert "nothing was copied" in capsys.readouterr().out
    assert not (tmp_path / "r.json").exists()


def test_execute_copies_nothing_if_any_source_is_missing(monkeypatch, tmp_path):
    copies, _ = _fake_ee(monkeypatch, exists=lambda p: "_keptland/" not in p and "koraput" not in p)
    assert mod.main(["--execute", "--record", str(tmp_path / "r.json")]) == 3
    assert copies == []


def test_check_is_read_only(monkeypatch, capsys):
    copies, folders = _fake_ee(monkeypatch, exists=lambda p: "_keptland/" not in p)
    assert mod.main(["--check", "--config", "configs/sanjay_van_baseline_keptland.yaml"]) == 0
    assert copies == [] and folders == []
    out = capsys.readouterr().out
    assert "1 config(s), 8 asset(s) to copy; nothing copied (dry run, checked read-only)" in out
    assert "[source exists, destination absent]" in out


def test_execute_refuses_another_asset_root(monkeypatch, tmp_path):
    import fmu.settings as settings

    copies, _ = _fake_ee(monkeypatch, exists=lambda p: "_keptland/" not in p)

    class _Other:
        def resolved_asset_root(self):
            return "projects/elsewhere/assets/fmu"

    monkeypatch.setattr(settings, "get_settings", lambda: _Other())
    assert mod.main(["--execute", "--record", str(tmp_path / "r.json")]) == 3
    assert copies == []


def test_it_refuses_another_checkouts_code(monkeypatch, capsys):
    import fmu

    monkeypatch.setattr(fmu, "__file__", "/somewhere/else/src/fmu/__init__.py")
    assert mod.main([]) == 3
    assert "not from" in capsys.readouterr().out

