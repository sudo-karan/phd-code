"""The parts of scripts/fetch_ui_r3_layers.py that need no Earth Engine."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_ui_r3_layers as fetch  # noqa: E402


def test_r3_is_the_eighteen_runs_of_the_second_half_without_the_tile_or_a_check_copy():
    runs = fetch.r3_runs()
    assert len(runs) == 18
    assert not [r for r in runs if "tile" in r or "check" in r]
    assert {r for r in runs if r.startswith("sanjay_van")} == {
        "sanjay_van_baseline_keptland_r14", "sanjay_van_alphaearth_keptland_r14"}


def test_the_five_areas_each_share_their_masking_and_data_load_keys():
    found = fetch.areas()
    assert sorted(found) == ["angul", "dhenkanal", "kendujhar", "koraput", "sanjay_van"]
    assert [len(found[a]["runs"]) for a in sorted(found)] == [4, 4, 4, 4, 2]
    for a in found.values():
        for run in a["runs"]:
            keys = fetch.stage_keys(fetch.manifest(run))
            assert {s: keys[s] for s in fetch.SHARED_STAGES} == a["keys"]


def test_an_area_whose_runs_differ_in_a_shared_key_is_refused(tmp_path):
    for run, key in (("a_r14", "s1"), ("b_r14", "s2")):
        m = {"config_name": run, "config": {"roi": {"roi_file": "aois/sanjay_van.geojson"}},
             "stages": [{"name": "masking", "cache_key": key},
                        {"name": "data_load", "cache_key": "s9"}]}
        (tmp_path / f"{run}_manifest_export.json").write_text(json.dumps(m))
    with pytest.raises(SystemExit, match="masking key"):
        fetch.areas(tmp_path)


def test_an_asset_id_is_the_per_step_layouts_from_the_manifest():
    run = "odisha_v120_3ha_squares_angul_keptland_s1desc_r14"
    m = fetch.manifest(run)
    assert fetch.asset_id("projects/p/assets/fmu", run, "masking", "mask_provenance", m) == (
        f"projects/p/assets/fmu/{run}/masking/mask_provenance__s073c13df8c")
    with pytest.raises(SystemExit, match="not a cached output"):
        fetch.asset_id("projects/p/assets/fmu", run, "masking", "snic_clusters", m)


@pytest.mark.parametrize("grid", [
    [10.0, 0.0, 300000.0, 0.0, -10.0, 2400000.0],
    # A cached asset of the per-step layout reports its grid with a positive y step
    # (ee.Projection(<UTM>).atScale(10)); its pixel edges are the same lattice.
    [10.0, 0.0, 254300.0, 0.0, 10.0, 2294980.0],
])
def test_the_native_window_is_north_up_on_the_assets_pixel_edges_and_holds_the_bounds(grid):
    window, width, height = fetch.native_window((300123.4, 2399001.0, 300987.6, 2399876.5), grid)
    west, north = window[2], window[5]
    assert window[0] == 10.0 and window[4] == -10.0
    assert ((west - grid[2]) / 10).is_integer() and ((north - grid[5]) / 10).is_integer()
    assert west <= 300123.4 - 20 and north >= 2399876.5 + 20
    assert west + width * 10 >= 300987.6 + 20 and north - height * 10 <= 2399001.0 - 20
    # The bounds touch columns 12 to 98 and rows 12 to 99 from the origin's lines: 87 by 88
    # pixels, and 2 more on each side.
    assert (width, height) == (87 + 4, 88 + 4)


def test_a_rotated_grid_is_refused():
    with pytest.raises(ValueError, match="aligned with its axes"):
        fetch.native_window((0, 0, 1, 1), [10.0, 0.5, 0.0, 0.0, -10.0, 0.0])
