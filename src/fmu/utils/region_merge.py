"""Two-pass region merge over a superpixel adjacency graph.

Follows Xiong et al. 2024 section 2.6. Pure Python over the graph
`fmu.utils.adjacency` brings down, so it is fully unit-testable without Earth
Engine; the stage wrapper turns the result back into an `ee.Image` with
`snic_clusters.remap(...)`.

Pass 1 -- merge homogeneous neighbours, iterating to convergence:
  - a pair is eligible if their areas sum to at most `max_area_ha`, judged in
    whole pixels (`_whole_pixels_within`);
  - a **hard gate**, not a weighted sum: reject if *any* shared criterion
    exceeds its tolerance. This is Xiong's design and it keeps thresholds
    interpretable in physical units;
  - eligible pairs merge in ascending `d = sum (|delta| / tol)^2`, skipping any
    region already merged this round.

Pass 2 -- eliminate undersized regions, smallest first:
  - each sweep lists the undersized regions once and takes them in turn. A
    listed region that has reached `min_area_ha` by its turn can be merged once
    more all the same, unless `pass2_skip_at_min_area` is true, which skips it;
  - same rule with tolerances multiplied by `relax_factor`;
  - if no neighbour passes even relaxed, absorb into the neighbour sharing the
    longest boundary. This fallback is what prevents orphans;
  - **the fallback still respects the ceiling.** By default that is
    `max_area_ha`, as in pass 1. With `pass2_soft_ceiling` on, a region still
    below `min_area_ha` when its turn comes may go over `max_area_ha`, up to
    `max_area_ha + min_area_ha` and never further. It then takes, in this
    order: a neighbour that passes the relaxed tolerances and keeps the result
    at most `max_area_ha`, the closest; one that passes them with the result
    over it, the closest; the neighbour sharing the longest boundary with the
    result at most `max_area_ha`; the one sharing the longest boundary with the
    result over it. Going past the ceiling would break the derived
    `max_component_pixels` and silently delete the largest stands, which is the
    exact failure that cap exists to prevent. Regions that cannot be placed
    under the ceiling stay undersized and get reported.

Two properties this file is careful about:

**Attribute means are weighted by per-criterion valid pixel count, not total
pixels.** Regions are carried as (sum, valid_count) per band rather than as a
mean, so merging adds both and the mean falls out correctly. Weighting by total
pixels would let a null-canopy region merging into a defined-canopy one inherit
a canopy height for territory that never measured one -- the merge would invent
data. 14 of the 1249 superpixels in the committed baseline run have no
`canopy_height` at all (ETH no-data), so this is not hypothetical.

**A pair needs at least `min_defined_criteria` criteria defined on both sides,
in both passes.** One criterion is too weak a similarity test to justify a
merge. `compare` applies this floor under pass 2's relaxed tolerances as well,
so a pair that falls short never merges on its attributes: in pass 2 a region
below `min_area_ha` whose neighbours all fall short of the floor, or fail the
relaxed tolerances, joins one only by the shared-edge fallback, which ignores
attributes; and two regions that are both at or above the minimum and fall
short do not merge at all. Corrected 20 Oct 2026 (review C13): this said that
such pairs "drop to pass 2, which is the right destination", as if pass 2
could still match them on their attributes.

Provenance -- what each stand is made of. It is recorded beside the merge and
never read back by it: no merge decision depends on anything described here.

`MergeResult.stand_provenance[stand_id]` holds one dict per final stand, under
the same stand ids as `stand_attributes`, with the fields in
`PROVENANCE_FIELDS`. Every name is at most 10 characters, because the exported
`stands_merged` layer has a shapefile twin and a shapefile truncates anything
longer without saying so:

  n_superpx   int  superpixels the stand is made of (1 = it never merged)
  n_pass1     int  merges inside it made by pass 1, tolerances as configured
  n_relaxed   int  merges inside it made by pass 2 under the relaxed tolerances
  n_fallback  int  merges inside it made by pass 2's shared-edge fallback,
                   which ignores attributes
  below_min   int  1 if the stand ended below `min_area_ha`, else 0
  below_why   str  why, when below_min is 1; "" when it is 0. One of:
                     "isolated"       it shares no edge with another stand:
                                      no 4-connected neighbour in the graph
                                      (`fmu.utils.adjacency`), so a stand that
                                      meets another only at a corner is
                                      isolated too (review C16; this said "it
                                      touches no other stand")
                     "area_blocked"   every neighbouring stand is too big to
                                      take it under the ceiling: `max_area_ha`,
                                      or `max_area_ha + min_area_ha` with
                                      `pass2_soft_ceiling` on
                     "iteration_cap"  it still had a neighbour it could have
                                      joined when pass 2 stopped at
                                      `max_pass2_iterations`

`below_min` is 0/1 rather than a bool, and `below_why` is "" rather than None,
on purpose: a number and a never-null string come through both export formats
(shapefile, GeoJSON) unchanged, with no reliance on how either one writes a
boolean or a null.

What ties these to the totals in `diagnostics`:

  - a stand of m superpixels contains exactly m - 1 merges, so
    n_pass1 + n_relaxed + n_fallback == n_superpx - 1;
  - over all stands, n_pass1 sums to `pass1_merges`, n_relaxed to
    `pass2_merges - pass2_fallback_merges`, and n_fallback to
    `pass2_fallback_merges`;
  - below_min sums to `stands_below_min_area`, and each below_why value is
    counted in the total `BELOW_WHY_TOTALS` names for it. "iteration_cap" is
    `orphans_no_attribute_match`: the comment where that total is counted
    explains why running out of iterations is the only way to reach it.

It lives beside `stand_attributes`, not inside it. `stand_attributes[sid]`
mixes two fixed keys with keys named after the criterion bands, and the config
chooses those names -- so a provenance key in there could collide with a band,
and would change what every existing reader of that dict receives (it is
written whole into the run records, which are compared between runs).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from fmu.utils.adjacency import SuperpixelGraph
from fmu.utils.logging import get_logger

log = get_logger(__name__)

# Per-stand provenance fields, in the order they are written into
# `MergeResult.stand_provenance[stand_id]`. The module docstring says what each
# one means. Each name is at most 10 characters: the shapefile field-name limit.
PROVENANCE_FIELDS: tuple[str, ...] = (
    "n_superpx",
    "n_pass1",
    "n_relaxed",
    "n_fallback",
    "below_min",
    "below_why",
)

# `below_why` value -> the `diagnostics` total that counts the stands with it.
BELOW_WHY_TOTALS: dict[str, str] = {
    "isolated": "orphans_isolated",
    "area_blocked": "orphans_area_blocked",
    "iteration_cap": "orphans_no_attribute_match",
}


@dataclass
class _Region:
    """Accumulator for one region under construction.

    Holds sums and valid counts rather than means so that a merge is addition.
    """

    n_pixels: int
    sums: dict[str, float]
    valid: dict[str, int]
    # Sum of (centroid * n_pixels), so the merged centroid is also addition.
    lon_sum: float = 0.0
    lat_sum: float = 0.0

    def mean(self, band: str) -> float | None:
        v = self.valid.get(band, 0)
        return self.sums[band] / v if v else None

    def frac_valid(self, band: str) -> float:
        return self.valid.get(band, 0) / self.n_pixels if self.n_pixels else 0.0

    def centroid(self) -> tuple[float, float]:
        if not self.n_pixels:
            return (0.0, 0.0)
        return (self.lon_sum / self.n_pixels, self.lat_sum / self.n_pixels)

    def absorb(self, other: _Region) -> None:
        self.n_pixels += other.n_pixels
        for band, s in other.sums.items():
            self.sums[band] = self.sums.get(band, 0.0) + s
        for band, v in other.valid.items():
            self.valid[band] = self.valid.get(band, 0) + v
        self.lon_sum += other.lon_sum
        self.lat_sum += other.lat_sum


@dataclass
class MergeResult:
    """The merge's output plus everything needed to report on it."""

    # Dense superpixel index -> stand id, numbered 0..n_stands-1.
    assignment: list[int]
    n_stands: int
    # stand id -> {n_pixels, area_ha, <band>, frac_valid_<band>}
    stand_attributes: dict[int, dict[str, Any]] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    # stand id -> {n_superpx, n_pass1, n_relaxed, n_fallback, below_min,
    # below_why}: what each stand is made of. Same stand ids as
    # `stand_attributes`, and one entry per stand. The fields are documented in
    # the module docstring.
    stand_provenance: dict[int, dict[str, Any]] = field(default_factory=dict)


def _whole_pixels_within(scale_m: int, *bounds_ha: float) -> int:
    """The most whole pixels whose area is at most the sum of `bounds_ha`.

    Worked out exactly, so that a bound of exactly N pixels admits N pixels at
    any scale (review B18): each bound is taken as the decimal it prints as
    (`str` gives the shortest decimal that reads back as the same float, so a
    bound written in a config as 0.35 is 0.35) and the arithmetic is on
    fractions. Floats would not do: 35 * 0.01 is a hair over 0.35.
    """
    total_ha = sum((Fraction(str(b)) for b in bounds_ha), Fraction(0))
    return math.floor(total_ha * 10_000 / (scale_m * scale_m))


class _UnionFind:
    def __init__(self, n: int) -> None:
        self._parent = list(range(n))

    def find(self, i: int) -> int:
        root = i
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[i] != root:  # path compression
            self._parent[i], i = root, self._parent[i]
        return root

    def union(self, keep: int, absorb: int) -> None:
        """Point `absorb`'s root at `keep`'s root. Caller decides which wins, so
        the surviving root is predictable rather than rank-dependent."""
        self._parent[self.find(absorb)] = self.find(keep)


def merge_superpixels(
    graph: SuperpixelGraph,
    means: dict[int, dict[str, float | None]],
    valid_counts: dict[int, dict[str, int]],
    *,
    criteria: dict[str, float],
    relax_factor: float,
    min_area_ha: float,
    max_area_ha: float,
    min_defined_criteria: int,
    min_frac_valid: float,
    max_pass2_iterations: int,
    centroids: dict[int, tuple[float, float]] | None = None,
    pass2_skip_at_min_area: bool = False,
    pass2_soft_ceiling: bool = False,
) -> MergeResult:
    """Run both passes and return the stand assignment plus diagnostics.

    `pass2_skip_at_min_area` chooses what pass 2 does with a region that was
    undersized when the sweep listed it and has reached `min_area_ha` by the
    time its turn comes (a smaller region joined it earlier in the sweep).
    False, the default and the behaviour of every earlier run: it still takes
    its turn and can be merged once more. True: it is skipped, since it is no
    longer undersized. See docs/decisions.yaml, spec-merge-pass2-skip-at-minimum.

    `pass2_soft_ceiling` chooses the ceiling pass 2 works under. False, the
    default and the behaviour of every earlier run: `max_area_ha`, as in pass 1.
    True: a region whose area is still below `min_area_ha` when its turn comes
    may join a neighbour even if the result is over `max_area_ha`, up to
    `max_area_ha + min_area_ha` (`pass2_partner` below gives the order of
    choice). The diagnostics then also say how many merges went over
    `max_area_ha`, how many stands ended over it and by how much, and how many
    of those stands never merged. Pass 1, and a region that has reached the
    minimum by its turn, keep `max_area_ha`. See docs/decisions.yaml,
    spec-merge-pass2-soft-ceiling.
    """
    n = graph.n_regions
    if n == 0:
        return MergeResult(assignment=[], n_stands=0, diagnostics={"n_superpixels": 0})

    bands = sorted(criteria)
    uf = _UnionFind(n)
    regions: dict[int, _Region] = {}
    for i in range(n):
        m = means.get(i, {})
        c = valid_counts.get(i, {})
        lon, lat = (centroids or {}).get(i, (0.0, 0.0))
        px = graph.n_pixels[i]
        # A None mean means the band has no valid pixel in this region. Carry it
        # as (sum 0, valid 0) rather than (sum 0, valid n): the mean stays
        # undefined instead of collapsing to 0.0, and a merge with a region that
        # does have data inherits only that region's evidence.
        defined = {b: m.get(b) for b in bands}
        regions[i] = _Region(
            n_pixels=px,
            sums={
                b: (0.0 if v is None else float(v) * c.get(b, 0))
                for b, v in defined.items()
            },
            valid={
                b: (0 if v is None else c.get(b, 0)) for b, v in defined.items()
            },
            lon_sum=lon * px,
            lat_sum=lat * px,
        )

    px_to_ha = graph.scale_m * graph.scale_m / 10_000.0

    def area(root: int) -> float:
        return regions[root].n_pixels * px_to_ha

    # The ceilings a merge is held to, in whole pixels (review B18): a merge adds
    # the two regions' pixels and compares the sum with these. Adding two float
    # areas judged some merges that end exactly on a ceiling as over it (at 3 ha,
    # 10 of the 299 ways to split 300 px). The minimum is compared as before, a
    # region's area against min_area_ha.
    max_px = _whole_pixels_within(graph.scale_m, max_area_ha)
    soft_ceiling_px = _whole_pixels_within(graph.scale_m, max_area_ha, min_area_ha)

    def joined_px(a: int, b: int) -> int:
        """The pixels of two regions together."""
        return regions[a].n_pixels + regions[b].n_pixels

    def order_key(root: int) -> tuple[float, float, int]:
        """Deterministic tie-break: centroid, then dense index.

        Not SNIC labels: the two arms' tessellations diverge run to run, so
        label order is not a stable thing to sort by. Rounded to 7 decimal
        places (~1 cm) so float noise cannot reorder otherwise-equal stands.

        What the code does, recorded 20 Oct 2026 (review C12): the dense index
        is the rank of the root superpixel's SNIC label (`fmu.utils.adjacency`
        numbers the sorted labels 0 to n - 1), so where two centroids agree to
        7 decimals this key falls back on SNIC label order. And the shared-edge
        fallback of `pass2_partner` does not use this key: a tie there, two
        neighbours sharing boundaries of the same length, goes to the lower
        root index, which is SNIC label order
        (tests/test_region_merge.py::test_a_fallback_tie_goes_to_the_lower_root_index_the_snic_label_order).
        The register entry spec-merge-runs-client-side-uncached says ties are
        broken by centroid; whether the code or the entry is to change is a
        question for Jaskaran.
        """
        lon, lat = regions[root].centroid()
        return (round(lon, 7), round(lat, 7), root)

    def compare(a: int, b: int, tolerances: dict[str, float]) -> tuple[bool, float, int]:
        """(passes gate, distance, number of criteria defined on both sides).

        The third element is the count of criteria defined on BOTH regions, and it
        has to be the full count even when the gate fails, because the caller uses
        it to attribute the rejection:

            if n_defined < min_defined_criteria: blocked_undefined += 1

        This used to return the moment a band exceeded its tolerance, so the count
        was "criteria checked so far". With min_defined_criteria=2 and the first
        band failing, a genuine tolerance rejection was filed under
        pass1_pairs_blocked_by_undefined_criteria_round1 -- and the ordering makes
        that the common case rather than a corner one, since `criteria` declares
        canopy_height first and canopy_height is documented as the binding band.

        So: no early return. Every defined criterion is counted, and the tolerance
        failure is carried in a flag. `d` is not accumulated for a band that
        exceeded, which costs nothing -- the distance is only read when the gate
        passes, and math.inf is returned otherwise either way.
        """
        d = 0.0
        n_defined = 0
        exceeded = False
        for band, tol in tolerances.items():
            ma, mb = regions[a].mean(band), regions[b].mean(band)
            if ma is None or mb is None:
                continue
            n_defined += 1
            delta = abs(ma - mb)
            if delta > tol:
                exceeded = True
                continue
            d += (delta / tol) ** 2
        if exceeded or n_defined < min_defined_criteria:
            return (False, math.inf, n_defined)
        return (True, d, n_defined)

    # Provenance: one (surviving root, counter name) per merge, in the order the
    # merges happen. Appended to where a merge happens and read only after the
    # stands are numbered; neither pass looks at it.
    merges_made: list[tuple[int, str]] = []

    # ---- Pass 1: merge homogeneous neighbours, to convergence ----
    pass1_rounds = 0
    pass1_merges = 0
    pass1_blocked_by_area = 0
    pass1_blocked_by_undefined = 0
    while True:
        candidates: list[tuple[float, tuple[float, float, int], int, int]] = []
        blocked_area = 0
        blocked_undefined = 0
        for i, j in graph.edges:
            a, b = uf.find(i), uf.find(j)
            if a == b:
                continue
            if joined_px(a, b) > max_px:
                blocked_area += 1
                continue
            ok, d, n_defined = compare(a, b, criteria)
            if not ok:
                if n_defined < min_defined_criteria:
                    blocked_undefined += 1
                continue
            lo, hi = (a, b) if order_key(a) <= order_key(b) else (b, a)
            candidates.append((d, order_key(lo), lo, hi))
        if pass1_rounds == 0:
            pass1_blocked_by_area = blocked_area
            pass1_blocked_by_undefined = blocked_undefined
        if not candidates:
            break

        candidates.sort()
        touched: set[int] = set()
        merged_this_round = 0
        for _d, _key, a, b in candidates:
            if a in touched or b in touched:
                continue
            ra, rb = uf.find(a), uf.find(b)
            if ra == rb:
                continue
            # Re-check: earlier merges this round may have grown one side past
            # the cap. Skipping is correct -- the pair gets reconsidered next
            # round against the grown region.
            if joined_px(ra, rb) > max_px:
                continue
            keep, gone = (ra, rb) if order_key(ra) <= order_key(rb) else (rb, ra)
            merges_made.append((keep, "n_pass1"))  # provenance only
            regions[keep].absorb(regions[gone])
            del regions[gone]
            uf.union(keep, gone)
            touched.update((a, b, ra, rb))
            merged_this_round += 1
        if not merged_this_round:
            break
        pass1_merges += merged_this_round
        pass1_rounds += 1

    log.info(
        "  merge pass 1: %d merges over %d rounds -> %d regions",
        pass1_merges,
        pass1_rounds,
        len(regions),
    )

    # ---- Pass 2: eliminate undersized regions ----
    relaxed = {b: t * relax_factor for b, t in criteria.items()}
    # With pass2_soft_ceiling on: the most a pass-2 merge of a region below
    # min_area_ha may make, and what Config.max_component_pixels() is derived
    # from. It is checked, in whole pixels (soft_ceiling_px), on the result of
    # each merge, not assumed from "below the minimum plus at most max_area_ha":
    # a neighbour already over max_area_ha after an earlier such merge could
    # otherwise take a second region and pass it.
    soft_ceiling_ha = max_area_ha + min_area_ha
    pass2_merges = 0
    pass2_fallback_merges = 0
    # With pass2_soft_ceiling on: the merges that took a region over
    # max_area_ha, by a relaxed match and by the shared-edge fallback. "Over"
    # is decided as the hard ceiling decides it, in whole pixels, so a merge
    # that ends exactly on max_area_ha is not over it, as stands_over_max_area,
    # which compares to 6 decimals, does not count the stand it makes.
    pass2_relaxed_over_max = 0
    pass2_fallback_over_max = 0
    pass2_iterations = 0

    # Both of these used to scan the whole edge dict on every call, and shared_edge
    # is called once per fitting neighbour inside a max(), so pass 2 cost roughly
    # iterations x undersized x degree x |E|. At the ~1300 superpixels a live run
    # produces that is a couple of seconds and invisible. At merge.max_superpixels
    # = 50000 -- a limit the code advertises as reachable -- it is hours of pure
    # Python, which would look like a hang rather than a cost.
    #
    # Built once here from the post-pass-1 union-find state, then maintained
    # incrementally by _fuse() at the single place pass 2 merges. They deliberately
    # outlive the pass-2 loop: the orphan-classification pass below calls
    # root_neighbours() again, once per surviving undersized root.
    def _pair(a: int, b: int) -> tuple[int, int]:
        return (a, b) if a < b else (b, a)

    adjacency: dict[int, set[int]] = {r: set() for r in regions}
    shared_px: dict[tuple[int, int], int] = {}
    for (_i, _j), _count in graph.edges.items():
        _a, _b = uf.find(_i), uf.find(_j)
        if _a == _b:
            continue
        adjacency.setdefault(_a, set()).add(_b)
        adjacency.setdefault(_b, set()).add(_a)
        _k = _pair(_a, _b)
        shared_px[_k] = shared_px.get(_k, 0) + _count

    def root_neighbours(root: int) -> set[int]:
        return {n for n in adjacency.get(root, ()) if n in regions}

    def shared_edge(root_a: int, root_b: int) -> float:
        return shared_px.get(_pair(root_a, root_b), 0) * float(graph.scale_m)

    def _fuse(keep: int, gone: int) -> None:
        """Fold `gone`'s adjacency into `keep`. Called once per pass-2 merge."""
        for nb in adjacency.pop(gone, set()):
            adjacency.get(nb, set()).discard(gone)
            count = shared_px.pop(_pair(gone, nb), 0)
            if nb == keep:
                continue
            if count:
                key = _pair(keep, nb)
                shared_px[key] = shared_px.get(key, 0) + count
            adjacency[nb].add(keep)
            adjacency.setdefault(keep, set()).add(nb)
        adjacency.setdefault(keep, set()).discard(gone)

    def pass2_partner(r: int) -> tuple[int, bool, bool] | None:
        """The neighbour `r` joins in pass 2, or None if none can take it.

        Returns (partner, by the shared-edge fallback, result over max_area_ha).
        Neighbours that keep the result at most max_area_ha are `fitting`. With
        pass2_soft_ceiling on and `r` still below min_area_ha, those that take
        it over max_area_ha but not over soft_ceiling_ha are `over`, and the
        order of choice is (spec-merge-pass2-soft-ceiling):

          1. a fitting neighbour that passes the relaxed tolerances, the closest;
          2. else an over one that passes them, the closest;
          3. else the fitting neighbour sharing the longest boundary;
          4. else the over one sharing the longest boundary;
          5. else none (area-blocked).

        Otherwise `over` is empty and this is the rule of every earlier run:
        steps 1 and 3 over the fitting neighbours. Closest is `d` under the
        relaxed tolerances, ties broken by order_key; the longest boundary is
        Xiong's eliminate-pass fallback, ties broken by the lower root index:
        SNIC label order, not the centroid order_key gives (review C12; see
        order_key).
        """
        soft = pass2_soft_ceiling and area(r) < min_area_ha
        fitting: list[int] = []
        over: list[int] = []
        for nb in sorted(root_neighbours(r), key=order_key):
            if joined_px(r, nb) <= max_px:
                fitting.append(nb)
            elif soft and joined_px(r, nb) <= soft_ceiling_px:
                over.append(nb)
        for candidates, over_max in ((fitting, False), (over, True)):
            scored = []
            for nb in candidates:
                ok, d, _ = compare(r, nb, relaxed)
                if ok:
                    scored.append((d, order_key(nb), nb))
            if scored:
                scored.sort()
                return scored[0][2], False, over_max
        for candidates, over_max in ((fitting, False), (over, True)):
            if candidates:
                partner = max(
                    candidates, key=lambda nb: (shared_edge(r, nb), -order_key(nb)[2])
                )
                return partner, True, over_max
        return None

    for _ in range(max_pass2_iterations):
        undersized = sorted(
            (r for r in regions if area(r) < min_area_ha),
            key=lambda r: (area(r), order_key(r)),
        )
        if not undersized:
            break
        pass2_iterations += 1
        progress = False
        for r in undersized:
            if r not in regions:
                continue  # absorbed earlier in this same sweep
            if pass2_skip_at_min_area and area(r) >= min_area_ha:
                continue  # grew to the minimum earlier in this sweep: not undersized
            chosen = pass2_partner(r)
            if chosen is None:
                continue  # area-blocked; reported below
            partner, used_fallback, over_max = chosen
            # Merge the smaller region into the larger, so the surviving root is
            # the one with more evidence behind its attributes.
            keep, gone = (
                (partner, r)
                if regions[partner].n_pixels >= regions[r].n_pixels
                else (r, partner)
            )
            merges_made.append(  # provenance only
                (keep, "n_fallback" if used_fallback else "n_relaxed")
            )
            regions[keep].absorb(regions[gone])
            del regions[gone]
            uf.union(keep, gone)
            _fuse(keep, gone)
            pass2_merges += 1
            pass2_fallback_merges += int(used_fallback)
            if over_max:
                if used_fallback:
                    pass2_fallback_over_max += 1
                else:
                    pass2_relaxed_over_max += 1
            progress = True
        if not progress:
            break

    if pass2_iterations >= max_pass2_iterations and any(
        area(r) < min_area_ha for r in regions
    ):
        log.warning(
            "  merge pass 2 hit its %d-iteration cap with regions still below "
            "min_area_ha. Reporting them rather than looping.",
            max_pass2_iterations,
        )

    log.info(
        "  merge pass 2: %d merges (%d via the shared-edge fallback) over %d "
        "sweeps -> %d stands",
        pass2_merges,
        pass2_fallback_merges,
        pass2_iterations,
        len(regions),
    )
    if pass2_soft_ceiling:
        log.info(
            "  merge pass 2 soft ceiling: %d merges went over max_area_ha "
            "(%d relaxed, %d via the shared-edge fallback), none past %.4f ha",
            pass2_relaxed_over_max + pass2_fallback_over_max,
            pass2_relaxed_over_max,
            pass2_fallback_over_max,
            soft_ceiling_ha,
        )

    # ---- Number the stands and classify what did not merge ----
    roots = sorted(regions, key=order_key)
    root_to_stand = {root: sid for sid, root in enumerate(roots)}
    assignment = [root_to_stand[uf.find(i)] for i in range(n)]

    # The ceiling a stand below the minimum had to join a neighbour under, in
    # whole pixels: max_area_ha, or with pass2_soft_ceiling on, soft_ceiling_ha.
    ceiling_below_min_px = soft_ceiling_px if pass2_soft_ceiling else max_px
    orphans_isolated = 0
    orphans_area_blocked = 0
    orphans_no_attribute_match = 0
    area_in_undersized_ha = 0.0
    stands_below_min_area = 0
    # Provenance: root -> which of the three branches below counted it. Written
    # in the same branch as its total, so the two cannot disagree.
    why_below_min: dict[int, str] = {}
    for root in roots:
        if area(root) >= min_area_ha:
            continue
        stands_below_min_area += 1
        area_in_undersized_ha += area(root)
        nbrs = root_neighbours(root)
        if not nbrs:
            orphans_isolated += 1
            why_below_min[root] = "isolated"
        elif not any(joined_px(root, nb) <= ceiling_below_min_px for nb in nbrs):
            # Every neighbour is already too big to absorb this one under the
            # ceiling. This is the signal that max_area_ha is too tight, and it
            # is what stranded 163 of 388 regions in the min-3/max-4 prototype.
            orphans_area_blocked += 1
            why_below_min[root] = "area_blocked"
        else:
            # Reachable only if pass 2 ran out of iterations: the shared-edge
            # fallback ignores attributes, so a region with a fitting neighbour
            # is never stranded for want of a match.
            orphans_no_attribute_match += 1
            why_below_min[root] = "iteration_cap"

    stand_attributes: dict[int, dict[str, Any]] = {}
    stands_with_incomplete_criteria = 0
    for root in roots:
        sid = root_to_stand[root]
        reg = regions[root]
        attrs: dict[str, Any] = {
            "n_pixels": reg.n_pixels,
            "area_ha": round(area(root), 6),
        }
        incomplete = False
        for band in bands:
            frac = reg.frac_valid(band)
            attrs[f"frac_valid_{band}"] = round(frac, 6)
            # Below the floor the mean describes too little of the stand to be
            # reported as the stand's value. Null, not a number -- profiling
            # must not present a canopy height for a stand that mostly has none.
            attrs[band] = reg.mean(band) if frac >= min_frac_valid else None
            if frac < min_frac_valid:
                incomplete = True
        stands_with_incomplete_criteria += int(incomplete)
        stand_attributes[sid] = attrs

    # ---- Per-stand provenance: a tally of what happened above ----
    # Keys in PROVENANCE_FIELDS order. Nothing here feeds back into the merge.
    stand_provenance: dict[int, dict[str, Any]] = {
        root_to_stand[root]: {
            "n_superpx": 0,
            "n_pass1": 0,
            "n_relaxed": 0,
            "n_fallback": 0,
            "below_min": int(root in why_below_min),
            "below_why": why_below_min.get(root, ""),
        }
        for root in roots
    }
    for sid in assignment:
        stand_provenance[sid]["n_superpx"] += 1
    # `keep` may itself have been folded into another root later; `assignment`
    # already follows that, so it names the stand the merge ended up inside.
    for keep, counter in merges_made:
        stand_provenance[assignment[keep]][counter] += 1

    diagnostics: dict[str, Any] = {
        "n_superpixels": n,
        "n_stands": len(roots),
        "reduction_factor": round(n / len(roots), 3) if roots else 0.0,
        "pass1_rounds": pass1_rounds,
        "pass1_merges": pass1_merges,
        "pass1_pairs_blocked_by_area_round1": pass1_blocked_by_area,
        "pass1_pairs_blocked_by_undefined_criteria_round1": pass1_blocked_by_undefined,
        "pass2_iterations": pass2_iterations,
        "pass2_merges": pass2_merges,
        # The honest version of "surrounded by genuinely different forest": the
        # fallback ignores attributes, so these are the merges no relaxed
        # criterion could justify.
        "pass2_fallback_merges": pass2_fallback_merges,
        "stands_below_min_area": stands_below_min_area,
        "area_in_undersized_stands_ha": round(area_in_undersized_ha, 4),
        "orphans_isolated": orphans_isolated,
        "orphans_area_blocked": orphans_area_blocked,
        "orphans_no_attribute_match": orphans_no_attribute_match,
        "stands_with_incomplete_criteria": stands_with_incomplete_criteria,
    }
    if pass2_soft_ceiling:
        # Only with the setting on, so the diagnostics of every other run keep
        # exactly the keys they had. A stand is over max_area_ha when its area
        # as reported in stand_attributes is over max_area_ha taken to the same
        # 6 decimals, so a stand exactly at max_area_ha, which float arithmetic
        # can put a hair to either side of it, is not counted. A single
        # superpixel larger than max_area_ha counts too, and is counted again
        # as never merged: it came in that size, so the setting did not make it.
        reported_max_ha = round(max_area_ha, 6)
        stands_over = [
            sid for sid, a in stand_attributes.items() if a["area_ha"] > reported_max_ha
        ]
        excess = sorted(
            (stand_attributes[sid]["area_ha"] - max_area_ha for sid in stands_over),
            reverse=True,
        )
        diagnostics.update(
            {
                "pass2_relaxed_merges_over_max_area": pass2_relaxed_over_max,
                "pass2_fallback_merges_over_max_area": pass2_fallback_over_max,
                "stands_over_max_area": len(stands_over),
                "stands_over_max_area_never_merged": sum(
                    1 for sid in stands_over if stand_provenance[sid]["n_superpx"] == 1
                ),
                "excess_over_max_area_total_ha": round(sum(excess, 0.0), 4),
                "excess_over_max_area_largest_ha": round(excess[0], 4) if excess else 0.0,
                "excess_over_max_area_each_ha": [round(e, 4) for e in excess],
            }
        )
    return MergeResult(
        assignment=assignment,
        n_stands=len(roots),
        stand_attributes=stand_attributes,
        diagnostics=diagnostics,
        stand_provenance=stand_provenance,
    )


def calibrate_thresholds(
    graph: SuperpixelGraph,
    means: dict[int, dict[str, float | None]],
    criteria: dict[str, float],
    *,
    min_defined_criteria: int,
) -> dict[str, Any]:
    """Where the configured tolerances land in this AOI's own difference
    distribution, and what fraction of pairs the gate actually admits.

    Absolute units are the contract; this is the calibration tool. Two things it
    reports, and the second is the one that matters:

      - `percentile_of_threshold`: per band, the share of adjacent pairs whose
        difference falls at or below the tolerance. This is the number the spec
        originally described as "p60-p75", and taken alone it is misleading.
      - `joint_admit_rate`: the share of pairs the gate admits, of the
        `n_pairs_with_any_defined_criterion` pairs with at least one criterion
        defined on both sides. The gate admits a pair when every criterion
        defined on both sides is within its tolerance and at least
        `min_defined_criteria` of them are defined on both sides, as in
        `merge_superpixels`. The gate is conjunctive, so per-band marginals do
        not describe it: three criteria at ~54%, ~76% and ~79% marginal admit
        38.7% jointly, not the 32.4% independence would predict and not any of
        the marginals.

    Before 20 Oct 2026 (review C14) the joint rate also counted as admitted a
    pair with fewer than `min_defined_criteria` criteria defined that passed the
    ones it had, which the gate rejects; the joint rates recorded before then
    are from before the fix.

    A low joint rate is **not** a reason to loosen a threshold. Pass rate is a
    diagnostic, not an objective; tuning to a target admit rate is exactly the
    unprincipled-parameter critique this design exists to escape. Pass 1 also
    iterates to convergence, so a per-round rate is not the share of total
    merging. Choose thresholds on held-out R-squared at matched stand count.
    """
    bands = sorted(criteria)
    diffs: dict[str, list[float]] = {b: [] for b in bands}
    joint_pass = 0
    joint_total = 0
    for i, j in graph.edges:
        mi, mj = means.get(i, {}), means.get(j, {})
        passes_all = True
        n_defined = 0
        for band in bands:
            a, b = mi.get(band), mj.get(band)
            if a is None or b is None:
                continue
            n_defined += 1
            delta = abs(a - b)
            diffs[band].append(delta)
            if delta > criteria[band]:
                passes_all = False
        if n_defined:
            joint_total += 1
            joint_pass += int(passes_all and n_defined >= min_defined_criteria)

    def pct(sorted_vals: list[float], threshold: float) -> float:
        if not sorted_vals:
            return float("nan")
        below = sum(1 for v in sorted_vals if v <= threshold)
        return round(100.0 * below / len(sorted_vals), 2)

    def quantile(sorted_vals: list[float], q: float) -> float | None:
        if not sorted_vals:
            return None
        idx = min(len(sorted_vals) - 1, int(q * len(sorted_vals)))
        return round(sorted_vals[idx], 6)

    report: dict[str, Any] = {"n_pairs": len(graph.edges), "per_band": {}}
    for band in bands:
        vals = sorted(diffs[band])
        report["per_band"][band] = {
            "threshold": criteria[band],
            "n_pairs_defined": len(vals),
            "percentile_of_threshold": pct(vals, criteria[band]),
            "p25": quantile(vals, 0.25),
            "p50": quantile(vals, 0.50),
            "p75": quantile(vals, 0.75),
            "p90": quantile(vals, 0.90),
        }
    report["joint_admit_rate_pct"] = (
        round(100.0 * joint_pass / joint_total, 2) if joint_total else float("nan")
    )
    report["n_pairs_with_any_defined_criterion"] = joint_total
    return report
