"""Two-pass region merge over a superpixel adjacency graph.

Follows Xiong et al. 2024 section 2.6. Pure Python over the graph
`fmu.utils.adjacency` brings down, so it is fully unit-testable without Earth
Engine; the stage wrapper turns the result back into an `ee.Image` with
`snic_clusters.remap(...)`.

Pass 1 -- merge homogeneous neighbours, iterating to convergence:
  - a pair is eligible if their areas sum to at most `max_area_ha`;
  - a **hard gate**, not a weighted sum: reject if *any* shared criterion
    exceeds its tolerance. This is Xiong's design and it keeps thresholds
    interpretable in physical units;
  - eligible pairs merge in ascending `d = sum (|delta| / tol)^2`, skipping any
    region already merged this round.

Pass 2 -- eliminate undersized regions, smallest first:
  - same rule with tolerances multiplied by `relax_factor`;
  - if no neighbour passes even relaxed, absorb into the neighbour sharing the
    longest boundary. This fallback is what prevents orphans;
  - **the fallback still respects `max_area_ha`.** Violating it would break the
    derived `max_component_pixels` and silently delete the largest stands, which
    is the exact failure that cap exists to prevent. Regions that cannot be
    placed stay undersized and get reported.

Two properties this file is careful about:

**Attribute means are weighted by per-criterion valid pixel count, not total
pixels.** Regions are carried as (sum, valid_count) per band rather than as a
mean, so merging adds both and the mean falls out correctly. Weighting by total
pixels would let a null-canopy region merging into a defined-canopy one inherit
a canopy height for territory that never measured one -- the merge would invent
data. 14 of the 1249 superpixels in the committed baseline run have no
`canopy_height` at all (ETH no-data), so this is not hypothetical.

**A pair needs at least `min_defined_criteria` criteria defined on both sides.**
One criterion is too weak a similarity test to justify a pass-1 merge. Pairs
that fall short drop to pass 2, which is the right destination -- refusing to
merge them at all does not avoid a weak merge, it just leaves them to the
blinder shared-edge rule.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from fmu.utils.adjacency import SuperpixelGraph
from fmu.utils.logging import get_logger

log = get_logger(__name__)


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
) -> MergeResult:
    """Run both passes and return the stand assignment plus diagnostics."""
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
        regions[i] = _Region(
            n_pixels=px,
            sums={
                b: (0.0 if m.get(b) is None else float(m[b]) * c.get(b, 0))
                for b in bands
            },
            valid={b: (0 if m.get(b) is None else c.get(b, 0)) for b in bands},
            lon_sum=lon * px,
            lat_sum=lat * px,
        )

    px_to_ha = graph.scale_m * graph.scale_m / 10_000.0

    def area(root: int) -> float:
        return regions[root].n_pixels * px_to_ha

    def order_key(root: int) -> tuple[float, float, int]:
        """Deterministic tie-break: centroid, then dense index.

        Not SNIC labels: the two arms' tessellations diverge run to run, so
        label order is not a stable thing to sort by. Rounded to 7 decimal
        places (~1 cm) so float noise cannot reorder otherwise-equal stands.
        """
        lon, lat = regions[root].centroid()
        return (round(lon, 7), round(lat, 7), root)

    def compare(a: int, b: int, tolerances: dict[str, float]) -> tuple[bool, float, int]:
        """(passes gate, distance, number of criteria defined on both sides)."""
        d = 0.0
        n_defined = 0
        for band, tol in tolerances.items():
            ma, mb = regions[a].mean(band), regions[b].mean(band)
            if ma is None or mb is None:
                continue
            n_defined += 1
            delta = abs(ma - mb)
            if delta > tol:
                return (False, math.inf, n_defined)
            d += (delta / tol) ** 2
        if n_defined < min_defined_criteria:
            return (False, math.inf, n_defined)
        return (True, d, n_defined)

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
            if area(a) + area(b) > max_area_ha:
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
            if area(ra) + area(rb) > max_area_ha:
                continue
            keep, gone = (ra, rb) if order_key(ra) <= order_key(rb) else (rb, ra)
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
    pass2_merges = 0
    pass2_fallback_merges = 0
    pass2_iterations = 0

    def root_neighbours(root: int) -> set[int]:
        out: set[int] = set()
        for i, j in graph.edges:
            a, b = uf.find(i), uf.find(j)
            if a == root and b != root:
                out.add(b)
            elif b == root and a != root:
                out.add(a)
        return out

    def shared_edge(root_a: int, root_b: int) -> float:
        total = 0
        for (i, j), count in graph.edges.items():
            a, b = uf.find(i), uf.find(j)
            if {a, b} == {root_a, root_b}:
                total += count
        return total * float(graph.scale_m)

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
            fitting = sorted(
                (
                    nb
                    for nb in root_neighbours(r)
                    if area(r) + area(nb) <= max_area_ha
                ),
                key=order_key,
            )
            if not fitting:
                continue  # area-blocked; reported below
            scored = []
            for nb in fitting:
                ok, d, _ = compare(r, nb, relaxed)
                if ok:
                    scored.append((d, order_key(nb), nb))
            if scored:
                scored.sort()
                partner = scored[0][2]
                used_fallback = False
            else:
                # Xiong's eliminate-pass fallback: longest shared boundary.
                partner = max(
                    fitting, key=lambda nb: (shared_edge(r, nb), -order_key(nb)[2])
                )
                used_fallback = True
            # Merge the smaller region into the larger, so the surviving root is
            # the one with more evidence behind its attributes.
            keep, gone = (
                (partner, r)
                if regions[partner].n_pixels >= regions[r].n_pixels
                else (r, partner)
            )
            regions[keep].absorb(regions[gone])
            del regions[gone]
            uf.union(keep, gone)
            pass2_merges += 1
            pass2_fallback_merges += int(used_fallback)
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

    # ---- Number the stands and classify what did not merge ----
    roots = sorted(regions, key=order_key)
    root_to_stand = {root: sid for sid, root in enumerate(roots)}
    assignment = [root_to_stand[uf.find(i)] for i in range(n)]

    orphans_isolated = 0
    orphans_area_blocked = 0
    orphans_no_attribute_match = 0
    area_in_undersized_ha = 0.0
    stands_below_min_area = 0
    for root in roots:
        if area(root) >= min_area_ha:
            continue
        stands_below_min_area += 1
        area_in_undersized_ha += area(root)
        nbrs = root_neighbours(root)
        if not nbrs:
            orphans_isolated += 1
        elif not any(area(root) + area(nb) <= max_area_ha for nb in nbrs):
            # Every neighbour is already too big to absorb this one. This is the
            # signal that max_area_ha is too tight, and it is what stranded 163
            # of 388 regions in the min-3/max-4 prototype.
            orphans_area_blocked += 1
        else:
            # Reachable only if pass 2 ran out of iterations: the shared-edge
            # fallback ignores attributes, so a region with a fitting neighbour
            # is never stranded for want of a match.
            orphans_no_attribute_match += 1

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

    diagnostics = {
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
    return MergeResult(
        assignment=assignment,
        n_stands=len(roots),
        stand_attributes=stand_attributes,
        diagnostics=diagnostics,
    )


def calibrate_thresholds(
    graph: SuperpixelGraph,
    means: dict[int, dict[str, float | None]],
    criteria: dict[str, float],
) -> dict[str, Any]:
    """Where the configured tolerances land in this AOI's own difference
    distribution, and what fraction of pairs the gate actually admits.

    Absolute units are the contract; this is the calibration tool. Two things it
    reports, and the second is the one that matters:

      - `percentile_of_threshold`: per band, the share of adjacent pairs whose
        difference falls at or below the tolerance. This is the number the spec
        originally described as "p60-p75", and taken alone it is misleading.
      - `joint_admit_rate`: the share of pairs passing *all* criteria at once.
        The gate is conjunctive, so per-band marginals do not describe it: three
        criteria at ~54%, ~76% and ~79% marginal admit 38.7% jointly, not the
        32.4% independence would predict and not any of the marginals.

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
        any_defined = False
        for band in bands:
            a, b = mi.get(band), mj.get(band)
            if a is None or b is None:
                continue
            any_defined = True
            delta = abs(a - b)
            diffs[band].append(delta)
            if delta > criteria[band]:
                passes_all = False
        if any_defined:
            joint_total += 1
            joint_pass += int(passes_all)

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
