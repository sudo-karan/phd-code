"""The export stage's vector layers one ROI part at a time (round 9, issue #44 item 11), offline.

An ROI of one polygon is one part, and its layers are built exactly as before round 9.
An ROI of several is split into its own polygons; each layer is built, counted and read
back a part at a time, and numbered 1..N over all parts by the stage's own rule. Parts
within two pixels of each other are not split.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from fmu.stages import export

REPO = Path(__file__).resolve().parent.parent


class _Part:
    def __init__(self, name: str, gaps: dict[str, float]):
        self.name, self.gaps = name, gaps

    def distance(self, other: _Part, maxError: float) -> float:  # noqa: N803 - Earth Engine's name
        return self.gaps[other.name]


class _Roi:
    def __init__(self, parts: list[_Part]):
        self.parts = parts

    def geometries(self) -> Any:
        roi = self

        class _List:
            def size(self) -> int:
                return len(roi.parts)

            def get(self, i: int) -> _Part:
                return roi.parts[i]

        return _List()


@pytest.fixture
def fake_ee():
    with patch("fmu.stages.export.safe_get_info", side_effect=lambda obj, context="": obj), \
         patch("fmu.stages.export.ee.Geometry", side_effect=lambda g: g), \
         patch("fmu.stages.export.ee.List", side_effect=lambda items: list(items)):
        yield


def _three_parts(gap: float) -> _Roi:
    names = ["a", "b", "c"]
    return _Roi([_Part(n, {m: gap for m in names if m != n}) for n in names])


def test_one_polygon_is_one_part_the_roi_itself(fake_ee):
    roi = _Roi([_Part("a", {})])
    assert export._roi_parts(roi, 10) == [roi]


def test_several_polygons_are_their_parts(fake_ee):
    roi = _three_parts(gap=300.0)
    parts = export._roi_parts(roi, 10)
    assert [p.name for p in parts] == ["a", "b", "c"]


def test_parts_within_two_pixels_are_built_whole(fake_ee, caplog):
    roi = _three_parts(gap=15.0)
    assert export._roi_parts(roi, 10) == [roi]
    assert "within two pixels" in caplog.text


def test_one_part_builds_the_layer_as_before():
    calls: list[Any] = []

    def build(*, ctx, config, scale, region):
        calls.append(region)
        return f"layer over {region}"

    whole, parts = export._layer_by_part(build, ctx=None, config=None, scale=10, parts=["ROI"], id_field="stand_id")
    assert whole == "layer over ROI" and parts == ["layer over ROI"] and calls == ["ROI"]


def test_several_parts_are_built_one_by_one_and_numbered_over_all():
    built: list[Any] = []

    def build(*, ctx, config, scale, region):
        built.append(region)
        return f"layer over {region}"

    class _Union:
        def __init__(self, items):
            self.items = items

        def flatten(self):
            return ("flattened", tuple(self.items))

    with patch("fmu.stages.export.ee.FeatureCollection", side_effect=_Union), \
         patch("fmu.stages.export._renumber_by_centroid",
               side_effect=lambda fc, id_field: ("renumbered", fc, id_field)):
        whole, parts = export._layer_by_part(
            build, ctx=None, config=None, scale=10, parts=["p1", "p2"], id_field="unit_id"
        )
    assert built == ["p1", "p2"]
    assert parts == ["layer over p1", "layer over p2"]
    assert whole == ("renumbered", ("flattened", ("layer over p1", "layer over p2")), "unit_id")


def test_counts_add_up_over_the_parts_and_a_split_stand_is_counted_once():
    class _Layer:
        def __init__(self, labels):
            self.labels = labels

        def size(self):
            return len(self.labels)

        def aggregate_array(self, prop):
            assert prop == "stand_lbl"
            return self.labels

    parts = [_Layer([1, 2, 2]), _Layer([7.0, 8])]
    with patch("fmu.stages.export.safe_get_info", side_effect=lambda obj, context="": obj), \
         patch("fmu.stages.export.ee.Dictionary", side_effect=lambda d: d), \
         patch("fmu.stages.export.ee.List", side_effect=lambda items: list(items)):
        counts = export._count_by_part(parts, context="test", label_property="stand_lbl")
        plain = export._count_by_part(parts, context="test")
    assert counts == {"n_features": 5, "n_stands": 4, "n_split": 1, "max_pieces": 2}
    assert plain["n_features"] == 5 and plain["n_stands"] == 0


def test_the_builders_take_a_region():
    import inspect

    for build in (
        export._build_merged_feature_collection,
        export._build_snic_feature_collection,
        export._build_dissolved_feature_collection,
    ):
        assert "region" in inspect.signature(build).parameters


def _runner():
    sys.path.insert(0, str(REPO / "odisha_script"))
    spec = importlib.util.spec_from_file_location(
        "odisha_phase2_2_run_pipeline", REPO / "odisha_script" / "odisha_phase2_2_run_pipeline.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_runner_reads_each_part_and_numbers_over_all(monkeypatch):
    runner = _runner()

    def polygon(lat, lon, **props):
        return {"type": "Feature", "geometry": None,
                "properties": {"centroid_lat": lat, "centroid_lon": lon, **props}}

    read = {
        "p1": [polygon(20.4, 85.1, stand_id=1, stand_lbl=8)],
        "p2": [polygon(20.6, 85.3, stand_id=1, stand_lbl=3), polygon(20.5, 85.1, stand_id=2, stand_lbl=4)],
    }
    monkeypatch.setattr(runner, "_roi_parts", lambda roi, scale: ["p1", "p2"])
    monkeypatch.setattr(runner, "to_wgs84", lambda fc: fc)
    monkeypatch.setattr(runner, "read_layer", lambda fc, context: read[fc])
    monkeypatch.setattr(runner, "LAYER_BUILDERS", {
        "stands_merged": (lambda *, ctx, config, scale, region: region, "stand_id"),
    })

    class _Ctx:
        def get(self, key):
            return "ROI"

    class _Cfg:
        name = "cfg"

        class export:  # noqa: N801 - stands in for config.export
            analysis_scale_m = 10

    gj = runner.read_layer_by_part(_Cfg(), _Ctx(), "stands_merged")
    assert gj["type"] == "FeatureCollection" and gj["columns"] == []
    assert [(f["properties"]["stand_id"], f["properties"]["stand_lbl"]) for f in gj["features"]] == [
        (1, 3), (2, 4), (3, 8)
    ]
