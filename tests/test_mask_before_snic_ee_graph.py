"""The kept-land path of segmentation and merge builds a valid Earth Engine request.

Offline: earthengine-api's own test initialisation (`ee.apitestcase`) loads the algorithm
signatures it ships (`ee/tests/algorithms.json`) and sends nothing anywhere. Building a
call checks the function exists and takes the arguments given, by name, so a misspelt
argument or a wrong method fails here rather than on the first paid run. What Earth Engine
then computes is not checked here: scripts/check_snic_on_kept_land.py does that, on Earth
Engine.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

apitestcase = pytest.importorskip("ee.apitestcase")

REPO = Path(__file__).resolve().parent.parent
BOX_YAML = REPO / "configs" / "odisha_v120_3ha_squares_koraput.yaml"


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


def _invocations(encoded: dict[str, Any]) -> list[tuple[str, set[str]]]:
    """(function name, argument names) of every call in an encoded expression."""
    found: list[tuple[str, set[str]]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            inv = node.get("functionInvocationValue")
            if isinstance(inv, dict):
                found.append((inv["functionName"], set(inv.get("arguments", {}))))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(encoded)
    return found


def _masked_config():
    from fmu.config import Config

    raw = yaml.safe_load(BOX_YAML.read_text())
    raw["segmentation"]["mask_before_snic"] = True
    raw["segmentation"]["drop_kept_patches_below_min_area"] = True
    return Config.model_validate(raw)


def test_masked_segmentation_and_its_coverage_check_are_valid_requests(offline_ee, monkeypatch):
    ee = offline_ee
    import fmu.stages.merge as merge_module
    import fmu.stages.segmentation as segmentation_module
    import fmu.utils.kept_land as kept_land_module
    from fmu.stages.base import PipelineContext

    config = _masked_config()
    bands = [b.band for b in config.segmentation.input_bands]
    requested: list[tuple[str, dict[str, Any]]] = []

    def get_info(obj: Any, context: str = "") -> Any:
        # Every request is encoded as it would be sent: an invalid one fails here.
        requested.append((context, ee.serializer.encode(obj, for_cloud_api=True)))
        if context in ("z-score band names", "snic_means bands"):
            return list(bands)
        if context == "kept land in the ROI":
            return {"kept": 1}
        if context == "RMS adjacent feature distance over kept land":
            return {"dx2_sum": 30.0, "dx2_count": 10, "dy2_sum": 10.0, "dy2_count": 10}
        if context == "SNIC output grid scale":
            return 10.0
        if context == "SNIC output grid CRS":
            return "EPSG:32644"
        if context.endswith("kept land and superpixels"):
            return {"kept": 100, "kept_unlabelled": 0, "labelled_not_kept": 0, "small_patches": 5}
        raise AssertionError(f"unexpected request: {context}")

    for module in (segmentation_module, kept_land_module):
        monkeypatch.setattr(module, "safe_get_info", get_info)
    grid = ee.Projection("EPSG:32644").atScale(10)
    monkeypatch.setattr(segmentation_module, "_analysis_grid", lambda roi, scale: grid)

    roi = ee.Geometry.Rectangle([82.80, 18.50, 82.85, 18.55])
    ctx = PipelineContext()
    ctx.set("roi", roi)
    for source in config.segmentation.input_sources():
        ctx.set(source, ee.Image(f"projects/fake/assets/{source}"))
    ctx.set("habitat_mask", ee.Image("projects/fake/assets/habitat_mask"))

    result = segmentation_module.SegmentationStage().run(ctx, config)
    calls = {
        key: _invocations(ee.serializer.encode(result.outputs[key], for_cloud_api=True))
        for key in ("snic_clusters", "snic_means")
    }
    for key, found in calls.items():
        names = {name for name, _ in found}
        (snic_args,) = {frozenset(a) for n, a in found if n == "Image.Segmentation.SNIC"}
        assert {"image", "size", "compactness", "connectivity", "neighborhoodSize", "seeds"} <= snic_args, key
        for needed in (
            "Image.Segmentation.seedGrid",
            "Image.connectedComponents",
            "Image.reduceConnectedComponents",
            "Image.connectedPixelCount",
            "Image.updateMask",
        ):
            assert needed in names, (key, needed)
        (cpc_args,) = {frozenset(a) for n, a in found if n == "Image.connectedPixelCount"}
        assert cpc_args == {"input", "maxSize", "eightConnected"}

    # The coverage the merge measures is a valid request too, on a label image.
    monkeypatch.setattr(merge_module, "kept_land_coverage", kept_land_module.kept_land_coverage)
    cover = kept_land_module.kept_land_coverage(
        result.outputs["snic_clusters"],
        ctx.get("habitat_mask"),
        roi,
        10,
        min_patch_pixels=config.kept_patch_min_pixels(),
        connectivity=config.segmentation.connectivity,
        context="merge input",
    )
    assert cover["small_patches_ha"] == 0.05
    contexts = [c for c, _ in requested]
    assert contexts[0] == "kept land in the ROI"
    (coverage_request,) = [e for c, e in requested if c.endswith("kept land and superpixels")]
    # Its own reduction names the label image's projection and no scale. (The other
    # reductions in the request are the z-score's, inside the label image's graph.)
    reduce_args = [a for n, a in _invocations(coverage_request) if n == "Image.reduceRegion"]
    (own,) = [a for a in reduce_args if "crs" in a]
    assert "scale" not in own
    assert json.dumps(coverage_request)  # plain data, as it would be sent
