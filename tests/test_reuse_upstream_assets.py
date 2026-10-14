"""scripts/reuse_upstream_assets.py, offline: what it would copy, and what it refuses.

The plan for the six kept-land configs of round 3 is built from the committed configs and the demo
records alone, so it is checked here exactly as the dry run prints it. Earth Engine is replaced by
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
    **{f"odisha_v120_3ha_squares_{d}_keptland": 9  # masking 4, data_load 1, features 4
       for d in ("kendujhar", "angul", "dhenkanal", "koraput")},
}


@pytest.fixture(scope="module")
def plans():
    return {p.name: p for p in (mod.plan_for(*pair) for pair in mod.PAIRS)}


def test_the_pairs_are_the_six_keptland_configs():
    names = {Path(new).stem for new, _, _ in mod.PAIRS}
    assert names == set(EXPECTED_COPIES)
    assert names == {p.stem for p in (REPO / "configs").glob("*_keptland.yaml")}


def test_each_plan_copies_what_its_source_run_cached_before_segmentation(plans):
    for name, plan in plans.items():
        assert len(plan.copies) == EXPECTED_COPIES[name], name
        assert {c.stage for c in plan.copies} <= set(mod.UPSTREAM_STAGES)
        assert not {c.stage for c in plan.copies} & NEVER
        rec = json.loads((REPO / plan.record).read_text())
        (run,) = [r for r in rec["runs"] if r["config"] == plan.source_config]
        listed = {a["asset"] for a in run["assets"] if a["stage"] not in NEVER}
        assert {c.source for c in plan.copies} == listed, name


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
    for plan in plans.values():
        assert set(plan.differences) == {
            "name", "description", "export.drive_folder", "segmentation.mask_before_snic",
            "merge.pass2_soft_ceiling", "clustering.fit_excludes_stands_below_min_area",
        }


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
    for s in mod.UPSTREAM_STAGES:
        text = (REPO / "src" / "fmu" / "stages" / f"{s}.py").read_text()
        assert not re.search(r"config\.(segmentation|merge|clustering)\b", text), s
        # Nor the name or description, nor a Config method (max_component_pixels() reads
        # merge.pass2_soft_ceiling, kept_patch_min_pixels() reads drop_kept_patches_...).
        assert not re.search(r"config\.(name|description)\b", text), s
        assert not re.search(r"config\.\w+\(", text), s


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
    assert "6 config(s), 51 asset(s) to copy; nothing copied (dry run)" in out
    assert "segmentation/" not in out


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
    assert mod.main(["--execute", "--record", str(record)]) == 0
    assert len(copies) == 51 == len(folders)
    assert len({d for _, d in copies}) == 51
    assert all("_keptland/" in d and "_keptland/" not in s for s, d in copies)
    assert not any(f"/{stage}/" in d for _, d in copies for stage in NEVER)
    out = capsys.readouterr().out
    assert "copied 51 asset(s); 51 recorded in" in out
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
        mod.main(["--execute", "--record", str(record)])
    assert len(json.loads(record.read_text())["copies"]) == 10
    assert json.loads((tmp_path / "keptland_reuse_run.json").read_text())["completed"] is False
    # Without --resume the record is not overwritten.
    assert mod.main(["--execute", "--record", str(record)]) == 3
    monkeypatch.setattr(ee.data, "copyAsset", lambda s, d: (copies.append((s, d)), copied.add(d)))
    assert mod.main(["--execute", "--resume", "--record", str(record)]) == 0
    assert len(copies) == 51 and len({d for _, d in copies}) == 51
    assert len(json.loads(record.read_text())["copies"]) == 51
    assert json.loads((tmp_path / "keptland_reuse_run.json").read_text())["completed"] is True


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

