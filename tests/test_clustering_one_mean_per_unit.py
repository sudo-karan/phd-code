"""One mean per unit label, over all of its pixels (review B14).

The clustering stage averages the features over each unit (a stand, or a superpixel when the
merge is off) and fits k-means on one row per unit. It used reduceConnectedComponents, which
averages each 8-connected piece of a label on its own: a stand in two pieces had two means,
its k-means row came from one of them, and its pieces could get two types. It now takes one
mean per label over every pixel the label has in the ROI, with a grouped reduction of the
stack by the label image, and paints it back on every pixel of the label with remap.

The grouped reduction sums each band, unmasked (0 where it has no data), beside a band of 1
where it has data, and the mean is the one over the other. The first version of this change
took a grouped unweighted mean of the masked bands, which the numpy stand-ins below averaged
over each band's pixels with data; read on Earth Engine (tests/test_clustering_unit_means_live.py,
20 Oct 2026), a grouped unweighted reducer adds a band's masked pixels into its sum, so the
stand-ins now refuse a masked band in an unweighted grouped reduction, and that version fails
here.

The numbers are computed on numpy stand-ins for the images (tests/_ee_arrays.py), through
ClusteringStage.run up to its first sample, which reads the unit means. The calls are pinned
here and by tests/test_clustering_off_golden.py; what Earth Engine makes of them is checked by
tests/test_clustering_unit_means_live.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

import fmu.stages.clustering as clustering
from _clustering_stand_ins import HANDCRAFTED_DECOMPOSED, run_stage
from _ee_arrays import Image, install
from _ee_recorder import calls, made_by
from fmu.config import load_config
from fmu.stages.base import PipelineContext
from fmu.utils.gee import LABEL_BAND

REPO = Path(__file__).resolve().parent.parent
BASELINE = REPO / "configs" / "sanjay_van_baseline.yaml"  # hand-crafted, merge on

# Four stands on a 6 x 6 grid, 0 where there is none. Stand 7 is in two pieces: four pixels
# top left, and one bottom right, which touches stand 5 only.
LABELS = np.array(
    [
        [7, 7, 0, 3, 3, 3],
        [7, 7, 0, 3, 3, 3],
        [0, 0, 0, 0, 0, 0],
        [9, 9, 0, 0, 5, 5],
        [9, 9, 0, 0, 5, 5],
        [0, 0, 0, 0, 0, 7],
    ],
    dtype=float,
)
NDVI = np.array(
    [
        [1.0, 1.0, 0.0, 1.0, 2.0, 3.0],
        [1.0, 1.0, 0.0, 4.0, 5.0, 6.0],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        [2.0, 2.0, 0.0, 0.0, 10.0, 20.0],
        [2.0, 2.0, 0.0, 0.0, 30.0, 40.0],
        [0.0, 0.0, 0.0, 0.0, 0.0, 6.0],
    ]
)
# Canopy height has no data on the east column of stand 3 (30 and 60), nor over stand 9.
CANOPY = np.where(LABELS == 7, 5.0, np.where(LABELS == 5, 8.0, 0.0))
CANOPY[0:2, 3:6] = [[10.0, 20.0, 30.0], [40.0, 50.0, 60.0]]
CANOPY_HAS_DATA = ~((LABELS == 9) | ((LABELS == 3) & (np.arange(6)[None, :] == 5)))
# One pixel of stand 7 lies outside the habitat mask.
HABITAT = np.ones((6, 6))
HABITAT[0, 0] = 0.0
IN_HABITAT = HABITAT != 0


class _FirstSampleError(Exception):
    """Raised by the stand-in for the stage's first sample, with the image it was given."""

    def __init__(self, image: Any):
        self.image = image


def _capture(image: Any, *args: Any, **kwargs: Any) -> Any:
    raise _FirstSampleError(image)


def _unit_means(monkeypatch) -> Image:
    """The image of unit means, inside the habitat mask, that the stage samples first."""
    config = load_config(BASELINE)
    install(monkeypatch, clustering)
    # Before round 13 the stage checked the labels against the cap and measured a
    # neighbourhood for reduceConnectedComponents first: stubbed, so that this test runs on
    # that code too, where it fails (stand 7 has two means).
    monkeypatch.setattr(
        clustering,
        "assert_components_fit",
        lambda *a, **k: {"n_components": 4, "largest_component_px": 6, "max_component_px_cap": 1200},
        raising=False,
    )
    monkeypatch.setattr(
        clustering, "_component_neighbourhood_px", lambda *a, **k: (6, 10), raising=False
    )
    monkeypatch.setattr(clustering, "_sample_one_point_per_unit", _capture)
    ctx = PipelineContext()
    ctx.set("roi", "<roi>")
    ctx.set(config.unit_label_key(), Image({"stand_clusters": LABELS}, {"stand_clusters": LABELS != 0}))
    ctx.set("habitat_mask", Image({"habitat": HABITAT}))
    ctx.set("optical_features", Image({"ndvi_mean": NDVI}))
    ctx.set("radar_features", Image({"vv_p50": np.full((6, 6), -7.0)}))
    ctx.set("structure_features", Image({"canopy_height": CANOPY}, {"canopy_height": CANOPY_HAS_DATA}))
    ctx.set("static_features", Image({"elevation": np.full((6, 6), 230.0)}))
    with pytest.raises(_FirstSampleError) as got:
        clustering.ClusteringStage().run(ctx, config)
    return got.value.image


def test_a_stand_in_two_pieces_has_one_mean_over_both(monkeypatch):
    """(4 x 1.0 + 6.0) / 5 pixels: one mean over both pieces, the pixel outside the habitat
    mask included."""
    means = _unit_means(monkeypatch)
    assert means.values("ndvi_mean", (LABELS == 7) & IN_HABITAT) == {2.0}
    assert means.values("canopy_height", (LABELS == 7) & IN_HABITAT) == {5.0}


def test_a_stand_in_one_piece_has_the_mean_reduce_connected_components_gave(monkeypatch):
    """For every stand in one piece, the numbers of the call the stage made before round 13
    (here exactly: the stand-in sums the same pixels in the same order)."""
    means = _unit_means(monkeypatch)
    stack = Image(
        {"ndvi_mean": NDVI, "canopy_height": CANOPY, LABEL_BAND: LABELS},
        {"canopy_height": CANOPY_HAS_DATA, LABEL_BAND: LABELS != 0},
    )
    per_piece = stack.reduceConnectedComponents(None, labelBand=LABEL_BAND)
    for stand in (3, 5, 9):
        pixels = np.equal(LABELS, stand)
        for band in ("ndvi_mean", "canopy_height"):
            assert means.values(band, pixels) == per_piece.values(band, pixels)
    assert means.values("ndvi_mean", LABELS == 3) == {3.5}
    assert means.values("ndvi_mean", LABELS == 5) == {25.0}


def test_a_band_is_averaged_over_the_pixels_where_it_has_data(monkeypatch):
    """Stand 3's canopy height is the mean of its four pixels with data (10, 20, 40, 50), and
    every pixel of the stand holds it, the two without data included."""
    means = _unit_means(monkeypatch)
    assert means.values("canopy_height", LABELS == 3) == {30.0}


def test_a_stand_with_no_data_in_a_band_is_masked_in_that_band_only(monkeypatch):
    means = _unit_means(monkeypatch)
    assert means.values("canopy_height", LABELS == 9) == {None}
    assert means.values("ndvi_mean", LABELS == 9) == {2.0}


def test_the_habitat_mask_comes_after_the_means(monkeypatch):
    means = _unit_means(monkeypatch)
    assert means.value("ndvi_mean", (0, 0)) is None
    assert means.value("ndvi_mean", (0, 1)) == 2.0


def test_a_pixel_of_no_stand_holds_nothing(monkeypatch):
    means = _unit_means(monkeypatch)
    assert list(means.bands) == ["ndvi_mean", "vv_p50", "canopy_height", "elevation"]
    for band in means.bands:
        assert means.values(band, LABELS == 0) == {None}


def _grouped_reduction(log: list) -> Any:
    (reduction,) = [
        c for c in calls(log, ".reduceRegion")
        if c.kwargs["reducer"].name == "ee.Reducer.sum().unweighted().forEachBand().group()"
    ]
    return reduction


def test_the_grouped_reduction_counts_each_pixel_once_in_the_label_grid():
    """Unweighted sums, so each pixel counts once; grouped by the label band, which follows
    the feature bands and their bands of pixels with data; in the label image's own grid at
    the analysis scale, with no bestEffort, which would average a coarser grid; and no
    reduceConnectedComponents in the stage."""
    config = load_config(BASELINE)
    _, log, ctx = run_stage(clustering, config)
    assert not calls(log, ".reduceConnectedComponents")
    reduction = _grouped_reduction(log)
    assert set(reduction.kwargs) == {"reducer", "geometry", "crs", "maxPixels"}
    assert reduction.kwargs["geometry"] is ctx.get("roi")
    assert reduction.kwargs["maxPixels"] == 1_000_000_000
    (group,) = calls(log, "ee.Reducer.sum().unweighted().forEachBand().group")
    assert group.kwargs == {"groupField": 2 * len(HANDCRAFTED_DECOMPOSED), "groupName": LABEL_BAND}
    at_scale = made_by(log, reduction.kwargs["crs"])
    assert at_scale.attr == "atScale" and at_scale.args == (config.export.analysis_scale_m,)
    projection = made_by(log, at_scale.owner)
    assert projection.attr == "projection"
    assert made_by(log, projection.owner).owner is ctx.get(config.unit_label_key())


def test_no_band_goes_into_the_grouped_reduction_masked():
    """Earth Engine's grouped unweighted reducers add a band's masked pixels into the sum (read
    on Earth Engine, 20 Oct 2026): every band of the reduced image is a band unmasked to 0, a
    0/1 band of where a band has data, or the labels. Both are unmasked everywhere
    (sameFootprint false): unmask(0) alone leaves a band masked outside its footprint, and a
    unit cut by a band's footprint then took in its masked pixels (read on Earth Engine, 20 Oct
    2026: 2,664 and 32 pixels where 1,320 and 16 are right)."""
    config = load_config(BASELINE)
    _, log, _ = run_stage(clustering, config)
    reduction = _grouped_reduction(log)
    with_labels = made_by(log, reduction.owner)
    assert with_labels.attr == "addBands"
    summed = made_by(log, with_labels.owner)
    assert summed.attr == "addBands"
    unmasked = made_by(log, summed.owner)
    assert (unmasked.attr, unmasked.args) == ("unmask", (0, False))
    (has_data,) = summed.args
    renamed = made_by(log, has_data)
    assert renamed.attr == "rename"
    everywhere = made_by(log, renamed.owner)
    assert (everywhere.attr, everywhere.args) == ("unmask", (0, False))
    above_zero = made_by(log, everywhere.owner)
    assert (above_zero.attr, above_zero.args) == ("gt", (0,))
    the_mask = made_by(log, above_zero.owner)
    assert the_mask.attr == "mask"
    assert the_mask.owner is unmasked.owner  # the same feature bands
