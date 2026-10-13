"""Tests of `fmu.evaluation.segmentation_accuracy` with known answers.

Every geometry is built here. No real site is read.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import shapely
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box

from fmu.evaluation.segmentation_accuracy import (
    PAIR_COLUMNS,
    PER_REFERENCE_COLUMNS,
    SUMMARY_KEYS,
    BoundaryMatch,
    SegmentationAccuracy,
    boundary_match,
    segmentation_accuracy,
)

SQUARE = box(0, 0, 10, 10)
MEASURES = ("over", "under", "d")


def _row(frame, **where):
    sel = frame
    for key, value in where.items():
        sel = sel[sel[key] == value]
    assert len(sel) == 1
    return sel.iloc[0]


# ---------------------------------------------------------------------------
# Over- and under-segmentation: hand-worked cases
# ---------------------------------------------------------------------------


def test_identical_maps_score_zero():
    polys = [box(0, 0, 10, 10), box(10, 0, 20, 10), box(0, 10, 20, 30)]
    res = segmentation_accuracy(polys, polys)
    assert isinstance(res, SegmentationAccuracy)
    assert list(res.pairs.columns) == PAIR_COLUMNS
    assert list(res.per_reference.columns) == PER_REFERENCE_COLUMNS
    assert list(res.summary) == SUMMARY_KEYS
    # Neighbours touch along an edge only, so each reference matches itself alone.
    assert res.pairs[["reference", "stand"]].to_numpy().tolist() == [[0, 0], [1, 1], [2, 2]]
    for key in MEASURES:
        assert res.pairs[key].to_numpy() == pytest.approx(0.0, abs=1e-12)
        assert res.per_reference[key].to_numpy() == pytest.approx(0.0, abs=1e-12)
        assert res.summary[key] == pytest.approx(0.0, abs=1e-12)
        assert res.summary[f"{key}_per_reference"] == pytest.approx(0.0, abs=1e-12)
        assert res.summary[f"{key}_area_weighted"] == pytest.approx(0.0, abs=1e-12)
    assert res.summary["n_references"] == 3
    assert res.summary["n_stands"] == 3
    assert res.summary["n_pairs"] == 3
    assert res.summary["n_unmatched_references"] == 0


def test_reference_cut_into_two_equal_stands():
    stands = [box(0, 0, 5, 10), box(5, 0, 10, 10)]
    res = segmentation_accuracy(stands, [SQUARE])
    assert len(res.pairs) == 2
    assert res.pairs["stand"].tolist() == [0, 1]
    assert res.pairs["intersection_area"].tolist() == [50.0, 50.0]
    assert res.pairs["reference_area"].tolist() == [100.0, 100.0]
    assert res.pairs["stand_area"].tolist() == [50.0, 50.0]
    # Each stand covers half of the reference (over = 1 - 50/100) and lies
    # wholly inside it (under = 1 - 50/50).
    assert res.pairs["over"].to_numpy() == pytest.approx(0.5)
    assert res.pairs["under"].to_numpy() == pytest.approx(0.0)
    assert res.pairs["d"].to_numpy() == pytest.approx(0.5 / math.sqrt(2))
    ref = _row(res.per_reference, reference=0)
    assert ref["n_matched"] == 2
    assert ref["over"] == pytest.approx(0.5)
    assert ref["under"] == pytest.approx(0.0)
    assert ref["d"] == pytest.approx(0.5 / math.sqrt(2))
    assert res.summary["over"] == pytest.approx(0.5)
    assert res.summary["d_area_weighted"] == pytest.approx(0.5 / math.sqrt(2))


def test_one_stand_four_times_the_reference():
    stand = box(0, 0, 20, 20)
    res = segmentation_accuracy([stand], [SQUARE])
    pair = _row(res.pairs, reference=0, stand=0)
    assert pair["over"] == pytest.approx(0.0)
    assert pair["under"] == pytest.approx(0.75)  # three quarters of the stand lie outside
    assert pair["d"] == pytest.approx(0.75 / math.sqrt(2))


def test_one_stand_covering_four_reference_squares():
    refs = [box(0, 0, 10, 10), box(10, 0, 20, 10), box(0, 10, 10, 20), box(10, 10, 20, 20)]
    res = segmentation_accuracy([box(0, 0, 20, 20)], refs)
    assert len(res.pairs) == 4
    assert res.pairs["reference"].tolist() == [0, 1, 2, 3]
    assert res.pairs["over"].to_numpy() == pytest.approx(0.0)
    assert res.pairs["under"].to_numpy() == pytest.approx(0.75)
    assert res.pairs["d"].to_numpy() == pytest.approx(0.75 / math.sqrt(2))
    assert res.per_reference["n_matched"].tolist() == [1, 1, 1, 1]
    assert res.summary["under_per_reference"] == pytest.approx(0.75)


def test_stand_shifted_against_reference():
    res = segmentation_accuracy([box(4, 0, 14, 10)], [SQUARE])
    pair = _row(res.pairs, reference=0, stand=0)
    assert pair["intersection_area"] == pytest.approx(60.0)
    assert pair["over"] == pytest.approx(0.4)
    assert pair["under"] == pytest.approx(0.4)
    assert pair["d"] == pytest.approx(0.4)  # sqrt((0.16 + 0.16) / 2)


def test_reference_with_no_stand():
    refs = [SQUARE, box(100, 100, 120, 110)]
    res = segmentation_accuracy([SQUARE], refs)
    lone = _row(res.per_reference, reference=1)
    assert lone["n_matched"] == 0
    assert lone["over"] == 1.0
    assert math.isnan(lone["under"])
    assert math.isnan(lone["d"])
    assert res.summary["n_unmatched_references"] == 1
    assert res.summary["n_pairs"] == 1
    # Clinton's summary is over matched pairs only.
    assert res.summary["over"] == pytest.approx(0.0)
    # Per reference: (0 + 1) / 2; by area: (0 * 100 + 1 * 200) / 300.
    assert res.summary["over_per_reference"] == pytest.approx(0.5)
    assert res.summary["over_area_weighted"] == pytest.approx(2.0 / 3.0)
    # The unmatched reference has no stand to measure, so it is left out here.
    assert res.summary["under_per_reference"] == pytest.approx(0.0)
    assert res.summary["d_area_weighted"] == pytest.approx(0.0)


def test_touching_along_an_edge_is_not_a_match():
    res = segmentation_accuracy([box(10, 0, 20, 10)], [SQUARE])
    assert len(res.pairs) == 0
    assert list(res.pairs.columns) == PAIR_COLUMNS
    assert res.per_reference["n_matched"].tolist() == [0]
    assert res.per_reference["over"].tolist() == [1.0]
    for key in MEASURES:
        assert math.isnan(res.summary[key])
        assert math.isnan(res.summary[f"{key}_per_reference"])
        assert math.isnan(res.summary[f"{key}_area_weighted"])
    assert res.summary["n_references"] == 1
    assert res.summary["n_stands"] == 1
    assert res.summary["n_pairs"] == 0
    assert res.summary["n_unmatched_references"] == 1


# ---------------------------------------------------------------------------
# The matching rule
# ---------------------------------------------------------------------------


def test_small_overlap_that_meets_no_rule_is_not_matched():
    # The stand covers 20% of the reference and 20% of itself lies in it;
    # neither centroid is inside the other polygon.
    res = segmentation_accuracy([box(8, 0, 18, 10)], [SQUARE])
    assert len(res.pairs) == 0


# Four stands, each matched to the 10 x 10 reference square by ONE rule only.
_FAR = box(1000, 0, 1100, 100)
ONE_RULE_STANDS = {
    # the reference centroid (5, 5) is in the stand; the stand's centroid
    # (17, 5) is outside; 12 of the stand's 52 m2 are inside
    "reference centroid in stand": (box(4, 4, 30, 6), 12.0),
    # the stand's centroid (5, 1.1) is in the reference; 2 of its 14 m2 are inside
    "stand centroid in reference": (box(-30, 1, 40, 1.2), 2.0),
    # 4 of the stand's 5.9 m2 are inside; its centroid is pulled out by a far part
    "more than half of the stand": (MultiPolygon([box(0, 0, 2, 2), box(100, 0, 101.9, 1)]), 4.0),
    # the stand covers 96% of the reference but not its centroid
    "more than half of the reference": (
        MultiPolygon([SQUARE.difference(box(4, 4, 6, 6)), _FAR]),
        96.0,
    ),
}


@pytest.mark.parametrize("rule", list(ONE_RULE_STANDS))
def test_each_rule_alone_is_enough(rule):
    stand, area = ONE_RULE_STANDS[rule]
    # Check the construction: exactly one of the four conditions holds.
    holds = {
        "reference centroid in stand": bool(stand.covers(SQUARE.centroid)),
        "stand centroid in reference": bool(SQUARE.covers(stand.centroid)),
        "more than half of the stand": area / stand.area > 0.5,
        "more than half of the reference": area / SQUARE.area > 0.5,
    }
    assert [name for name, ok in holds.items() if ok] == [rule]
    assert stand.intersection(SQUARE).area == pytest.approx(area)

    res = segmentation_accuracy([stand], [SQUARE])
    pair = _row(res.pairs, reference=0, stand=0)
    over, under = 1 - area / 100.0, 1 - area / stand.area
    assert pair["over"] == pytest.approx(over)
    assert pair["under"] == pytest.approx(under)
    assert pair["d"] == pytest.approx(math.sqrt((over**2 + under**2) / 2))


def test_min_overlap_fraction_drops_a_pair_only_when_declared():
    # A long strip that holds the reference centroid: 20 of its 400 m2 are in
    # the 100 m2 reference, so the overlap is 0.2 of the smaller polygon.
    strip = box(-100, 4, 100, 6)
    assert len(segmentation_accuracy([strip], [SQUARE]).pairs) == 1
    assert len(segmentation_accuracy([strip], [SQUARE], min_overlap_fraction=0.15).pairs) == 1
    assert len(segmentation_accuracy([strip], [SQUARE], min_overlap_fraction=0.25).pairs) == 0
    # A small stand wholly inside the reference is never a sliver by this rule.
    inside = box(4.9, 4.9, 5.1, 5.1)
    assert len(segmentation_accuracy([inside], [SQUARE], min_overlap_fraction=0.9).pairs) == 1
    for bad in (-0.1, 1.0, float("nan")):
        with pytest.raises(ValueError, match="min_overlap_fraction"):
            segmentation_accuracy([SQUARE], [SQUARE], min_overlap_fraction=bad)


# ---------------------------------------------------------------------------
# Independent recomputation
# ---------------------------------------------------------------------------


def test_against_a_direct_recomputation_on_random_rectangles():
    rng = np.random.default_rng(7)

    def rectangles(n):
        x0 = rng.uniform(0, 80, n)
        y0 = rng.uniform(0, 80, n)
        return [
            box(a, b, a + w, b + h)
            for a, b, w, h in zip(x0, y0, rng.uniform(3, 25, n), rng.uniform(3, 25, n), strict=True)
        ]

    stands, refs = rectangles(40), rectangles(25)
    res = segmentation_accuracy(stands, refs)

    expected = {}
    for i, x in enumerate(refs):
        for j, y in enumerate(stands):
            area = x.intersection(y).area
            if area <= 0:
                continue
            if (
                y.covers(x.centroid)
                or x.covers(y.centroid)
                or area / y.area > 0.5
                or area / x.area > 0.5
            ):
                over, under = 1 - area / x.area, 1 - area / y.area
                expected[(i, j)] = (over, under, math.sqrt((over**2 + under**2) / 2))
    assert len(expected) > 10
    got = {
        (int(r.reference), int(r.stand)): (r.over, r.under, r.d)
        for r in res.pairs.itertuples(index=False)
    }
    assert set(got) == set(expected)
    for key, value in expected.items():
        assert got[key] == pytest.approx(value, abs=1e-12)
    # sorted by reference, then stand
    assert list(got) == sorted(got)

    values = np.array(list(expected.values()))
    assert res.summary["over"] == pytest.approx(values[:, 0].mean())
    assert res.summary["under"] == pytest.approx(values[:, 1].mean())
    assert res.summary["d"] == pytest.approx(values[:, 2].mean())

    per_over, per_d, areas_over, areas_d = [], [], [], []
    for i, x in enumerate(refs):
        mine = [v for (ri, _), v in expected.items() if ri == i]
        row = _row(res.per_reference, reference=i)
        assert row["n_matched"] == len(mine)
        assert row["reference_area"] == pytest.approx(x.area)
        per_over.append(np.mean([v[0] for v in mine]) if mine else 1.0)
        areas_over.append(x.area)
        assert row["over"] == pytest.approx(per_over[-1])
        if mine:
            per_d.append(np.mean([v[2] for v in mine]))
            areas_d.append(x.area)
            assert row["d"] == pytest.approx(per_d[-1])
    assert res.summary["over_per_reference"] == pytest.approx(np.mean(per_over))
    assert res.summary["d_per_reference"] == pytest.approx(np.mean(per_d))
    assert res.summary["over_area_weighted"] == pytest.approx(np.average(per_over, weights=areas_over))
    assert res.summary["d_area_weighted"] == pytest.approx(np.average(per_d, weights=areas_d))
    assert res.summary["n_unmatched_references"] == sum(
        1 for i in range(len(refs)) if not any(ri == i for ri, _ in expected)
    )


def test_measures_stay_in_range_and_do_not_depend_on_units_or_order():
    rng = np.random.default_rng(11)
    stands = [box(a, b, a + 12, b + 9) for a, b in rng.uniform(0, 60, (30, 2))]
    refs = [box(a, b, a + 15, b + 15) for a, b in rng.uniform(0, 60, (12, 2))]
    res = segmentation_accuracy(stands, refs)
    for key in MEASURES:
        col = res.pairs[key].to_numpy()
        assert ((col >= 0) & (col < 1)).all()
    # Ratios of areas: the same map in kilometres gives the same numbers.
    scaled = segmentation_accuracy(
        [shapely.transform(g, lambda c: c / 1000.0) for g in stands],
        [shapely.transform(g, lambda c: c / 1000.0) for g in refs],
    )
    for key in ("over", "under", "d", "d_per_reference", "d_area_weighted"):
        assert scaled.summary[key] == pytest.approx(res.summary[key], rel=1e-9)
    # Reordering the stands renames them and changes nothing else.
    order = rng.permutation(len(stands))
    shuffled = segmentation_accuracy([stands[k] for k in order], refs)
    for key in SUMMARY_KEYS:
        assert shuffled.summary[key] == pytest.approx(res.summary[key], rel=1e-12)
    # Same input, same output, to the last bit.
    again = segmentation_accuracy(stands, refs)
    assert again.pairs.equals(res.pairs)
    assert again.per_reference.equals(res.per_reference)
    assert again.summary == res.summary


# ---------------------------------------------------------------------------
# Input handling
# ---------------------------------------------------------------------------


def test_empty_geometries_are_dropped_and_positions_kept():
    stands = [Polygon(), box(0, 0, 5, 10), Polygon(), box(5, 0, 10, 10)]
    refs = [Polygon(), SQUARE]
    res = segmentation_accuracy(stands, refs)
    assert res.pairs["reference"].tolist() == [1, 1]
    assert res.pairs["stand"].tolist() == [1, 3]
    assert res.per_reference["reference"].tolist() == [1]
    assert res.summary["n_references"] == 1
    assert res.summary["n_stands"] == 2


def test_multipolygons_and_arrays_are_accepted():
    halves = MultiPolygon([box(0, 0, 4, 10), box(6, 0, 10, 10)])
    res = segmentation_accuracy(np.array([halves], dtype=object), (SQUARE,))
    pair = _row(res.pairs, reference=0, stand=0)
    assert pair["over"] == pytest.approx(0.2)
    assert pair["under"] == pytest.approx(0.0)


def test_no_stands_or_no_references():
    res = segmentation_accuracy([], [SQUARE])
    assert len(res.pairs) == 0
    assert res.per_reference["over"].tolist() == [1.0]
    assert math.isnan(res.summary["over"])
    assert res.summary["n_stands"] == 0
    assert res.summary["n_unmatched_references"] == 1
    res = segmentation_accuracy([SQUARE], [])
    assert len(res.pairs) == 0
    assert len(res.per_reference) == 0
    assert list(res.per_reference.columns) == PER_REFERENCE_COLUMNS
    assert math.isnan(res.summary["d_per_reference"])
    assert res.summary["n_references"] == 0


def test_malformed_geometries_raise():
    bowtie = Polygon([(0, 0), (10, 10), (10, 0), (0, 10)])
    with pytest.raises(ValueError, match="invalid"):
        segmentation_accuracy([bowtie], [SQUARE])
    with pytest.raises(ValueError, match="invalid"):
        boundary_match([SQUARE], [bowtie], 1.0)
    with pytest.raises(ValueError, match="LineString"):
        segmentation_accuracy([SQUARE], [LineString([(0, 0), (1, 1)])])
    with pytest.raises(ValueError, match="not a shapely geometry"):
        segmentation_accuracy([SQUARE, None], [SQUARE])
    with pytest.raises(ValueError, match="sequence"):
        segmentation_accuracy(SQUARE, [SQUARE])


# ---------------------------------------------------------------------------
# Boundary match
# ---------------------------------------------------------------------------


def test_boundary_identical_maps():
    polys = [box(0, 0, 10, 10), box(10, 0, 20, 10)]
    res = boundary_match(polys, polys, 0.5)
    assert isinstance(res, BoundaryMatch)
    assert res.precision == pytest.approx(1.0)
    assert res.recall == pytest.approx(1.0)
    assert res.f == pytest.approx(1.0)
    assert res.tolerance == 0.5
    # The shared edge counts once: 2 * 40 - 10.
    assert res.stand_boundary_length == pytest.approx(70.0)
    assert res.reference_boundary_length == pytest.approx(70.0)
    assert res.matched_stand_length == pytest.approx(70.0)
    assert res.matched_reference_length == pytest.approx(70.0)


def test_boundary_extra_dividing_line():
    stands = [box(0, 0, 5, 10), box(5, 0, 10, 10)]
    res = boundary_match(stands, [SQUARE], 0.1)
    assert res.stand_boundary_length == pytest.approx(50.0)
    assert res.reference_boundary_length == pytest.approx(40.0)
    assert res.recall == pytest.approx(1.0)
    # Of the 10 m dividing line only 0.1 m at each end is near the outline.
    assert res.matched_stand_length == pytest.approx(40.2, abs=1e-6)
    assert res.precision == pytest.approx(40.2 / 50.0, abs=1e-3)
    p, r = 40.2 / 50.0, 1.0
    assert res.f == pytest.approx(2 * p * r / (p + r), abs=1e-3)
    # Swapping the roles swaps precision and recall.
    swapped = boundary_match([SQUARE], stands, 0.1)
    assert swapped.precision == pytest.approx(res.recall)
    assert swapped.recall == pytest.approx(res.precision)
    assert swapped.f == pytest.approx(res.f)


def test_boundary_offset_against_the_tolerance():
    stand = [box(1, 0, 11, 10)]  # the reference square moved 1 m in x
    wide = boundary_match(stand, [SQUARE], 2.0)
    assert wide.precision == pytest.approx(1.0)
    assert wide.recall == pytest.approx(1.0)
    assert wide.f == pytest.approx(1.0)
    # Tolerance 0.5 m, offset 1 m. Stand boundary (40 m): 9.5 m of the top and
    # 9.5 m of the bottom edge lie within 0.5 m of the reference's top and
    # bottom edges, 0.5 m at each end of the left edge lies near them, and the
    # right edge is 1 m from the reference throughout: 20 m of 40.
    tight = boundary_match(stand, [SQUARE], 0.5)
    assert tight.matched_stand_length == pytest.approx(20.0, abs=0.01)
    assert tight.matched_reference_length == pytest.approx(20.0, abs=0.01)
    assert tight.precision == pytest.approx(0.5, abs=0.01)
    assert tight.recall == pytest.approx(0.5, abs=0.01)
    assert tight.f == pytest.approx(0.5, abs=0.01)
    # A tolerance just under the offset misses the two long edges; just over
    # it catches them.
    assert boundary_match(stand, [SQUARE], 0.99).precision < 0.76
    assert boundary_match(stand, [SQUARE], 1.01).precision == pytest.approx(1.0)


def test_boundary_far_apart_scores_zero():
    res = boundary_match([box(100, 100, 110, 110)], [SQUARE], 1.0)
    assert res.precision == 0.0
    assert res.recall == 0.0
    assert res.f == 0.0


def test_boundary_ignore_removes_the_shared_outline():
    refs = [box(0, 0, 5, 10), box(5, 0, 10, 10)]
    stands = [box(0, 0, 5, 5), box(0, 5, 5, 10), box(5, 0, 10, 10)]  # one more inner line
    # With the outline in, most of the boundary matches trivially: the outline
    # (40) and the shared dividing line (10) match, and of the extra 5 m line
    # 0.1 m at each end is near another boundary.
    plain = boundary_match(stands, refs, 0.1)
    assert plain.stand_boundary_length == pytest.approx(55.0)
    assert plain.precision == pytest.approx(50.2 / 55.0, abs=1e-4)
    assert plain.recall == pytest.approx(1.0)
    # With a 0.5 m band round the outline ignored, what is left is the
    # dividing line (9 m) in both maps and 4.5 m of the extra line in the
    # stands, of which 0.1 m is near the dividing line.
    outline = SQUARE.boundary.buffer(0.5)
    res = boundary_match(stands, refs, 0.1, ignore=outline)
    assert res.reference_boundary_length == pytest.approx(9.0, abs=1e-6)
    assert res.stand_boundary_length == pytest.approx(13.5, abs=1e-6)
    assert res.matched_stand_length == pytest.approx(9.1, abs=1e-6)
    assert res.precision == pytest.approx(9.1 / 13.5, abs=1e-6)
    assert res.recall == pytest.approx(1.0)
    # A sequence of geometries is the same as their union.
    parts = [SQUARE.boundary.buffer(0.5), Point(500, 500).buffer(1.0)]
    assert boundary_match(stands, refs, 0.1, ignore=parts) == res
    with pytest.raises(ValueError, match="ignore"):
        boundary_match(stands, refs, 0.1, ignore=[1, 2])


def test_boundary_degenerate_inputs():
    none = boundary_match([], [SQUARE], 1.0)
    assert math.isnan(none.precision)
    assert none.recall == 0.0  # there is a reference boundary and the map found none of it
    assert math.isnan(none.f)
    assert none.stand_boundary_length == 0.0
    no_ref = boundary_match([SQUARE], [], 1.0)
    assert no_ref.precision == 0.0
    assert math.isnan(no_ref.recall)
    assert math.isnan(no_ref.f)
    both = boundary_match([], [], 1.0)
    assert math.isnan(both.precision) and math.isnan(both.recall) and math.isnan(both.f)
    # Everything ignored is the same as nothing there.
    gone = boundary_match([SQUARE], [SQUARE], 1.0, ignore=box(-5, -5, 15, 15))
    assert math.isnan(gone.precision) and math.isnan(gone.recall) and math.isnan(gone.f)
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="tolerance"):
            boundary_match([SQUARE], [SQUARE], bad)


def test_boundary_is_symmetric_and_repeatable_on_random_maps():
    rng = np.random.default_rng(3)
    cuts_a = np.sort(rng.uniform(5, 95, 6))
    cuts_b = cuts_a + rng.normal(0, 1.5, 6)

    def strips(cuts):
        edges = np.concatenate([[0.0], cuts, [100.0]])
        return [box(lo, 0, hi, 50) for lo, hi in zip(edges[:-1], edges[1:], strict=True)]

    a, b = strips(cuts_a), strips(cuts_b)
    res = boundary_match(a, b, 2.0)
    again = boundary_match(a, b, 2.0)
    assert res == again
    other = boundary_match(b, a, 2.0)
    assert other.precision == pytest.approx(res.recall)
    assert other.recall == pytest.approx(res.precision)
    assert 0.0 <= res.precision <= 1.0 and 0.0 <= res.recall <= 1.0
    # A wider tolerance can only match more.
    assert boundary_match(a, b, 4.0).precision >= res.precision - 1e-12
    # Direct count for the inner lines: a 50 m cut matches (but for its two
    # ends, which lie on the shared outline and always match) when it is
    # within 2 m of a cut of the other map.
    near = np.abs(cuts_a[:, None] - cuts_b[None, :]).min(axis=1) <= 2.0
    assert 0 < near.sum() < near.size
    outline = box(0, 0, 100, 50).boundary.buffer(3.0)
    inner = boundary_match(a, b, 2.0, ignore=outline)
    assert inner.stand_boundary_length == pytest.approx(6 * 44.0, abs=1e-6)
    assert inner.precision == pytest.approx(near.mean(), abs=1e-9)
