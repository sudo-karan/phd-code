"""Non-live tests for the merge's soft ceiling, `merge.pass2_soft_ceiling`.

Register entry spec-merge-pass2-soft-ceiling, Jaskaran's decision D2 of 14 Oct
2026: in the merge's second pass, a region still below `min_area_ha` when its
turn comes may join a neighbour even if the result is over `max_area_ha`, up to
`max_area_ha + min_area_ha` and never further. Off by default.

Four things are pinned here:

  - **the order of choice**, on hand-built graphs small enough that the right
    answer can be read off the numbers in the test. For a region below the
    minimum: (1) a neighbour that passes the relaxed tolerances and keeps the
    result at most `max_area_ha`, the closest; (2) else one that passes them
    with the result over it, the closest; (3) else the neighbour sharing the
    longest edge with the result at most `max_area_ha`; (4) else the one
    sharing the longest edge with the result over it; (5) else no merge;
  - **the cap**: no merge makes a stand larger than `max_area_ha +
    min_area_ha`, so no merged stand is larger than
    `Config.max_component_pixels()`, above which `reduceConnectedComponents`
    deletes a stand without a word. Checked on many seeded random graphs: those
    of tests/test_region_merge_provenance.py, a hundred of them again with a
    tighter ceiling, and graphs built to put many regions below the minimum
    beside stands close to the ceiling (and 9000 more in the slow tier);
  - **what the diagnostics say** about the merges and stands over
    `max_area_ha`;
  - **that off changes nothing.** `data/region_merge_soft_ceiling_off.json`
    holds digests of what the merge produced on every graph in this file,
    under both values of `pass2_skip_at_min_area`, as committed at 363ea6d,
    before the setting existed (the file says how it was written, as
    tests/test_segmentation_off_golden.py does for segmentation). With the
    setting off, today's merge has to reproduce each one: the stands, their
    attributes and provenance, and the diagnostics key for key. Five graphs
    are the exception: review B18 (round 13) changed the merge on them, by
    comparing its area bounds in whole pixels, and they are pinned to the
    digests it gives since (`OFF_DIGESTS_SINCE_B18`). When B18 was made,
    today's merge with the setting off gave on every graph what the merge at
    363ea6d gives with B18's comparison put in it.
"""

from __future__ import annotations

import functools
import hashlib
import json
import math
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from importlib import util as importlib_util
from pathlib import Path
from typing import Any

import pytest
import yaml

from fmu.config import Config, MergeParams
from fmu.utils.adjacency import SuperpixelGraph
from fmu.utils.region_merge import MergeResult, merge_superpixels

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
GOLDEN_PATH = HERE / "data" / "region_merge_soft_ceiling_off.json"
MERGE_SOURCE = "src/fmu/utils/region_merge.py"
BASELINE_YAML = REPO_ROOT / "configs" / "sanjay_van_baseline.yaml"

sys.path.insert(0, str(HERE))
from test_region_merge_provenance import (  # noqa: E402
    CRITERIA,
    DEFAULTS,
    GENERATOR_VERSION,
    GOLDEN_SEEDS,
    PINNED_DIAGNOSTICS,
    Case,
    _Draws,
    _inputs_digest,
    _made_of,
    _sha256,
    _stand_of,
    assert_provenance_invariants,
    random_case,
)

# The diagnostics the merge adds with the setting on, in the order it adds them.
SOFT_CEILING_KEYS = (
    "pass2_relaxed_merges_over_max_area",
    "pass2_fallback_merges_over_max_area",
    "stands_over_max_area",
    "stands_over_max_area_never_merged",
    "excess_over_max_area_total_ha",
    "excess_over_max_area_largest_ha",
    "excess_over_max_area_each_ha",
)


# ---------------------------------------------------------------------------
# The invariants, checked on every result this file makes
# ---------------------------------------------------------------------------


@functools.cache
def _baseline() -> Config:
    return Config.model_validate(yaml.safe_load(BASELINE_YAML.read_text()))


@functools.cache
def _config(min_area_ha: float, max_area_ha: float, scale_m: int, soft: bool) -> Config:
    """The shipped baseline config with these merge bounds and analysis scale.

    The merge block is validated as a config file's would be; the rest is the
    baseline's, copied rather than loaded again, which would cost more than
    the merge it is checked against.
    """
    base = _baseline()
    merge = MergeParams.model_validate(
        {
            **base.merge.model_dump(),
            "min_area_ha": min_area_ha,
            "max_area_ha": max_area_ha,
            "pass2_soft_ceiling": soft,
        }
    )
    export = base.export.model_copy(update={"analysis_scale_m": scale_m})
    return base.model_copy(update={"merge": merge, "export": export})


def assert_soft_ceiling_invariants(
    result: Any, graph: SuperpixelGraph, **settings: Any
) -> None:
    """What has to hold for any result, with the setting on or off.

    Reads only the result, the graph and the settings, never the merge's
    internals. Takes the keyword arguments of `merge_superpixels`.

    First the provenance invariants of tests/test_region_merge_provenance.py.
    That checker files a stand below the minimum as area_blocked when no
    neighbour could take it under the ceiling that applies to it, which it reads
    from the settings: `max_area_ha`, or with the soft ceiling on, `max_area_ha +
    min_area_ha`, in whole pixels as the merge counts them (review B18).

    Then the cap: a stand built by merging (more than one superpixel) is at
    most the ceiling, in pixels and in hectares as reported (6 decimals, so
    compared with the ceiling to 6 decimals: a stand exactly on it, which float
    arithmetic can put a hair to either side of it, is on it), so it is smaller
    than `Config.max_component_pixels()` of a config with these settings. A
    stand of one superpixel is as it came in, and the merge stage checks every
    superpixel against the same cap before it merges.

    Then the diagnostics: with the setting off, exactly the keys they had
    before it existed; with it on, those and seven more, which agree with the
    stands, the counts as ints and the areas as floats.
    """
    on = settings.get("pass2_soft_ceiling", False)
    max_ha, min_ha = settings["max_area_ha"], settings["min_area_ha"]
    ceiling = max_ha + min_ha if on else max_ha
    assert_provenance_invariants(result, graph, **settings)
    if graph.n_regions == 0:
        return

    stand_px = [0] * result.n_stands
    for i, sid in enumerate(result.assignment):
        stand_px[sid] += graph.n_pixels[i]
    ceiling_px = math.ceil(ceiling * 10_000 / (graph.scale_m * graph.scale_m))
    cap_px = _config(min_ha, max_ha, graph.scale_m, on).max_component_pixels()
    assert ceiling_px < cap_px, (ceiling_px, cap_px)
    merged = [sid for sid, p in result.stand_provenance.items() if p["n_superpx"] > 1]
    too_big = [
        (sid, stand_px[sid], result.stand_attributes[sid]["area_ha"])
        for sid in merged
        if stand_px[sid] > ceiling_px
        or result.stand_attributes[sid]["area_ha"] > round(ceiling, 6)
    ]
    assert not too_big, f"stands past the ceiling {ceiling} ha ({ceiling_px} px): {too_big}"

    d = result.diagnostics
    if not on:
        assert list(d) == list(PINNED_DIAGNOSTICS)
        return
    assert list(d) == [*PINNED_DIAGNOSTICS, *SOFT_CEILING_KEYS]
    for key in (
        "pass2_relaxed_merges_over_max_area",
        "pass2_fallback_merges_over_max_area",
        "stands_over_max_area",
        "stands_over_max_area_never_merged",
    ):
        assert type(d[key]) is int, (key, d[key])
    for key in ("excess_over_max_area_total_ha", "excess_over_max_area_largest_ha"):
        assert type(d[key]) is float, (key, d[key])
    assert all(type(e) is float for e in d["excess_over_max_area_each_ha"])
    areas = {sid: a["area_ha"] for sid, a in result.stand_attributes.items()}
    over = {sid for sid, a in areas.items() if a > round(max_ha, 6)}
    excess = sorted((areas[sid] - max_ha for sid in over), reverse=True)
    assert d["stands_over_max_area"] == len(excess)
    assert d["stands_over_max_area_never_merged"] == len(over - set(merged))
    assert d["excess_over_max_area_each_ha"] == [round(e, 4) for e in excess]
    assert d["excess_over_max_area_total_ha"] == round(sum(excess), 4)
    assert d["excess_over_max_area_largest_ha"] == (round(excess[0], 4) if excess else 0.0)
    relaxed_over = d["pass2_relaxed_merges_over_max_area"]
    fallback_over = d["pass2_fallback_merges_over_max_area"]
    assert 0 <= relaxed_over <= d["pass2_merges"] - d["pass2_fallback_merges"]
    assert 0 <= fallback_over <= d["pass2_fallback_merges"]
    # A merged stand ends over max_area_ha only through a merge that went over
    # it, and two stands cannot share one.
    assert len(over.intersection(merged)) <= relaxed_over + fallback_over


def _merge(case: Case, *, soft: bool | None, skip: bool) -> MergeResult:
    """Merge a case under one rule and check the invariants. `soft=None` leaves
    the setting out, as every caller did before it existed."""
    settings = {**case.settings, "pass2_skip_at_min_area": skip}
    if soft is not None:
        settings["pass2_soft_ceiling"] = soft
    result = merge_superpixels(case.graph, case.means, case.valid_counts, **settings)
    assert_soft_ceiling_invariants(result, case.graph, **settings)
    return result


# ---------------------------------------------------------------------------
# Hand-built graphs
# ---------------------------------------------------------------------------
#
# As in tests/test_region_merge_provenance.py: 10 m pixels, so 1 ha = 100 px; the
# minimum is 100 px, `max_area_ha` 1000 px, and so the cap 1100 px. `std` is 0.5
# everywhere, so `ch` alone decides every gate: 2.0 in pass 1, 3.5 relaxed.
# Unless a test says otherwise, no two neighbours are alike enough for pass 1.

# name -> the graph, given as the keyword arguments of `_case`.
HAND_BUILT: dict[str, dict[str, Any]] = {
    # U (9 ha) - r (0.5 ha) - O (9.9 ha). r is 3.0 m from U and 0.5 m from O.
    "relaxed match under the ceiling, a closer one over it": dict(
        n_pixels=[900, 50, 990], edges={(0, 1): 5, (1, 2): 5}, ch=[13.0, 10.0, 10.5]
    ),
    # The same, but U is unlike r (20 m) and shares the longer edge; O is 3.0 m off.
    "relaxed match over the ceiling, a fallback under it": dict(
        n_pixels=[900, 50, 990], edges={(0, 1): 20, (1, 2): 5}, ch=[30.0, 10.0, 13.0]
    ),
    # Neither matches even relaxed; O, over the ceiling, shares the longer edge.
    "fallback under the ceiling, a longer edge over it": dict(
        n_pixels=[900, 50, 990], edges={(0, 1): 2, (1, 2): 20}, ch=[30.0, 10.0, 25.0]
    ),
    # 0.1 ha between two 9.95 ha regions, unlike both: 10.05 ha either way.
    "nothing fits under the ceiling": dict(
        n_pixels=[995, 10, 995], edges={(0, 1): 5, (1, 2): 5}, ch=[10.0, 30.0, 10.0]
    ),
    # A 9.9 ha hub H with two small regions touching it only, unlike it.
    "cap: the second region would pass it": dict(
        n_pixels=[990, 60, 70], edges={(0, 1): 4, (0, 2): 4}, ch=[10.0, 30.0, 50.0]
    ),
    "cap: the second region fits under it": dict(
        n_pixels=[990, 40, 60], edges={(0, 1): 4, (0, 2): 4}, ch=[10.0, 30.0, 50.0]
    ),
    "cap: the second region lands on it": dict(
        n_pixels=[990, 50, 60], edges={(0, 1): 4, (0, 2): 4}, ch=[10.0, 30.0, 50.0]
    ),
    # A - B - C, none alike. A joins B first; then B's turn.
    "grown to the minimum before its turn": dict(
        n_pixels=[60, 70, 950], edges={(0, 1): 2, (1, 2): 2}, ch=[5.0, 25.0, 45.0]
    ),
    "still below the minimum at its turn": dict(
        n_pixels=[20, 70, 950], edges={(0, 1): 2, (1, 2): 2}, ch=[5.0, 25.0, 45.0]
    ),
    # The edge of it: B is exactly 1.0 ha at its turn, or one pixel short.
    "exactly at the minimum at its turn": dict(
        n_pixels=[30, 70, 950], edges={(0, 1): 2, (1, 2): 2}, ch=[5.0, 25.0, 45.0]
    ),
    "one pixel short of the minimum at its turn": dict(
        n_pixels=[29, 70, 950], edges={(0, 1): 2, (1, 2): 2}, ch=[5.0, 25.0, 45.0]
    ),
    # Alike enough for pass 1 (0.5 m), but 10.4 ha together.
    "pass 1 blocked by the ceiling, pass 2 over it": dict(
        n_pixels=[990, 50], edges={(0, 1): 5}, ch=[10.0, 10.5]
    ),
    "pass 1 blocked by the ceiling, nothing undersized": dict(
        n_pixels=[600, 600], edges={(0, 1): 10}, ch=[10.0, 10.1]
    ),
    # H1 (9.9 ha) with a1 (0.5 ha, 3.0 m off); H2 (9.75 ha) with b2 (0.6 ha) and
    # a2 (0.7 ha), both unlike it.
    "two hubs": dict(
        n_pixels=[990, 50, 975, 60, 70],
        edges={(0, 1): 4, (2, 3): 4, (2, 4): 4},
        ch=[10.0, 13.0, 30.0, 50.0, 70.0],
    ),
    # A superpixel that came in at 10.5 ha, over the ceiling, beside a 2 ha one
    # (12.5 ha together, past the cap); and the same superpixel beside a
    # 0.3 ha one (10.8 ha together, under the cap). Unlike each other.
    "a superpixel over the ceiling, alone": dict(
        n_pixels=[1050, 200], edges={(0, 1): 5}, ch=[10.0, 30.0]
    ),
    "a superpixel over the ceiling takes a region": dict(
        n_pixels=[1050, 30], edges={(0, 1): 5}, ch=[10.0, 30.0]
    ),
}


def _case(n_pixels: list[int], edges: dict[tuple[int, int], int], ch: list[float]) -> Case:
    graph = SuperpixelGraph(
        raw_labels=list(range(100, 100 + len(n_pixels))),
        n_pixels=n_pixels,
        edges=edges,
        scale_m=10,
    )
    means: dict[int, dict[str, float | None]] = {
        i: {"ch": v, "std": 0.5} for i, v in enumerate(ch)
    }
    counts = {i: {"ch": px, "std": px} for i, px in enumerate(n_pixels)}
    return Case(graph, means, counts, {"criteria": CRITERIA, **DEFAULTS, "centroids": None})


def _run(name: str, *, soft: bool | None = True, skip: bool = False) -> MergeResult:
    return _merge(_case(**HAND_BUILT[name]), soft=soft, skip=skip)


def _soft(result: MergeResult) -> dict[str, Any]:
    """The seven diagnostics the setting adds."""
    return {k: result.diagnostics[k] for k in SOFT_CEILING_KEYS}


NOTHING_OVER = {
    "pass2_relaxed_merges_over_max_area": 0,
    "pass2_fallback_merges_over_max_area": 0,
    "stands_over_max_area": 0,
    "stands_over_max_area_never_merged": 0,
    "excess_over_max_area_total_ha": 0.0,
    "excess_over_max_area_largest_ha": 0.0,
    "excess_over_max_area_each_ha": [],
}


def test_a_relaxed_match_under_the_ceiling_beats_a_closer_one_over_it():
    """Step 1 before step 2. r passes the relaxed gate with both neighbours, and
    O is the closer (d = (0.5/3.5)^2 against (3.0/3.5)^2), but only U keeps the
    result at most 10 ha. Under the soft ceiling r still joins U: the best
    match with the ceiling ignored (reading A) would have been O."""
    on = _run("relaxed match under the ceiling, a closer one over it")
    assert on.assignment == [0, 0, 1]
    assert _stand_of(on, 1) == _made_of(2, relaxed=1)
    assert _soft(on) == NOTHING_OVER
    off = _run("relaxed match under the ceiling, a closer one over it", soft=False)
    assert off.assignment == on.assignment and off.stand_provenance == on.stand_provenance


def test_a_relaxed_match_over_the_ceiling_beats_a_fallback_under_it():
    """Step 2 before step 3. U would keep the result under 10 ha but no relaxed
    criterion matches it, so the hard ceiling leaves r only the fallback, into
    U. Under the soft ceiling the relaxed match with O comes first: 10.4 ha."""
    on = _run("relaxed match over the ceiling, a fallback under it")
    assert on.assignment == [0, 1, 1]
    assert _stand_of(on, 1) == _made_of(2, relaxed=1)
    assert on.stand_attributes[1]["area_ha"] == 10.4
    assert _soft(on) == {
        **NOTHING_OVER,
        "pass2_relaxed_merges_over_max_area": 1,
        "stands_over_max_area": 1,
        "excess_over_max_area_total_ha": 0.4,
        "excess_over_max_area_largest_ha": 0.4,
        "excess_over_max_area_each_ha": [0.4],
    }
    off = _run("relaxed match over the ceiling, a fallback under it", soft=False)
    assert off.assignment == [0, 0, 1]
    assert _stand_of(off, 1) == _made_of(2, fallback=1)


def test_the_fallback_takes_a_neighbour_under_the_ceiling_before_a_longer_edge_over_it():
    """Step 3 before step 4. No neighbour matches even relaxed. O shares ten
    times U's boundary with r, but joining O would go over 10 ha and joining U
    would not, so r joins U, as it does under the hard ceiling."""
    case = _case(**HAND_BUILT["fallback under the ceiling, a longer edge over it"])
    assert case.graph.shared_edge_m(1, 2) > case.graph.shared_edge_m(1, 0)
    on = _run("fallback under the ceiling, a longer edge over it")
    assert on.assignment == [0, 0, 1]
    assert _stand_of(on, 1) == _made_of(2, fallback=1)
    assert _soft(on) == NOTHING_OVER
    assert _run("fallback under the ceiling, a longer edge over it", soft=False).assignment == (
        on.assignment
    )


def test_with_nothing_under_the_ceiling_the_fallback_goes_over_it():
    """Step 4. Under the hard ceiling r stays below the minimum, area-blocked
    (the case of test_an_area_blocked_undersized_stand). Under the soft one it
    joins the neighbour sharing the longest edge; the two tie, so the lower
    index wins, as in the hard-ceiling fallback: 10.05 ha."""
    off = _run("nothing fits under the ceiling", soft=False)
    assert _stand_of(off, 1) == _made_of(1, below_why="area_blocked")
    on = _run("nothing fits under the ceiling")
    assert on.assignment == [0, 0, 1]
    assert _stand_of(on, 1) == _made_of(2, fallback=1)
    assert on.diagnostics["stands_below_min_area"] == on.diagnostics["orphans_area_blocked"] == 0
    assert _soft(on) == {
        **NOTHING_OVER,
        "pass2_fallback_merges_over_max_area": 1,
        "stands_over_max_area": 1,
        "excess_over_max_area_total_ha": 0.05,
        "excess_over_max_area_largest_ha": 0.05,
        "excess_over_max_area_each_ha": [0.05],
    }


def test_a_neighbour_already_over_the_ceiling_takes_no_region_that_would_pass_the_cap():
    """The cap binds on the result of each merge. The 0.6 ha region joins H
    first (10.5 ha, over 10 ha). The 0.7 ha one would make 11.2 ha, past the
    11 ha cap, so it stays below the minimum, filed as area_blocked: no
    neighbour could take it under 11 ha. Under the hard ceiling both stay."""
    on = _run("cap: the second region would pass it")
    assert on.assignment == [0, 0, 1]
    assert on.stand_attributes[0]["area_ha"] == 10.5
    assert _stand_of(on, 2) == _made_of(1, below_why="area_blocked")
    assert on.diagnostics["orphans_area_blocked"] == 1
    assert _soft(on)["excess_over_max_area_each_ha"] == [0.5]
    off = _run("cap: the second region would pass it", soft=False)
    assert off.assignment == [0, 1, 2]
    assert off.diagnostics["orphans_area_blocked"] == 2


def test_a_neighbour_already_over_the_ceiling_takes_a_region_that_stays_under_the_cap():
    """The 0.4 ha region takes H to 10.3 ha; the 0.6 ha one then makes 10.9 ha,
    under the cap, and joins too. Both merges went over 10 ha."""
    on = _run("cap: the second region fits under it")
    assert on.stand_provenance == {0: _made_of(3, fallback=2)}
    assert _soft(on) == {
        **NOTHING_OVER,
        "pass2_fallback_merges_over_max_area": 2,
        "stands_over_max_area": 1,
        "excess_over_max_area_total_ha": 0.9,
        "excess_over_max_area_largest_ha": 0.9,
        "excess_over_max_area_each_ha": [0.9],
    }


def test_a_merge_may_end_exactly_on_the_cap():
    """At most `max_area_ha + min_area_ha`, not under it: 9.9 + 0.5 + 0.6 is
    11.0 ha, and that is 1100 px, the cap in pixels, under the derived
    `max_component_pixels()` of 1320."""
    on = _run("cap: the second region lands on it")
    assert on.stand_provenance == {0: _made_of(3, fallback=2)}
    assert on.stand_attributes[0]["n_pixels"] == 1100
    assert on.stand_attributes[0]["area_ha"] == 11.0
    assert _config(1.0, 10.0, 10, True).max_component_pixels() == 1320
    assert _soft(on)["excess_over_max_area_each_ha"] == [1.0]


@pytest.mark.parametrize("skip", [False, True])
def test_a_region_that_reached_the_minimum_before_its_turn_keeps_the_hard_ceiling(skip):
    """A (0.6 ha) joins B (0.7 ha) first, so B is 1.3 ha when its turn comes.
    "Only regions below the minimum" is read at that moment, not when the sweep
    listed B: with pass2_skip_at_min_area false B takes its turn under the hard
    ceiling, and C (9.5 ha) cannot take it under 10 ha; with it true B is
    skipped. Either way the result is the hard ceiling's. Read at the listing,
    B would have joined C, at 10.8 ha."""
    on = _run("grown to the minimum before its turn", skip=skip)
    off = _run("grown to the minimum before its turn", soft=False, skip=skip)
    assert on.assignment == off.assignment == [0, 0, 1]
    assert on.stand_provenance == off.stand_provenance
    assert _soft(on) == NOTHING_OVER


def test_a_region_still_below_the_minimum_at_its_turn_gets_the_soft_ceiling():
    """The same chain with A at 0.2 ha: B is 0.9 ha at its turn, still below the
    minimum, so it may join C over the ceiling (10.4 ha). Under the hard ceiling
    it stays, area-blocked."""
    on = _run("still below the minimum at its turn")
    assert on.stand_provenance == {0: _made_of(3, fallback=2)}
    assert _soft(on)["pass2_fallback_merges_over_max_area"] == 1
    assert _soft(on)["excess_over_max_area_each_ha"] == [0.4]
    off = _run("still below the minimum at its turn", soft=False)
    assert off.assignment == [0, 0, 1]
    assert _stand_of(off, 1) == _made_of(2, fallback=1, below_why="area_blocked")


@pytest.mark.parametrize("skip", [False, True])
def test_a_region_exactly_at_the_minimum_at_its_turn_keeps_the_hard_ceiling(skip):
    """The edge of "below the minimum". A (0.3 ha) joins B (0.7 ha) first, so B
    is exactly 1.0 ha (100 px) when its turn comes: at the minimum, not below
    it, so it keeps the hard ceiling and C (9.5 ha) cannot take it under 10 ha
    (with pass2_skip_at_min_area true it is skipped). With one pixel less in A,
    B is 0.99 ha at its turn, below the minimum, and joins C at 10.49 ha."""
    at = _run("exactly at the minimum at its turn", skip=skip)
    assert at.assignment == [0, 0, 1]
    assert [a["area_ha"] for a in at.stand_attributes.values()] == [1.0, 9.5]
    assert _soft(at) == NOTHING_OVER
    off = _run("exactly at the minimum at its turn", soft=False, skip=skip)
    assert off.assignment == at.assignment and off.stand_provenance == at.stand_provenance

    short = _run("one pixel short of the minimum at its turn", skip=skip)
    assert short.stand_provenance == {0: _made_of(3, fallback=2)}
    assert short.stand_attributes[0]["area_ha"] == 10.49
    assert _soft(short)["pass2_fallback_merges_over_max_area"] == 1


def test_pass_1_keeps_the_hard_ceiling():
    """Two regions alike enough for pass 1 whose areas add up to over 10 ha are
    not merged by it, setting on or off. When one of them is below the minimum,
    pass 2 makes the merge, and it is counted as a relaxed second-pass merge,
    not a first-pass one."""
    for name in (
        "pass 1 blocked by the ceiling, nothing undersized",
        "pass 1 blocked by the ceiling, pass 2 over it",
    ):
        on, off = _run(name), _run(name, soft=False)
        for key in PINNED_DIAGNOSTICS:
            if key.startswith("pass1_"):
                assert on.diagnostics[key] == off.diagnostics[key], (name, key)
        assert on.diagnostics["pass1_merges"] == 0
        assert on.diagnostics["pass1_pairs_blocked_by_area_round1"] == 1
    big = _run("pass 1 blocked by the ceiling, nothing undersized")
    assert big.n_stands == 2 and _soft(big) == NOTHING_OVER
    small = _run("pass 1 blocked by the ceiling, pass 2 over it")
    assert small.stand_provenance == {0: _made_of(2, relaxed=1)}
    assert _soft(small)["pass2_relaxed_merges_over_max_area"] == 1


def test_the_diagnostics_on_a_known_case():
    """H1 takes a1 by a relaxed match (10.4 ha). H2 takes b2 by the fallback
    (10.35 ha), and a2 would then make 11.05 ha, past the cap, so it stays
    below the minimum. Two merges over 10 ha, one of each kind; two stands over
    it, by 0.4 and 0.35 ha, both made by merging. The seven keys come after the
    sixteen that every run has, in a fixed order; with the setting off none of
    them is there."""
    on = _run("two hubs")
    assert on.assignment == [0, 0, 1, 1, 2]
    assert list(on.diagnostics) == [*PINNED_DIAGNOSTICS, *SOFT_CEILING_KEYS]
    assert {k: on.diagnostics[k] for k in ("pass2_merges", "pass2_fallback_merges")} == {
        "pass2_merges": 2,
        "pass2_fallback_merges": 1,
    }
    assert _soft(on) == {
        "pass2_relaxed_merges_over_max_area": 1,
        "pass2_fallback_merges_over_max_area": 1,
        "stands_over_max_area": 2,
        "stands_over_max_area_never_merged": 0,
        "excess_over_max_area_total_ha": 0.75,
        "excess_over_max_area_largest_ha": 0.4,
        "excess_over_max_area_each_ha": [0.4, 0.35],
    }
    assert on.diagnostics["orphans_area_blocked"] == on.diagnostics["stands_below_min_area"] == 1
    assert _stand_of(on, 4) == _made_of(1, below_why="area_blocked")
    off = _run("two hubs", soft=False)
    assert list(off.diagnostics) == list(PINNED_DIAGNOSTICS)
    assert off.diagnostics["orphans_area_blocked"] == 3 and off.diagnostics["pass2_merges"] == 0


def test_a_superpixel_that_came_in_over_the_ceiling_is_counted_as_never_merged():
    """A stand over max_area_ha that the setting did not make: a 10.5 ha
    superpixel that nothing joins, as with the setting off. It is counted among
    the stands over max_area_ha, as Jaskaran asked, and again among those that
    never merged, so the stage does not put it down to the setting. Once it
    takes a 0.3 ha region (10.8 ha, under the 11 ha cap) it is a merged stand
    like any other."""
    alone = _run("a superpixel over the ceiling, alone")
    assert alone.assignment == _run("a superpixel over the ceiling, alone", soft=False).assignment
    assert alone.n_stands == 2 and alone.diagnostics["pass2_merges"] == 0
    assert _soft(alone) == {
        **NOTHING_OVER,
        "stands_over_max_area": 1,
        "stands_over_max_area_never_merged": 1,
        "excess_over_max_area_total_ha": 0.5,
        "excess_over_max_area_largest_ha": 0.5,
        "excess_over_max_area_each_ha": [0.5],
    }

    takes = _run("a superpixel over the ceiling takes a region")
    assert takes.stand_provenance == {0: _made_of(2, fallback=1)}
    assert takes.stand_attributes[0]["area_ha"] == 10.8
    assert _soft(takes) == {
        **NOTHING_OVER,
        "pass2_fallback_merges_over_max_area": 1,
        "stands_over_max_area": 1,
        "excess_over_max_area_total_ha": 0.8,
        "excess_over_max_area_largest_ha": 0.8,
        "excess_over_max_area_each_ha": [0.8],
    }
    off = _run("a superpixel over the ceiling takes a region", soft=False)
    assert _stand_of(off, 1) == _made_of(1, below_why="area_blocked")


@pytest.mark.parametrize("name", sorted(HAND_BUILT))
def test_off_is_the_same_whether_the_setting_is_left_out_or_written_out(name):
    for skip in (False, True):
        left_out = _run(name, soft=None, skip=skip)
        written_out = _run(name, soft=False, skip=skip)
        assert _full_outputs(left_out) == _full_outputs(written_out), (name, skip)


# ---------------------------------------------------------------------------
# Seeded random graphs
# ---------------------------------------------------------------------------

# The 200 seeds whose merge tests/test_region_merge_provenance.py pins, and 100
# more. `test_the_cap_holds_on_thousands_more_graphs` (slow tier) takes the
# seeds after these.
RANDOM_SEEDS = range(300)
TIGHT_SEEDS = range(100)
CROWDED_SEEDS = range(100)
assert set(GOLDEN_SEEDS) <= set(RANDOM_SEEDS)

# Raise this whenever `crowded_case` changes what it builds for a seed: the
# committed digests are of these exact graphs.
CROWDED_VERSION = 1


def tight_case(seed: int) -> Case:
    """random_case(seed) with `max_area_ha` brought down to just above
    `min_area_ha`, so that pass 1 leaves many stands close to the ceiling and
    pass 2 many regions below the minimum beside them."""
    case = random_case(seed)
    factor = (1.05, 1.25, 1.5)[seed % 3]
    settings = {**case.settings, "max_area_ha": case.settings["min_area_ha"] * factor}
    return Case(case.graph, case.means, case.valid_counts, settings)


def crowded_case(seed: int) -> Case:
    """Stands close to the ceiling with many regions below the minimum beside them.

    Blocks on a grid, each a superpixel at most the minimum short of the
    ceiling (one in five is about half of it, so that pass 1 has pairs to
    merge), and specks smaller than the minimum, each touching one to three
    blocks and sometimes another speck; one in twenty touches nothing. Under
    the hard ceiling most specks stay below the minimum, area-blocked; under
    the soft one they join until the block beside them reaches the cap. The
    bounds sit a fraction of a pixel off a whole number of pixels, so that no
    sum of areas lands on one and float rounding decides no merge.
    """
    rng = _Draws(seed)
    cols, rows = 2 + rng.below(4), 2 + rng.below(3)
    n_blocks = cols * rows
    max_px = 20 + rng.below(981)  # the ceiling, in whole pixels
    min_px = 2 + rng.below(max_px // 2 - 1)  # 2 to max_px // 2
    n_pixels: list[int] = []
    for _ in range(n_blocks):
        if rng.chance(0.2):
            n_pixels.append(min_px + rng.below(max_px // 2 - min_px + 1))
        else:
            n_pixels.append(max_px - rng.below(min_px))

    # ---- edges: blocks on the grid, specks beside them
    side = max(2, math.isqrt(max_px))
    edges: dict[tuple[int, int], int] = {}
    on_grid: list[list[int]] = [[] for _ in range(n_blocks)]
    for b in range(n_blocks):
        right = [b + 1] if b % cols + 1 < cols else []
        down = [b + cols] if b // cols + 1 < rows else []
        for nb in right + down:
            edges[(b, nb)] = 1 + rng.below(side)
            on_grid[b].append(nb)
            on_grid[nb].append(b)
    home = list(range(n_blocks))  # the block each region sits on or beside
    for _ in range(n_blocks + rng.below(3 * n_blocks + 1)):
        i = len(n_pixels)
        n_pixels.append(1 + rng.below(min_px - 1))
        block = rng.below(n_blocks)
        home.append(block)
        if rng.chance(0.05):
            continue  # touches nothing
        edges[(block, i)] = 1 + rng.below(4)
        others = list(on_grid[block])
        for _ in range(2):
            if others and rng.chance(0.4):
                edges[(others.pop(rng.below(len(others))), i)] = 1 + rng.below(4)
        if i > n_blocks and rng.chance(0.3):
            edges[(n_blocks + rng.below(i - n_blocks), i)] = 1 + rng.below(2)
    n = len(n_pixels)
    scale_m = rng.pick((10, 10, 20, 30))
    graph = SuperpixelGraph(
        raw_labels=[5000 + 7 * i for i in range(n)],
        n_pixels=n_pixels,
        edges=edges,
        scale_m=scale_m,
    )

    # ---- attributes: half the specks are close to their block, give or take
    # the relaxed tolerances; the rest are anything
    level = [(rng.between(5.0, 30.0), rng.between(0.3, 1.5)) for _ in range(n_blocks)]
    means: dict[int, dict[str, float | None]] = {}
    counts: dict[int, dict[str, int]] = {}
    centroids: dict[int, tuple[float, float]] = {}
    for i, px in enumerate(n_pixels):
        if i < n_blocks:
            ch, sd = level[i]
        elif rng.chance(0.5):
            ch = level[home[i]][0] + rng.between(-4.0, 4.0)
            sd = level[home[i]][1] + rng.between(-0.6, 0.6)
        else:
            ch, sd = rng.between(5.0, 30.0), rng.between(0.3, 1.5)
        means[i] = {"ch": ch, "std": sd}
        counts[i] = {"ch": px, "std": px}
        jitter = 0.0 if i < n_blocks else 0.5
        x = home[i] % cols + 0.5 + jitter * (rng.unit() - 0.5)
        y = home[i] // cols + 0.5 + jitter * (rng.unit() - 0.5)
        centroids[i] = (77.0 + x * 0.001, 28.5 - y * 0.001)

    px_to_ha = scale_m * scale_m / 10_000.0
    tolerance_scale = rng.pick((0.5, 1.0, 1.0, 2.0))
    settings: dict[str, Any] = dict(
        criteria={"ch": 2.0 * tolerance_scale, "std": 0.45 * tolerance_scale},
        relax_factor=rng.pick((1.25, 1.75, 1.75, 2.5)),
        min_area_ha=(min_px - 0.25) * px_to_ha,
        max_area_ha=(max_px + 0.5) * px_to_ha,
        min_defined_criteria=1 + rng.below(2),
        min_frac_valid=0.5,
        max_pass2_iterations=rng.pick((1, 2, 60, 60, 60)),
        centroids=centroids if not rng.chance(0.1) else None,
    )
    return Case(graph, means, counts, settings)


def all_cases() -> list[tuple[str, Case]]:
    """Every graph this file merges, by name, in a fixed order."""
    cases = [(name, _case(**spec)) for name, spec in HAND_BUILT.items()]
    cases += [(f"random {seed}", random_case(seed)) for seed in RANDOM_SEEDS]
    cases += [(f"tight {seed}", tight_case(seed)) for seed in TIGHT_SEEDS]
    cases += [(f"crowded {seed}", crowded_case(seed)) for seed in CROWDED_SEEDS]
    return cases


@dataclass
class Run:
    """One graph merged under each rule: `off` and `on` hold the results with
    pass2_skip_at_min_area false and true, in that order."""

    name: str
    case: Case
    off: list[MergeResult]
    on: list[MergeResult]


@pytest.fixture(scope="module")
def runs() -> list[Run]:
    """Every graph, merged with the setting off and on, under both values of
    pass2_skip_at_min_area. `_merge` checks the invariants on each result."""
    out = []
    for name, case in all_cases():
        off = [_merge(case, soft=False, skip=skip) for skip in (False, True)]
        on = [_merge(case, soft=True, skip=skip) for skip in (False, True)]
        out.append(Run(name, case, off, on))
    return out


def _touching(result: MergeResult, graph: SuperpixelGraph) -> list[set[int]]:
    near: list[set[int]] = [set() for _ in range(result.n_stands)]
    for i, j in graph.edges:
        a, b = result.assignment[i], result.assignment[j]
        if a != b:
            near[a].add(b)
            near[b].add(a)
    return near


def test_every_result_keeps_the_invariants_and_the_cap(runs):
    """Done by the fixture, on every result: this states it, and that pass 1
    does the same with the setting on as off, whatever pass 2 then does."""
    assert len(runs) == (
        len(HAND_BUILT) + len(RANDOM_SEEDS) + len(TIGHT_SEEDS) + len(CROWDED_SEEDS)
    )
    for run in runs:
        for off, on in zip(run.off, run.on, strict=True):
            for key in PINNED_DIAGNOSTICS:
                if key.startswith("pass1_"):
                    assert on.diagnostics[key] == off.diagnostics[key], (run.name, key)


def test_the_soft_ceiling_binds_on_the_seeded_graphs(runs):
    """A cap that never binds proves nothing. On the seeded graphs the setting
    has to move stands, make merges over `max_area_ha` of both kinds, leave
    stands over it, and leave a region below the minimum, area-blocked, beside
    a stand already over `max_area_ha`: the case the cap exists for."""
    seen = {
        "stands moved": 0,
        "a relaxed merge over max_area_ha": 0,
        "a fallback merge over max_area_ha": 0,
        "a stand over max_area_ha": 0,
        "area-blocked beside a stand already over max_area_ha": 0,
    }
    for run in runs:
        if run.name in HAND_BUILT:
            continue
        max_ha = round(run.case.settings["max_area_ha"], 6)  # as the merge reports it
        for off, on in zip(run.off, run.on, strict=True):
            d = on.diagnostics
            seen["stands moved"] += on.assignment != off.assignment
            seen["a relaxed merge over max_area_ha"] += d["pass2_relaxed_merges_over_max_area"] > 0
            seen["a fallback merge over max_area_ha"] += d["pass2_fallback_merges_over_max_area"] > 0
            seen["a stand over max_area_ha"] += d["stands_over_max_area"] > 0
            near = _touching(on, run.case.graph)
            seen["area-blocked beside a stand already over max_area_ha"] += any(
                p["below_why"] == "area_blocked"
                and any(on.stand_attributes[nb]["area_ha"] > max_ha for nb in near[sid])
                for sid, p in on.stand_provenance.items()
            )
    too_rare = {name: count for name, count in seen.items() if count < 20}
    assert not too_rare, f"reached by fewer than 20 of the merges: {too_rare} (all: {seen})"


@pytest.mark.slow
def test_the_cap_holds_on_thousands_more_graphs():
    """The invariants and the cap on 9000 graphs the fast tier does not merge,
    under all four rules (about a minute and a half):

        pytest -m slow tests/test_region_merge_soft_ceiling.py
    """
    for seed in range(RANDOM_SEEDS.stop, RANDOM_SEEDS.stop + 3000):
        cases = [random_case(seed), tight_case(seed), crowded_case(seed)]
        for case in cases:
            for soft in (False, True):
                for skip in (False, True):
                    _merge(case, soft=soft, skip=skip)


# ---------------------------------------------------------------------------
# Off changes nothing: digests from before the setting existed
# ---------------------------------------------------------------------------


def _full_outputs(result: Any) -> dict[str, Any]:
    """Everything the merge returns, the order of the diagnostics keys included."""
    return {
        "assignment": result.assignment,
        "n_stands": result.n_stands,
        "stand_attributes": [[sid, a] for sid, a in sorted(result.stand_attributes.items())],
        "diagnostics": result.diagnostics,
        "diagnostics_keys": list(result.diagnostics),
        "stand_provenance": [[sid, p] for sid, p in sorted(result.stand_provenance.items())],
    }


def off_digest(results: list[Any]) -> str:
    """One digest over a graph's results under both values of
    pass2_skip_at_min_area. Sixteen hex digits: this tells a change apart, it
    is not a signature."""
    return _sha256([_full_outputs(r) for r in results])[:16]


# The graphs on which review B18 (round 13: the merge's area bounds compared in whole
# pixels, not on a float sum of two areas) changed what the merge does with the
# setting off, and the digest each gives since. On no other graph did it change
# anything: when B18 was made, today's merge with the setting off gave on every graph
# what the merge at 363ea6d gives with only that comparison changed.
OFF_DIGESTS_SINCE_B18: dict[str, str] = {
    "random 3": "496dfacd5dd6a773",
    "random 53": "5b1179874670fff3",
    "random 98": "8c866d021b869719",
    "tight 53": "10ad930826bae6c7",
    "tight 98": "fb3e2f9386e8fc50",
}


@pytest.fixture(scope="module")
def off_golden() -> dict[str, Any]:
    return json.loads(GOLDEN_PATH.read_text())


def test_the_golden_is_of_the_graphs_in_this_file(off_golden, runs):
    """If this fails, the comparison below is meaningless rather than failed:
    the merge is being run on other graphs. A generator was changed (raise its
    version and regenerate the fixture) or this platform does not reproduce
    the draws."""
    assert off_golden["generator_versions"] == {
        "random_case": GENERATOR_VERSION,
        "crowded_case": CROWDED_VERSION,
    }
    assert list(off_golden["digests"]) == [run.name for run in runs]
    assert _inputs_digest([run.case for run in runs]) == off_golden["inputs_sha256"]


def test_with_the_setting_off_the_merge_is_the_one_before_the_setting(off_golden, runs):
    """Off, the merge must give on every graph, under both values of
    pass2_skip_at_min_area, exactly what it gave at the commit named in the
    fixture: the stands, their attributes and provenance, and the diagnostics,
    key for key and in order. On the five graphs of `OFF_DIGESTS_SINCE_B18` it
    must give what is pinned there."""
    assert all(off_golden["digests"][n] != d for n, d in OFF_DIGESTS_SINCE_B18.items())
    expected = {**off_golden["digests"], **OFF_DIGESTS_SINCE_B18}
    changed = [run.name for run in runs if off_digest(run.off) != expected[run.name]]
    assert not changed, (
        f"with merge.pass2_soft_ceiling off, merge_superpixels no longer gives what it gave "
        f"at {off_golden['made_from']['commit'][:7]} (or since review B18, where pinned) on "
        f"{len(changed)} of {len(runs)} graphs ({changed[:10]}). Off has to change nothing; "
        f"if this was meant, say so in the commit and pin the new digests, as "
        f"OFF_DIGESTS_SINCE_B18 does."
    )


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True, check=True
    ).stdout


def write_off_golden(commit: str) -> None:
    """Write the fixture from the merge as committed at `commit`.

    The file is read with `git show`, so neither the working tree nor the index
    is touched and the code that runs is the committed one whatever the checkout
    holds. That code has no `pass2_soft_ceiling`, so it is not passed. The
    fixture holds no date, machine or Python version, so running this again
    from the same commit reproduces it byte for byte.
    """
    source = _git("show", f"{commit}:{MERGE_SOURCE}")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "region_merge_at_commit.py"
        path.write_text(source)
        spec = importlib_util.spec_from_file_location(path.stem, path)
        assert spec is not None and spec.loader is not None
        module = importlib_util.module_from_spec(spec)
        sys.modules[spec.name] = module  # dataclasses look their module up by name
        spec.loader.exec_module(module)
    merge: Callable[..., Any] = module.merge_superpixels
    cases = all_cases()
    full_commit = _git("rev-parse", f"{commit}^{{commit}}").strip()
    fixture = {
        "what": (
            f"Digests of what merge_superpixels produced for the {len(cases)} graphs of "
            "tests/test_region_merge_soft_ceiling.py, under pass2_skip_at_min_area false "
            "and true, BEFORE merge.pass2_soft_ceiling was added to it. That test asserts "
            "that the merge with the setting off still produces exactly this."
        ),
        "made_from": {
            "commit": full_commit,
            "file": MERGE_SOURCE,
            "git_blob": _git("rev-parse", f"{commit}:{MERGE_SOURCE}").strip(),
            "file_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        },
        "how": (
            f"python tests/test_region_merge_soft_ceiling.py {full_commit}  (from the "
            "repo root). It reads the file above with `git show`, loads merge_superpixels "
            "from that text, runs it on every graph of all_cases() and writes this file. "
            "The working tree's region_merge.py is not used."
        ),
        "digest": (
            "first 16 hex digits of the sha256 of JSON (sorted keys, no spaces) of the two "
            "results, pass2_skip_at_min_area false then true, each {assignment, n_stands, "
            "stand_attributes, diagnostics, diagnostics_keys, stand_provenance}: everything "
            "the merge returns, with the order of the diagnostics keys"
        ),
        "generator_versions": {"random_case": GENERATOR_VERSION, "crowded_case": CROWDED_VERSION},
        "inputs_sha256": _inputs_digest([case for _, case in cases]),
        "digests": {
            name: off_digest(
                [
                    merge(case.graph, case.means, case.valid_counts, **case.settings,
                          pass2_skip_at_min_area=skip)
                    for skip in (False, True)
                ]
            )
            for name, case in cases
        },
    }
    GOLDEN_PATH.parent.mkdir(exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(fixture, indent=1) + "\n")
    print(f"wrote {GOLDEN_PATH} ({GOLDEN_PATH.stat().st_size} bytes) from {full_commit}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(
            "usage: python tests/test_region_merge_soft_ceiling.py <commit>\n"
            "  <commit> is the commit whose merge the digests should be made from."
        )
    write_off_golden(sys.argv[1])
