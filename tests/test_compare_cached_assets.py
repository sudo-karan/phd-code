"""scripts/compare_cached_assets.py: the offline part, and that it stays read-only.

The comparison itself needs Earth Engine and is not run here.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "compare_cached_assets.py"


def _load():
    spec = importlib.util.spec_from_file_location("compare_cached_assets", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _row(**kw):
    row = {
        "stage": "masking", "key": "habitat_mask", "bands": 1, "same_grid": True,
        "pixel_values_compared": 1000, "pixel_bands_that_differ": 0,
        "pixels_whose_mask_differs": 0, "largest_abs_difference": 0, "in_band": "habitat_mask",
    }
    row.update(kw)
    return row


def test_an_identical_asset_reads_as_reproduced_exactly():
    (line,) = _load().summarise_rows([_row()])
    assert "masking/habitat_mask" in line and "reproduced exactly" in line


def test_a_differing_asset_says_how_much_and_where():
    (line,) = _load().summarise_rows(
        [_row(stage="data_load", key="s2_composite", bands=4, pixel_values_compared=4000,
              pixel_bands_that_differ=1000,
              largest_abs_difference=497, in_band="B8_median")]
    )
    assert "differs: 1000 of 4000 pixel values (25.0%)" in line
    assert "largest difference 497 in band B8_median" in line


def test_a_mask_difference_is_reported_even_when_values_agree():
    (line,) = _load().summarise_rows([_row(pixels_whose_mask_differs=12)])
    assert "reproduced exactly" not in line and "the mask differs at 12" in line


def test_a_different_pixel_grid_is_flagged():
    (line,) = _load().summarise_rows([_row(same_grid=False)])
    assert "different pixel grids" in line


def test_a_missing_asset_is_a_row_not_a_crash():
    (line,) = _load().summarise_rows(
        [{"stage": "clustering", "key": "cluster_labels", "outcome": "not cached for x_repro"}]
    )
    assert "clustering/cluster_labels" in line and "not cached for x_repro" in line


def test_the_script_cannot_submit_a_task_or_write_an_asset():
    """It is run while batch jobs are queued, so it must only read."""
    src = SCRIPT.read_text()
    for forbidden in ("ee.batch", "Export.", "start_export", "copyAsset", "deleteAsset",
                      "createFolder", "createAsset", "use_cache=True"):
        assert forbidden not in src, forbidden


def test_the_run_record_sits_beside_the_result_and_holds_the_commit():
    mod = _load()
    assert mod.run_record_path(Path("docs/x/site_assets.json")) == Path("docs/x/site_assets_run.json")
    src = SCRIPT.read_text()
    rows_part, record_part = src.split("record = {", 1)
    assert '"date"' in record_part and "git_state()" in record_part and '"command_line"' in record_part
    # The rows themselves stay results only: no date and no commit goes into them.
    assert "datetime.datetime.now" not in rows_part
