"""Non-live tests for the reduceConnectedComponents neighbourhood in clustering.

`reduceConnectedComponents(maxSize=N)` treats N as an extent and pads every tile
by it, so passing the count-derived cap (1200 px at 10 ha / 10 m) makes memory
grow with bands x pad, and a wide band stack runs out of memory. The stage now
passes the measured widest unit extent plus a margin, never wider than the cap.

What is pinned here:
  - the arithmetic that decides that number: it must always exceed the widest
    extent below the cap (or a stand would be masked), never exceed the cap (or
    it would widen the old neighbourhood), and never truncate a float span
    downwards;
  - the EE wrapper: which grids it measures in, with which reduceRegion
    arguments, that it takes the larger measurement, that it refuses to fall
    back silently when a measurement is empty but labels exist, and that it
    warns when a disjoint label has pushed the neighbourhood to the cap;
  - the stage wiring: ClusteringStage.run hands _compute_superpixel_means the
    measured neighbourhood, not the cap and not the raw widest extent.

No Earth Engine call is made.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

import fmu.stages.clustering as clustering_mod
from fmu.config import Config
from fmu.stages.base import PipelineContext
from fmu.stages.clustering import (
    _RCC_EXTENT_MARGIN,
    _RCC_EXTENT_PAD_PX,
    ClusteringStage,
    _neighbourhood_from_groups,
)
from fmu.utils.gee import LABEL_BAND

BASELINE_YAML = Path(__file__).parent.parent / "configs" / "sanjay_van_baseline.yaml"


def _g(min_xy: list[float], max_xy: list[float]) -> dict[str, list[float]]:
    return {"min": min_xy, "max": max_xy}


def _expected(widest: int) -> int:
    return math.ceil(widest * _RCC_EXTENT_MARGIN) + _RCC_EXTENT_PAD_PX


# ---------- pure arithmetic ----------


def test_widest_extent_is_span_plus_one():
    assert _neighbourhood_from_groups([_g([10, 20], [137, 40])], cap=1200) == (128, 156)


def test_uses_the_larger_axis():
    widest, neighbourhood = _neighbourhood_from_groups([_g([0, 0], [5, 90])], cap=1200)
    assert widest == 91
    assert neighbourhood == _expected(91) == 112


def test_widest_across_groups():
    groups = [_g([0, 0], [9, 9]), _g([100, 100], [150, 300]), _g([5, 5], [60, 7])]
    assert _neighbourhood_from_groups(groups, cap=1200) == (201, _expected(201))


def test_never_wider_than_cap():
    assert _neighbourhood_from_groups([_g([0, 0], [1199, 0])], cap=1200) == (1200, 1200)


@pytest.mark.parametrize("groups", [[], None])
def test_empty_or_null_groups_fall_back_to_cap(groups):
    assert _neighbourhood_from_groups(groups, cap=1200) == (0, 1200)


@pytest.mark.parametrize("widest", [1, 50, 128, 999])
def test_neighbourhood_strictly_exceeds_extent_below_cap(widest):
    got_widest, neighbourhood = _neighbourhood_from_groups(
        [_g([0, 0], [widest - 1, 0])], cap=10_000
    )
    assert got_widest == widest
    assert neighbourhood > widest


@pytest.mark.parametrize("max_x", [136.9999999, 137.0000001])
def test_float_span_is_rounded_not_truncated(max_x):
    """Pixel coordinates arrive as floats. A 127-px span delivered as
    126.9999999 must still be a 128-px extent: int() would make it 127, which
    under-measures -- the one direction this must not err in."""
    widest, neighbourhood = _neighbourhood_from_groups(
        [_g([10.0, 0.0], [max_x, 0.0])], cap=1200
    )
    assert widest == 128
    assert neighbourhood == 156


# ---------- EE wrapper ----------


def _wrapper_mocks(monkeypatch, responses):
    """Patch ee and safe_get_info in the clustering module; return the ee mock,
    the two distinct projections, the two images, and the recorded contexts."""
    ee_mock = MagicMock()
    monkeypatch.setattr(clustering_mod, "ee", ee_mock)
    calls: list[str] = []

    def fake_get_info(obj, *, context=""):
        calls.append(context)
        return responses[len(calls) - 1]

    monkeypatch.setattr(clustering_mod, "safe_get_info", fake_get_info)

    proj_feature = MagicMock(name="feature_band0_proj")
    proj_label = MagicMock(name="label_proj")
    feature_image = MagicMock(name="feature_image")
    unit_labels = MagicMock(name="unit_labels")
    feature_image.select.return_value.projection.return_value.atScale.return_value = (
        proj_feature
    )
    unit_labels.select.return_value.projection.return_value.atScale.return_value = (
        proj_label
    )
    return ee_mock, proj_feature, proj_label, feature_image, unit_labels, calls


def _call_wrapper(unit_labels, feature_image, *, cap=1200, n_labels=184, largest=1000):
    return clustering_mod._component_neighbourhood_px(
        unit_labels,
        feature_image,
        MagicMock(name="roi"),
        10,
        cap=cap,
        n_labels=n_labels,
        largest_component_px=largest,
        context="test",
    )


def test_wrapper_measures_both_projections_and_takes_the_larger(monkeypatch):
    responses = [
        {"groups": [_g([0, 0], [127, 0])]},  # feature grid (EPSG:4326)
        {"groups": [_g([0, 0], [119, 0])]},  # label grid (UTM)
    ]
    ee_mock, proj_f, proj_l, feature_image, unit_labels, calls = _wrapper_mocks(
        monkeypatch, responses
    )

    result = _call_wrapper(unit_labels, feature_image)

    assert len(calls) == 2
    assert result == (128, 156)

    # Coordinates are generated in each projection in turn: feature grid first.
    assert [c.args[0] for c in ee_mock.Image.pixelCoordinates.call_args_list] == [
        proj_f,
        proj_l,
    ]
    feature_image.select.return_value.projection.return_value.atScale.assert_called_with(10)
    unit_labels.select.return_value.projection.return_value.atScale.assert_called_with(10)

    reduce_calls = (
        ee_mock.Image.pixelCoordinates.return_value.addBands.return_value.reduceRegion.call_args_list
    )
    assert len(reduce_calls) == 2
    for call, proj in zip(reduce_calls, (proj_f, proj_l), strict=True):
        kwargs = call.kwargs
        # Evaluated in the grid being measured, never downsampled.
        assert kwargs["crs"] is proj
        assert "bestEffort" not in kwargs
        assert "scale" not in kwargs
        assert kwargs["maxPixels"] == 1_000_000_000

    # Grouped by the label band that pixelCoordinates' x, y (bands 0, 1) precede.
    ee_mock.Reducer.minMax.return_value.repeat.assert_called_with(2)
    ee_mock.Reducer.minMax.return_value.repeat.return_value.group.assert_called_with(
        groupField=2, groupName=LABEL_BAND
    )


@pytest.mark.parametrize(
    "bad",
    [None, {}, {"groups": None}, {"groups": []}],
    ids=["none", "missing", "null", "empty"],
)
@pytest.mark.parametrize("which", [0, 1], ids=["feature-grid", "label-grid"])
def test_wrapper_raises_when_groups_missing_but_labels_exist(monkeypatch, bad, which):
    good = {"groups": [_g([0, 0], [99, 0])]}
    responses = [good, good]
    responses[which] = bad
    *_, feature_image, unit_labels, _calls = _wrapper_mocks(monkeypatch, responses)

    with pytest.raises(RuntimeError, match="returned no groups"):
        _call_wrapper(unit_labels, feature_image, n_labels=5)


def test_wrapper_with_no_labels_falls_back_to_cap_silently(monkeypatch):
    *_, feature_image, unit_labels, _calls = _wrapper_mocks(monkeypatch, [{}, None])
    assert _call_wrapper(unit_labels, feature_image, n_labels=0, largest=0) == (0, 1200)


def test_wrapper_warns_when_a_disjoint_label_forces_the_cap(monkeypatch, caplog):
    # widest 91 -> 112 before the cap; cap 100 binds. 91 > 2 * 40: no single
    # connected object of 40 px can be 91 px wide.
    groups = {"groups": [_g([0, 0], [90, 0])]}
    *_, feature_image, unit_labels, _calls = _wrapper_mocks(monkeypatch, [groups, groups])

    with caplog.at_level(logging.WARNING, logger=clustering_mod.log.name):
        result = _call_wrapper(unit_labels, feature_image, cap=100, largest=40)

    assert result == (91, 100)
    assert "reused across disjoint places" in caplog.text


@pytest.mark.parametrize(
    ("cap", "largest"),
    [(100, 50), (1200, 10)],
    ids=["cap-binds-but-extent-plausible", "extent-implausible-but-cap-not-reached"],
)
def test_wrapper_does_not_warn_otherwise(monkeypatch, caplog, cap, largest):
    groups = {"groups": [_g([0, 0], [90, 0])]}
    *_, feature_image, unit_labels, _calls = _wrapper_mocks(monkeypatch, [groups, groups])

    with caplog.at_level(logging.WARNING, logger=clustering_mod.log.name):
        _call_wrapper(unit_labels, feature_image, cap=cap, largest=largest)

    assert "disjoint" not in caplog.text


# ---------- stage wiring ----------


class _StopAfterMeansError(Exception):
    """Raised from the patched _compute_superpixel_means to end run() early."""


def test_run_passes_measured_neighbourhood_to_superpixel_means(monkeypatch):
    raw = yaml.safe_load(BASELINE_YAML.read_text())
    raw["clustering"] = {**raw.get("clustering", {}), "feature_source": "handcrafted"}
    config = Config.model_validate(raw)
    cap = config.max_component_pixels()

    ctx = PipelineContext()
    for key in (
        "roi",
        "habitat_mask",
        config.unit_label_key(),
        "optical_features",
        "radar_features",
        "structure_features",
        "static_features",
    ):
        ctx.set(key, MagicMock(name=key))

    decomposed = MagicMock(name="decomposed_stack")
    monkeypatch.setattr(clustering_mod, "_build_raw_feature_stack", lambda **_: MagicMock())
    monkeypatch.setattr(clustering_mod, "safe_get_info", lambda obj, *, context="": ["b0"])
    monkeypatch.setattr(clustering_mod, "_decompose_cyclic_bands", lambda img: (decomposed, []))
    monkeypatch.setattr(
        clustering_mod,
        "assert_components_fit",
        lambda *a, **k: {
            "n_components": 3,
            "largest_component_px": 50,
            "max_component_px_cap": cap,
        },
    )

    neighbourhood_calls: list[tuple[tuple, dict]] = []

    def fake_neighbourhood(*args, **kwargs):
        neighbourhood_calls.append((args, kwargs))
        return 7, 9  # (widest, neighbourhood): deliberately neither is the cap

    monkeypatch.setattr(clustering_mod, "_component_neighbourhood_px", fake_neighbourhood)

    seen: dict[str, object] = {}

    def fake_means(feature_image, unit_labels, max_size):
        seen.update(feature_image=feature_image, unit_labels=unit_labels, max_size=max_size)
        raise _StopAfterMeansError

    monkeypatch.setattr(clustering_mod, "_compute_superpixel_means", fake_means)

    with pytest.raises(_StopAfterMeansError):
        ClusteringStage().run(ctx, config)

    assert seen["max_size"] == 9
    assert seen["max_size"] not in (cap, 7)
    assert seen["feature_image"] is decomposed
    assert seen["unit_labels"] is ctx.get(config.unit_label_key())

    (args, kwargs), = neighbourhood_calls
    assert args[1] is decomposed  # measured in the grid of the stack being reduced
    assert kwargs["cap"] == cap
    assert kwargs["n_labels"] == 3
    assert kwargs["largest_component_px"] == 50
