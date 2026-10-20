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


def _expanded(encoded: dict[str, Any], interned: dict[Any, Any] | None = None) -> dict[str, Any]:
    """An encoded expression as one tree: each `valueReference` replaced by its value, and
    the body of each function definition (a key of the same table) by the body itself. A
    function is mapped over a list since review B14 (the unit means).

    A value referred to more than once is expanded once and shared, and equal subtrees of the
    trees expanded with one `interned` table are one object, so that the tree is as large as the
    request and comparing two trees stops where they share a subtree. Since B14 the unit means
    refer to the grouped sums twice per band, and copies made the test hold about 10 GB."""
    values = encoded["values"]
    table: dict[Any, Any] = {} if interned is None else interned
    done: dict[str, Any] = {}

    def one(node: Any) -> Any:
        parts = node.items() if isinstance(node, dict) else enumerate(node)
        key = (type(node).__name__, tuple(
            (k, id(v) if isinstance(v, (dict, list)) else (type(v).__name__, v)) for k, v in parts))
        return table.setdefault(key, node)

    def reference(name: str) -> Any:
        if name not in done:
            done[name] = expand(values[name])
        return done[name]

    def expand(node: Any) -> Any:
        if isinstance(node, dict):
            if set(node) == {"valueReference"}:
                return reference(node["valueReference"])
            if set(node) == {"functionDefinitionValue"}:
                definition = node["functionDefinitionValue"]
                body = reference(definition["body"])
                return one({"functionDefinitionValue": one(
                    {key: body if key == "body" else expand(value) for key, value in definition.items()})})
            return one({key: expand(value) for key, value in node.items()})
        if isinstance(node, list):
            return one([expand(value) for value in node])
        return node

    return reference(encoded["result"])


def test_a_value_referred_to_more_than_once_is_expanded_once():
    """A check of the B14 fix (round 13): the unit means refer to the grouped sums twice per band,
    and a helper that copied a value at every reference made this file's test hold about 10 GB
    (a review of the round's own changes measured it)."""
    shared = {"functionInvocationValue": {"functionName": "Image.load",
                                          "arguments": {"id": {"constantValue": "a"}}}}
    encoded = {"result": "0", "values": {
        "0": {"arrayValue": {"values": [{"valueReference": "1"}, {"valueReference": "1"}]}},
        "1": shared,
    }}
    first, second = _expanded(encoded)["arrayValue"]["values"]
    assert first == shared and first is second
    interned: dict[Any, Any] = {}
    one, other = (_expanded(encoded, interned)["arrayValue"]["values"][0] for _ in range(2))
    assert one is other  # equal subtrees are one object across the trees of one table
    assert len(_calls(_expanded(encoded), "Image.load")) == 2  # each reference still counts


def _calls(node: Any, name: str, where: Any = None) -> list[dict[str, Any]]:
    """The arguments of every call of `name` in an expanded tree (those `where` accepts, if
    given), outermost first, a call under a shared subtree once for each place it is referred
    to. Each subtree is walked once, and keeps only the calls asked for."""
    walked: dict[int, list[dict[str, Any]]] = {}

    def walk(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, (dict, list)):
            return []
        if id(value) not in walked:
            found: list[dict[str, Any]] = []
            if isinstance(value, dict):
                inv = value.get("functionInvocationValue")
                if isinstance(inv, dict) and inv["functionName"] == name:
                    arguments = inv.get("arguments", {})
                    if where is None or where(arguments):
                        found.append(arguments)
                items: Any = value.values()
            else:
                items = value
            for item in items:
                found.extend(walk(item))
            walked[id(value)] = found
        return walked[id(value)]

    return list(walk(node))


def _outermost_call(node: Any) -> tuple[str, dict[str, Any]]:
    """(function name, arguments) of the first call in an expanded tree, outermost first."""
    stack = [node]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            inv = value.get("functionInvocationValue")
            if isinstance(inv, dict):
                return inv["functionName"], inv.get("arguments", {})
            stack.extend(reversed(list(value.values())))
        elif isinstance(value, list):
            stack.extend(reversed(value))
    raise AssertionError("no call in the tree")


def _remaps(node: Any) -> list[tuple[Any, Any, Any]]:
    """(from, to, defaultValue) of every Image.remap in a tree that masks stands: one with a
    default value. The unit means remap the labels too (review B14), with no default."""
    return [
        (a["from"]["constantValue"], a["to"]["constantValue"], a["defaultValue"]["constantValue"])
        for a in _calls(node, "Image.remap", lambda a: "defaultValue" in a)
    ]


def _call(node: Any, name: str) -> dict[str, Any]:
    """The arguments of the one call of `name` in a tree."""
    (args,) = _calls(node, name)
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
    interned: dict[Any, Any] = {}  # the trees share their equal subtrees, so they compare quickly

    # The rows of every unit, as with the setting off: no mask on the stand labels.
    (all_rows,) = [_expanded(e, interned) for e in requested[ALL_ROWS]]
    assert _remaps(all_rows) == []
    training_image = _sampled_image(all_rows)

    # The fit's rows: the training image masked to the other stands.
    (fit_rows,) = [_expanded(e, interned) for e in requested[FIT_ROW_COUNT]]
    assert _outermost_call(fit_rows)[0] == "Collection.size"
    assert _remaps(fit_rows) == [(ids, [0] * len(ids), 1)]
    masked = _sampled_image(fit_rows)["functionInvocationValue"]
    assert masked["functionName"] == "Image.updateMask"
    assert masked["arguments"]["image"] == training_image

    # The stands left out: their labels, from the training image masked to them alone.
    (their_rows,) = [_expanded(e, interned) for e in requested[LEFT_OUT_ROWS]]
    name, args = _outermost_call(their_rows)
    assert name == "AggregateFeatureCollection.array"
    assert args["property"]["constantValue"] == "fmu_label"
    assert _remaps(their_rows) == [(ids, [1] * len(ids), 0)]
    alone = _sampled_image(their_rows)["functionInvocationValue"]
    assert alone["arguments"]["image"] == training_image

    # No statistic of the preprocessing is taken over a masked sample. (The scaling read
    # Earth Engine's "p25/p50/p75 of" a band until review B16; it reads its "values of".)
    statistics = [
        _expanded(e, interned)
        for context, encoded in requested.items()
        if context.startswith(("skew of ", "min of ", "values of "))
        for e in encoded
    ]
    assert len(statistics) > 40
    assert all(_remaps(s) == [] for s in statistics)

    # The output: the clusterer was trained on the fit's rows and types the whole training
    # image, the stands left out of the fit included.
    labels = _expanded(ee.serializer.encode(result.outputs["cluster_labels"], for_cloud_api=True),
                       interned)
    cluster = _call(labels, "Image.cluster")
    assert cluster["image"] == training_image
    train = _call(cluster["clusterer"], "Clusterer.train")
    assert _remaps(train["features"]) == [(ids, [0] * len(ids), 1)]
    assert _sampled_image(train["features"]) == _sampled_image(fit_rows)
