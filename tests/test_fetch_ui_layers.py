"""The parts of scripts/fetch_ui_layers.py that need no Earth Engine."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_ui_layers as fetch  # noqa: E402


def test_bands_to_fetch_adds_canopy_height_once_and_keeps_the_order():
    odisha = [("s2_composite", "B4_median"), ("structure_features", "canopy_height"),
              ("optical_features", "ndvi_amplitude_annual")]
    assert fetch.bands_to_fetch(odisha) == odisha
    without = [("s2_composite", "B4_median"), ("radar_features", "vv_minus_vh_median")]
    assert fetch.bands_to_fetch(without) == [*without, ("structure_features", "canopy_height")]


def test_bands_to_fetch_leaves_out_the_band_segmentation_computes_itself():
    got = fetch.bands_to_fetch([("s2_composite", "composite_nirv"), ("s2_composite", "B8_median")])
    assert got == [("s2_composite", "B8_median"), ("structure_features", "canopy_height")]


def test_mask_nodata_writes_nan_in_every_band_where_a_pixel_is_not_valid():
    data = np.arange(12, dtype="float64").reshape(2, 2, 3)
    valid = np.array([[1, 0, 1], [1, 1, 0]])
    out = fetch.mask_nodata(data, valid)
    assert out.dtype == np.float32
    assert np.isnan(out[:, 0, 1]).all() and np.isnan(out[:, 1, 2]).all()
    assert np.isfinite(out[:, valid == 1]).all()
    assert out[1, 1, 0] == 9.0


def test_grid_files_are_the_true_colour_files_in_part_order(tmp_path):
    folder = tmp_path / "a_run"
    folder.mkdir()
    for name in ("part02_b_true_colour.tif", "part01_a_true_colour.tif", "part01_a_habitat_mask.tif"):
        (folder / name).write_bytes(b"")
    assert [p.name for p in fetch.grid_files(tmp_path, "a_run")] == ["part01_a_true_colour.tif", "part02_b_true_colour.tif"]
    with pytest.raises(SystemExit, match="masking transparency tool"):
        fetch.grid_files(tmp_path, "another_run")


def test_band_groups_keep_each_request_under_the_limit_and_lose_no_band():
    names = [f"A{i:02d}" for i in range(64)]
    # A small part: everything in one request.
    assert fetch.band_groups(names, 100_000) == [names]
    # A part of 360,000 pixels: 64 bands and a validity band would be 93.6 MB.
    groups = fetch.band_groups(names, 360_000)
    assert [b for g in groups for b in g] == names
    assert all((len(g) + 1) * 360_000 * 4 <= fetch.MAX_REQUEST_BYTES for g in groups)
    assert len(groups) > 1
    # A part so large that one band is over the limit still goes one band at a time.
    assert fetch.band_groups(names[:3], 20_000_000) == [["A00"], ["A01"], ["A02"]]
