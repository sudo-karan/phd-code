"""A flat cell has no aspect direction: its aspect sin and cos are both 0 (review A5).

ee.Terrain.products gave a cell with no gradient an aspect of 0 (review A5), and the sin/cos
decomposition turned that into (0, 1), the pair of a slope facing due north. The clustering stage and the profiling
stage each decompose aspect per pixel, before the unit means; both now give a cell whose slope
is 0 the pair (0, 0), so that a stand's mean aspect vector holds only the directions of its
sloping cells. Computed here on numpy stand-ins for the images (tests/_ee_arrays.py).
"""

from __future__ import annotations

import math
from types import ModuleType

import pytest

import fmu.stages.clustering as clustering
import fmu.stages.profiling as profiling
from _ee_arrays import Image, install

MODULES = [clustering, profiling]

# One row of four cells: flat, a slope facing due north, a slope facing due east, and a
# flat cell whose phase is a quarter turn.
FLAT, NORTH, EAST, FLAT_PHASE = (0, 0), (0, 1), (0, 2), (0, 3)
STACK = Image(
    {
        "elevation": [[210.0, 230.0, 250.0, 210.0]],
        "slope": [[0.0, 12.0, 5.0, 0.0]],
        "aspect": [[0.0, 0.0, 90.0, 0.0]],
        "ndvi_phase_annual": [[0.0, 0.0, 0.0, math.pi / 2]],
    }
)


def _decomposed(module: ModuleType, monkeypatch, stack: Image = STACK) -> Image:
    install(monkeypatch, module)
    image, decomposed = module._decompose_cyclic_bands(stack)
    assert decomposed == ["aspect", "ndvi_phase_annual"]
    return image


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_a_flat_cell_and_a_north_facing_slope_get_different_aspect_pairs(module, monkeypatch):
    image = _decomposed(module, monkeypatch)
    assert image.pair("aspect", FLAT) != image.pair("aspect", NORTH)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_a_flat_cell_has_no_aspect_direction(module, monkeypatch):
    image = _decomposed(module, monkeypatch)
    assert image.pair("aspect", FLAT) == (0.0, 0.0)
    assert image.pair("aspect", FLAT_PHASE) == (0.0, 0.0)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_a_sloping_cell_keeps_its_direction(module, monkeypatch):
    image = _decomposed(module, monkeypatch)
    assert image.pair("aspect", NORTH) == (0.0, 1.0)
    sin, cos = image.pair("aspect", EAST)
    assert sin == pytest.approx(1.0) and cos == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_the_phase_of_a_flat_cell_is_untouched(module, monkeypatch):
    """Only aspect needs a gradient to have a direction; the phase pair is the phase's."""
    image = _decomposed(module, monkeypatch)
    sin, cos = image.pair("ndvi_phase_annual", FLAT_PHASE)
    assert sin == pytest.approx(1.0) and cos == pytest.approx(0.0, abs=1e-12)
    assert image.pair("ndvi_phase_annual", FLAT) == (0.0, 1.0)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_the_other_bands_pass_through(module, monkeypatch):
    image = _decomposed(module, monkeypatch)
    assert list(image.bands) == [
        "elevation", "slope", "aspect_sin", "aspect_cos",
        "ndvi_phase_annual_sin", "ndvi_phase_annual_cos",
    ]
    assert [image.value("slope", at) for at in (FLAT, NORTH, EAST)] == [0.0, 12.0, 5.0]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_aspect_without_slope_is_refused(module, monkeypatch):
    """Which cells are flat is read from the slope, which features_static emits beside
    aspect; a stack with aspect alone cannot say, so it is not decomposed as if none were."""
    with pytest.raises(ValueError, match="slope"):
        _decomposed(module, monkeypatch, STACK.select(["elevation", "aspect", "ndvi_phase_annual"]))
