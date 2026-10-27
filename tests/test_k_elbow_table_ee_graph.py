"""The k elbow's table as the client sends it to Earth Engine: every row has a geometry (round 14).

Offline, as tests/test_clustering_fit_excludes_ee_graph.py: earthengine-api's own test
initialisation (`ee.apitestcase`) and nothing sent anywhere. In both runs of round 14's second live
check (27 Oct 2026) Earth Engine refused the elbow's cache export, "Unable to export features with
null geometry.": the step made each row a Feature with no geometry argument (the round's record,
Done, Task 4, the second batch). Here the step runs in the fit's space, as every R3 config runs it,
on the real client with the answers of tests/_clustering_stand_ins.py, and its table is encoded as
it is sent, both alone and as the expression of the export to an asset that the pipeline makes of
it (fmu.utils.caching.start_table_export, Export.table.toAsset): each row must be a Feature with the
fixed point [0, 0] as its geometry and the step's properties. What Earth Engine does with the
request is not checked here; the round's smoke test runs it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from _clustering_stand_ins import answers, inputs

apitestcase = pytest.importorskip("ee.apitestcase")

REPO = Path(__file__).resolve().parent.parent
BOX_YAML = REPO / "configs" / "odisha_v120_3ha_squares_koraput.yaml"
POINT = {"functionInvocationValue": {
    "functionName": "GeometryConstructors.Point",
    "arguments": {"coordinates": {"constantValue": [0, 0]}},
}}


class _Offline(apitestcase.ApiTestCase):
    __test__ = False  # a fixture's helper, not a test of its own

    def runTest(self) -> None:  # noqa: N802 - unittest's name
        pass


@pytest.fixture
def offline_ee():
    case = _Offline()
    case.setUp()
    try:
        import ee

        yield ee
    finally:
        case.tearDown()


def _expanded(encoded: dict[str, Any]) -> Any:
    """An encoded expression as one tree, each `valueReference` replaced by its value (the
    table is small: a value referred to by every row is copied into each)."""
    values = encoded["values"]

    def expand(node: Any) -> Any:
        if isinstance(node, dict):
            if set(node) == {"valueReference"}:
                return expand(values[node["valueReference"]])
            return {key: expand(value) for key, value in node.items()}
        if isinstance(node, list):
            return [expand(value) for value in node]
        return node

    return expand(values[encoded["result"]])


def _arguments(node: Any, name: str) -> list[dict[str, Any]]:
    """The arguments of every call of `name` in an expanded tree, in order."""
    found: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            inv = value.get("functionInvocationValue")
            if isinstance(inv, dict) and inv["functionName"] == name:
                found.append(inv.get("arguments", {}))
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(node)
    return found


def test_each_row_is_sent_with_the_fixed_point_as_its_geometry(offline_ee, monkeypatch):
    ee = offline_ee
    import fmu.stages.clustering as clustering
    from fmu.config import Config
    from fmu.stages import k_elbow
    from fmu.stages.base import PipelineContext

    raw = yaml.safe_load(BOX_YAML.read_text())
    raw["clustering"] = {**raw.get("clustering", {}), "fit_outside_earth_engine": True,
                         "log_rule": "right_skew", "fit_excludes_stands_below_min_area": False}
    raw["k_elbow"] = {"in_fit_space": True}
    config = Config.model_validate(raw)
    answer = answers(config, [])

    def get_info(obj: Any, context: str = "") -> Any:
        assert json.dumps(ee.serializer.encode(obj, for_cloud_api=True))  # every request encodes
        return answer(obj, context)

    for module in (k_elbow, clustering):
        monkeypatch.setattr(module, "safe_get_info", get_info)
    ctx = PipelineContext()
    ctx.set("roi", ee.Geometry.Rectangle([82.80, 18.50, 82.85, 18.55]))
    for key in sorted(inputs(config) - {"roi"}):
        ctx.set(key, ee.Image(f"projects/fake/assets/{key}"))
    result = k_elbow.KElbowStage().run(ctx, config)
    table = result.outputs["k_elbow"]
    task = ee.batch.Export.table.toAsset(
        collection=table, description="k_elbow", assetId="projects/fake/assets/k_elbow"
    )
    for sent in (table, task.config["expression"]):
        rows = _arguments(_expanded(ee.serializer.encode(sent, for_cloud_api=True)), "Feature")
        assert [r["metadata"]["constantValue"]["k"] for r in rows] == result.metadata["ks"]
        assert [r.get("geometry") for r in rows] == [POINT] * len(rows)
        first = rows[0]["metadata"]["constantValue"]
        assert first["in_fit_space"] == 1 and first["elbow_k"] == result.metadata["elbow_k"]
