"""fmu.evaluation.stand_overlap on squares worked by hand: Vatandaslar et al. (2025) eq. 1-3 and
Xiong et al. (2024) IoU shares, with the rules the papers leave open (ties, no overlap, the
strict threshold)."""

from __future__ import annotations

import math

import pytest
from shapely.geometry import Polygon, box

from fmu.evaluation.stand_overlap import iou_agreement, overlap_agreement


def test_olo_olu_overall_by_hand():
    refs = [box(0, 0, 10, 10)]                        # area 100
    stands = [box(0, 0, 10, 6), box(0, 6, 10, 10)]   # 60 and 40: the first overlaps most
    r = overlap_agreement(refs, stands)
    row = r.pairs.iloc[0]
    assert (row.reference, row.stand) == (0, 0)
    assert row.olo == pytest.approx(60 / 60) and row.olu == pytest.approx(60 / 100)
    assert row.overall == pytest.approx(0.8)
    assert r.summary["overall"] == pytest.approx(0.8)


def test_overall_is_the_mean_of_the_pairs_and_of_the_two_means():
    refs = [box(0, 0, 10, 10), box(20, 0, 30, 10)]
    stands = [box(0, 0, 10, 6), box(20, 0, 40, 10)]   # pair 1: OLO 1, OLU .6; pair 2: OLO 100/200, OLU 1
    s = overlap_agreement(refs, stands).summary
    assert s["olo"] == pytest.approx((1 + 0.5) / 2) and s["olu"] == pytest.approx((0.6 + 1) / 2)
    assert s["overall"] == pytest.approx(((1 + 0.6) / 2 + (0.5 + 1) / 2) / 2)
    assert s["overall"] == pytest.approx((s["olo"] + s["olu"]) / 2)


def test_ties_go_to_the_first_stand_and_unmatched_references_are_counted():
    refs = [box(0, 0, 10, 10), box(100, 100, 110, 110), Polygon()]
    stands = [box(0, 5, 10, 10), box(0, 0, 10, 5)]   # equal overlaps
    r = overlap_agreement(refs, stands)
    assert list(r.pairs.stand) == [0]
    assert r.summary["n_references"] == 2 and r.summary["n_unmatched_references"] == 1
    assert r.summary["n_matched"] == 1


def test_touching_is_not_overlapping():
    r = overlap_agreement([box(0, 0, 10, 10)], [box(10, 0, 20, 10)])
    assert r.summary["n_matched"] == 0 and math.isnan(r.summary["overall"])


def test_iou_by_hand_and_the_strict_thresholds():
    refs = [box(0, 0, 10, 10), box(50, 0, 60, 10)]
    stands = [
        box(0, 0, 10, 10),      # IoU 1
        box(55, 0, 65, 10),     # 50 / 150 = 1/3
        box(50, 0, 60, 5),      # 50 / 100 = 0.5 exactly: not > 0.5
        box(200, 0, 210, 10),   # no reference: IoU 0, counted
    ]
    r = iou_agreement(refs, stands)
    assert list(r.stands.iou.round(12)) == [1.0, round(1 / 3, 12), 0.5, 0.0]
    assert list(r.stands.reference) == [0, 1, 1, -1]
    assert r.summary["share_iou_gt_0.5"] == pytest.approx(1 / 4)
    assert r.summary["share_iou_gt_0.7"] == pytest.approx(1 / 4)
    assert r.summary["n_stands_without_reference"] == 1
    assert r.summary["mean_iou"] == pytest.approx((1 + 1 / 3 + 0.5 + 0) / 4)


def test_iou_pairs_each_stand_with_the_reference_it_overlaps_most():
    refs = [box(0, 0, 10, 10), box(10, 0, 20, 10)]
    r = iou_agreement(refs, [box(4, 0, 14, 10)])      # 60 with the first, 40 with the second
    assert r.stands.reference.iat[0] == 0
    assert r.stands.iou.iat[0] == pytest.approx(60 / (100 + 100 - 60))


def test_positions_name_the_input_and_bad_input_raises():
    r = iou_agreement([box(0, 0, 1, 1)], [Polygon(), box(0, 0, 1, 1)])
    assert list(r.stands.stand) == [1]
    with pytest.raises(ValueError):
        iou_agreement([box(0, 0, 1, 1)], [box(0, 0, 1, 1)], thresholds=(1.5,))
    with pytest.raises(ValueError):
        overlap_agreement(box(0, 0, 1, 1), [box(0, 0, 1, 1)])
