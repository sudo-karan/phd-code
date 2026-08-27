"""Non-live tests for `fmu.utils.components`.

Exercised against fake images so no Earth Engine call is made. What is being
pinned is the decision logic, not the reduction: given a component-size
histogram, does the guard raise, and does the message say something a person can
act on?

Why this guard exists: `reduceConnectedComponents(maxSize=N)` masks -- deletes
-- every component larger than N. There is no error and no warning. This has
already cost the project 15 superpixels / 43.9 ha in one arm of a two-arm
comparison, because the two configs hand-set the cap differently.
"""

from __future__ import annotations

import pytest

import fmu.utils.components as comp
from fmu.utils.components import (
    ComponentSizeError,
    assert_components_fit,
    largest_component_pixels,
)


class _FakeLabels:
    """Stand-in for a single-band ee.Image of integer labels."""

    def __init__(self, band: str = "snic_clusters") -> None:
        self.band = band

    def bandNames(self):  # noqa: N802 - mirrors the ee API
        return [self.band]

    def select(self, bands):
        return self

    def reduceRegion(self, **kwargs):  # noqa: N802 - mirrors the ee API
        return self


class _FakeReducer:
    @staticmethod
    def frequencyHistogram():  # noqa: N802 - mirrors the ee API
        return object()


class _FakeEE:
    """Just enough of `ee` for this module; building a real ee.Reducer would
    require an initialized client, which is the whole point of not doing it."""

    Reducer = _FakeReducer


@pytest.fixture
def histogram(monkeypatch):
    """Install a component-size histogram and capture the getInfo payloads."""
    monkeypatch.setattr(comp, "ee", _FakeEE)

    def install(counts: dict[str, float] | None, band: str = "snic_clusters"):
        payloads = [[band], {band: counts}]

        def fake_get_info(obj, *, context: str = ""):
            return payloads.pop(0)

        monkeypatch.setattr(comp, "safe_get_info", fake_get_info)
        return _FakeLabels(band)

    return install


# ---------- largest_component_pixels ----------


def test_reports_largest_and_count(histogram):
    labels = histogram({"1": 100, "2": 350, "3": 42})
    assert largest_component_pixels(labels, None, 10) == (350, 3)


def test_handles_an_empty_histogram(histogram):
    """An ROI with no labelled pixels must not blow up on max([])."""
    labels = histogram({})
    assert largest_component_pixels(labels, None, 10) == (0, 0)


def test_handles_a_null_histogram(histogram):
    """reduceRegion returns null for a fully-masked band."""
    labels = histogram(None)
    assert largest_component_pixels(labels, None, 10) == (0, 0)


def test_counts_come_back_as_ints(histogram):
    """GEE returns histogram counts as floats."""
    labels = histogram({"1": 100.0, "2": 350.0})
    largest, n = largest_component_pixels(labels, None, 10)
    assert isinstance(largest, int) and isinstance(n, int)
    assert (largest, n) == (350, 2)


def test_uses_the_images_own_band_name(histogram):
    labels = histogram({"7": 5}, band="stand_clusters")
    assert largest_component_pixels(labels, None, 10) == (5, 1)


# ---------- assert_components_fit ----------


def test_passes_with_headroom(histogram):
    labels = histogram({"1": 100, "2": 444})
    stats = assert_components_fit(labels, None, 10, 1200, context="test")
    assert stats == {
        "n_components": 2,
        "largest_component_px": 444,
        "max_component_px_cap": 1200,
    }


def test_raises_when_a_component_exceeds_the_cap(histogram):
    labels = histogram({"1": 100, "2": 1500})
    with pytest.raises(ComponentSizeError) as exc:
        assert_components_fit(labels, None, 10, 1200, context="test")
    msg = str(exc.value)
    assert "1500" in msg and "1200" in msg
    # The message must name the area that would be needed, so the reader can
    # act on it (raise max_area_ha) rather than just knowing a number is wrong.
    assert "15.00 ha" in msg


def test_boundary_equal_to_cap_passes(histogram):
    """maxSize masks components *larger* than it, so equal is still safe."""
    labels = histogram({"1": 1200})
    assert assert_components_fit(labels, None, 10, 1200, context="test")[
        "largest_component_px"
    ] == 1200


def test_one_over_the_cap_raises(histogram):
    labels = histogram({"1": 1201})
    with pytest.raises(ComponentSizeError):
        assert_components_fit(labels, None, 10, 1200, context="test")


def test_the_historical_regression_would_have_been_caught(histogram):
    """The embedding arm's largest superpixel was 342 px against a hand-set cap
    of 256; 15 superpixels totalling 43.9 ha were silently deleted. Under the
    derived cap of 1200 it passes; under the old 256 it raises."""
    labels = histogram({"1": 342})
    assert_components_fit(labels, None, 10, 1200, context="derived cap")

    labels = histogram({"1": 342})
    with pytest.raises(ComponentSizeError):
        assert_components_fit(labels, None, 10, 256, context="old hand-set cap")


def test_context_appears_in_the_error(histogram):
    labels = histogram({"1": 5000})
    with pytest.raises(ComponentSizeError, match="metrics per-stand confidence"):
        assert_components_fit(
            labels, None, 10, 1200, context="metrics per-stand confidence"
        )


def test_empty_labels_pass(histogram):
    """Nothing to mask means nothing to lose; the caller's own emptiness checks
    are the right place to complain about an empty ROI."""
    labels = histogram({})
    stats = assert_components_fit(labels, None, 10, 1200, context="test")
    assert stats["n_components"] == 0
