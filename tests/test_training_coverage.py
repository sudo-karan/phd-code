"""Non-live tests for the k-means training-row coverage report.

A run logged `k-means training rows: 289 (one per stand_clusters)` against a
merge that had just produced 327 stands. Both numbers were correct and neither
line referenced the other, so 38 stands -- 12% of the delineation -- had no say
in the cluster definitions they would be judged by, and nothing in the output
said so. The only guard was `n_units < k`, which 289 clears comfortably.

The two ways a unit goes missing are not equivalent, which is why the report
splits them rather than printing one shortfall:

  - outside the habitat mask: correct. A non-forest unit should not be typed as
    forest, and excluding it loses nothing.
  - inside habitat, dropped by `dropNulls`: a band has no data over it. That
    tracks input coverage rather than forest character, so the exclusion is
    non-random -- and since `cluster()` masks wherever an input band is masked,
    those units are absent from `cluster_labels` too.
"""

from __future__ import annotations

import pytest

import fmu.stages.clustering as clustering_mod
from fmu.stages.clustering import _count_units


class _FakeImage:
    def __init__(self, hist, band="stand_clusters"):
        self._hist = hist
        self._band = band

    def bandNames(self):  # noqa: N802 - mirrors the ee API
        return [self._band]

    def select(self, bands):
        return self

    def reduceRegion(self, **kw):  # noqa: N802 - mirrors the ee API
        return {self._band: self._hist}


@pytest.fixture
def fake_ee(monkeypatch):
    class _FakeEE:
        class Reducer:
            @staticmethod
            def frequencyHistogram():  # noqa: N802 - mirrors the ee API
                return object()

    monkeypatch.setattr(clustering_mod, "ee", _FakeEE)
    monkeypatch.setattr(
        clustering_mod,
        "safe_get_info",
        lambda obj, *, context="": obj,
    )


def test_counts_distinct_labels(fake_ee):
    labels = _FakeImage({"11": 100.0, "22": 250.0, "33": 4.0})
    assert _count_units(labels, None, 10, context="test") == 3


def test_an_empty_roi_counts_zero(fake_ee):
    assert _count_units(_FakeImage({}), None, 10, context="test") == 0


def test_a_missing_histogram_counts_zero(fake_ee):
    """`reduceRegion` returns null for the band when nothing is unmasked, and
    `len(None)` would raise inside a stage that had otherwise succeeded."""
    assert _count_units(_FakeImage(None), None, 10, context="test") == 0


def test_pixel_counts_do_not_affect_the_unit_count(fake_ee):
    """Distinct labels, not area. A 4-pixel sliver counts once, same as a
    1000-pixel stand."""
    small = _FakeImage({"1": 4.0, "2": 4.0})
    large = _FakeImage({"1": 1000.0, "2": 1000.0})
    assert _count_units(small, None, 10, context="t") == _count_units(
        large, None, 10, context="t"
    )


# ---------- the arithmetic the log line reports ----------
#
# Held separately from _train_and_apply_kmeans, whose surrounding EE calls
# (stratifiedSample, wekaKMeans.train, cluster) would need a fake far larger
# than the question warrants.


def _split(n_total: int, n_in_habitat: int, n_rows: int) -> tuple[int, int]:
    n_non_habitat = max(n_total - n_in_habitat, 0)
    n_null_dropped = max(n_in_habitat - n_rows, 0)
    return n_non_habitat, n_null_dropped


def test_the_observed_run_splits_into_two_causes():
    """327 stands, 289 rows. Whatever the habitat split turns out to be, the two
    causes must account for the whole shortfall."""
    n_non_habitat, n_null_dropped = _split(327, 303, 289)
    assert n_non_habitat == 24
    assert n_null_dropped == 14
    assert n_non_habitat + n_null_dropped == 327 - 289


def test_full_coverage_reports_no_shortfall():
    assert _split(327, 327, 327) == (0, 0)


def test_a_shortfall_entirely_from_the_habitat_mask_flags_no_null_drops():
    """The benign case must not raise the warning: excluding non-forest units is
    the mask doing its job."""
    n_non_habitat, n_null_dropped = _split(327, 289, 289)
    assert n_non_habitat == 38
    assert n_null_dropped == 0


def test_a_shortfall_entirely_from_missing_band_data_is_attributed_there():
    n_non_habitat, n_null_dropped = _split(327, 327, 289)
    assert n_non_habitat == 0
    assert n_null_dropped == 38


def test_the_split_never_goes_negative():
    """Different reductions can disagree at the very edge of the ROI, so the
    counts are not guaranteed to nest. A negative count in a warning would be
    worse than the shortfall it describes."""
    assert _split(300, 327, 350) == (0, 0)


# ---------- what reaches the manifest ----------


def test_coverage_keys_are_recorded_for_the_manifest():
    """The row count alone was what hid this. All five numbers travel together
    so a manifest read after the fact can still reconstruct the split."""
    import inspect

    src = inspect.getsource(clustering_mod._train_and_apply_kmeans)
    for key in (
        "n_training_units",
        "n_units_total",
        "n_units_in_habitat",
        "n_units_outside_habitat",
        "n_units_dropped_null_band",
    ):
        assert key in src, key


def test_the_stage_spreads_coverage_into_its_metadata():
    import inspect

    src = inspect.getsource(clustering_mod.ClusteringStage.run)
    assert "**unit_coverage" in src
