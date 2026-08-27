"""Non-live tests for the explained-variance metric and its config guards.

R^2 = 1 - SS_within / SS_total (Xiong et al. 2024 Eq. 4-6) replaces silhouette
as the cross-arm headline. Silhouette is computed in each arm's own feature
space (21-D vs 64-D) and is strongly dimensionality-dependent, so it was never
valid across arms; under two independent segmentations it is doubly invalid.

Three ways this metric can be quietly wrong, all pinned here:

  - computed at **region** level instead of pixel level, which makes any
    partition score 1.000 by construction;
  - reported **without `n_stands`**, when R^2 rises monotonically with stand
    count and is 1.0 in the limit of one stand per pixel;
  - reported on an attribute the segmentation or merge already used, while
    labelled held out.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

import fmu.utils.components as comp
from fmu.config import Config, MetricsParams, R2Attribute, load_config
from fmu.utils.components import explained_variance_r2

REPO_ROOT = Path(__file__).parent.parent
CONFIG_DIR = REPO_ROOT / "configs"
BASELINE_YAML = CONFIG_DIR / "sanjay_van_baseline.yaml"
SHIPPED_CONFIGS = sorted(CONFIG_DIR.glob("sanjay_van_*.yaml"))


# ---------- config: R2Attribute ----------


def test_defaults_pair_one_used_attribute_with_held_out_ones():
    """The used one is the literature-comparable number (Xiong reports 81.80%
    on mean canopy height); the held-out ones are the evidence."""
    attrs = MetricsParams().r2_attributes
    used = [a for a in attrs if not a.held_out]
    held = [a for a in attrs if a.held_out]
    assert len(used) == 1 and used[0].band == "canopy_height"
    assert len(held) >= 1


def test_default_attributes_are_available_in_both_arms():
    """An embedding run computes no radar or static features, so an attribute
    from either would silently drop out of exactly one arm of the comparison."""
    sources = MetricsParams().input_sources()
    assert sources <= {"s2_composite", "structure_features", "optical_features"}


def test_held_out_defaults_to_true():
    a = R2Attribute(source="structure_features", band="canopy_height_max")
    assert a.held_out is True


def test_rejects_unknown_source():
    with pytest.raises(ValidationError):
        R2Attribute(source="lidar", band="x")  # type: ignore[arg-type]


# ---------- config: the held_out integrity check ----------


def _baseline_raw() -> dict:
    return yaml.safe_load(BASELINE_YAML.read_text())


def test_held_out_is_checked_against_merge_criteria():
    """canopy_height is a merge criterion, so R^2 on it is partly circular.
    Marking it held out would make the circular number the headline."""
    raw = _baseline_raw()
    raw["metrics"]["r2_attributes"] = [
        {"source": "structure_features", "band": "canopy_height", "held_out": True}
    ]
    with pytest.raises(ValidationError, match="held_out"):
        Config.model_validate(raw)


def test_held_out_is_checked_against_segmentation_input_bands():
    """B4_median helps draw the boundaries even though no merge criterion
    names it."""
    raw = _baseline_raw()
    raw["metrics"]["r2_attributes"] = [
        {"source": "s2_composite", "band": "B4_median", "held_out": True}
    ]
    with pytest.raises(ValidationError, match="held_out"):
        Config.model_validate(raw)


def test_marking_it_used_is_accepted():
    raw = _baseline_raw()
    raw["metrics"]["r2_attributes"] = [
        {"source": "structure_features", "band": "canopy_height", "held_out": False}
    ]
    Config.model_validate(raw)  # no raise


def test_a_genuinely_unused_attribute_passes_as_held_out():
    raw = _baseline_raw()
    raw["metrics"]["r2_attributes"] = [
        {"source": "radar_features", "band": "vh_p50", "held_out": True}
    ]
    Config.model_validate(raw)  # no raise


@pytest.mark.parametrize("path", SHIPPED_CONFIGS, ids=lambda p: p.stem)
def test_shipped_configs_report_at_least_one_held_out_attribute(path: Path):
    cfg = load_config(path)
    assert any(a.held_out for a in cfg.metrics.r2_attributes), path.stem


@pytest.mark.parametrize("path", SHIPPED_CONFIGS, ids=lambda p: p.stem)
def test_shipped_configs_also_report_the_literature_comparable_one(path: Path):
    cfg = load_config(path)
    assert any(not a.held_out for a in cfg.metrics.r2_attributes), path.stem


# ---------- explained_variance_r2 ----------


class _FakeBand:
    """A single band of pixel values, with the arithmetic the metric performs."""

    def __init__(self, values: list[float]) -> None:
        self.values = values

    def subtract(self, other):
        if isinstance(other, _FakeBand):
            return _FakeBand([a - b for a, b in zip(self.values, other.values)])
        return _FakeBand([a - float(other) for a in self.values])

    def pow(self, p):
        return _FakeBand([v**p for v in self.values])

    def multiply(self, m):
        return _FakeBand([v * m for v in self.values])

    def add(self, a):
        return _FakeBand([v + a for v in self.values])

    def rename(self, name):
        self.name = name
        return self


class _FakeStack:
    """Multi-band image over a fixed pixel set."""

    def __init__(self, bands: dict[str, list[float]]) -> None:
        self.bands = bands

    def bandNames(self):  # noqa: N802
        return list(self.bands)

    def select(self, b):
        if isinstance(b, list):
            return _FakeStack({k: self.bands[k] for k in b})
        return _FakeBand(self.bands[b])

    def addBands(self, other):
        return self

    def rename(self, name):
        return self

    def mask(self):
        return self

    def updateMask(self, m):
        return self

    def reduceConnectedComponents(self, **kw):
        return self._region_means

    def reduceRegion(self, **kw):
        return self


@pytest.fixture
def r2_server(monkeypatch):
    """Serve the two reductions the metric performs, from real arithmetic."""

    class _FakeReducer:
        @staticmethod
        def mean():
            return object()

        @staticmethod
        def sum():
            return object()

    class _FakeNumber:
        def __init__(self, v):
            self.v = float(v)

        def __float__(self):
            return self.v

    class _FakeEE:
        Reducer = _FakeReducer
        Number = staticmethod(lambda v: float(v))

        class Image:
            @staticmethod
            def cat(parts):
                merged: dict[str, list[float]] = {}
                for p in parts:
                    merged[p.name] = p.values
                return _Summable(merged)

    class _Summable:
        def __init__(self, bands):
            self.bands = bands

        def reduceRegion(self, **kw):
            return {k: sum(v) for k, v in self.bands.items()}

    def install(values: dict[str, list[float]], region_means: dict[str, list[float]]):
        stack = _FakeStack(values)
        stack._region_means = _FakeStack(region_means)

        def fake_get_info(obj, *, context: str = ""):
            if "bands" in context:
                return list(values)
            if "global means" in context:
                return {k: sum(v) / len(v) for k, v in values.items()}
            if "sums of squares" in context:
                return obj
            raise AssertionError(f"unexpected context {context!r}")

        monkeypatch.setattr(comp, "ee", _FakeEE)
        monkeypatch.setattr(comp, "safe_get_info", fake_get_info)
        return stack

    return install


def test_perfect_partition_scores_one(r2_server):
    """Every pixel equals its region mean: the partition explains everything."""
    values = {"ch": [10.0, 10.0, 20.0, 20.0]}
    means = {"ch": [10.0, 10.0, 20.0, 20.0]}
    stack = r2_server(values, means)
    out = explained_variance_r2(stack, stack, None, 10, 1200)
    assert out["ch"]["r2"] == pytest.approx(1.0)


def test_useless_partition_scores_zero(r2_server):
    """Every region mean equals the global mean: the partition explains nothing."""
    values = {"ch": [10.0, 20.0, 10.0, 20.0]}
    means = {"ch": [15.0, 15.0, 15.0, 15.0]}
    stack = r2_server(values, means)
    out = explained_variance_r2(stack, stack, None, 10, 1200)
    assert out["ch"]["r2"] == pytest.approx(0.0)


def test_partial_partition_scores_between(r2_server):
    values = {"ch": [10.0, 12.0, 20.0, 22.0]}
    means = {"ch": [11.0, 11.0, 21.0, 21.0]}
    stack = r2_server(values, means)
    r2 = explained_variance_r2(stack, stack, None, 10, 1200)["ch"]["r2"]
    assert 0.0 < r2 < 1.0
    # SS_within = 4 x 1 = 4; SS_total = 41+9+9+81 ... computed explicitly:
    gm = sum(values["ch"]) / 4
    ss_total = sum((v - gm) ** 2 for v in values["ch"])
    assert r2 == pytest.approx(1 - 4.0 / ss_total, abs=1e-6)


def test_sums_of_squares_are_reported_alongside(r2_server):
    """So a reader can recompute the ratio rather than trusting it."""
    values = {"ch": [10.0, 12.0, 20.0, 22.0]}
    means = {"ch": [11.0, 11.0, 21.0, 21.0]}
    stack = r2_server(values, means)
    s = explained_variance_r2(stack, stack, None, 10, 1200)["ch"]
    assert s["ss_within"] == pytest.approx(4.0)
    assert s["r2"] == pytest.approx(1 - s["ss_within"] / s["ss_total"])
    assert s["n_pixels"] == 4


def test_constant_attribute_is_dropped_not_scored_one(r2_server):
    """Zero total variance means there is nothing for a partition to explain.
    R^2 is undefined, not 1.0 -- which is what 0/0 in the formula would give."""
    values = {"flat": [5.0, 5.0, 5.0, 5.0]}
    means = {"flat": [5.0, 5.0, 5.0, 5.0]}
    stack = r2_server(values, means)
    assert explained_variance_r2(stack, stack, None, 10, 1200) == {}


def test_multiple_bands_are_scored_independently(r2_server):
    values = {"a": [10.0, 10.0, 20.0, 20.0], "b": [1.0, 9.0, 1.0, 9.0]}
    means = {"a": [10.0, 10.0, 20.0, 20.0], "b": [5.0, 5.0, 5.0, 5.0]}
    stack = r2_server(values, means)
    out = explained_variance_r2(stack, stack, None, 10, 1200)
    assert out["a"]["r2"] == pytest.approx(1.0)
    assert out["b"]["r2"] == pytest.approx(0.0)
