"""Non-live tests for the merge's per-stand provenance, and for the claim that
recording it moved no stand.

`merge_superpixels` reports, for every stand, how many superpixels it is made
of, how many of the merges inside it were pass-1, relaxed pass-2 and shared-edge
fallback merges, and whether and why it ended below `min_area_ha`. Before this,
only the totals over the whole run were kept.

Three things are pinned here:

  - **what the provenance says**, on hand-built graphs small enough that the
    right answer can be read off the numbers in the test;
  - **that it agrees with what the merge already reported.** Every graph this
    file builds goes through `assert_provenance_invariants`;
  - **that adding it changed no merge decision.** `data/region_merge_golden.json`
    holds digests of what the merge produced for 200 seeded random graphs
    *before* provenance was added, made by the committed version of the code
    (the file says which commit, and how). Today's code has to reproduce every
    one of them but 22. Review B18 (round 13) changed the merge on three, by
    comparing its area bounds in whole pixels, and they are pinned to the
    digests it gave (`DIGESTS_SINCE_B18`). When B18 was made, today's merge gave
    on all 200 graphs what the fixture's commit gives with B18's comparison put
    in it, so provenance still moved no stand. Round 14 changed it on 20 (seed
    98 among them again), by breaking a tie in the shared-edge fallback by
    centroid, not by SNIC label order (round 13 question 24), and they are pinned
    to the digests it gives since (`DIGESTS_SINCE_Q24`). When that was made,
    today's merge gave on all 200 graphs what the fixture's commit gives with
    B18's comparison and that tie rule put in it.

The random graphs are built the way a run builds them: a pixel grid with
non-habitat masked out is partitioned into superpixels, and adjacency, shared
boundary lengths, pixel counts and centroids are read off the pixels.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from importlib import util as importlib_util
from pathlib import Path
from typing import Any

import pytest

from fmu.utils.adjacency import SuperpixelGraph
from fmu.utils.region_merge import (
    BELOW_WHY_TOTALS,
    PROVENANCE_FIELDS,
    MergeResult,
    merge_superpixels,
)

REPO_ROOT = Path(__file__).parent.parent
GOLDEN_PATH = Path(__file__).parent / "data" / "region_merge_golden.json"
MERGE_SOURCE = "src/fmu/utils/region_merge.py"


# ---------------------------------------------------------------------------
# The invariants, checked on every graph this file builds
# ---------------------------------------------------------------------------


def assert_provenance_invariants(
    result: Any,
    graph: SuperpixelGraph,
    *,
    min_area_ha: float,
    max_area_ha: float,
    max_pass2_iterations: int,
    pass2_soft_ceiling: bool = False,
    **_other_settings: Any,
) -> None:
    """What has to hold between the provenance and what the merge reports.

    Reads only the result, the graph and the settings, never the merge's
    internals. Takes the keyword arguments of `merge_superpixels`.
    """
    d = result.diagnostics
    prov = result.stand_provenance
    if graph.n_regions == 0:
        assert prov == {}
        return

    # One entry per stand, the documented fields in the documented order.
    assert list(prov) == list(range(result.n_stands)) == list(result.stand_attributes)
    for p in prov.values():
        assert tuple(p) == PROVENANCE_FIELDS
        for name in ("n_superpx", "n_pass1", "n_relaxed", "n_fallback", "below_min"):
            assert type(p[name]) is int and p[name] >= 0, (name, p)
        assert (p["below_min"], p["below_why"] != "") in ((0, False), (1, True))

    # A stand of m superpixels contains exactly m - 1 merges.
    members = [0] * result.n_stands
    stand_px = [0] * result.n_stands
    for i, sid in enumerate(result.assignment):
        members[sid] += 1
        stand_px[sid] += graph.n_pixels[i]
    for sid, p in prov.items():
        assert p["n_superpx"] == members[sid]
        assert p["n_pass1"] + p["n_relaxed"] + p["n_fallback"] == p["n_superpx"] - 1

    # The per-stand counts sum to the totals the merge already reported.
    def total(name: str) -> int:
        return sum(p[name] for p in prov.values())

    assert total("n_superpx") == d["n_superpixels"]
    assert total("n_pass1") == d["pass1_merges"]
    assert total("n_relaxed") == d["pass2_merges"] - d["pass2_fallback_merges"]
    assert total("n_fallback") == d["pass2_fallback_merges"]
    assert total("below_min") == d["stands_below_min_area"]
    for why, total_key in BELOW_WHY_TOTALS.items():
        assert sum(1 for p in prov.values() if p["below_why"] == why) == d[total_key]

    # below_why, worked out again from the finished stands alone. A neighbour
    # could take a stand below the minimum if their pixels together are within
    # the ceiling, counted in whole pixels as the merge counts it (review B18):
    # max_area_ha, or with pass2_soft_ceiling on, max_area_ha + min_area_ha,
    # each as written, against the pixels' area in square metres.
    px_to_ha = graph.scale_m * graph.scale_m / 10_000.0
    ceiling_m2 = Fraction(str(max_area_ha)) * 10_000
    if pass2_soft_ceiling:
        ceiling_m2 += Fraction(str(min_area_ha)) * 10_000
    touching: list[set[int]] = [set() for _ in range(result.n_stands)]
    for i, j in graph.edges:
        a, b = result.assignment[i], result.assignment[j]
        if a != b:
            touching[a].add(b)
            touching[b].add(a)
    for sid, p in prov.items():
        area = stand_px[sid] * px_to_ha
        if area >= min_area_ha:
            expected = ""
        elif not touching[sid]:
            expected = "isolated"
        elif not any(
            (stand_px[sid] + stand_px[nb]) * graph.scale_m**2 <= ceiling_m2
            for nb in touching[sid]
        ):
            expected = "area_blocked"
        else:
            expected = "iteration_cap"
        assert p["below_why"] == expected, (sid, p, expected)
    if d["orphans_no_attribute_match"]:
        # The third cause is only reachable when pass 2 used up its sweeps.
        assert d["pass2_iterations"] == max_pass2_iterations


# ---------------------------------------------------------------------------
# Hand-built graphs
# ---------------------------------------------------------------------------

# 1 ha at 10 m = 100 px. Areas below are quoted in pixels for that reason.
DEFAULTS: dict[str, Any] = dict(
    relax_factor=1.75,
    min_area_ha=1.0,
    max_area_ha=10.0,
    min_defined_criteria=2,
    min_frac_valid=0.5,
    max_pass2_iterations=60,
)
# Relaxed in pass 2 to 3.5 and 0.7875.
CRITERIA = {"ch": 2.0, "std": 0.45}


def _run(
    n_pixels: list[int],
    edges: dict[tuple[int, int], int],
    ch: list[float],
    **over: Any,
) -> MergeResult:
    """Merge a hand-built graph and check the invariants on it.

    `ch` is each region's canopy height; `std` is 0.5 everywhere, so `ch` alone
    decides every gate in these cases.
    """
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
    kwargs = {"criteria": CRITERIA, **DEFAULTS, **over}
    result = merge_superpixels(graph, means, counts, **kwargs)
    assert_provenance_invariants(result, graph, **kwargs)
    return result


def _made_of(
    n_superpx: int,
    *,
    pass1: int = 0,
    relaxed: int = 0,
    fallback: int = 0,
    below_why: str = "",
) -> dict[str, Any]:
    """The provenance a stand is expected to carry."""
    return {
        "n_superpx": n_superpx,
        "n_pass1": pass1,
        "n_relaxed": relaxed,
        "n_fallback": fallback,
        "below_min": int(bool(below_why)),
        "below_why": below_why,
    }


def _stand_of(result: MergeResult, superpixel: int) -> dict[str, Any]:
    return result.stand_provenance[result.assignment[superpixel]]


def test_a_stand_built_only_by_first_pass_merges():
    """Six 1.5 ha regions in a row, close enough in height to merge under the
    tolerances as configured. Nothing is undersized, so pass 2 does not act and
    all five merges are pass-1 merges."""
    r = _run(
        [150] * 6,
        {(i, i + 1): 10 for i in range(5)},
        [10.0, 10.125, 10.5, 10.625, 11.25, 11.375],
    )
    assert r.stand_provenance == {0: _made_of(6, pass1=5)}


def test_a_stand_that_takes_a_relaxed_second_pass_merge():
    """A 0.3 ha region 3.5 m taller than its neighbour: over the 2.0 m gate, so
    pass 1 leaves it, but exactly at the relaxed 3.5 m one, so pass 2 places it
    on its attributes rather than by the fallback."""
    r = _run([500, 30], {(0, 1): 5}, [10.0, 13.5])
    assert r.stand_provenance == {0: _made_of(2, relaxed=1)}


def test_a_stand_that_takes_a_fallback_merge():
    """A 0.2 ha region unlike both neighbours. No relaxed criterion matches, so
    it joins the neighbour it shares the longer boundary with -- and the stand
    it lands in says so, while the other neighbour's stand is untouched."""
    r = _run([400, 20, 400], {(0, 1): 1, (1, 2): 20}, [10.0, 25.0, 11.0])
    assert r.n_stands == 2
    assert _stand_of(r, 0) == _made_of(1)
    assert _stand_of(r, 1) == _stand_of(r, 2) == _made_of(2, fallback=1)


def test_one_stand_can_hold_all_three_kinds():
    """A and B (3 ha each, 1 m apart) merge in pass 1. C (0.2 ha, 3 m off their
    mean) is over the gate but inside the relaxed one. D (0.3 ha, nothing like
    them) can only come in by the fallback. One stand, each kind counted once."""
    r = _run(
        [300, 300, 20, 30],
        {(0, 1): 10, (1, 2): 4, (0, 3): 6},
        [10.0, 11.0, 13.5, 40.0],
    )
    assert r.stand_provenance == {0: _made_of(4, pass1=1, relaxed=1, fallback=1)}


def test_an_isolated_undersized_stand():
    """0.2 ha and touching nothing. It cannot merge, and that is the reason
    recorded."""
    r = _run([500, 20], {}, [10.0, 10.0])
    assert _stand_of(r, 0) == _made_of(1)
    assert _stand_of(r, 1) == _made_of(1, below_why="isolated")


def test_a_stand_that_merged_everything_in_reach_is_isolated_too():
    """Three fragments that touch only each other merge into one 0.6 ha stand.
    It is still below the minimum and now touches nothing, so "isolated" is a
    statement about the finished stand, not only about lone superpixels."""
    r = _run([20, 20, 20], {(0, 1): 3, (1, 2): 3}, [10.0, 10.0, 10.0])
    assert r.stand_provenance == {0: _made_of(3, pass1=2, below_why="isolated")}


def test_an_area_blocked_undersized_stand():
    """A 0.1 ha region between two 9.95 ha ones: joining either would make
    10.05 ha, over the 10 ha cap. It stays undersized, and the cause recorded
    is the cap -- the one a looser `max_area_ha` would fix."""
    r = _run([995, 10, 995], {(0, 1): 5, (1, 2): 5}, [10.0, 30.0, 10.0])
    assert r.n_stands == 3
    assert _stand_of(r, 1) == _made_of(1, below_why="area_blocked")
    assert _stand_of(r, 0) == _stand_of(r, 2) == _made_of(1)


# A chain X - U - R - V of 5, 10, 12 and 500 pixels, none alike. In one sweep,
# smallest first: X (5) joins U, making U 15; U, now larger than R (12), takes
# R, making U 27 px and for the first time a neighbour of V. That used U's turn.
# U is still 0.27 ha, V could take it (5.27 ha, under the cap), and only another
# sweep would do it.
_CAP_CHAIN: dict[str, Any] = dict(
    n_pixels=[5, 10, 12, 500],
    edges={(0, 1): 2, (1, 2): 2, (2, 3): 2},
    ch=[5.0, 25.0, 45.0, 65.0],
)


def test_the_iteration_cap_case():
    """With one sweep allowed, the stand is left below the minimum beside a
    neighbour that could have taken it. That is the third cause, and it is
    counted in the total the diagnostics call `orphans_no_attribute_match`."""
    r = _run(**_CAP_CHAIN, max_pass2_iterations=1)
    assert r.n_stands == 2
    assert _stand_of(r, 1) == _made_of(3, fallback=2, below_why="iteration_cap")
    assert _stand_of(r, 3) == _made_of(1)
    assert r.diagnostics["orphans_no_attribute_match"] == 1


def test_one_more_sweep_resolves_the_iteration_cap_case():
    """Same graph, two sweeps allowed: the second finishes the job, so the cause
    above really was the cap and nothing about the regions."""
    r = _run(**_CAP_CHAIN, max_pass2_iterations=2)
    assert r.stand_provenance == {0: _made_of(4, fallback=3)}


# A chain A - B - C of 60, 70 and 500 pixels, none alike; the minimum is 100 px.
# One sweep lists A and B, smallest first. A joins B (its only neighbour) by the
# fallback, and B, the larger, is the one that stays: 130 px, no longer
# undersized. Then comes B's own turn.
_GROWN_CHAIN: dict[str, Any] = dict(
    n_pixels=[60, 70, 500],
    edges={(0, 1): 2, (1, 2): 2},
    ch=[5.0, 25.0, 45.0],
)


def test_a_region_that_reached_the_minimum_still_takes_its_turn_by_default():
    """The committed behaviour: B, already 1.3 ha, is merged once more, and by
    the fallback, so the whole chain becomes one stand."""
    r = _run(**_GROWN_CHAIN)
    assert r.stand_provenance == {0: _made_of(3, fallback=2)}
    assert r.diagnostics["pass2_merges"] == r.diagnostics["pass2_fallback_merges"] == 2
    assert _run(**_GROWN_CHAIN, pass2_skip_at_min_area=False).assignment == r.assignment


def test_with_the_setting_on_a_region_that_reached_the_minimum_is_skipped():
    """spec-merge-pass2-skip-at-minimum: B is no longer undersized when its turn
    comes, so pass 2 leaves it alone and C stays a stand of its own."""
    r = _run(**_GROWN_CHAIN, pass2_skip_at_min_area=True)
    assert r.n_stands == 2
    assert _stand_of(r, 0) == _stand_of(r, 1) == _made_of(2, fallback=1)
    assert _stand_of(r, 2) == _made_of(1)
    assert r.diagnostics["pass2_merges"] == r.diagnostics["pass2_fallback_merges"] == 1
    assert r.diagnostics["stands_below_min_area"] == 0


def test_the_setting_also_stops_a_second_relaxed_merge():
    """The same chain with neighbours alike enough for the relaxed tolerances
    (3.5 for `ch`) but not for the first pass (2.0). A joins B; their mean,
    25.35, is within 3.5 of C's 28.7. By default B then joins C as well."""
    chain = dict(n_pixels=[60, 70, 500], edges={(0, 1): 2, (1, 2): 2}, ch=[24.0, 26.5, 28.7])
    assert _run(**chain).stand_provenance == {0: _made_of(3, relaxed=2)}
    r = _run(**chain, pass2_skip_at_min_area=True)
    assert r.n_stands == 2
    assert _stand_of(r, 1) == _made_of(2, relaxed=1) and _stand_of(r, 2) == _made_of(1)


def test_the_setting_leaves_a_region_still_below_the_minimum_alone():
    """In the iteration-cap chain the region that grows (U, 15 then 27 px) never
    reaches the minimum, so the setting changes nothing there."""
    for sweeps in (1, 2):
        off = _run(**_CAP_CHAIN, max_pass2_iterations=sweeps)
        on = _run(**_CAP_CHAIN, max_pass2_iterations=sweeps, pass2_skip_at_min_area=True)
        assert on.assignment == off.assignment and on.stand_provenance == off.stand_provenance


# A chain A - B - C of 40, 60 and 500 pixels, none alike. A joins B, and B is
# then 100 px: exactly the minimum, 1.0 ha, and not a pixel over it.
_EXACT_CHAIN: dict[str, Any] = dict(
    n_pixels=[40, 60, 500],
    edges={(0, 1): 2, (1, 2): 2},
    ch=[5.0, 25.0, 45.0],
)


def test_a_region_exactly_at_the_minimum_has_reached_it():
    """The setting skips a region whose area is at or above `min_area_ha`, not
    only one above it. B is exactly 1.0 ha when its turn comes: by default it
    is merged once more, into C; with the setting on it is skipped, the same
    way the next sweep's list (regions below the minimum) would leave it out."""
    assert _run(**_EXACT_CHAIN).stand_provenance == {0: _made_of(3, fallback=2)}
    r = _run(**_EXACT_CHAIN, pass2_skip_at_min_area=True)
    assert r.assignment == [0, 0, 1]
    assert _stand_of(r, 1) == _made_of(2, fallback=1) and _stand_of(r, 2) == _made_of(1)
    assert r.stand_attributes[0]["n_pixels"] == 100
    assert r.stand_attributes[0]["area_ha"] == DEFAULTS["min_area_ha"]
    assert r.diagnostics["pass2_merges"] == 1
    assert r.diagnostics["stands_below_min_area"] == 0


# Five regions, none alike: a - b - C, with d and e touching C as well. In
# pixels a is 30, b 80, C 810, d 90 and e 95; the minimum is 100 px and the cap
# (`max_area_ha`, 10 ha) is 1000 px. One sweep lists a, b, d and e, smallest
# first, and a joins b (110 px) under either rule. What b does on its own turn
# decides how much room C has left under the cap for d and e.
_ROOM_UNDER_THE_CAP: dict[str, Any] = dict(
    n_pixels=[30, 80, 810, 90, 95],
    edges={(0, 1): 2, (1, 2): 2, (2, 3): 2, (2, 4): 2},
    ch=[5.0, 25.0, 45.0, 65.0, 85.0],
)


def test_the_setting_can_give_more_merges_and_fewer_stands():
    """The new rule's stands are not always a split of the old ones. Skipping
    one merge can leave room under `max_area_ha` for others.

    By default b (110 px) is merged once more, into C, which is then 920 px. d
    and e no longer fit (1010 and 1015 px), so they stay below the minimum,
    area-blocked: three stands from two merges. With the setting on, b is
    skipped and C is still 810 px, so it takes d (900 px) and then e (995 px):
    two stands from three merges, and nothing left below the minimum."""
    off = _run(**_ROOM_UNDER_THE_CAP)
    assert off.assignment == [0, 0, 0, 1, 2]
    assert _stand_of(off, 2) == _made_of(3, fallback=2)
    assert _stand_of(off, 3) == _stand_of(off, 4) == _made_of(1, below_why="area_blocked")
    assert off.diagnostics["pass2_merges"] == 2
    assert off.diagnostics["stands_below_min_area"] == 2

    on = _run(**_ROOM_UNDER_THE_CAP, pass2_skip_at_min_area=True)
    assert on.assignment == [0, 0, 1, 1, 1]
    assert _stand_of(on, 1) == _made_of(2, fallback=1)
    assert _stand_of(on, 2) == _made_of(3, fallback=2)
    assert on.diagnostics["pass2_merges"] == 3
    assert on.diagnostics["stands_below_min_area"] == 0

    assert on.diagnostics["pass2_merges"] > off.diagnostics["pass2_merges"]
    assert on.n_stands < off.n_stands


def test_a_graph_where_nothing_merges():
    """Two 2 ha regions 20 m apart in height. Pass 1 rejects the pair and pass 2
    has nothing undersized, so each stand is one superpixel with no merges."""
    r = _run([200, 200], {(0, 1): 10}, [10.0, 30.0])
    assert r.stand_provenance == {0: _made_of(1), 1: _made_of(1)}


def test_an_empty_graph():
    r = _run([], {}, [])
    assert r.n_stands == 0
    assert r.stand_provenance == {}


def test_field_names_fit_a_shapefile_and_clash_with_nothing():
    """The fields are headed for the exported `stands_merged` layer, whose
    shapefile twin truncates names past 10 characters without saying so, and
    which already has columns of its own."""
    already_on_the_layer = {
        "stand_id",
        "stand_lbl",
        "cluster_id",
        "area_ha",
        "perim_m",
        "n_pixels",
        "centroid_lat",
        "centroid_lon",
    }
    assert len(set(PROVENANCE_FIELDS)) == len(PROVENANCE_FIELDS)
    for name in PROVENANCE_FIELDS:
        assert len(name) <= 10, name
        assert name.isascii() and name.islower() and name.isidentifier(), name
        assert name not in already_on_the_layer, name


def test_provenance_sits_beside_stand_attributes_not_inside_them():
    """`stand_attributes[sid]` holds two fixed keys plus keys named after the
    criterion bands, and is written whole into `<config>_run.json`. Its key set
    is pinned; a band that happens to be called `n_pass1` keeps its mean there
    while the merge count of the same name lives in `stand_provenance`."""
    graph = SuperpixelGraph(
        raw_labels=[7, 9], n_pixels=[200, 200], edges={(0, 1): 10}, scale_m=10
    )
    means: dict[int, dict[str, float | None]] = {
        0: {"n_pass1": 10.0, "std": 0.5},
        1: {"n_pass1": 11.0, "std": 0.5},
    }
    counts = {0: {"n_pass1": 200, "std": 200}, 1: {"n_pass1": 200, "std": 200}}
    kwargs = {"criteria": {"n_pass1": 2.0, "std": 0.45}, **DEFAULTS}
    r = merge_superpixels(graph, means, counts, **kwargs)
    assert_provenance_invariants(r, graph, **kwargs)
    assert set(r.stand_attributes[0]) == {
        "n_pixels",
        "area_ha",
        "n_pass1",
        "frac_valid_n_pass1",
        "std",
        "frac_valid_std",
    }
    assert r.stand_attributes[0]["n_pass1"] == pytest.approx(10.5)  # the band mean
    assert r.stand_provenance[0]["n_pass1"] == 1  # the merge count


# ---------------------------------------------------------------------------
# Seeded random graphs, built the way a run builds them
# ---------------------------------------------------------------------------

# Raise this whenever `random_case` changes what it builds for a seed: the
# committed digests are of these exact graphs.
GENERATOR_VERSION = 1

# (band, typical level, spread across an area, tolerance in the shipped configs)
_BANDS = (
    ("canopy_height", 12.0, 8.0, 2.0),
    ("canopy_height_std", 2.0, 1.5, 0.45),
    ("ndvi_amplitude_annual", 0.2, 0.15, 0.03),
)


class _Draws:
    """Random draws built on `random.Random(seed).random()` and nothing else.

    That method's sequence for a seed is the one Python documents as
    reproducible; `shuffle`, `choice` and the rest are built here from it, with
    arithmetic IEEE 754 fixes exactly, so a seed means the same graph anywhere.
    """

    def __init__(self, seed: int) -> None:
        self.unit = random.Random(seed).random  # uniform on [0, 1)

    def below(self, n: int) -> int:
        return int(self.unit() * n)

    def between(self, lo: float, hi: float) -> float:
        return lo + (hi - lo) * self.unit()

    def chance(self, p: float) -> bool:
        return self.unit() < p

    def pick(self, options: Sequence[Any]) -> Any:
        return options[self.below(len(options))]

    def shuffled(self, items: list[Any]) -> list[Any]:
        out = list(items)
        for i in range(len(out) - 1, 0, -1):
            j = self.below(i + 1)
            out[i], out[j] = out[j], out[i]
        return out


@dataclass
class Case:
    """One seeded graph, and the settings to merge it with."""

    graph: SuperpixelGraph
    means: dict[int, dict[str, float | None]]
    valid_counts: dict[int, dict[str, int]]
    # Every keyword argument of `merge_superpixels`.
    settings: dict[str, Any]

    def merge(self, merge: Callable[..., Any] = merge_superpixels) -> Any:
        return merge(self.graph, self.means, self.valid_counts, **self.settings)


def random_case(seed: int, *, max_side: int = 24) -> Case:
    """A random superpixel graph with attributes and merge settings.

    Built from pixels, as `fmu.utils.adjacency` builds the real one:

      - a grid with non-habitat masked out as rectangles, a line right across
        (which splits the area), and small ringed patches (which leave regions
        that touch nothing);
      - superpixels grown from random seed pixels until the habitat is
        partitioned, plus single-pixel specks, so sizes vary and adjacency is
        that of a planar partition;
      - edges counted over right and down neighbours, one per boundary pixel
        pair; raw labels sparse and in an order unrelated to position;
      - attribute means that vary smoothly, roughly, in steps or not at all,
        with bands that have no valid pixel (`None`, count 0), regions with no
        attribute row, and valid counts below, at and above the pixel count;
      - centroids taken from the longitude / latitude means, as the stage does;
      - settings spread widely enough that pass-1, relaxed and fallback merges,
        area-blocked and isolated stands and the iteration cap all turn up.
    """
    rng = _Draws(seed)
    width = 4 + rng.below(max_side - 3)
    height = 4 + rng.below(max_side - 3)

    # ---- which pixels are habitat
    usable = [[True] * width for _ in range(height)]
    if rng.chance(0.3):
        for _ in range(1 + rng.below(3)):
            w = 1 + rng.below(max(1, width // 3))
            h = 1 + rng.below(max(1, height // 3))
            x0, y0 = rng.below(width - w + 1), rng.below(height - h + 1)
            for y in range(y0, y0 + h):
                usable[y][x0 : x0 + w] = [False] * w
    if rng.chance(0.2):
        if rng.chance(0.5):
            usable[rng.below(height)] = [False] * width
        else:
            x = rng.below(width)
            for row in usable:
                row[x] = False
    if rng.chance(0.35):
        for _ in range(1 + rng.below(3)):
            w, h = 1 + rng.below(2), 1 + rng.below(2)
            x0, y0 = rng.below(width - w + 1), rng.below(height - h + 1)
            for y in range(max(0, y0 - 1), min(height, y0 + h + 1)):
                for x in range(max(0, x0 - 1), min(width, x0 + w + 1)):
                    usable[y][x] = y0 <= y < y0 + h and x0 <= x < x0 + w
    if not any(any(row) for row in usable):
        usable[0][0] = True
    cells = [(y, x) for y in range(height) for x in range(width) if usable[y][x]]

    # ---- partition the habitat into superpixels
    label = [[-1] * width for _ in range(height)]
    frontier: list[tuple[int, int, int]] = []

    def claim(y: int, x: int, region: int) -> None:
        label[y][x] = region
        for ny, nx in ((y, x + 1), (y + 1, x), (y, x - 1), (y - 1, x)):
            if 0 <= ny < height and 0 <= nx < width and usable[ny][nx] and label[ny][nx] < 0:
                frontier.append((ny, nx, region))

    n_labels = max(1, len(cells) // rng.pick((2, 3, 5, 8, 12, 20, 35)))
    for region, (y, x) in enumerate(rng.shuffled(cells)[:n_labels]):
        claim(y, x, region)
    # Habitat no seed could reach (a ringed patch, the far side of a line)
    # becomes one more region per connected piece: `cells` is walked only once
    # the frontier has run dry.
    for y0, x0 in [(-1, -1), *cells]:
        if y0 >= 0 and label[y0][x0] < 0:
            claim(y0, x0, n_labels)
            n_labels += 1
        while frontier:
            k = rng.below(len(frontier))
            frontier[k], frontier[-1] = frontier[-1], frontier[k]
            y, x, region = frontier.pop()
            if label[y][x] < 0:
                claim(y, x, region)
    if rng.chance(0.25):
        for _ in range(1 + rng.below(4)):
            y, x = rng.pick(cells)
            label[y][x] = n_labels
            n_labels += 1

    # ---- dense indices in an order that has nothing to do with position
    present = sorted({label[y][x] for y, x in cells})
    dense = {lab: i for i, lab in enumerate(rng.shuffled(present))}
    n = len(present)
    raw_labels, raw = [], 1000
    for _ in range(n):
        raw += 1 + rng.below(5000)
        raw_labels.append(raw)
    n_pixels = [0] * n
    sum_x = [0] * n
    sum_y = [0] * n
    edges: dict[tuple[int, int], int] = {}
    for y, x in cells:
        i = dense[label[y][x]]
        n_pixels[i] += 1
        sum_x[i] += x
        sum_y[i] += y
        for ny, nx in ((y, x + 1), (y + 1, x)):
            if ny < height and nx < width and usable[ny][nx]:
                j = dense[label[ny][nx]]
                if j != i:
                    key = (i, j) if i < j else (j, i)
                    edges[key] = edges.get(key, 0) + 1
    scale_m = rng.pick((10, 10, 10, 20, 30))
    graph = SuperpixelGraph(
        raw_labels=raw_labels, n_pixels=n_pixels, edges=edges, scale_m=scale_m
    )

    # ---- attribute means and valid counts
    bands = _BANDS[: rng.pick((1, 2, 2, 3, 3, 3))]
    texture = rng.pick(("smooth", "smooth", "smooth", "rough", "stepped", "flat"))
    noise = {"smooth": 0.05, "rough": 1.0, "stepped": 0.3, "flat": 0.0}[texture]
    cell = 2 + rng.below(6)
    patch_cols = width // cell + 1
    shape = [
        (
            rng.between(-1.0, 1.0),
            rng.between(-1.0, 1.0),
            rng.between(0.0, 1.5),
            [rng.unit() - 0.5 for _ in range((height // cell + 1) * patch_cols)],
        )
        for _ in bands
    ]
    p_none = rng.pick((0.0, 0.0, 0.0, 0.03, 0.1, 0.3))
    p_no_row = rng.pick((0.0, 0.0, 0.0, 0.0, 0.03, 0.1))
    counting = rng.pick(("exact", "partial", "edge", "edge"))
    means: dict[int, dict[str, float | None]] = {}
    valid_counts: dict[int, dict[str, int]] = {}
    for i in range(n):
        px = n_pixels[i]
        cx, cy = sum_x[i] / px, sum_y[i] / px
        row_means: dict[str, float | None] = {}
        row_counts: dict[str, int] = {}
        for (band, level, spread, _tol), (gx, gy, weight, patches) in zip(
            bands, shape, strict=True
        ):
            patch = patches[(int(cy) // cell) * patch_cols + int(cx) // cell]
            value = level + spread * (
                gx * (cx / width - 0.5)
                + gy * (cy / height - 0.5)
                + weight * patch
                + noise * (rng.unit() - 0.5)
            )
            if texture == "flat":
                value = level
            elif texture == "stepped":
                value = math.floor(value / (spread / 8.0) + 0.5) * (spread / 8.0)
            if counting == "exact" or rng.chance(0.4):
                count = px
            elif counting == "partial":
                count = 1 + rng.below(px)
            else:  # around the pixel count, on either side of it
                count = max(1, px - px // 8 + rng.below(px // 4 + 2))
            if rng.chance(p_none):
                row_means[band], row_counts[band] = None, 0
            else:
                row_means[band], row_counts[band] = value, count
        row_means["longitude"] = 77.0 + cx * 0.0001
        row_means["latitude"] = 28.5 - cy * 0.0001
        row_counts["longitude"] = row_counts["latitude"] = px
        if not rng.chance(p_no_row):
            means[i], valid_counts[i] = row_means, row_counts
    centroids: dict[int, tuple[float, float]] | None = None
    if not rng.chance(0.1):
        centroids = {
            i: (float(m.get("longitude") or 0.0), float(m.get("latitude") or 0.0))
            for i, m in means.items()
        }

    # ---- settings
    px_to_ha = scale_m * scale_m / 10_000.0
    mean_ha = len(cells) * px_to_ha / n
    min_area_ha = mean_ha * rng.pick((0.3, 0.8, 1.5, 3.0, 3.0, 6.0, 15.0))
    if rng.chance(0.12):  # below the smallest region: pass 2 has nothing to do
        min_area_ha = min(n_pixels) * px_to_ha * 0.5
    max_area_ha = min_area_ha * rng.pick((1.2, 2.0, 3.0, 3.0, 10.0, 10.0, 40.0))
    max_pass2_iterations = rng.pick((1, 1, 2, 3, 60, 60, 60, 60))
    if rng.chance(0.2):
        # A minimum far above the superpixel size and a single sweep: stands
        # that are still small when the sweep ends, beside one that has room.
        min_area_ha = mean_ha * rng.pick((15.0, 40.0, 100.0))
        max_area_ha = min_area_ha * rng.pick((1.2, 3.0, 10.0))
        max_pass2_iterations = 1
    tolerance_scale = rng.pick((0.1, 0.3, 1.0, 1.0, 1.0, 3.0, 10.0))
    criteria = dict(
        rng.shuffled(
            [
                (band, tol * tolerance_scale * rng.between(0.7, 1.4))
                for band, _level, _spread, tol in bands
            ]
        )
    )
    settings: dict[str, Any] = dict(
        criteria=criteria,
        relax_factor=rng.pick((1.25, 1.75, 1.75, 1.75, 2.5, 5.0)),
        min_area_ha=min_area_ha,
        max_area_ha=max_area_ha,
        min_defined_criteria=1 + rng.below(len(bands)),
        min_frac_valid=rng.pick((0.0, 0.25, 0.5, 0.5, 0.5, 0.9, 1.0)),
        max_pass2_iterations=max_pass2_iterations,
        centroids=centroids,
    )
    return Case(graph, means, valid_counts, settings)


def branches_reached(diagnostics: dict[str, Any]) -> dict[str, bool]:
    """Which parts of the merge one run exercised, from its totals."""
    d = diagnostics
    return {
        "first-pass merge": d["pass1_merges"] > 0,
        "relaxed second-pass merge": d["pass2_merges"] > d["pass2_fallback_merges"],
        "shared-edge fallback merge": d["pass2_fallback_merges"] > 0,
        "isolated undersized stand": d["orphans_isolated"] > 0,
        "area-blocked undersized stand": d["orphans_area_blocked"] > 0,
        "iteration cap left a stand": d["orphans_no_attribute_match"] > 0,
        "nothing merged": d["n_stands"] == d["n_superpixels"],
        "pair short of defined criteria": (
            d["pass1_pairs_blocked_by_undefined_criteria_round1"] > 0
        ),
        "stand with incomplete criteria": d["stands_with_incomplete_criteria"] > 0,
    }


# ---------------------------------------------------------------------------
# The stands did not move: digests from before provenance existed
# ---------------------------------------------------------------------------

GOLDEN_SEEDS = range(200)

# The golden graphs on which review B18 (round 13: the merge's area bounds compared
# in whole pixels, not on a float sum of two areas) changed what the merge does, and
# the digest each gave. On no other graph did it change anything: when B18 was made,
# today's merge gave on all 200 graphs what the fixture's commit gives with only that
# comparison changed. Seed 98 has moved again since (DIGESTS_SINCE_Q24).
DIGESTS_SINCE_B18: dict[str, str] = {
    "3": "8039de8a6342d5add12d063968ae3e0bb928d0b62cacc995f51a4922bbfb8540",
    "53": "d1f57e24d7bcad2757bed21ca11d9daded76fdbea182d7ba7c7527fff6ebe73c",
    "98": "6291ccc8b07217e3c42dfea8d5a8a90dc94a3396ad5ae154de79725362e7e133",
}

# The golden graphs on which round 14 (round 13 question 24, answer (a): two
# neighbours sharing boundaries of the same length in pass 2's shared-edge fallback
# are taken by order_key, centroid first, not by the lower root index, which is SNIC
# label order) changed what the merge does, and the digest each gives since. On no
# other graph did it change anything: when it was made, today's merge gave on all 200
# graphs what the merge before it gives with only that tie rule changed, and what the
# fixture's commit gives with B18's comparison and that tie rule put in it. On each of
# these 20 a tie there was decided the other way; on 6 more (11, 65, 99, 106, 159 and
# 179) one was, and every output of the merge came out the same.
DIGESTS_SINCE_Q24: dict[str, str] = {
    "6": "3d3f1c0a2d5a3fa43165c7b1370f1f761739c64efec80eb2ad226a5251f1a040",
    "19": "9e66c044717aad012f59a453e37ee9919045ac0afd09d87719ea8b6d499f5ba2",
    "25": "9df722e7af2cc872d5acebd34017725300a332939889a781af5e8080e3e9639d",
    "26": "f605d14c489838a5a5194ad8ad65510df0b5d2d12eedeaaed1d17bde35b68f80",
    "54": "bb1c837804feadae2bcce953e074dddeb65b30973aa3845af2f8e31a2737b03f",
    "76": "c01e799eb6ca531fcbc993ddaa25e84a60ff864d14512308cece3889f13f1691",
    "77": "126f821f70034170ab51f48c998d1fd0b919dd368f474f69ed95d1cb55b3c49e",
    "95": "61103649847338a662ad7a0057b0e7d7fa85750306e5574f1da085aab6a9d76f",
    "98": "c9607fd25097bee48568426238a1a62e95470765fa185ec196817b62291ccd30",
    "109": "2e16469ea9ae7c42c8ed1aba4505d01b5d7ba768c99a627b798ffd576e69efe3",
    "124": "84ea7bd3c2aecd667c797ff78ca15053eff1cd576b975d24497c60050120e3c1",
    "126": "265584260d8c47b8068a2cf966e5eedc895c0df0913a9631c10344723b7bf550",
    "157": "0949dc7490fcfae973a66d168a2e91c287a63b23b59a7395383e1bfbeb96131c",
    "158": "210b29ce53dd6315810f96bee8ed4c5f66629047c2598b2fcd58a8a408c7b621",
    "168": "74ee904478493a0903fe9965ca39a4bb68bba395c30493556748b345c110b5ef",
    "171": "7c51840949d5c5db87bf014586579a7c0142459a79602975691a133df158a07e",
    "173": "932e9c089fbe90bd368bd33cd7abf148e8079f101b552e79b904647b0aa0653a",
    "177": "4fdd0454505cd2403bd6b483f2a1488db2277a473b93a26180ebbfbd15be780b",
    "183": "34069301bafd815f2e5abb5cd0e0daed474e08fb55ecc97e3e78473aebc494d6",
    "194": "664b6ec0c6e1fffe2f8ed6d80836f472ac400f5163e91cc68debf09abe2b7a4a",
}

# The diagnostics the merge reported when the digests were made. Named here, not
# read from the result, so a key added later does not disturb the comparison.
PINNED_DIAGNOSTICS = (
    "n_superpixels",
    "n_stands",
    "reduction_factor",
    "pass1_rounds",
    "pass1_merges",
    "pass1_pairs_blocked_by_area_round1",
    "pass1_pairs_blocked_by_undefined_criteria_round1",
    "pass2_iterations",
    "pass2_merges",
    "pass2_fallback_merges",
    "stands_below_min_area",
    "area_in_undersized_stands_ha",
    "orphans_isolated",
    "orphans_area_blocked",
    "orphans_no_attribute_match",
    "stands_with_incomplete_criteria",
)


def _sha256(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pinned_outputs(result: Any, case: Case) -> dict[str, Any]:
    """Everything the merge returned before provenance existed, by name."""
    keys = ["n_pixels", "area_ha"]
    for band in sorted(case.settings["criteria"]):
        keys += [band, f"frac_valid_{band}"]
    return {
        "assignment": result.assignment,
        "n_stands": result.n_stands,
        "diagnostics": {k: result.diagnostics[k] for k in PINNED_DIAGNOSTICS},
        "stand_attributes": [
            [sid, {k: result.stand_attributes[sid][k] for k in keys}]
            for sid in sorted(result.stand_attributes)
        ],
    }


def _inputs_digest(cases: list[Case]) -> str:
    """One digest over every generated graph and its settings, so a change in
    what the generator builds is told apart from a change in the merge."""
    payload = []
    for case in cases:
        s = case.settings
        payload.append(
            {
                "raw_labels": case.graph.raw_labels,
                "n_pixels": case.graph.n_pixels,
                "edges": [[i, j, c] for (i, j), c in sorted(case.graph.edges.items())],
                "scale_m": case.graph.scale_m,
                "means": sorted(case.means.items()),
                "valid_counts": sorted(case.valid_counts.items()),
                # In the order given: the gate walks the criteria in that order.
                "criteria": list(s["criteria"].items()),
                "centroids": s["centroids"] and sorted(s["centroids"].items()),
                "other": {k: v for k, v in s.items() if k not in ("criteria", "centroids")},
            }
        )
    return _sha256(payload)


@pytest.fixture(scope="module")
def golden() -> dict[str, Any]:
    return json.loads(GOLDEN_PATH.read_text())


@pytest.fixture(scope="module")
def golden_runs() -> list[tuple[int, Case, MergeResult]]:
    """Today's merge on every golden graph, run once for the tests below."""
    cases = [(seed, random_case(seed)) for seed in GOLDEN_SEEDS]
    return [(seed, case, case.merge()) for seed, case in cases]


def test_the_generator_still_builds_the_graphs_the_digests_were_made_from(
    golden, golden_runs
):
    """If this fails, the comparison below is meaningless rather than failed:
    the merge is being run on different graphs. Either `random_case` was edited
    (raise GENERATOR_VERSION and regenerate the fixture) or this platform does
    not reproduce the draws."""
    assert golden["generator_version"] == GENERATOR_VERSION
    assert [int(seed) for seed in golden["digests"]] == list(GOLDEN_SEEDS)
    assert _inputs_digest([case for _, case, _ in golden_runs]) == golden["inputs_sha256"]


def test_todays_merge_reproduces_every_committed_digest(golden, golden_runs):
    """The merge must produce the assignment, stand count, totals and stand
    attributes it produced at the commit named in the fixture, on every graph but
    the 22 of `DIGESTS_SINCE_B18` and `DIGESTS_SINCE_Q24`, where it must produce
    what is pinned there (the later where both pin a seed)."""
    assert all(golden["digests"][seed] != d for seed, d in DIGESTS_SINCE_B18.items())
    since_b18 = {**golden["digests"], **DIGESTS_SINCE_B18}
    assert all(since_b18[seed] != d for seed, d in DIGESTS_SINCE_Q24.items())
    expected = {**since_b18, **DIGESTS_SINCE_Q24}
    changed = [
        seed
        for seed, case, result in golden_runs
        if _sha256(pinned_outputs(result, case)) != expected[str(seed)]
    ]
    assert not changed, (
        f"merge_superpixels no longer produces what it produced at "
        f"{golden['made_from']['commit'][:7]} (or since review B18 or round 14's "
        f"fallback tie, where pinned) on {len(changed)} of {len(golden_runs)} seeded "
        f"graphs (seeds {changed}). If moving stands was the point of the change, say "
        f"so in the commit and pin the new digests, as DIGESTS_SINCE_Q24 does; if it "
        f"was not, this is the bug."
    )


def test_the_golden_graphs_reach_every_branch_of_the_merge(golden_runs):
    """A digest that matches says little if the graphs never exercised the code."""
    seen: dict[str, int] = {}
    for _seed, _case, result in golden_runs:
        for name, reached in branches_reached(result.diagnostics).items():
            seen[name] = seen.get(name, 0) + int(reached)
    too_rare = {name: count for name, count in seen.items() if count < 5}
    assert not too_rare, f"reached by fewer than 5 of 200 graphs: {too_rare} (all: {seen})"


def test_invariants_hold_on_every_golden_graph(golden_runs):
    for seed, case, result in golden_runs:
        try:
            assert_provenance_invariants(result, case.graph, **case.settings)
        except AssertionError as e:
            raise AssertionError(f"seed {seed}: {e}") from e


# ---------------------------------------------------------------------------
# Regenerating the fixture:  python tests/test_region_merge_provenance.py <commit>
# ---------------------------------------------------------------------------


def test_the_new_rule_keeps_the_invariants_and_moves_stands_on_some_golden_graphs(golden_runs):
    """With the setting on, the same 200 graphs still satisfy every invariant
    between provenance and totals, pass 1 makes the same merges, and on some of
    them the stands differ: the graphs do reach the case the setting is about.
    Nothing is asserted about how many pass-2 merges or stands there are: the
    setting can move both either way
    (`test_the_setting_can_give_more_merges_and_fewer_stands`). (The digests
    above are the proof that the default moves nothing.)"""
    differ = []
    for seed, case, off in golden_runs:
        settings = {**case.settings, "pass2_skip_at_min_area": True}
        on = merge_superpixels(case.graph, case.means, case.valid_counts, **settings)
        assert_provenance_invariants(on, case.graph, **settings)
        assert on.diagnostics["pass1_merges"] == off.diagnostics["pass1_merges"], seed
        if on.assignment != off.assignment:
            differ.append(seed)
    assert differ, "no golden graph reaches a region that grows to the minimum before its turn"


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True, check=True
    ).stdout


def write_golden(commit: str) -> None:
    """Write the fixture from the merge as committed at `commit`.

    The file is read with `git show`, so neither the working tree nor the index
    is touched and the code that runs is the committed one whatever the checkout
    holds. The fixture holds no date, machine or Python version, so running this
    again from the same commit reproduces it byte for byte.
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
    cases = [random_case(seed) for seed in GOLDEN_SEEDS]
    full_commit = _git("rev-parse", f"{commit}^{{commit}}").strip()
    fixture = {
        "what": (
            f"Digests of what merge_superpixels produced for {len(cases)} seeded "
            "random graphs BEFORE per-stand provenance was added to it. "
            "tests/test_region_merge_provenance.py asserts that the merge still "
            "produces exactly this."
        ),
        "made_from": {
            "commit": full_commit,
            "file": MERGE_SOURCE,
            "git_blob": _git("rev-parse", f"{commit}:{MERGE_SOURCE}").strip(),
            "file_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        },
        "how": (
            f"python tests/test_region_merge_provenance.py {full_commit}  (from "
            "the repo root). It reads the file above with `git show`, loads "
            "merge_superpixels from that text, runs it on random_case(seed) for "
            "seeds 0..199 and writes this file. The working tree's "
            "region_merge.py is not used."
        ),
        "digest": (
            "sha256 of JSON (sorted keys, no spaces) of {assignment, n_stands, "
            "diagnostics, stand_attributes}: diagnostics is the 16 keys in "
            "PINNED_DIAGNOSTICS; stand_attributes is, per stand, n_pixels, "
            "area_ha and each criterion band's mean and frac_valid"
        ),
        "generator_version": GENERATOR_VERSION,
        "inputs_sha256": _inputs_digest(cases),
        "digests": {
            str(seed): _sha256(pinned_outputs(case.merge(module.merge_superpixels), case))
            for seed, case in zip(GOLDEN_SEEDS, cases, strict=True)
        },
    }
    GOLDEN_PATH.parent.mkdir(exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(fixture, indent=1) + "\n")
    print(f"wrote {GOLDEN_PATH} ({GOLDEN_PATH.stat().st_size} bytes) from {full_commit}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(
            "usage: python tests/test_region_merge_provenance.py <commit>\n"
            "  <commit> is the commit whose merge the digests should be made from."
        )
    write_golden(sys.argv[1])
