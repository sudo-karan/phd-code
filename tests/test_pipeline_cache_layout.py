"""The orchestrator under the two cache layouts (round 9), offline.

With an empty cache a run takes the per-step layout: assets named by per-step
keys, images exported on the analysis grid (crs and crs_transform, no scale) and
carrying the record of their input images, tables exported as tables. With a
legacy asset in the cache the run takes the legacy layout and exports exactly as
before round 9 (the scale alone). The manifest says which, and why.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

import ee
import pytest

from fmu.config import Config
from fmu.pipeline import Pipeline
from fmu.stages.base import (
    PipelineContext,
    Stage,
    StageResult,
    _clear_registry_for_testing,
    _stage_registry,
    register_stage,
)
from fmu.utils.caching import ExportTaskInfo, active_layout

GRID = {"crs": "EPSG:32645", "crs_transform": [10.0, 0.0, 0.0, 0.0, 10.0, 0.0]}

# The ROI file `_config` names: a real one, written for each test to a temporary folder of
# its own, not the run folder the tests read. Since round 14 the per-step cache keys raise
# for a ROI file they cannot read, where they hashed None before (round 13 question 41).
_ROI_FILE: dict[str, Path] = {}
_ROI = {
    "type": "FeatureCollection",
    "features": [{"type": "Feature", "properties": {}, "geometry": {
        "type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}}],
}


@pytest.fixture(autouse=True)
def _a_real_roi_file(tmp_path_factory, monkeypatch):
    path = tmp_path_factory.mktemp("roi") / "t.geojson"
    path.write_text(json.dumps(_ROI))
    monkeypatch.setitem(_ROI_FILE, "path", path)


def _config(name: str = "layout_test") -> Config:
    return Config.model_validate(
        {
            "name": name,
            "roi": {"name": "t", "roi_file": str(_ROI_FILE["path"])},
            "dates": {
                "phenology": {"start": "2020-01-01", "end": "2020-12-31"},
                "radar": {"start": "2020-01-01", "end": "2020-12-31"},
                "optical_composite": {"start": "2020-01-01", "end": "2020-12-31"},
            },
        }
    )


class _FakeImage(ee.Image):
    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.props: dict[str, Any] = {}

    def set(self, key, value):  # noqa: A003 - Earth Engine's name
        out = _FakeImage(self.tag)
        out.props = {**self.props, key: value}
        return out

    def get(self, key):
        return self.props.get(key)

    def __repr__(self) -> str:
        return f"<fake image {self.tag}>"


class _FakeTable(ee.FeatureCollection):
    def __init__(self, tag: str) -> None:
        self.tag = tag

    def __repr__(self) -> str:
        return f"<fake table {self.tag}>"


class _FakeGeometry(ee.Geometry):
    def __init__(self) -> None:
        pass


class _FakeCollection:
    """What input_collections returns; the pipeline reads its ids in one request."""

    def __init__(self, ids: list[str]) -> None:
        self.ids = ids


@pytest.fixture(autouse=True)
def _registry():
    """Each test registers its own stages; the registry is put back as it was after."""
    saved = dict(_stage_registry)
    _clear_registry_for_testing()
    yield
    _clear_registry_for_testing()
    _stage_registry.update(saved)


def _register(run_log: list[str]) -> None:
    @register_stage("img_stage")
    class ImgStage(Stage):
        name = "img_stage"
        required_inputs = {"roi"}
        produces = {"img"}

        def input_collections(self, ctx, config):
            return {"coll": _FakeCollection(["b/2", "b/1"])}

        def run(self, ctx, config):
            run_log.append("img")
            return StageResult(outputs={"img": _FakeImage("live img")})

    @register_stage("table_stage")
    class TableStage(Stage):
        name = "table_stage"
        required_inputs = {"img"}
        produces = {"tbl"}
        cacheable_outputs: ClassVar[set[str]] = {"tbl"}
        table_outputs: ClassVar[set[str]] = {"tbl"}

        def run(self, ctx, config):
            run_log.append("tbl")
            return StageResult(outputs={"tbl": _FakeTable("live tbl")})


@contextmanager
def _fake_ee(existing: set[str]):
    """Fake the cache calls of fmu.pipeline. Paths are <stage>/<key>__<suffix>."""
    calls: dict[str, list[dict[str, Any]]] = {"image": [], "table": []}

    def start_export(**kw):
        calls["image"].append(kw)
        return ExportTaskInfo(task_id=f"I{len(calls['image'])}", asset_path=kw["asset_path"],
                              description=kw["description"])

    def start_table_export(table, **kw):
        calls["table"].append({"table": table, **kw})
        return ExportTaskInfo(task_id=f"T{len(calls['table'])}", asset_path=kw["asset_path"],
                              description=kw["description"])

    def safe_get_info(obj, context=""):
        # The pipeline reads input ids as one ee.Dictionary of aggregate_arrays,
        # and the cached assets' records as one ee.Dictionary of .get()s.
        return obj

    def fake_dictionary(d):
        return {k: (sorted(v.ids) if isinstance(v, _FakeCollection) else v) for k, v in d.items()}

    with patch("fmu.pipeline.cached_asset_path",
               side_effect=lambda n, s, k, f=None: f"{s}/{k}__{f}"), \
         patch("fmu.pipeline.asset_exists", side_effect=lambda p: p in existing), \
         patch("fmu.pipeline.load_cached_image", side_effect=lambda p: _FakeImage(f"cached {p}")), \
         patch("fmu.pipeline.load_cached_table", side_effect=lambda p: _FakeTable(f"cached {p}")), \
         patch("fmu.pipeline.start_export", side_effect=start_export), \
         patch("fmu.pipeline.start_table_export", side_effect=start_table_export), \
         patch("fmu.pipeline.analysis_grid_export_args", return_value=dict(GRID)), \
         patch("fmu.pipeline.safe_get_info", side_effect=safe_get_info), \
         patch("ee.Dictionary", side_effect=fake_dictionary), \
         patch("ee.ImageCollection", side_effect=lambda c: _AggCollection(c)):
        yield calls


class _AggCollection:
    def __init__(self, c: _FakeCollection) -> None:
        self.c = c

    def aggregate_array(self, prop: str) -> _FakeCollection:
        assert prop == "system:id"
        return self.c


def _run(tmp_path, existing: set[str], **kw):
    run_log: list[str] = []
    _register(run_log)
    ctx = PipelineContext()
    ctx.set("roi", _FakeGeometry())
    with _fake_ee(existing) as calls:
        result = Pipeline(["img_stage", "table_stage"], use_cache=True, **kw).run(
            config=_config(), run_dir=tmp_path, initial_context=ctx
        )
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    return result, manifest, calls, run_log


def test_an_empty_cache_takes_the_per_step_layout(tmp_path):
    result, manifest, calls, run_log = _run(tmp_path, set())
    assert manifest["cache_layout"] == "per_step"
    assert "no asset of the legacy layout" in manifest["cache_layout_reason"]
    assert run_log == ["img", "tbl"]
    (img_export,) = calls["image"]
    # on the analysis grid: crs and crs_transform; the scale is what the grid is at
    assert img_export["crs"] == GRID["crs"] and img_export["crs_transform"] == GRID["crs_transform"]
    assert img_export["asset_path"].startswith("img_stage/img__s")
    # the record of its input images rides on the asset
    record = json.loads(img_export["image"].props["fmu_input_images"])
    assert record["coll"]["count"] == 2 and len(record["coll"]["sha256"]) == 64
    (tbl_export,) = calls["table"]
    assert tbl_export["asset_path"].startswith("table_stage/tbl__s")
    stages = {s["name"]: s for s in manifest["stages"]}
    assert stages["img_stage"]["cache_key"].startswith("s")
    images = stages["img_stage"]["input_images"]["img"]
    assert images["source"] == "computed in this run"
    assert images["collections"]["coll"]["ids"] == ["b/1", "b/2"]
    assert manifest["environment"]["python"]
    lists = json.loads((tmp_path / "input_images.json").read_text())
    assert lists == {"img_stage": {"coll": ["b/1", "b/2"]}}


def test_a_legacy_asset_keeps_the_legacy_layout_and_its_exports(tmp_path):
    cfg = _config()
    from fmu.utils.caching import config_fingerprint

    legacy_img = f"img_stage/img__{config_fingerprint(cfg)}"
    result, manifest, calls, run_log = _run(tmp_path, {legacy_img})
    assert manifest["cache_layout"] == "legacy"
    # img is read back; the table stage misses and exports as a table
    assert run_log == ["tbl"]
    assert calls["image"] == []
    (tbl_export,) = calls["table"]
    assert tbl_export["asset_path"] == f"table_stage/tbl__{config_fingerprint(cfg)}"
    img = {s["name"]: s for s in manifest["stages"]}["img_stage"]
    assert img["cache_status"] == {"img": "hit"}
    # a legacy asset carries no record of its input images
    assert "not_recorded" in img["input_images"]["img"]


def test_legacy_image_exports_are_as_before_round_9(tmp_path):
    result, manifest, calls, _ = _run(tmp_path, set(), cache_layout="legacy")
    (img_export,) = calls["image"]
    assert img_export["scale"] == 10
    assert "crs" not in img_export and "crs_transform" not in img_export
    assert "fmu_input_images" not in img_export["image"].props
    assert manifest["cache_layout_reason"] == "given to Pipeline()"


def test_a_cached_per_step_asset_gives_its_record_back(tmp_path):
    cfg = _config()
    from fmu.utils.caching import step_key

    path = f"img_stage/img__{step_key(cfg, 'img_stage')}"
    recorded = json.dumps({"coll": {"count": 2, "sha256": "ab" * 32}})

    def load(p):
        img = _FakeImage(f"cached {p}")
        img.props = {"fmu_input_images": recorded}
        return img

    run_log: list[str] = []
    _register(run_log)
    ctx = PipelineContext()
    ctx.set("roi", _FakeGeometry())
    with _fake_ee({path}), patch("fmu.pipeline.load_cached_image", side_effect=load):
        Pipeline(["img_stage", "table_stage"], use_cache=True, cache_layout="per_step").run(
            config=cfg, run_dir=tmp_path, initial_context=ctx
        )
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    img = {s["name"]: s for s in manifest["stages"]}["img_stage"]
    assert img["cache_status"] == {"img": "hit"}
    assert img["input_images"]["img"] == {
        "source": "the cached asset",
        "collections": {"coll": {"count": 2, "sha256": "ab" * 32}},
    }


def test_the_layout_is_in_use_during_the_run_only(tmp_path):
    seen: list[Any] = []

    @register_stage("looks")
    class Looks(Stage):
        name = "looks"
        required_inputs: ClassVar[set[str]] = set()
        produces = {"x"}
        cacheable_outputs: ClassVar[set[str]] = set()

        def run(self, ctx, config):
            seen.append(active_layout(config))
            return StageResult(outputs={"x": 1})

    cfg = _config()
    with _fake_ee(set()):
        Pipeline(["looks"], use_cache=True).run(config=cfg, run_dir=tmp_path)
    assert seen == ["per_step"]
    assert active_layout(cfg) is None


def test_no_cache_no_layout(tmp_path):
    @register_stage("plain")
    class Plain(Stage):
        name = "plain"
        required_inputs: ClassVar[set[str]] = set()
        produces = {"x"}

        def run(self, ctx, config):
            return StageResult(outputs={"x": 1})

    with patch("fmu.pipeline.asset_exists") as exists:
        Pipeline(["plain"]).run(config=_config(), run_dir=tmp_path)
    exists.assert_not_called()
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["cache_layout"] is None and manifest["stages"][0]["cache_key"] is None


def test_an_unknown_layout_is_refused():
    with pytest.raises(ValueError):
        Pipeline(["x"], cache_layout="sideways")


def test_failed_input_ids_are_recorded_not_raised(tmp_path):
    run_log: list[str] = []
    _register(run_log)
    ctx = PipelineContext()
    ctx.set("roi", _FakeGeometry())
    with _fake_ee(set()), patch("fmu.pipeline.safe_get_info", side_effect=ee.EEException("boom")):
        Pipeline(["img_stage", "table_stage"], use_cache=True).run(
            config=_config(), run_dir=tmp_path, initial_context=ctx
        )
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    img = {s["name"]: s for s in manifest["stages"]}["img_stage"]
    assert "boom" in img["input_images"]["img"]["error"]


def test_the_real_start_export_puts_the_grid_on_the_task():
    from fmu.utils import caching

    task = MagicMock()
    task.id = "TASK"
    with patch("fmu.utils.caching.ensure_parent_folders"), \
         patch("fmu.utils.caching.ee.batch.Export.image.toAsset", return_value=task) as to_asset:
        caching.start_export(image="IMG", asset_path="p/a/b", roi="ROI", scale=10,
                             description="d", **GRID)
        caching.start_export(image="IMG", asset_path="p/a/c", roi="ROI", scale=10, description="d")
    on_grid, legacy = to_asset.call_args_list
    assert on_grid.kwargs["crs"] == "EPSG:32645"
    assert on_grid.kwargs["crsTransform"] == GRID["crs_transform"]
    assert "scale" not in on_grid.kwargs
    assert legacy.kwargs == {"image": "IMG", "description": "d", "assetId": "p/a/c",
                             "region": "ROI", "maxPixels": 1_000_000_000, "scale": 10}


def test_the_grid_args_come_from_the_analysis_grid():
    from fmu.utils import grid

    proj = MagicMock()
    with patch("fmu.utils.grid.analysis_grid", return_value=proj), \
         patch("fmu.utils.grid.safe_get_info",
               return_value={"type": "Projection", "crs": "EPSG:32644", "transform": [10, 0, 0, 0, 10, 0]}):
        args = grid.analysis_grid_export_args("ROI", 10)
    assert args == {"crs": "EPSG:32644", "crs_transform": [10.0, 0.0, 0.0, 0.0, 10.0, 0.0]}


def test_a_stage_that_caches_nothing_has_no_cache_key(tmp_path):
    """Round 9 question 5 (a): profiling and export cache nothing, so no key names an asset."""

    @register_stage("caches_nothing")
    class CachesNothing(Stage):
        name = "caches_nothing"
        required_inputs: ClassVar[set[str]] = set()
        produces = {"x"}
        cacheable_outputs: ClassVar[set[str]] = set()

        def run(self, ctx, config):
            return StageResult(outputs={"x": 1})

    with _fake_ee(set()):
        Pipeline(["caches_nothing"], use_cache=True).run(config=_config(), run_dir=tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["cache_layout"] == "per_step"
    assert manifest["stages"][0]["cache_key"] is None
