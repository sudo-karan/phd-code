"""scripts/check_fit_excludes_stands.py, offline: what it concludes, and that its requests are
valid (built with earthengine-api's offline test initialisation, as in
tests/test_check_snic_on_kept_land.py: nothing is sent)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "check_fit_excludes_stands.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_fit_excludes_stands", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Ten units with a row, 2.0 as Earth Engine sends a number; stands 3, 7 and 11 are below the
# minimum, and 11 has no row (outside the habitat mask, say).
EVERY = [float(i) for i in range(10)]
BELOW = {3: 0.4, 7: 0.2, 11: 0.9}
FIT = [v for v in EVERY if int(v) not in BELOW]
REPORT = {"n_stands_below_min_area": 3, "n_stands_left_out_of_fit": 2}


def _result(**rows: Any) -> dict[str, Any]:
    mod = _load()
    return {
        "rows": {**mod.compare_rows(EVERY, FIT, BELOW, REPORT), **rows},
        "types": mod.typed([{"unit": 3, "histogram": {"1": 4}}, {"unit": 7, "histogram": {"0": 2}}],
                           [3, 7]),
        "summary_numbers": {"units_in_habitat": 12, "units_fitted": 8,
                            "units_dropped_missing_band": 2, "units_left_out_of_fit": 2},
        "stage_warnings": [],
        "export_tasks_submitted": 0,
    }


def test_rows_left_out_as_intended_pass_every_check():
    rows = _load().compare_rows(EVERY, FIT, BELOW, REPORT)
    assert rows["rows_add_up"] and rows["fit_holds_no_stand_below_min"]
    assert rows["left_out_are_the_stands_below_min_with_a_row"]
    assert (rows["rows"], rows["fit_rows"], rows["left_out_rows"]) == (10, 8, 2)
    assert rows["stands_below_min_with_a_row"] == 2
    text = "\n".join(_load().verdicts(_result()))
    assert text.count("as expected:") == 6 and "NOT" not in text
    assert "the fit's 8 rows and the 2 left out are the 10 rows of every unit" in text
    assert "each of the 2 stands left out has one type" in text
    assert "units_in_habitat 12 = units_fitted 8 + units_dropped_missing_band 2 + " \
           "units_left_out_of_fit 2" in text


def test_a_mask_that_does_not_match_the_labels_is_caught():
    """If the remap matched no label, the fit would hold every row: nothing left out."""
    mod = _load()
    rows = mod.compare_rows(EVERY, EVERY, BELOW, {**REPORT, "n_stands_left_out_of_fit": 0})
    assert not rows["fit_holds_no_stand_below_min"]
    assert rows["fit_rows_of_stands_below_min"] == [3, 7]
    assert not rows["left_out_are_the_stands_below_min_with_a_row"]
    text = "\n".join(mod.verdicts({**_result(), "rows": rows}))
    assert "NOT as expected: the fit holds rows of stands below the minimum: [3, 7]" in text


def test_a_row_left_out_that_is_not_below_the_minimum_is_caught():
    mod = _load()
    rows = mod.compare_rows(EVERY, [v for v in FIT if v != 5.0], BELOW, REPORT)
    assert rows["left_out_not_below_min"] == [5]
    assert not rows["left_out_are_the_stands_below_min_with_a_row"]


def test_untyped_stands_and_warnings_are_named():
    mod = _load()
    res = _result()
    res["types"] = mod.typed([{"unit": 3, "histogram": {"1": 4, "2": 1}}], [3, 7])
    res["stage_warnings"] = ["k-means fit: none of the 2 stand(s) below merge.min_area_ha had a row",
                             "2 stand_clusters unit(s) sit inside the habitat mask but contributed"]
    text = "\n".join(mod.verdicts(res))
    assert "NOT as expected: of the 2 stands left out, 1 have no type and 1 more than one" in text
    assert ("NOT as expected: the clustering stage logged 1 warning(s) of the path with the setting "
            "on: k-means fit") in text


def test_a_warning_of_the_default_path_does_not_count_against_it():
    res = _result()
    res["stage_warnings"] = ["2 stand_clusters unit(s) sit inside the habitat mask but contributed"]
    assert "NOT" not in "\n".join(_load().verdicts(res))


def test_with_no_stand_below_the_minimum_it_says_it_tested_nothing():
    """With the setting on the stage always takes the path, so with nothing below the minimum
    every other line holds: that must not read as a pass."""
    mod = _load()
    res = _result()
    res["rows"] = mod.compare_rows(EVERY, EVERY, {}, {"n_stands_left_out_of_fit": 0})
    res["types"] = mod.typed([], [])
    lines = mod.verdicts(res)
    assert lines[0] == ("NOT as expected: no stand below the minimum has a training row, so "
                        "nothing was left out of the fit and the lines below test nothing")


def test_an_error_is_reported_as_such():
    text = "\n".join(_load().verdicts({"error": "the stage left nothing out",
                                       "export_tasks_submitted": 0}))
    assert text.startswith("the check could not be run: the stage left nothing out")


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
            if context.startswith("stand labels"):
                return {"every": EVERY, "fit": FIT}
            return {"groups": [{"unit": 3, "histogram": {"1": 4}}]}

        roi = ee.Geometry.Rectangle([82.80, 18.50, 82.85, 18.55])
        img = ee.Image("projects/fake/assets/x")
        sample = img.stratifiedSample(numPoints=1, classBand="fmu_label", region=roi, scale=10)
        labels = mod.row_labels(ee, get_info, training_sample=sample, fit_sample=sample,
                                label_band="fmu_label")
        assert labels == {"every": EVERY, "fit": FIT}
        groups = mod.types_of(ee, get_info, cluster_labels=img, unit_labels=img, left_out=[3, 7],
                              roi=roi, scale=10)
        assert groups == [{"unit": 3, "histogram": {"1": 4}}]
        assert mod.types_of(ee, get_info, cluster_labels=img, unit_labels=img, left_out=[],
                            roi=roi, scale=10) == []
        assert len(sent) == 2
    finally:
        case.tearDown()
