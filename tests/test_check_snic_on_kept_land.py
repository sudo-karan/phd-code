"""scripts/check_snic_on_kept_land.py, offline: what it says, and that its requests are valid.

The requests are built with earthengine-api's offline test initialisation, as in
tests/test_mask_before_snic_ee_graph.py: nothing is sent, but a misspelt function or
argument fails here.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "check_snic_on_kept_land.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_snic_on_kept_land", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _result(**masked: Any) -> dict[str, Any]:
    run = {"masked_pixels_labelled": 0, "kept_pixels_unlabelled": 0, "superpixels": 900,
           "pieces": 900, "superpixels_in_pieces": 0, "patches_without_grid_point": 40,
           "superpixels_on_those_patches": 40, **masked}
    return {
        "masked_run": run,
        "seed_grid_is_snics_own_grid": {"pixels": 1000, "pixels_differing": 0},
        "size_matters_with_seeds": {"pixels": 1000, "pixels_differing": 0},
        "connected_components_max_size": {"big_square_pixels": 225, "small_square_pixels": 81,
                                          "big_square_labelled": 225, "small_square_labelled": 81},
        "connected_pixel_count": {"big_square_min": 100, "big_square_max": 100,
                                  "small_square_min": 81, "small_square_max": 81},
        "export_tasks_submitted": 0,
    }


def test_all_as_expected_says_so_line_by_line():
    lines = _load().verdicts(_result())
    text = "\n".join(lines)
    assert text.count("as expected:") == 4 and "NOT" not in text
    assert "each of the 40 kept patches no grid point falls in is one superpixel" in text
    assert "0 of 1000 pixels differ" in text
    assert "maxSize is an extent" in text
    assert "big square holds 100 to 100, small square 81 to 81" in text
    assert lines[-1] == "export tasks submitted: 0"


def test_what_is_not_as_expected_is_named_with_its_count():
    text = "\n".join(_load().verdicts(_result(
        masked_pixels_labelled=12, superpixels_in_pieces=3, pieces=903,
        superpixels_on_those_patches=400)))
    assert "NOT as expected: SNIC gave 12 masked pixels a superpixel" in text
    assert "3 superpixels are in more than one piece (903 pieces for 900 superpixels)" in text
    assert "40 kept patches no grid point falls in hold 400 superpixels" in text


def test_a_count_limit_and_a_failed_step_are_reported_as_such():
    res = _result()
    res["connected_components_max_size"]["big_square_labelled"] = 0
    res["masked_run"] = {"error": "User memory limit exceeded."}
    text = "\n".join(_load().verdicts(res))
    assert "maxSize is a number of pixels" in text
    assert "the masked segmentation could not be run: User memory limit exceeded." in text


def test_its_requests_are_valid_earth_engine_requests():
    apitestcase = pytest.importorskip("ee.apitestcase")

    class _Offline(apitestcase.ApiTestCase):
        __test__ = False

        def runTest(self) -> None:  # noqa: N802
            pass

    case = _Offline()
    case.setUp()
    try:
        import ee

        mod = _load()
        sent: list[str] = []

        def get_info(obj: Any, context: str = "") -> Any:
            ee.serializer.encode(obj, for_cloud_api=True)  # an invalid request fails here
            sent.append(context)
            if context.startswith("checks 1-2"):
                return {"masked_labelled": 0, "kept_unlabelled": 0}
            if context.startswith("checks 3-4"):
                return {"superpixels": {"1": 5, "2": 7}, "pieces": {"8": 5, "9": 7},
                        "extra_patches": {"3": 2}, "labels_on_extra": {"2": 2}}
            if context.startswith("check:"):
                return {"differ": 0, "n": 10}
            return {"big_square_pixels": 225, "small_square_pixels": 81,
                    "big_square_labelled": 225, "small_square_labelled": 81,
                    "big_min": 100, "big_max": 100, "small_min": 81, "small_max": 81}

        grid = ee.Projection("EPSG:32644").atScale(10)
        roi = ee.Geometry.Rectangle([82.80, 18.50, 82.85, 18.55])
        img = ee.Image("projects/fake/assets/x")
        kept = img.gt(0)
        got = mod.measure_masked(ee, get_info, raw=img, final=img, kept=kept, on_grid=kept,
                                 seeds=kept, roi=roi, grid=grid, connectivity=8)
        assert got["superpixels"] == 2 and got["superpixels_in_pieces"] == 0
        assert got["patches_without_grid_point"] == got["superpixels_on_those_patches"] == 1
        assert mod.differing(ee, get_info, img, img, roi=roi, grid=grid, context="check: x") == {
            "pixels": 10, "pixels_differing": 0}
        cc, cpc = mod.squares(ee, get_info, x0=500000, y0=2000000, epsg=32644, scale=10)
        assert cc["big_square_labelled"] == 225 and cpc["small_square_max"] == 81
        assert len(sent) == 4
    finally:
        case.tearDown()
