# DRAFT decisions.md entry: clustering passes a measured reduceConnectedComponents neighbourhood

Status: draft for phd-notebook/decisions.md. Code change is uncommitted on
phd-code branch `phase2-stand-validation` (src/fmu/stages/clustering.py,
tests/test_clustering_neighbourhood.py, tests/test_clustering_live.py, docs).

## Symptom

ClusteringStage on the Odisha AlphaEarth config (64 embedding bands) failed
with "User memory limit exceeded" on the first getInfo after the per-unit means.
The hand-crafted Odisha configs (22 bands) ran on the same stands, AOI and
scale.

## Cause

`reduceConnectedComponents(maxSize=N)` treats N as an EXTENT in pixels and pads
every tile by N. tileScale does not shrink that pad. The pipeline passed
`Config.max_component_pixels()`, which is a pixel COUNT cap: 1200 px at
merge.max_area_ha = 10 ha and 10 m. So each 256 px tile was evaluated over about
(256 + 2 x 1200)^2 = 2656^2 px per band. Memory scales with bands x pad, and
64 bands crossed the limit where 22 did not.

## Mechanism of the fix

ClusteringStage still runs `assert_components_fit` against the cap, unchanged.
It then measures each label's min/max pixel coordinates (x, y) with
`pixelCoordinates` + `minMax().repeat(2).group(label)` over the ROI, with no
bestEffort and maxPixels 1e9, in two grids:

  - the feature stack's band-0 projection at analysis_scale_m (EPSG:4326 here),
  - the label image's projection at analysis_scale_m (UTM here).

widest = max over labels and grids of `round(max span) + 1`.
neighbourhood = `min(cap, ceil(widest x 1.2) + 2)`
(`_RCC_EXTENT_MARGIN`, `_RCC_EXTENT_PAD_PX`).
That value is passed as maxSize. The stage metadata records
`rcc_neighbourhood_px` and `widest_unit_extent_px`.

Fail loud (ENG-012): if either measurement returns no groups while the label
histogram found labels, the stage raises. It does not fall back to the cap. If
the cap binds and widest > 2 x largest_component_px, it logs a WARNING that a
label reused across disjoint places inflated the extent.

## Invariant argument (why every unit is still aggregated whole)

Note: an earlier version of this argument said "nothing was masked at the cap,
because assert_components_fit bounds the count". That is unsound across grids.
The count is measured in the UTM label grid, while reduceConnectedComponents
runs in the feature band-0 grid (EPSG:4326), where extents are ~1/cos(lat)
larger. Corrected argument:

EE masks an object only when it is strictly larger than maxSize in either
dimension.

1. Cap does not bind (neighbourhood < cap). neighbourhood > widest, and widest is
   measured in the grid the reduction evaluates in. So no label exceeds maxSize,
   and each is aggregated over all its pixels. The old call, at maxSize = cap >
   neighbourhood > widest, also masked nothing, since no label is wider than
   widest in that grid. Both versions average the same pixels per unit.
2. Cap binds (neighbourhood == cap). The argument passed is the old argument, so
   behaviour is exactly the old behaviour, including any pre-existing edge case
   at the cap.

The reduced stack's band-0 grid is the feature band-0 grid. This was verified
live, not only assumed: identical projection, and identical widest extent
(AlphaEarth 128 px in both, v120 91 px in both;
scratchpad/clustfix/review_proj.json).

Values agree up to floating-point summation order, not bit for bit. A different
tiling can change the order in which EE sums a unit's pixels. Do not expect
byte-identical metadata JSON.

Precondition: the argument holds when the lazy outputs are evaluated at
analysis_scale_m in the measured grids. This holds for today's pipeline:

  - cache exports (`caching.start_export`) and Drive exports pass `scale` with
    no `crs`, so they use the image's first-band CRS at that scale;
  - profiling and export reduce at `scale` with no `crs`, reading either cached
    assets or the same lazy graph;
  - the only unmeasured difference is grid origin alignment on export (same CRS
    and scale), worth about a pixel of extent. The x1.2 + 2 px margin absorbs it.

Evaluating the lazy cluster_labels in another CRS or at a coarser scale is
outside the argument.

## Live evidence (Odisha, 2026-09-14; scripts in scratchpad/clustfix/)

OLD = HEAD copy of clustering.py, NEW = this change, both on the same cached
upstream context (equiv_live.py -> equiv_odisha_*.json).

| | v120 hand-crafted | current hand-crafted |
|---|---|---|
| widest extent / neighbourhood (px) | 91 / 112 | 103 / 126 |
| cap (px) | 1200 | 1200 |
| cluster_labels NEW vs OLD, whole ROI | neq 0, maskneq 0 | neq 0, maskneq 0 |
| sample confusion NEW vs OLD | diagonal, agreement 1.0 (n 2389) | diagonal, agreement 1.0 (n 2388) |
| discrete clustering_metadata fields | identical | identical |
| log_offsets max abs diff | 0.0 | 3.3e-16 |
| scaling max abs diff | 0.0 | 2.4e-14 |
| training rows | 178, same labels and order, max abs 7.3e-14 (150 of 178 bitwise equal) | 172, same labels and order, max abs 1.94e-13 (0 bitwise equal) |

AlphaEarth end to end (NEW; run_alphaearth_clustering.py, run_alphaearth.log):
ClusteringStage.run completed in 153.7 s. 184 stands, largest 1000 px (cap
1200). Widest extent 128 px (4326 grid; 120 px in UTM), neighbourhood 156 px.
64 active bands, 3 log-transformed (A24, A31, A56). n_training_units 162 of 184
(22 outside habitat). The cluster_labels frequencyHistogram evaluated, and all 6
clusters are populated. OLD, at maxSize 1200, hit the user memory limit on this
config.

Site-specific numbers, for the record: Odisha's widest stand is 128 px in the
EPSG:4326 feature grid vs 120 px in the UTM label grid (~1/cos 21 deg). The
stacks are 22 hand-crafted vs 64 AlphaEarth bands. The pad drops from 1200 px to
112-156 px per tile edge.

## Cache

`config_fingerprint` is unchanged, so existing cached cluster_labels /
feature_stack assets stay addressable. That is legitimate only because NEW
reproduces OLD (above). Nothing needs rebuilding because of this change.

Observed PRE-EXISTING drift, not caused by this change and not fixed by it: a
fresh recompute differs from the cached assets under OLD and NEW alike, and by
exactly the same amounts (drift_consistency: v120 0.0 / 0.0; current 3.3e-16 /
2.4e-14):

  - metadata floats differ only on terrain bands: elevation, slope, aspect_sin,
    aspect_cos, plus ~1e-14 noise elsewhere. v120 scaling up to 0.48 (elevation
    spread), log_offset slope 0.080. current scaling up to 0.21 (elevation
    spread). Discrete fields are identical.
  - cluster_labels, fresh vs cached, over the ROI:
    - v120: neq 50216 of 77338 pixel-weight units. Sample Hungarian agreement
      0.772; the cluster-to-cluster map is not the identity, so clusters 0/3/4
      are reshuffled and not merely renumbered.
    - current: neq 1698 of 77335, agreement 0.982.

The upstream terrain inputs appear to have changed since the cache was written.
Any Phase 2 statistic read from cached v120 cluster_labels is therefore not
what a fresh run would produce. That needs its own decision (rebuild with
`rebuild_cache.py --delete`, or pin and document the cached version).

## Known limits

- Valid at analysis_scale_m in the measured grids only (see Precondition).
- An elongated stand, or a label reused across disjoint places, can push the
  neighbourhood to the cap. A wide band stack can then run out of memory again.
  That failure is loud: the same EE error as before, with
  `widest_unit_extent_px` in the log, plus a WARNING for the disjoint case. It
  never silently changes values.
- Other call sites still pass the cap and would hit the same memory limit on a
  wide stack. Not changed in this round:
  - `src/fmu/stages/metrics.py:255` takes `max_component_px =
    config.max_component_pixels()`, passed as `maxSize` at
    `metrics.py:266-273` (per-stand confidence; a 1-band agreement map, so
    unlikely to OOM).
  - `src/fmu/stages/metrics.py:533` passes `config.max_component_pixels()` to
    `explained_variance_r2`, which calls reduceConnectedComponents at
    `src/fmu/utils/components.py:154-158` (r2_attributes bands; memory scales
    with the configured attributes).
  - `src/fmu/stages/merge.py:113` uses the cap only for `assert_components_fit`,
    with no reduceConnectedComponents call.
  - `scripts/inspect_metrics.py:146,183` prints the value only.
- profiling.py and export.py neither call reduceConnectedComponents nor read the
  cap. See the F9 note in the task report.
