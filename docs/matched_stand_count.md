# Matched stand count for held-out R²

**Status: design note. Nothing here is implemented.**

## The gap

Three places in this repo say that held-out R² must be read at a matched stand count:

- `README.md` — choose thresholds on held-out R² at matched stand count
- `calibrate_thresholds()`'s docstring — the same
- `explained_variance_r2()` — warns in its docstring that R² rises monotonically with region
  count, and the metrics stage prints `n_stands` beside every R² row it emits

Nothing equalises it. The warning is real and the number is printed, but the comparison the
warning exists to protect is left to the reader to perform, on two runs that were never
constrained to be comparable.

## Why it bites

R² here is `1 − SS_within/SS_total` over regions. In the limit of one region per pixel,
SS_within is 0 and R² is 1.0 for any image whatsoever. So an arm that produces more stands
scores higher for free, and "arm A explains more variance than arm B" is unreadable unless
both produced the same number of stands.

This is not hypothetical for the comparison the thesis rests on. The two arms segment
different feature spaces — six hand-crafted bands versus a 64-dimensional embedding — and
`default_stage_names()` no longer forces a shared SNIC. Their stand counts are free to differ,
and the merge's area bounds do not pin them: `min_area_ha`/`max_area_ha` bound each stand, not
how many there are.

The baseline currently lands on 327 stands. If the AlphaEarth arm lands on, say, 500, its R²
will be higher and the difference will be mostly arithmetic.

## Three mechanisms, and what each costs

### A. Tune `segmentation.size` per arm until the counts match

Run each arm at several SNIC seed spacings, pick the pair whose stand counts agree, compare
R² there.

- **Honest.** Both arms are compared at a count neither was tuned to favour.
- **Expensive.** Each probe is a full cold SNIC plus merge; matching to within a few percent
  could take several rounds per arm.
- **Confounded.** Changing `size` changes the superpixels the merge starts from, so it changes
  what a stand *is*, not just how many there are. Matching the count this way may buy the
  comparison at the cost of the thing being compared.

### B. Report R² as a curve against `n_stands`, not a scalar

Sweep each arm across a range of stand counts and plot R² against `n_stands`. Compare curves,
not points.

- **Strictly more informative.** It shows whether one arm dominates everywhere or only at one
  operating point, which a single matched comparison cannot.
- **Robust to the confound in A**, because no count is privileged.
- **Costs the same compute as A**, but yields more for it.
- **Harder to state.** "Arm A's curve is above arm B's over 200–600 stands" is a weaker
  headline than a single number, and if the curves cross there is no headline at all — which
  is itself worth knowing.

### C. Subsample stands to the smaller count before computing R²

Take the arm with more stands, drop stands at random until the counts match, recompute.

- **Cheap** — no re-segmentation, and it can be done from existing artifacts.
- **Wrong.** Dropping stands does not undo the finer partition; the surviving stands are still
  the small ones the finer segmentation produced, so SS_within stays low. It equalises the
  count without equalising what the count was standing in for.

Recorded so it is not proposed later as the obvious cheap fix. It is not one.

## Recommendation

**B**, with A as a fallback if a single number is needed for a specific claim.

The curve is the honest object, and the sweep it needs is the same sweep A needs anyway. If a
scalar is required — a table cell, an abstract — quote the curve at a stated `n_stands` and
say so in the caption, rather than quoting a bare R².

## What implementing it would touch

- `metrics.r2_attributes` already names the attributes; no schema change needed there.
- A sweep driver would sit in `scripts/`, not in the pipeline: it re-runs the existing stages
  at several `segmentation.size` values and collects `(n_stands, R²)` pairs.
- Each point in the sweep is a distinct config fingerprint, so the cache handles it correctly
  without change — `segmentation` is a cache-relevant block.
- `report.py` would gain a curve figure; `fig_separating_power`'s neighbour, and subject to the
  same rule that a ranking is not evidence without a null.

## What must not happen

Do not equalise the count by lowering `min_defined_criteria`, widening `merge.criteria`
tolerances, or moving `min_area_ha`/`max_area_ha` to hit a target. Those change what a stand is
in order to make a number comparable, which is the tuning-to-a-target failure the standing
rules already forbid, wearing a different hat.
