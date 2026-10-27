"""Every reduction of the merge counts on the label image's own projection (round 14).

The live check of round 14 stopped in the merge in both runs (27 Oct 2026): the label histogram
counted each superpixel's pixels on the label asset's own grid, while the grouped reduction of
the criteria bands was given crs "EPSG:32645", a CRS name, and scale 10, from which Earth Engine
builds a grid of its own. At the boxes' edge three superpixels of 1,202 took one or two pixels
more on that grid than in the histogram, so a valid count was above its superpixel's pixel count
and the check of review B17 stopped the merge ("superpixel -1586256414 has 29 valid
canopy_height pixels but 28 pixels in the label histogram"). Counted on the label asset's own
grid, its crs and transform, the two agree (read-only calls 9 and 10 of the round 14 record).

So every reduction the merge asks Earth Engine for (the component-size check's histogram, the
label histogram, the two boundary pair histograms, the kept-land sums and the grouped reduction
of each criterion band) is given the label image's projection as `crs`, and no `scale` and no
`crsTransform`: Earth Engine then counts on that projection exactly, transform included, and all
of them count the same pixels. Jaskaran's answer to question 11 of round 14 (27 Oct 2026): "Fix
the merge's grid, test first".

Earth Engine is the recorder of tests/_ee_recorder.py, in every module the stage calls on it, so
each reduction is checked as the code asks for it; the last test builds the same reductions with
the real client, offline, so the arguments are checked as they would be sent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import fmu.stages.merge as merge_module
import fmu.utils.adjacency as adjacency_module
import fmu.utils.components as components_module
import fmu.utils.kept_land as kept_land_module
from _ee_recorder import Call, Rec, calls, made_by
from fmu.config import load_config
from fmu.stages.base import PipelineContext
from fmu.stages.merge import MergeStage

REPO = Path(__file__).resolve().parent.parent
# The config whose live check stopped in the merge: kept land only, so the stage measures kept
# land too, and three criteria.
CHECK_YAML = REPO / "configs" / "odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_a.yaml"
CRITERIA = ("canopy_height", "canopy_height_std", "ndvi_amplitude_annual")


def _answer(context: str) -> Any:
    """What Earth Engine would answer each request of the merge, by its context: two
    superpixels side by side, each with every criterion band defined on all its pixels."""
    if context in ("merge input band names", "merge adjacency band name", "merge criteria label band"):
        return ["snic_clusters"]
    if context == "merge input component size histogram":
        return {"snic_clusters": {"11": 40.0, "22": 60.0}}
    if context == "merge adjacency label histogram":
        return {"snic_clusters": {"11": 40.0, "22": 60.0, "null": 7.0}}
    if context == "merge adjacency label projection scale":
        return 10.0
    if context == "merge adjacency right-neighbour pairs":
        return {"pair": {"1": 5.0}}
    if context == "merge adjacency down-neighbour pairs":
        return {"pair": {}}
    if context == "merge input: kept land and superpixels":
        return {"kept": 100, "kept_unlabelled": 0, "labelled_not_kept": 0, "small_patches": 0}
    if context == "merge criteria bands":
        return [*CRITERIA, "longitude", "latitude"]
    if context.startswith("merge criteria: "):
        band = context.removeprefix("merge criteria: ")
        value = {"longitude": 84.6, "latitude": 20.8}.get(band, 1.0)
        return {"groups": [{"label": 11, "value": value * 40, "has_data": 40.0},
                           {"label": 22, "value": value * 60, "has_data": 60.0}]}
    raise AssertionError(f"unexpected request: {context!r}")


def _run_the_stage(monkeypatch) -> tuple[list[Call], Rec, dict[int, str]]:
    """MergeStage.run on the live check's config, Earth Engine recorded everywhere it is
    called. Returns the log, the label image the stage was given and the context each request
    was made with, by the id of the object requested."""
    monkeypatch.chdir(REPO)
    config = load_config(CHECK_YAML)
    assert config.segmentation.mask_before_snic
    assert tuple(c.band for c in config.merge.criteria) == CRITERIA
    log: list[Call] = []
    asked: dict[int, str] = {}

    def get_info(obj: Any, context: str = "") -> Any:
        asked[id(obj)] = context
        return _answer(context)

    ee = Rec("ee", log)
    for module in (merge_module, adjacency_module, components_module, kept_land_module):
        monkeypatch.setattr(module, "ee", ee)
    for module in (adjacency_module, components_module, kept_land_module):
        monkeypatch.setattr(module, "safe_get_info", get_info)
    labels = Rec("snic_clusters", log)
    ctx = PipelineContext()
    ctx.set("roi", Rec("roi", log))
    ctx.set("snic_clusters", labels)
    for source in {c.source for c in config.merge.criteria} | {"habitat_mask"}:
        ctx.set(source, Rec(source, log))
    result = MergeStage().run(ctx, config)
    assert result.outputs["merge_diagnostics"]["n_superpixels"] == 2
    return log, labels, asked


def _taken_from(log: list[Call], obj: Any, image: Rec) -> bool:
    """Whether `obj` is `image`, or a band of it selected or renamed."""
    while obj is not image:
        found = [c for c in log if c.out is obj]
        if len(found) != 1 or found[0].attr not in ("select", "rename"):
            return False
        obj = found[0].owner
    return True


def _is_the_label_projection(log: list[Call], crs: Any, labels: Rec) -> bool:
    if not isinstance(crs, Rec):
        return False  # none given, or a CRS name such as "EPSG:32645"
    made = made_by(log, crs)
    return made.attr == "projection" and not made.args and _taken_from(log, made.owner, labels)


def test_every_reduction_of_the_merge_is_on_the_label_images_own_projection(monkeypatch):
    """The component-size check, the label histogram, the right and down pair histograms, the
    kept-land sums and a grouped reduction per band of the criteria image (the three criteria
    and pixelLonLat's two): each is given the label image's projection as crs, and no scale and
    no crsTransform. On the code before round 14's fix the label histogram, the pair histograms
    and the component-size check were given a scale and no crs, and the grouped reductions the
    CRS name with a scale."""
    log, labels, asked = _run_the_stage(monkeypatch)
    reductions = calls(log, ".reduceRegion")
    assert len(reductions) == 1 + 3 + 1 + len(CRITERIA) + 2
    # Each reduction is fetched once, under the context that names it.
    assert len({asked[id(r.out)] for r in reductions}) == len(reductions)
    wrong = {
        asked[id(r.out)]: sorted(r.kwargs)
        for r in reductions
        if "scale" in r.kwargs
        or "crsTransform" in r.kwargs
        or not _is_the_label_projection(log, r.kwargs.get("crs"), labels)
    }
    assert not wrong, f"reductions not on the label image's own projection: {wrong}"


def _resolve(node: Any, values: dict[str, Any]) -> Any:
    """A node of an encoded expression, its value references followed."""
    while isinstance(node, dict) and "valueReference" in node:
        node = values[node["valueReference"]]
    return node


def _image_of(node: Any, values: dict[str, Any]) -> str | None:
    """The asset an encoded image is loaded from, through select and rename."""
    node = _resolve(node, values)
    while isinstance(node, dict) and "functionInvocationValue" in node:
        inv = node["functionInvocationValue"]
        if inv["functionName"] == "Image.load":
            return _resolve(inv["arguments"]["id"], values)["constantValue"]
        if inv["functionName"] not in ("Image.select", "Image.rename"):
            return None
        node = _resolve(inv["arguments"]["input"], values)
    return None


def test_the_real_client_builds_every_reduction_on_the_label_projection(monkeypatch):
    """Offline, as tests/test_mask_before_snic_ee_graph.py: earthengine-api's own test
    initialisation loads the algorithm signatures it ships and sends nothing. Each reduction
    of the merge, built by the real client and encoded as it would be sent, hands
    Image.reduceRegion a crs that is Image.projection of the label image (or of a band of it),
    and no scale and no crsTransform."""
    apitestcase = pytest.importorskip("ee.apitestcase")

    class _Offline(apitestcase.ApiTestCase):
        __test__ = False

        def runTest(self) -> None:  # noqa: N802 - unittest's name
            pass

    case = _Offline()
    case.setUp()
    try:
        import ee

        sent: dict[str, dict[str, Any]] = {}

        def get_info(obj: Any, context: str = "") -> Any:
            encoded = ee.serializer.encode(obj, for_cloud_api=True)
            values = encoded["values"]
            found = [
                v["functionInvocationValue"]
                for v in values.values()
                if v.get("functionInvocationValue", {}).get("functionName") == "Image.reduceRegion"
            ]
            if found:
                (reduction,) = found
                sent[context] = {"arguments": reduction["arguments"], "values": values}
            if context == "merge criteria bands":
                return ["canopy_height"]
            return _answer(context)

        for module in (adjacency_module, components_module, kept_land_module):
            monkeypatch.setattr(module, "safe_get_info", get_info)
        roi = ee.Geometry.Rectangle([84.80, 20.80, 84.85, 20.85])
        labels = ee.Image("projects/fake/assets/snic_clusters")
        components_module.assert_components_fit(
            labels, roi, 10, 480, context="merge input", crs=labels.projection()
        )
        graph = adjacency_module.extract_superpixel_graph(
            labels, roi, 10, context="merge adjacency"
        )
        adjacency_module.extract_superpixel_attributes(
            ee.Image("projects/fake/assets/criteria"), labels, graph, roi, 10,
            context="merge criteria",
        )
        kept_land_module.kept_land_coverage(
            labels, ee.Image("projects/fake/assets/habitat_mask"), roi, 10,
            min_patch_pixels=100, connectivity=8, context="merge input",
        )
    finally:
        case.tearDown()

    assert sorted(sent) == [
        "merge adjacency down-neighbour pairs",
        "merge adjacency label histogram",
        "merge adjacency right-neighbour pairs",
        "merge criteria: canopy_height",
        "merge input component size histogram",
        "merge input: kept land and superpixels",
    ]
    for context, request in sent.items():
        args, values = request["arguments"], request["values"]
        assert "scale" not in args and "crsTransform" not in args, context
        crs = _resolve(args["crs"], values)["functionInvocationValue"]
        assert crs["functionName"] == "Image.projection", context
        assert _image_of(crs["arguments"]["image"], values) == (
            "projects/fake/assets/snic_clusters"
        ), context
