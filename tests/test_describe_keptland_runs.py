"""scripts/describe_keptland_runs.py, offline: the descriptive numbers of a kept-land run."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "describe_keptland_runs.py"


def _load():
    spec = importlib.util.spec_from_file_location("describe_keptland_runs", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_numbers_of_a_run():
    run = {
        "merge_diagnostics": {
            "n_stands": 4, "n_superpixels": 9, "stands_below_min_area": 2, "orphans_isolated": 2,
            "orphans_area_blocked": 0, "stands_over_max_area": 1,
            "excess_over_max_area_each_ha": [0.5],
            "kept_land": {"kept_land_ha": 25.0, "kept_land_ha_without_superpixel": 0.0,
                          "superpixel_ha_off_kept_land": 0.0, "small_patches_ha": 0.0}},
        "stand_attributes": {"1": {"area_ha": 0.2, "n_pixels": 20},
                             "2": {"area_ha": 10.5, "n_pixels": 1050},
                             "3": {"area_ha": 4.0, "n_pixels": 400},
                             "4": {"area_ha": 0.0, "n_pixels": 0}},
    }
    manifest = {
        "config": {"merge": {"max_area_ha": 10.0, "min_area_ha": 1.0}},
        "stages": [{"name": "export", "metadata": {"manifest": {"clustering": {
            "n_stands_left_out_of_fit": 2, "area_ha_in_stands_left_out_of_fit": 1.1}}}}],
    }
    got = _load().describe(run, manifest)
    assert (got["stands"], got["smallest_stand_ha"], got["largest_stand_ha"]) == (4, 0.0, 10.5)
    assert (got["stands_with_no_pixel"], got["smallest_stand_with_a_pixel_ha"]) == (1, 0.2)
    assert got["stands_over_max_area"] == 1 and got["excess_over_max_area_each_ha"] == [0.5]
    assert got["excess_over_max_area_each_ha_in_merge_diagnostics"] == [0.5]
    assert (got["stands_left_out_of_fit"], got["area_ha_left_out_of_fit"]) == (2, 1.1)
    assert got["kept_land_ha"] == 25.0 and got["kept_land_ha_without_superpixel"] == 0.0


def test_the_documented_command_describes_every_run_and_no_other_record(capsys):
    """Review C42: `python scripts/describe_keptland_runs.py`, with no run named, stopped on
    sanjay_van_alphaearth_keptland_stand_means_run.json, the run record of a script
    (scripts/alphaearth_stand_means.py), which has no export manifest beside it."""
    mod = _load()
    assert mod.main([]) == 0
    printed = [line for line in capsys.readouterr().out.splitlines() if not line.startswith(" ")]
    runs = sorted(p.name.removesuffix("_manifest_export.json")
                  for p in mod.RUNS_DIR.glob("*_manifest_export.json"))
    assert printed == runs and len(runs) == 10
    assert "sanjay_van_alphaearth_keptland_stand_means" not in printed
