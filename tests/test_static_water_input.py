"""The water distance_to_water is measured to reaches past the ROI (review A1), offline.

distance_to_water is fastDistanceTransform's distance from each pixel to the nearest JRC
water pixel (occurrence >= masking.jrc_water_occurrence_threshold), looked for within a
square neighbourhood of half-width features_static.max_water_distance_pixels. Before round
13 the transform read masking's water_mask, which is clipped to the ROI, so it never saw
water outside the ROI: every value was min(distance to water inside the ROI, the reach), and
all 219 stands of the Angul _r9 box layer read exactly 10,000 m. The stage now builds its own
water input, with masking's definition (one function, `jrc_water_mask`), over the ROI buffered
by the transform's full reach, the corner of the square, and clips only the result. Earth
Engine is replaced by the recorder of tests/_ee_recorder.py.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

import fmu.stages.features_static as static_module
import fmu.stages.masking as masking_module
from _ee_recorder import Rec, calls, made_by
from fmu.config import Config, load_config
from fmu.stages.base import PipelineContext

REPO = Path(__file__).resolve().parent.parent
HANDCRAFTED = REPO / "configs" / "odisha_v120_3ha_squares_angul_keptland_s1desc_r9.yaml"
BANDS = ["elevation", "slope", "aspect", "distance_to_water", "annual_rainfall"]


def _record(monkeypatch) -> list:
    log: list = []
    monkeypatch.setattr(static_module, "ee", Rec("ee", log))
    monkeypatch.setattr(static_module, "safe_get_info", lambda obj, context="": list(BANDS))
    return log


def _run_static(monkeypatch, config: Config):
    log = _record(monkeypatch)
    ctx = PipelineContext()
    roi = Rec("roi", log)
    ctx.set("roi", roi)
    # masking's output, as the pipeline's context holds it; the stage must not read it.
    water_mask = Rec("water_mask", log)
    ctx.set("water_mask", water_mask)
    result = static_module.FeaturesStaticStage().run(ctx, config)
    return result, log, roi, water_mask


def _config(path: Path = HANDCRAFTED, **static) -> Config:
    raw = yaml.safe_load(path.read_text())
    raw["features_static"] = {**raw.get("features_static", {}), **static}
    return Config.model_validate(raw)


def _chain(log: list, image: Rec) -> list[tuple]:
    """The calls that made `image`, first to last: (method, args, kwargs) of each, the first
    named in full ("ee.Image")."""
    made = {id(c.out): c for c in log}
    call = made[id(image)]
    out = []
    while id(call.owner) in made:
        out.append((call.attr, call.args, call.kwargs))
        call = made[id(call.owner)]
    out.append((call.name, call.args, call.kwargs))
    return out[::-1]


def test_the_transform_reads_jrc_water_over_the_roi_buffered_by_its_reach(monkeypatch):
    config = _config()
    _, log, roi, water_mask = _run_static(monkeypatch, config)
    (transform,) = calls(log, ".fastDistanceTransform")
    assert transform.name == "ee.Image().select().clip().gte().unmask().fastDistanceTransform"
    assert transform.owner is not water_mask
    assert transform.args == (1000, "pixels", "squared_euclidean")
    image, select, clip, gte, unmask = _chain(log, transform.owner)
    assert image == ("ee.Image", ("JRC/GSW1_4/GlobalSurfaceWater",), {})
    assert select == ("select", ("occurrence",), {})
    assert gte == ("gte", (50.0,), {})
    assert unmask == ("unmask", (0,), {})
    # Clipped to the ROI buffered by the reach of the neighbourhood's corners:
    # ceil(sqrt(2) x 1000) = 1415 pixels of 10 m.
    (region,) = clip[1]
    buffer = made_by(log, region)
    assert buffer.owner is roi and buffer.attr == "buffer"
    assert buffer.args == (14150,) and buffer.kwargs == {"maxError": 1}


def test_only_the_result_is_clipped_to_the_roi(monkeypatch):
    config = _config()
    _, log, roi, _ = _run_static(monkeypatch, config)
    (cat,) = calls(log, "ee.Image.cat")
    clip = [c for c in log if c.owner is cat.out]
    assert [(c.attr, c.args) for c in clip] == [("clip", (roi,))]
    # The distance band is in the stack, capped (this config caps it) and renamed.
    (rename,) = [c for c in log if c.attr == "rename" and c.args == ("distance_to_water",)]
    assert rename.out in cat.args[0]
    assert made_by(log, rename.owner).attr == "min"


def test_the_stage_reads_no_masking_output(monkeypatch):
    assert static_module.FeaturesStaticStage.required_inputs == {"roi"}
    log = _record(monkeypatch)
    ctx = PipelineContext()
    ctx.set("roi", Rec("roi", log))
    static_module.FeaturesStaticStage().run(ctx, _config())


@pytest.mark.parametrize(
    ("pixels", "scale", "reach"),
    [(1000, 10, 14150), (100, 10, 1420), (500, 30, 21240), (10000, 10, 141430)],
)
def test_the_reach_is_the_corner_of_the_square_neighbourhood(pixels, scale, reach):
    """ceil(sqrt(2) x pixels) whole pixels: no corner of the neighbourhood is left out."""
    assert static_module.water_reach_m(pixels, scale) == reach
    assert reach >= math.sqrt(2) * pixels * scale
    assert reach - scale < math.sqrt(2) * pixels * scale


def test_the_buffer_follows_the_neighbourhood_and_the_scale(monkeypatch):
    raw = yaml.safe_load(HANDCRAFTED.read_text())
    raw["features_static"]["max_water_distance_pixels"] = 500
    raw["export"]["analysis_scale_m"] = 30
    _, log, _, _ = _run_static(monkeypatch, Config.model_validate(raw))
    (buffer,) = calls(log, "roi.buffer")
    assert buffer.args == (21240,)
    (transform,) = calls(log, ".fastDistanceTransform")
    assert transform.args == (500, "pixels", "squared_euclidean")


def test_masking_water_mask_is_the_same_definition_over_the_roi(monkeypatch):
    """masking's water_mask (landcover_summary, the display) is unchanged: JRC occurrence at the
    threshold, unmasked to 0, over the ROI itself."""
    log: list = []
    monkeypatch.setattr(masking_module, "ee", Rec("ee", log))
    monkeypatch.setattr(
        masking_module, "_load_indiasat_collection", lambda asset, params, roi: Rec("lulc", log)
    )
    ctx = PipelineContext()
    roi = Rec("roi", log)
    ctx.set("roi", roi)
    config = load_config(HANDCRAFTED)
    result = masking_module.MaskingStage().run(ctx, config)
    assert _chain(log, result.outputs["water_mask"]) == [
        ("ee.Image", ("JRC/GSW1_4/GlobalSurfaceWater",), {}),
        ("select", ("occurrence",), {}),
        ("clip", (roi,), {}),
        ("gte", (50.0,), {}),
        ("unmask", (0,), {}),
        ("rename", ("water_mask",), {}),
    ]
