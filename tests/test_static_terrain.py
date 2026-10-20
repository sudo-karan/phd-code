"""Slope and aspect in fractional degrees, on the DEM as float (review A5, first half), offline.

Until round 13 features_static took elevation, slope and aspect from ee.Terrain.products on
NASADEM's `elevation`. In the committed _r9 and tile layers every one-pixel stand has a
whole-number slope, aspect and elevation, while the float bands of the same asset keep their
decimals, so the three smallest gradients the review found (0.93, 0.99 and 1.36 degrees) all
read 1. The review traced this to the integer DEM. Read on Earth Engine in round 13 (read-only
calls 1 and 2 of docs/handoff/2026-10-20-round13.md), the cause is ee.Terrain.products itself:
it gives slope and aspect as integer bands on the integer DEM and on the DEM cast to float
alike, while ee.Terrain.slope and ee.Terrain.aspect give floats on both (slope
14.976821606934545 at one Angul pixel where the products give 15). So the stage casts the DEM to
float, as the brief asks, and takes slope and aspect from ee.Terrain.slope and
ee.Terrain.aspect; elevation is the DEM's band, its values unchanged by the cast. Earth Engine is
replaced by the recorder of tests/_ee_recorder.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import fmu.stages.features_static as static_module
from _ee_recorder import Rec, calls
from fmu.config import load_config
from fmu.stages.base import PipelineContext

REPO = Path(__file__).resolve().parent.parent
HANDCRAFTED = REPO / "configs" / "odisha_v120_3ha_squares_angul_keptland_s1desc_r9.yaml"
BANDS = ["elevation", "slope", "aspect", "distance_to_water", "annual_rainfall"]
DEM_AS_FLOAT = [
    ("ee.Image", ("NASA/NASADEM_HGT/001",), {}),
    ("select", ("elevation",), {}),
    ("toFloat", (), {}),
]


def _run(monkeypatch) -> list:
    log: list = []
    monkeypatch.setattr(static_module, "ee", Rec("ee", log))
    monkeypatch.setattr(static_module, "safe_get_info", lambda obj, context="": list(BANDS))
    ctx = PipelineContext()
    ctx.set("roi", Rec("roi", log))
    static_module.FeaturesStaticStage().run(ctx, load_config(HANDCRAFTED))
    return log


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


def _renamed(log: list, image: Rec) -> list[tuple]:
    return [c.args for c in log if c.owner is image and c.attr == "rename"]


def test_the_terrain_products_are_not_used(monkeypatch):
    """ee.Terrain.products gives slope and aspect in whole degrees, on a float DEM too
    (read-only call 2): the cast alone would not fix A5."""
    assert calls(_run(monkeypatch), "ee.Terrain.products") == []


@pytest.mark.parametrize("band", ["slope", "aspect"])
def test_slope_and_aspect_are_computed_on_the_dem_as_float(monkeypatch, band):
    log = _run(monkeypatch)
    (call,) = calls(log, f"ee.Terrain.{band}")
    (dem,) = call.args
    assert call.kwargs == {}
    assert _chain(log, dem) == DEM_AS_FLOAT
    assert _renamed(log, call.out) == [(band,)]


def test_elevation_is_the_dem_as_float_with_its_values(monkeypatch):
    """The cast changes the band's type, not its values: NASADEM's elevation is whole metres."""
    log = _run(monkeypatch)
    (cast,) = calls(log, ".toFloat")
    assert _chain(log, cast.out) == DEM_AS_FLOAT
    assert _renamed(log, cast.out) == [("elevation",)]
    (slope,) = calls(log, "ee.Terrain.slope")
    (aspect,) = calls(log, "ee.Terrain.aspect")
    assert slope.args[0] is aspect.args[0] is cast.out
