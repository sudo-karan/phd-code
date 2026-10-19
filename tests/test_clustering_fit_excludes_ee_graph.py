"""With clustering.fit_excludes_stands_below_min_area on, clustering builds valid Earth Engine requests.

Offline, as tests/test_mask_before_snic_ee_graph.py: earthengine-api's own test initialisation
(`ee.apitestcase`) loads the algorithm signatures it ships (`ee/tests/algorithms.json`) and
sends nothing anywhere. The whole stage runs on the real client, with the answers of
tests/_clustering_stand_ins.py, and every request is encoded as it would be sent, so a
misspelt argument or a wrong method fails here rather than on the first paid run. The
encoded requests then show what the masks are made of, which rows the fit is trained on and
which image is typed. What Earth Engine computes from them is not checked here: the setting
has not run on Earth Engine yet.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from _clustering_stand_ins import FIT_ROW_COUNT, LEFT_OUT_ROWS, answers, inputs

apitestcase = pytest.importorskip("ee.apitestcase")

REPO = Path(__file__).resolve().parent.parent
BOX_YAML = REPO / "configs" / "odisha_v120_3ha_squares_koraput.yaml"
BELOW_MIN = {4: 0.12, 9: 0.5, 12: 0.03, 15: 0.8}
WITH_A_ROW = [4, 9, 12]
ALL_ROWS = "k-means training row count"


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


def _expanded(encoded: dict[str, Any]) -> dict[str, Any]:
    """An encoded expression as one tree: each `valueReference` replaced by its value, and
    the body of each function definition (a key of the same table) by the body itself. A
    function is mapped over a list since review B14 (the unit means)."""
    values = encoded["values"]

    def expand(node: Any) -> Any:
        if isinstance(node, dict):
            if set(node) == {"valueReference"}:
                return expand(values[node["valueReference"]])
            if set(node) == {"functionDefinitionValue"}:
                definition = node["functionDefinitionValue"]
                body = expand(values[definition["body"]])
                return {"functionDefinitionValue": {**definition, "body": body}}
            return {key: expand(value) for key, value in node.items()}
        if isinstance(node, list):
            return [expand(value) for value in node]
        return node

    return expand(values[encoded["result"]])


def _invocations(node: Any) -> list[tuple[str, dict[str, Any]]]:
    """(function name, arguments) of every call in an expanded tree, outermost first."""
    found: list[tuple[str, dict[str, Any]]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            inv = value.get("functionInvocationValue")
            if isinstance(inv, dict):
                found.append((inv["functionName"], inv.get("arguments", {})))
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(node)
    return found


def _remaps(node: Any) -> list[tuple[Any, Any, Any]]:
    """(from, to, defaultValue) of every Image.remap in a tree that masks stands: one with a
    default value. The unit means remap the labels too (review B14), with no default."""
    return [
        (a["from"]["constantValue"], a["to"]["constantValue"], a["defaultValue"]["constantValue"])
        for name, a in _invocations(node)
        if name == "Image.remap" and "defaultValue" in a
    ]


def _call(node: Any, name: str) -> dict[str, Any]:
    """The arguments of the one call of `name` in a tree."""
    (args,) = [a for n, a in _invocations(node) if n == name]
    return args


def _sampled_image(request: Any) -> Any:
    """The image a sample-based request sampled, before the labels were added to it."""
    sample = _call(request, "Image.stratifiedSample")
    stacked = sample["image"]["functionInvocationValue"]
    assert stacked["functionName"] == "Image.addBands"
    return stacked["arguments"]["dstImg"]


def _run(ee: Any, monkeypatch: Any) -> tuple[Any, dict[str, list[Any]]]:
    import fmu.stages.clustering as clustering_module
    from fmu.config import Config
    from fmu.stages.base import PipelineContext

    raw = yaml.safe_load(BOX_YAML.read_text())
    raw["clustering"]["fit_excludes_stands_below_min_area"] = True
    config = Config.model_validate(raw)
    answer = answers(config, [], fit_rows=17, left_out_rows=WITH_A_ROW)
    requested: dict[str, list[Any]] = {}

    def get_info(obj: Any, context: str = "") -> Any:
        # Every request is encoded as it would be sent: an invalid one fails here.
        encoded = ee.serializer.encode(obj, for_cloud_api=True)
        assert json.dumps(encoded)  # plain data, as it would be sent
        requested.setdefault(context, []).append(encoded)
        return answer(obj, context)

    monkeypatch.setattr(clustering_module, "safe_get_info", get_info)

    ctx = PipelineContext()
    ctx.set("roi", ee.Geometry.Rectangle([82.80, 18.50, 82.85, 18.55]))
    for key in sorted(inputs(config) - {"roi"}):
        ctx.set(key, ee.Image(f"projects/fake/assets/{key}"))
    provenance = {sid: {"below_min": int(sid in BELOW_MIN), "below_why": ""} for sid in range(25)}
    ctx.set("stand_provenance", provenance)
    ctx.set("stand_attributes", {sid: {"area_ha": BELOW_MIN.get(sid, 2.5)} for sid in range(25)})
    result = clustering_module.ClusteringStage().run(ctx, config)
    return result, requested


def test_the_requests_with_the_setting_on_are_valid_and_mask_the_right_stands(offline_ee, monkeypatch):
    ee = offline_ee
    result, requested = _run(ee, monkeypatch)
    ids = sorted(BELOW_MIN)

    # The rows of every unit, as with the setting off: no mask on the stand labels.
    (all_rows,) = [_expanded(e) for e in requested[ALL_ROWS]]
    assert _remaps(all_rows) == []
    training_image = _sampled_image(all_rows)

    # The fit's rows: the training image masked to the other stands.
    (fit_rows,) = [_expanded(e) for e in requested[FIT_ROW_COUNT]]
    assert _invocations(fit_rows)[0][0] == "Collection.size"
    assert _remaps(fit_rows) == [(ids, [0] * len(ids), 1)]
    masked = _sampled_image(fit_rows)["functionInvocationValue"]
    assert masked["functionName"] == "Image.updateMask"
    assert masked["arguments"]["image"] == training_image

    # The stands left out: their labels, from the training image masked to them alone.
    (their_rows,) = [_expanded(e) for e in requested[LEFT_OUT_ROWS]]
    name, args = _invocations(their_rows)[0]
    assert name == "AggregateFeatureCollection.array"
    assert args["property"]["constantValue"] == "fmu_label"
    assert _remaps(their_rows) == [(ids, [1] * len(ids), 0)]
    alone = _sampled_image(their_rows)["functionInvocationValue"]
    assert alone["arguments"]["image"] == training_image

    # No statistic of the preprocessing is taken over a masked sample.
    statistics = [
        _expanded(e)
        for context, encoded in requested.items()
        if context.startswith(("skew of ", "min of ", "p25/p50/p75 of "))
        for e in encoded
    ]
    assert len(statistics) > 40
    assert all(_remaps(s) == [] for s in statistics)

    # The output: the clusterer was trained on the fit's rows and types the whole training
    # image, the stands left out of the fit included.
    labels = _expanded(ee.serializer.encode(result.outputs["cluster_labels"], for_cloud_api=True))
    cluster = _call(labels, "Image.cluster")
    assert cluster["image"] == training_image
    train = _call(cluster["clusterer"], "Clusterer.train")
    assert _remaps(train["features"]) == [(ids, [0] * len(ids), 1)]
    assert _sampled_image(train["features"]) == _sampled_image(fit_rows)
