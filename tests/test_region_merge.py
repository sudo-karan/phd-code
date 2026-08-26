"""Non-live tests for `fmu.utils.region_merge`.

Pure Python over a hand-built adjacency graph -- no Earth Engine anywhere, which
is the point of having the merge live outside the stage.

The cases here are chosen to pin the decisions that are easy to get subtly
wrong and impossible to notice from a stand map:

  - the gate is **conjunctive** (any criterion over tolerance rejects), not a
    weighted sum;
  - attribute means are weighted by **per-criterion valid pixel count**, so a
    null-canopy region cannot give a merged stand a canopy height for territory
    that never measured one;
  - `max_area_ha` binds in **both** passes, including the shared-edge fallback,
    because the derived `max_component_pixels` depends on it;
  - orphans are split by cause, since "surrounded by different forest" and
    "every neighbour is already too big" call for opposite fixes.
"""

from __future__ import annotations

import pytest

from fmu.utils.adjacency import SuperpixelGraph
from fmu.utils.region_merge import calibrate_thresholds, merge_superpixels

# 1 ha at 10 m = 100 px. Areas below are quoted in pixels for that reason.
PX_PER_HA = 100

DEFAULTS = dict(
    relax_factor=1.75,
    min_area_ha=1.0,
    max_area_ha=10.0,
    min_defined_criteria=2,
    min_frac_valid=0.5,
    max_pass2_iterations=60,
)


def _graph(n_pixels: list[int], edges: dict[tuple[int, int], int]) -> SuperpixelGraph:
    return SuperpixelGraph(
        raw_labels=list(range(100, 100 + len(n_pixels))),
        n_pixels=n_pixels,
        edges=edges,
        scale_m=10,
    )


def _attrs(
    rows: list[dict[str, float | None]], n_pixels: list[int]
) -> tuple[dict, dict]:
    """Means plus valid counts, defaulting every band to fully valid."""
    means = {i: dict(r) for i, r in enumerate(rows)}
    counts = {
        i: {b: (0 if v is None else n_pixels[i]) for b, v in r.items()}
        for i, r in enumerate(rows)
    }
    return means, counts


def _run(graph, means, counts, criteria, **over):
    kwargs = {**DEFAULTS, **over}
    return merge_superpixels(graph, means, counts, criteria=criteria, **kwargs)


# ---------- pass 1: the hard gate ----------


def test_similar_neighbours_merge():
    px = [200, 200]
    means, counts = _attrs(
        [{"ch": 10.0, "std": 0.5}, {"ch": 10.5, "std": 0.55}], px
    )
    r = _run(_graph(px, {(0, 1): 10}), means, counts, {"ch": 2.0, "std": 0.45})
    assert r.n_stands == 1
    assert r.assignment == [0, 0]


def test_one_criterion_over_tolerance_rejects_the_whole_pair():
    """A hard gate, not a weighted sum: being very close on two criteria does
    not buy tolerance on the third. This is Xiong's design and it is what keeps
    thresholds interpretable in physical units."""
    px = [200, 200]
    means, counts = _attrs(
        [
            {"ch": 10.0, "std": 0.50, "amp": 0.10},
            {"ch": 10.0, "std": 0.50, "amp": 0.90},  # amp wildly out
        ],
        px,
    )
    r = _run(
        _graph(px, {(0, 1): 10}),
        means,
        counts,
        {"ch": 2.0, "std": 0.45, "amp": 0.03},
    )
    assert r.n_stands == 2


def test_exactly_at_tolerance_merges():
    px = [200, 200]
    means, counts = _attrs([{"ch": 10.0, "std": 0.5}, {"ch": 12.0, "std": 0.5}], px)
    r = _run(_graph(px, {(0, 1): 10}), means, counts, {"ch": 2.0, "std": 0.45})
    assert r.n_stands == 1


def test_just_over_tolerance_does_not_merge():
    px = [200, 200]
    means, counts = _attrs([{"ch": 10.0, "std": 0.5}, {"ch": 12.01, "std": 0.5}], px)
    r = _run(_graph(px, {(0, 1): 10}), means, counts, {"ch": 2.0, "std": 0.45})
    assert r.n_stands == 2


def test_pass1_iterates_to_convergence():
    """A chain of similar regions collapses to one stand, which needs more than
    one round: each round merges at most one partner per region."""
    px = [150] * 6
    means, counts = _attrs(
        [{"ch": 10.0 + 0.1 * i, "std": 0.5} for i in range(6)], px
    )
    edges = {(i, i + 1): 10 for i in range(5)}
    r = _run(_graph(px, edges), means, counts, {"ch": 2.0, "std": 0.45})
    assert r.n_stands == 1
    assert r.diagnostics["pass1_rounds"] > 1


def test_non_adjacent_regions_never_merge():
    """Identical attributes are not enough; the merge is over an adjacency
    graph, so two identical patches across the park stay separate stands."""
    px = [200, 200]
    means, counts = _attrs([{"ch": 10.0, "std": 0.5}, {"ch": 10.0, "std": 0.5}], px)
    r = _run(_graph(px, {}), means, counts, {"ch": 2.0, "std": 0.45})
    assert r.n_stands == 2


# ---------- min_defined_criteria ----------


def test_pair_with_one_defined_criterion_does_not_merge_in_pass1():
    """One criterion is too weak a similarity test. The pair falls to pass 2 --
    the right destination, since refusing outright would leave it to the blinder
    shared-edge rule anyway."""
    px = [200, 200]
    means = {0: {"ch": None, "std": 0.5}, 1: {"ch": 10.0, "std": 0.52}}
    counts = {0: {"ch": 0, "std": 200}, 1: {"ch": 200, "std": 200}}
    r = _run(
        _graph(px, {(0, 1): 10}),
        means,
        counts,
        {"ch": 2.0, "std": 0.45},
        min_area_ha=0.5,  # both are 2 ha, so pass 2 has no reason to act
    )
    assert r.n_stands == 2
    assert r.diagnostics["pass1_pairs_blocked_by_undefined_criteria_round1"] == 1


def test_lowering_min_defined_criteria_lets_that_pair_merge():
    px = [200, 200]
    means = {0: {"ch": None, "std": 0.5}, 1: {"ch": 10.0, "std": 0.52}}
    counts = {0: {"ch": 0, "std": 200}, 1: {"ch": 200, "std": 200}}
    r = _run(
        _graph(px, {(0, 1): 10}),
        means,
        counts,
        {"ch": 2.0, "std": 0.45},
        min_defined_criteria=1,
    )
    assert r.n_stands == 1


# ---------- valid-pixel weighting ----------


def test_merged_mean_is_weighted_by_valid_pixels_not_total():
    """The failure this prevents: a region with no canopy data merging into one
    with data must not dilute the result as though it had measured 0 m, and must
    not contribute area to the average at all."""
    px = [100, 300]
    # Region 0 has NO canopy height; region 1 is fully measured at 12 m.
    means = {0: {"ch": None, "std": 0.50}, 1: {"ch": 12.0, "std": 0.52}}
    counts = {0: {"ch": 0, "std": 100}, 1: {"ch": 300, "std": 300}}
    r = _run(
        _graph(px, {(0, 1): 10}),
        means,
        counts,
        {"ch": 2.0, "std": 0.45},
        min_defined_criteria=1,
    )
    assert r.n_stands == 1
    attrs = r.stand_attributes[0]
    # 12.0, not 9.0 (which is what total-pixel weighting with a 0 would give).
    assert attrs["ch"] == pytest.approx(12.0)
    # ...and the stand records that only 3/4 of it has canopy data.
    assert attrs["frac_valid_ch"] == pytest.approx(0.75)


def test_band_below_min_frac_valid_is_reported_as_null():
    px = [300, 100]
    means = {0: {"ch": None, "std": 0.50}, 1: {"ch": 12.0, "std": 0.52}}
    counts = {0: {"ch": 0, "std": 300}, 1: {"ch": 100, "std": 100}}
    r = _run(
        _graph(px, {(0, 1): 10}),
        means,
        counts,
        {"ch": 2.0, "std": 0.45},
        min_defined_criteria=1,
    )
    attrs = r.stand_attributes[0]
    assert attrs["frac_valid_ch"] == pytest.approx(0.25)
    # A mean over a quarter of the stand is not the stand's canopy height.
    assert attrs["ch"] is None
    assert r.diagnostics["stands_with_incomplete_criteria"] == 1


def test_fully_valid_stand_is_not_flagged_incomplete():
    px = [200, 200]
    means, counts = _attrs([{"ch": 10.0, "std": 0.5}, {"ch": 10.2, "std": 0.5}], px)
    r = _run(_graph(px, {(0, 1): 10}), means, counts, {"ch": 2.0, "std": 0.45})
    assert r.diagnostics["stands_with_incomplete_criteria"] == 0
    assert r.stand_attributes[0]["frac_valid_ch"] == pytest.approx(1.0)


# ---------- area bounds ----------


def test_max_area_blocks_a_pass1_merge():
    """Two 6 ha regions are similar but would make a 12 ha stand."""
    px = [600, 600]
    means, counts = _attrs([{"ch": 10.0, "std": 0.5}, {"ch": 10.1, "std": 0.5}], px)
    r = _run(
        _graph(px, {(0, 1): 10}),
        means,
        counts,
        {"ch": 2.0, "std": 0.45},
        max_area_ha=10.0,
    )
    assert r.n_stands == 2
    assert r.diagnostics["pass1_pairs_blocked_by_area_round1"] == 1


def test_no_stand_ever_exceeds_max_area():
    """The invariant the derived component cap rests on. If the merge could
    exceed max_area_ha, reduceConnectedComponents would silently mask the
    largest stands out of every downstream result."""
    px = [200] * 12
    means, counts = _attrs([{"ch": 10.0, "std": 0.5} for _ in range(12)], px)
    edges = {(i, i + 1): 10 for i in range(11)}
    r = _run(_graph(px, edges), means, counts, {"ch": 2.0, "std": 0.45})
    for attrs in r.stand_attributes.values():
        assert attrs["area_ha"] <= 10.0


def test_pass2_fallback_also_respects_max_area():
    """A tiny region wedged between two regions that are already at the cap
    stays undersized rather than pushing one of them over it."""
    px = [995, 10, 995]  # 9.95 ha, 0.10 ha, 9.95 ha -- either merge is 10.05 ha
    means, counts = _attrs(
        [
            {"ch": 10.0, "std": 0.5},
            {"ch": 30.0, "std": 3.0},  # nothing like its neighbours
            {"ch": 10.0, "std": 0.5},
        ],
        px,
    )
    edges = {(0, 1): 5, (1, 2): 5}
    r = _run(_graph(px, edges), means, counts, {"ch": 2.0, "std": 0.45})
    assert r.diagnostics["stands_below_min_area"] == 1
    assert r.diagnostics["orphans_area_blocked"] == 1
    for attrs in r.stand_attributes.values():
        assert attrs["area_ha"] <= 10.0


# ---------- pass 2 ----------


def test_undersized_region_is_absorbed_via_relaxed_tolerances():
    """0.3 ha region differs by 3 m -- over the 2 m gate but under the relaxed
    3.5 m one, so pass 2 places it where pass 1 would not."""
    px = [500, 30]
    means, counts = _attrs([{"ch": 10.0, "std": 0.5}, {"ch": 13.0, "std": 0.6}], px)
    r = _run(_graph(px, {(0, 1): 5}), means, counts, {"ch": 2.0, "std": 0.45})
    assert r.n_stands == 1
    assert r.diagnostics["pass2_merges"] == 1
    assert r.diagnostics["pass2_fallback_merges"] == 0


def test_shared_edge_fallback_picks_the_longest_boundary():
    """No relaxed criterion matches either neighbour, so the tie-break decides.
    Region 2 shares far more boundary, so the fragment joins it."""
    px = [400, 20, 400]
    means, counts = _attrs(
        [
            {"ch": 10.0, "std": 0.5},
            {"ch": 25.0, "std": 3.0},
            {"ch": 11.0, "std": 0.6},
        ],
        px,
    )
    edges = {(0, 1): 1, (1, 2): 20}
    r = _run(_graph(px, edges), means, counts, {"ch": 2.0, "std": 0.45})
    assert r.diagnostics["pass2_fallback_merges"] == 1
    assert r.assignment[1] == r.assignment[2]
    assert r.assignment[1] != r.assignment[0]


def test_isolated_undersized_region_is_reported_not_merged():
    px = [500, 20]
    means, counts = _attrs([{"ch": 10.0, "std": 0.5}, {"ch": 10.0, "std": 0.5}], px)
    r = _run(_graph(px, {}), means, counts, {"ch": 2.0, "std": 0.45})
    assert r.n_stands == 2
    assert r.diagnostics["orphans_isolated"] == 1
    assert r.diagnostics["orphans_area_blocked"] == 0


def test_orphan_causes_are_reported_separately():
    """The two causes call for opposite fixes: area-blocked says max_area_ha is
    too tight, isolated says the region genuinely touches nothing."""
    d = _run(
        _graph([500, 20], {}),
        *_attrs([{"ch": 10.0, "std": 0.5}, {"ch": 10.0, "std": 0.5}], [500, 20]),
        {"ch": 2.0, "std": 0.45},
    ).diagnostics
    assert set(d) >= {
        "orphans_isolated",
        "orphans_area_blocked",
        "orphans_no_attribute_match",
        "stands_below_min_area",
        "area_in_undersized_stands_ha",
    }


def test_area_in_undersized_stands_is_reported():
    px = [500, 20]
    means, counts = _attrs([{"ch": 10.0, "std": 0.5}, {"ch": 10.0, "std": 0.5}], px)
    d = _run(_graph(px, {}), means, counts, {"ch": 2.0, "std": 0.45}).diagnostics
    assert d["area_in_undersized_stands_ha"] == pytest.approx(0.2)


# ---------- determinism ----------


def test_result_is_deterministic_across_runs():
    px = [150] * 8
    rows = [{"ch": 10.0 + 0.3 * i, "std": 0.5 + 0.02 * i} for i in range(8)]
    edges = {(i, i + 1): 10 for i in range(7)}
    centroids = {i: (77.0 + i * 0.001, 28.5 - i * 0.001) for i in range(8)}
    results = [
        _run(
            _graph(px, edges),
            *_attrs(rows, px),
            {"ch": 2.0, "std": 0.45},
            centroids=centroids,
        ).assignment
        for _ in range(5)
    ]
    assert all(a == results[0] for a in results)


def test_stand_ids_are_dense_from_zero():
    px = [150] * 6
    rows = [{"ch": 10.0 + 3.0 * i, "std": 0.5} for i in range(6)]
    r = _run(_graph(px, {(i, i + 1): 5 for i in range(5)}), *_attrs(rows, px),
             {"ch": 2.0, "std": 0.45})
    assert sorted(set(r.assignment)) == list(range(r.n_stands))


# ---------- degenerate inputs ----------


def test_empty_graph_returns_empty_result():
    r = _run(_graph([], {}), {}, {}, {"ch": 2.0})
    assert r.n_stands == 0
    assert r.assignment == []


def test_no_criteria_defined_anywhere_leaves_everything_unmerged():
    """If the criteria bands are all no-data, pass 1 cannot justify anything and
    pass 2 has nothing undersized to place."""
    px = [200, 200]
    means = {0: {"ch": None, "std": None}, 1: {"ch": None, "std": None}}
    counts = {0: {"ch": 0, "std": 0}, 1: {"ch": 0, "std": 0}}
    r = _run(_graph(px, {(0, 1): 10}), means, counts, {"ch": 2.0, "std": 0.45})
    assert r.n_stands == 2
    assert r.diagnostics["n_stands"] == r.diagnostics["n_superpixels"]


def test_reduction_factor_is_reported():
    px = [150] * 4
    rows = [{"ch": 10.0, "std": 0.5} for _ in range(4)]
    r = _run(_graph(px, {(i, i + 1): 10 for i in range(3)}), *_attrs(rows, px),
             {"ch": 2.0, "std": 0.45})
    assert r.diagnostics["reduction_factor"] == pytest.approx(4 / r.n_stands)


# ---------- calibrate_thresholds ----------


def test_calibration_reports_the_joint_rate_not_just_marginals():
    """The point of the helper. Two criteria each admitting most pairs can admit
    far fewer jointly, because the gate is conjunctive -- per-band percentiles do
    not describe it."""
    px = [100] * 4
    # Pair (0,1): ch passes, std fails.  Pair (2,3): std passes, ch fails.
    rows = [
        {"ch": 10.0, "std": 0.5},
        {"ch": 10.5, "std": 2.0},
        {"ch": 10.0, "std": 0.5},
        {"ch": 20.0, "std": 0.55},
    ]
    means, _ = _attrs(rows, px)
    graph = _graph(px, {(0, 1): 5, (2, 3): 5})
    report = calibrate_thresholds(graph, means, {"ch": 2.0, "std": 0.45})
    assert report["per_band"]["ch"]["percentile_of_threshold"] == 50.0
    assert report["per_band"]["std"]["percentile_of_threshold"] == 50.0
    # Each criterion admits half the pairs; together they admit none.
    assert report["joint_admit_rate_pct"] == 0.0


def test_calibration_reports_quantiles_of_the_difference_distribution():
    px = [100] * 5
    rows = [{"ch": float(v)} for v in (10, 11, 13, 16, 20)]
    means, _ = _attrs(rows, px)
    graph = _graph(px, {(i, i + 1): 5 for i in range(4)})
    report = calibrate_thresholds(graph, means, {"ch": 2.0})
    band = report["per_band"]["ch"]
    assert band["n_pairs_defined"] == 4
    assert band["p50"] is not None
    assert band["p25"] <= band["p50"] <= band["p75"] <= band["p90"]


def test_calibration_skips_pairs_with_undefined_bands():
    px = [100, 100]
    means = {0: {"ch": None}, 1: {"ch": 10.0}}
    report = calibrate_thresholds(_graph(px, {(0, 1): 5}), means, {"ch": 2.0})
    assert report["per_band"]["ch"]["n_pairs_defined"] == 0
    assert report["n_pairs_with_any_defined_criterion"] == 0
