# Phase 2 predictions

Written and committed **before any statistic relating field data to stands was computed.**
At the time of the commit the repo held the pipeline outputs and the plot↔stand join (plot
counts per stand, stand areas, boundary distances), and nothing that relates a field variable to
a stand. The git history of this file against `odisha_phase2_5_stats.py` and its results file is
the evidence.

A null result that was predicted is a finding. A null result that was not is a failed experiment.
This file is the difference between the two.

---

## Scope of what will be tested first

**The pilot AOI only.** It covers six Dhenkanal village forests (+200 m buffer, 912 ha) and 60
plots. The brief says to scale to the 21-habitation set only once the pilot is non-degenerate.
That set is additionally held because its AOI failed its own exit condition (267 plots inside,
not 261; see `odisha_phase2_0_results.txt`). **Decision (Jaskaran, 2026-09-14): include all
267.** The full set runs after the pilot.

What the pilot's geometry allows. These are geometry facts, computed from plot coordinates only:

- Nearest-neighbour plot spacing: p25 96 m, median 169 m, p75 222 m. **No plot has another within
  56 m** (the radius of a 1 ha disc); 31 of 60 have one within 178 m (a 10 ha disc).
- Plot pairs by separation: **14** at 0–100 m, 37 at 100–200 m, 106 at 200–400 m, 92 at 400–800 m;
  272 within-site pairs; 1,498 pairs more than 2 km apart.

**Consequences, stated now:**

1. `stands_snic` (~1 ha superpixels) will hold **0–3 multi-plot superpixels** in the pilot. Every
   SNIC-layer statistic will be degenerate and will be reported as *not estimable*, not as a
   result.
2. `stands_merged` (1–10 ha) should hold roughly **6–15 multi-plot stands containing 12–35
   plots**. The brief's "68 stands holding 204 of 274 plots" is a full-set figure, and the pilot
   is sparser than the Koraput habitations that dominate the full set.
3. The 0–100 m distance band has 14 pairs in total, so its same-stand/different-stand cells will be
   tiny. That band will be reported with its n and read as uninformative.
4. Whatever the outcome, **the pilot is underpowered for 6.1 and 6.2.** Only 6.3's distant-pair
   form has many pairs, and even then only 60 plots.

**Known when this file was committed**, stated so nothing above reads as a forecast of it. Step 4
had run: plots were joined to stands, but no statistic relating a field variable to a stand had
been computed. The counts were:

| arm / layer | stands | multi-plot stands | plots in them | plots > 30 m from a boundary |
|---|---|---|---|---|
| v120 / `stands_merged` | 197 | 13 | 35 | 14 |
| v120 / `stands_snic` | 868 | 4 | 10 | 4 |
| v120 / `stands_dissolved` | 97 | 7 | 59 | 52 |
| current / `stands_merged` | 188 | 11 | 32 | 15 |
| current / `stands_snic` | 872 | 5 | 16 | 3 |

Consequence 1 was drafted before the join and **missed**: 4 and 5 multi-plot superpixels, not 0–3.
They come from the two densest sites; Kerijoli has 10 plots in 8.3 ha. The SNIC layer is therefore
thin but estimable, and will be reported as such. Consequence 2 held: 13 and 11 merged stands
holding 35 and 32 plots.

---

## The standing prediction

From Phase 1 follow-up work: **within-site explained variance is expected to be low.** With
habitation means removed, ETH explains R² 0.029 of field Lorey's height and `vh_iqr` explains
0.003. The SNIC stack is built on bands with almost no within-site signal against field
variables. Every plot in the pilot is compared with plots in its own village forest or in another
village forest 5–25 km away, so the delineation question is a within-site question.

**Predicted outcome: the stands do not group field-similar plots better than a size-matched,
spatially coherent random partition does.**

> **Addendum, 2026-09-16 — source of the two R² figures above.** The values 0.029 (ETH) and 0.003
> (`vh_iqr`) have **no committed results file behind them**. They come from Phase 1 follow-up work
> whose output was never committed, so they cannot be reproduced from this repository as it stands.
> They are recorded here as unsourced. **No prediction is changed by this note** — the predictions
> in this document stand exactly as pre-registered at commit `78ba075`, and the standing prediction
> above does not depend on the two figures being exact, only on within-site explained variance
> being low. Re-deriving them was considered and set aside (decision of 2026-09-16).

---

## 6.1 Within- vs between-stand variance, R²_P(Y) = 1 − SS_within / SS_total

**Raw values will be high and mean nothing on their own.** For n plots in g groups placed at
random, E[R²] ≈ (g − 1)/(n − 1). Restricted to multi-plot stands, those are mostly pairs, so g ≈ n/2
and **E[R²] ≈ 0.45–0.55 from nothing.** Spatial autocorrelation adds to that: nearby plots are
alike and small stands hold nearby plots. The all-plots version is inflated further by singleton
stands, which contribute zero within-stand variance.

| variable | predicted raw R², restricted | predicted excess over rotation null (obs − null median) | predicted percentile vs rotation null |
|---|---|---|---|
| `loreys_h_m` | 0.4–0.8 | −0.10 to +0.10 | < 95 |
| `loreys_h_tree_m` | 0.4–0.8 | −0.10 to +0.10 | < 95 |
| `h_top5_m` | 0.4–0.8 | −0.10 to +0.10 | < 95 |
| `crown_cover_pct` | 0.4–0.8 | −0.10 to +0.10 | < 95 |
| `sal_ba_frac` | 0.4–0.8 | −0.10 to +0.10 | < 95 |
| `n_species` | 0.4–0.8 | −0.10 to +0.10 | < 95 |
| `dbh_mean_cm` | 0.4–0.8 | −0.10 to +0.10 | < 95 |

With 7 variables tested at p95, **0.35 false exceedances are expected by chance**, so one variable
above p95 on its own is within prediction. The variables are also correlated (the three height
measures especially), so exceedances would not be independent.

---

## 6.2 Pairwise boundary test

- `d_field` rises with `d_geo` in both measures: Bray–Curtis on relative basal-area composition,
  and |ΔLorey's|. Predicted.
- **Raw, stratified:** within a distance band, same-stand pairs will look *slightly* more similar
  than different-stand pairs, because inside a band same-stand pairs sit nearer its lower edge.
  A raw difference in the "stands work" direction is therefore **predicted, and not evidence.**
- **Against the null:** the same-stand minus different-stand difference in each band, and the
  `same_stand` coefficient in `d_field ~ d_geo + same_stand`, sit **inside the null's central 90%**.
- **Pairs where both plots are > 30 m from a stand boundary:** same prediction, with fewer pairs.
  If the all-pairs effect is null, it is not expected to appear in this subset.
- Within-band label-permutation p-values: predicted > 0.05. With the cell sizes above they have
  almost no power, and they do not control for the spatial structure the null does.

OLS standard errors on the pair regression are **not valid**: every plot appears in many pairs.
Only the null percentile is read.

---

## 6.3 Label agreement (a different question: typology, not delineation)

**Field forest type:** average-linkage (UPGMA) hierarchical clustering on Bray–Curtis
dissimilarity of **relative** species basal area, cut at **6 groups**. The types are derived
over **all 274 plots**, since the typology is a property of the field data. They are then
evaluated on whichever plots carry a stand `cluster_id` (60 in the pilot). Species identity is
the normalised binomial (see `odisha_phase2_3_join.py`), and records of every habit count
towards basal area.

Why: there is no Odisha forest-type key to hand, so a rule set (Sal-dominant if
`sal_ba_frac > 0.5`, and then what?) would be invented rules for the other 232 species strings.
Relative rather than absolute basal area keeps it a statement about composition, not stocking,
and plot size is unknown in any case. Six groups matches k, so ARI/NMI are not driven by a
granularity mismatch. A two-class Sal-dominant rule (`sal_ba_frac > 0.5`) is reported alongside
as a transparent secondary.

Predicted on the pilot's 60 plots, against the merged stand's `cluster_id`:

- **ARI: −0.05 to +0.10.** NMI: 0.05–0.25; NMI is biased upward at small n with 6×6 tables.
  Cramér's V: 0.25–0.45; V is also biased upward at small n. None of the three sits above the
  rotation null's p95.
- **Distant pairs (> 2 km):** same-label pairs are no more field-similar than different-label
  pairs; the difference falls inside the null's central 90%. The k-means label is built on
  ETH height, NDVI amplitude and radar, and none of them has shown composition signal beyond
  R² 0.03 at plot scale.

---

## Arms

- **`odisha_current_handcrafted` vs `odisha_v120_handcrafted`:** no detectable difference. The
  difference in excess-over-own-null falls inside either arm's null spread. The removed band
  scored R² = 0.000 against crown cover, so removing it should neither help nor hurt a field
  metric; it changes the partition without changing its field relevance.
- **`odisha_alphaearth`:** its k-means stage exceeded the Earth Engine interactive memory limit
  on the pilot (skew of `A00`), on four attempts with every input cached. **Decision (Jaskaran,
  2026-09-14): fix the clustering stage's memory use, then run the arm.** Its results arrive after
  this file is committed, and the prediction here is unchanged by that: no directional prediction. The embedding sees more than the
  hand-crafted stack, so a composition signal (Bray–Curtis, `sal_ba_frac`) is *possible*, but
  nothing in Phase 1 measured it. Predicted excess within ±0.10, as for the primary arm.
- **Raw R² is never compared across arms or layers.** The comparison is excess over each
  partition's own size-matched null, reported with stand count and area distribution beside it.

---

## What would be a surprise, and what it would mean

| outcome | what it would mean | what would follow |
|---|---|---|
| Primary arm, `loreys_h_m` or `crown_cover_pct` at ≥ p97.5 of the rotation null, same direction in the > 30 m boundary subset | Stands carry within-site structural signal that the band-level test could not see. An aggregation effect: a stand mean of a compressed product still ranks neighbouring stands. | Not believed on 60 plots. Needs the full set. The noise null planned as a second check failed its size check, so no second null corroborates it. It would contradict the Phase 1 within-site figures and would have to be reconciled with them, not reported over them. |
| Primary arm at ≤ p2.5 (stands *split* alike plots) | The merge criteria cut against field structure, e.g. ETH's compression merging tall and short plots while splitting alike ones on texture. | Would be a finding against the method as run, and a reason to look at which criterion does the splitting. |
| Composition (`sal_ba_frac`, Bray–Curtis) beyond p97.5 in the AlphaEarth arm only | The embedding delineates composition that the hand-crafted stack does not. | The first positive evidence for the embedding arm on field data; would need the full set. |
| ARI ≥ 0.2, or distant same-label pairs clearly more alike than different-label pairs | The k-means typology tracks forest type at landscape scale even if the delineation adds nothing within site. | A typology finding, **not** a delineation finding; it must not be reported as the stands working. |
| Fewer than 5 multi-plot merged stands | The pilot cannot answer 6.1 at all. | Reported as not estimable. The decision on whether and how to run the full set goes to Jaskaran. |
| Noise null size distribution does not match the observed partition (stand count off by > 25%, or median area off by > 50%) | The null is not size-matched, and excess over it is not interpretable. | Reported as a failed null, and the rotation null is read instead. **Not fixed by tuning the noise tolerances toward a match after seeing R².** **This happened before any statistic existed; see the Null models section.** |

---

## Null models, fixed before the statistics

**Decision (Jaskaran, 2026-09-14): the rotation null is the primary and only null. The noise-SNIC
null is reported as a documented failure and is not used for any percentile.** Why: before any
statistic was computed, `odisha_phase2_4_noise_null.py --size-check 3` showed SNIC on iid noise
fragmenting. Over three seeds the median superpixel was 4 px, and 51.5–53.1% of superpixels were
≤ 4 px. Only 45–60 of ~535 slivers per seed touched the ROI edge. The observed SNIC median is
82 px (v120, current) and 94 px (AlphaEarth), with 0.0–2.9% ≤ 4 px
(`odisha_phase2_4_results.txt`). Smoothing the noise to restore the match would have added a
free parameter to the primary null, and that was declined.

**Planned primary, NOT USED (failed its size check): noise-SNIC, ≥199 realisations.**

- SNIC runs through `SegmentationStage` itself (z-score, distance scale, UTM grid pin) on a
  stack of iid N(0,1) bands, one fresh seed per realisation, with the same `size` 10 and
  `compactness` 0.5. Each realisation uses one 6-band noise stack, and that single noise SNIC is
  **shared by all three arms** (common random numbers), so arm-vs-arm comparisons are paired.
  Band count does not matter here because the distance normaliser makes compactness independent
  of it; AlphaEarth's 64 bands are not mimicked.
- Noise criteria map onto the arm's real criteria in sorted band order, the order
  `calibrate_thresholds` and `merge_superpixels` iterate in.
- The merge is `merge_superpixels` itself, with the same `relax_factor`, `min_area_ha`,
  `max_area_ha` and `min_defined_criteria`. It merges on **noise criteria**: one noise band per
  real criterion. Each tolerance is set to the quantile of that realisation's own
  adjacent-superpixel noise differences equal to the `percentile_of_threshold` the real tolerance
  reached in the observed run (from `calibrate_thresholds`). That fixes the null's merge rate to
  the observed one by construction, so its size distribution matches, and it involves no
  tuning to any field result. **Why noise criteria rather than the real ETH/NDVI bands:** merging
  noise superpixels on the real criteria would carry the real criteria's spatial signal into the
  null, and the null would stop being a random partition.
- Plot → null stand is sampled on Earth Engine at the plot pixels. Boundary distance is the
  distance transform, pixel centre to pixel centre, to the nearest pixel adjacent to a different
  stand; the ROI edge is not a boundary. In noise-null comparisons the "> 30 m" filter applies
  to this raster distance for the observed partition and the null alike. The headline
  observed values use the vector join and its vector boundary distance. **The observed partition is put
  through exactly the same sampling code as realisation 0**, so the observed value and the null
  are computed by one code path.

**PRIMARY, by the decision above: rigid rotation + translation of the real stand map,** 999
realisations, offline. It applies to every arm and layer. The plots stay where they are and only
the map is moved, so boundary distances under the null are vector distances, like the observed
ones. The
plot configuration of each AOI part is rotated by a uniform angle and translated by a uniform
offset within the part. Any realisation that puts a plot outside every stand polygon of that
part is redrawn. Field values stay with their plots, and inter-plot distances are unchanged.
This null is also the one used for 6.3, because it preserves the cluster-label map's own
spatial structure.

**Reported for every statistic:** observed value, null distribution (median, p5, p95, and a
figure), observed percentile, and excess over the null median. `n_stands` and `n_plots` are given
beside every R².

---

## Pending, and deliberately not done in this phase

- **Percentile tolerance for `MergeCriterion`** (the outstanding Phase 1 recommendation).
  `calibrate_thresholds()` can report a percentile but not accept one. Building it mid-experiment
  would mean the supervisor's test ran against a method he did not ask for.
- **No replacement canopy-height source.** Meta/WRI is DISQUALIFIED (Phase 1). Its absence is a
  decision.
