# Phase 2 status

Stand-level field validation on Odisha: whether the method's stands group plots that are alike
on the ground, what was run to test it, what the pre-registered predictions said, and what is
still pending.

Every number here comes from code that has been run. Nothing is estimated. The statistics are
in `odisha_phase2_5_results.txt` and `odisha_phase2_5_summary.csv` (corrected run, commit
`9f5271e`). The predictions were committed before any statistic existed
(`PHASE2_PREDICTIONS.md`, commit `78ba075`). The first, unverified run is kept at `8d4c2ed`.
**Corrections lists every primary-layer figure that changed since that run, and every change that
alters a reading. The complete list, secondary layers included, is the CORRECTIONS section of
`odisha_phase2_5_results.txt`.**

**Scope: pilot only.** 60 plots in six Dhenkanal village forests. The AlphaEarth arm and the full
267-plot set have **no statistics yet** (see Pending).

---

## The answer to the supervisor's question

*Do plots that are ecologically alike end up in the same stand, and plots that differ in
different ones?*

**On the pilot, not distinguishably more often than chance, on a pilot that was pre-registered as
underpowered for this test** (`PHASE2_PREDICTIONS.md`, Consequence 4). The primary partition is
`stands_merged` from `odisha_v120_handcrafted`: 197 stands, median 3.93 ha. Its stands group
field-alike plots no better than rotated and translated copies of the same stand map do.

How to read the numbers. The **rotation null** moves the real stand map 1999 times by a random
rotation and shift, leaving the plots and their field values in place. **Excess** = observed
value minus the median over those moves. **Percentile** = where the observed value falls among
them. 95 or above would mean the stands do better than chance; 5 or below, worse.

- **Within- vs between-stand variance (6.1).** The test uses the 13 multi-plot stands, which hold
  35 of the 60 plots. For all seven field variables, excess over the rotation null runs from
  **−0.172 to +0.129**. Percentiles run from **3.2 to 92.0**. **None is above p95.**
- **Pairwise test at matched distance (6.2).** In Bray–Curtis composition, same-stand pairs sit at
  the rotation null's **88.6 and 76.0** percentiles in the 100–200 m and 200–400 m bands. The
  stand effect in the regression sits at **86.7**.
  - For |ΔLorey's height| the same two bands sit at **16.4 and 10.6**. The regression sits at
    **12.5**.
  - Every one of these is inside the null's central 90%.
  - The 0–100 m band (9 same-stand / 5 different-stand pairs; 59.4 and 69.5) is uninformative by
    pre-registration (Consequence 3). The 400–800 m band has 2 same-stand pairs and is
    uninformative.

The answer is honest only with its scope attached.

- **Small and underpowered.** 60 plots in 6 village forests. Only 13 stands hold more than one
  plot, and those hold 35 plots. The null is wide: for `loreys_h_m` its p5–p95 runs from 0.56 to
  0.85 R² at (13 stands, 35 plots). A real but modest effect could sit inside it.
- **One stand dominates.** A single 8-plot Kerijoli stand supplies 28 of the 46 same-stand pairs.
- **The null is not a perfect match.** It is size-matched by construction, since it moves the
  same polygons, but it puts fewer plots together than the observed map does: 46 same-stand pairs
  observed against a null median of 25. The part of that mismatch estimated through group sizes
  alone biases 6.1 against the stands by **−0.007 to −0.034 R²** (SENSITIVITY).
- **Most of what the raw R² captures is between-village difference** (SENSITIVITY).
- **The secondary `current` arm differs on composition.** Its pooled Bray–Curtis stand effect sits
  above p95 (99.8). That signal rests on Kerijoli: it falls to 80.7 without Kerijoli.

The last four are set out below the primary tables. None of them turns the answer into a positive
result.

---

## What was run

| step | what | result | source |
|---|---|---|---|
| configs | three method versions written as configs, not as reverts. `odisha_v120_handcrafted`: the pre-Odisha method (six-band SNIC, three-criterion merge). `odisha_current_handcrafted`: the same with `canopy_height_std` removed. `odisha_alphaearth`: embedding delineation with the same merge rule as v120 | — | commit `aa4d647` |
| AOIs | **pilot:** six Dhenkanal site polygons, +200 m, 6 parts, 912.0 ha, **60 plots**. **Full:** 21 habitations with ≥ 5 plots, hull +300 m, 4298.7 ha, **267 plots** (261 intended plus 6 from smaller habitations inside the hulls; included by decision) | exit conditions PASS | `odisha_phase2_0_results.txt` |
| habitat mask | MaskingStage run over discs around every plot | **257 of 274 plots kept = 93.8%** (floor 80%). Pilot 60 of 60. KENDUJHAR lowest at 8 of 12 (66.7%). `meta_chm == 0` plots 106 of 122. 15 of the 17 dropped plots are IndiaSAT cropland, 2 are built-up | `odisha_phase2_1_results.txt` |
| pipeline passes | three cache passes per config (segmentation → clustering → export), so each cached asset is computed from the asset upstream of it | v120: 933 superpixels → **197 merged stands**. current: 932 → 188 | `odisha_phase2_2_run_pipeline.py`, `odisha_phase2_3_results.txt` |
| field table and join | plots joined to stand polygons by geometry. Field table reproduces Phase 1 Lorey's height, top-5 height and crown cover exactly (max \|Δ\| = 0) | vector stand id equals the raster at the plot pixel for **60 of 60** plots in every merged and SNIC layer. 0 boundary-ambiguous plots | `odisha_phase2_3_results.txt` |
| null | **rotation null, 1999 realisations**, offline: rigid rotation plus translation of the stand map within each AOI part. Plots and their field values stay in place; draws that leave a plot off every polygon are redrawn. **Size-matched by construction** (the same stand polygons, moved), but **not matched on how often plots share a stand**: 46 same-stand pairs observed vs null median 25 (primary). The noise-SNIC null **failed its size check** before any statistic existed and is excluded by recorded decision | — | `PHASE2_PREDICTIONS.md` (Null models), `odisha_phase2_4_results.txt`, `odisha_phase2_5_results.txt` |

What the join gave, before any field statistic (from `PHASE2_PREDICTIONS.md`):

| arm / layer | stands | multi-plot stands | plots in them | plots > 30 m from a boundary |
|---|---|---|---|---|
| **v120 / `stands_merged`** | **197** | **13** | **35** | **14** |
| v120 / `stands_snic` | 868 | 4 | 10 | 4 |
| v120 / `stands_dissolved` | 97 | 7 | 59 | 52 |
| current / `stands_merged` | 188 | 11 | 32 | 15 |
| current / `stands_snic` | 872 | 5 | 16 | 3 |

---

## PRIMARY RESULT — v120 / `stands_merged` (pilot)

Partition: 197 stands, area p10 1.20 / median 3.93 / p90 9.39 ha. All 60 plots assigned.
12 of 201 polygons (22.40 of 915.02 ha) carry no `cluster_id`. Figures:
`odisha_phase2_5_primary_r2_null.png` and `odisha_phase2_5_pairwise_bands.png`.

### 6.1 Within- vs between-stand variance, R² = 1 − SS_within / SS_total

The observed values come from the vector join. "Restricted" means multi-plot stands only. The
null median, p5, p95, excess and percentile all refer to the restricted R², over 1999 rotation
realisations. (k, n) = (stands, plots).

| variable | R² all (k, n) | R² restricted (k, n) | null median | p5 | p95 | **excess** | **percentile** |
|---|---|---|---|---|---|---|---|
| `loreys_h_m` | 0.764 (38, 60) | 0.633 (13, 35) | 0.735 | 0.56 | 0.85 | **−0.102** | **17.1** |
| `loreys_h_tree_m` | 0.762 (38, 60) | 0.629 (13, 35) | 0.741 | 0.57 | 0.85 | **−0.112** | **15.2** |
| `crown_cover_pct` | 0.855 (38, 60) | 0.780 (13, 35) | 0.796 | 0.62 | 0.93 | **−0.016** | **43.8** |
| `sal_ba_frac` | 0.739 (38, 60) | 0.613 (13, 35) | 0.753 | 0.62 | 0.87 | **−0.140** | **4.1** |
| `n_species` | 0.930 (38, 60) | 0.890 (13, 35) | 0.761 | 0.58 | 0.90 | **+0.129** | **92.0** |
| `dbh_mean_cm` | 0.736 (38, 60) | 0.601 (13, 35) | 0.772 | 0.63 | 0.91 | **−0.172** | **3.2** |
| `h_top5_m` | 0.780 (38, 60) | 0.705 (13, 35) | 0.754 | 0.63 | 0.88 | **−0.050** | **27.6** |

The raw R² values are high, and on their own they mean nothing. The rotated map reaches a median
of 0.735–0.796 with no field information in it at all. **Six of seven excesses are negative (all
but `n_species`). No variable reaches p95, and none falls to the p2.5 "stands split alike plots"
threshold.** The two lowest are `dbh_mean_cm` at 3.2 and `sal_ba_frac` at 4.1. Read them with the
null-shape bias below, which pushes percentiles down.

### 6.2 Pairwise boundary test at matched distance

Pairs are taken within an AOI part. `diff` = mean over different-stand pairs − mean over
same-stand pairs, so positive means same-stand pairs are more alike.

- Cells with n ≤ 3 on either side are marked uninformative and given no percentile (R4, a rule
  added in the corrected run).
- The 0–100 m band is read as uninformative by pre-registration (Consequence 3), whatever its n.
- The naive within-band permutation p pools sites, and its pairs are not independent. The script
  labels it **INVALID**. That label is a post-hoc judgment; the pre-registered prediction for this
  p is scored under Predictions.

**Bray–Curtis on relative basal-area composition, all pairs**

| band | n same | n diff | mean same | mean diff | diff | rotation percentile |
|---|---|---|---|---|---|---|
| 0–100 m | 9 | 5 | 0.275 | 0.342 | 0.067 | 59.4 (n_null 1996); uninformative by Consequence 3 |
| 100–200 m | 17 | 20 | 0.314 | 0.515 | 0.201 | **88.6** (n_null 1999) |
| 200–400 m | 18 | 88 | 0.463 | 0.548 | 0.086 | **76.0** (n_null 1998) |
| 400–800 m | 2 | 90 | 0.368 | 0.606 | 0.238 | uninformative (n ≤ 3) |

Regression `d_field ~ d_geo + same_stand` (pairs < 800 m, n = 249, 46 same-stand):
**beta_same −0.1426**, beta per 100 m 0.0285. Null median −0.0362. **Stand-effect percentile 86.7**
(n_null 1999). High means more similar than the null.

**|ΔLorey's height| (m), all pairs**

| band | n same | n diff | mean same | mean diff | diff | rotation percentile |
|---|---|---|---|---|---|---|
| 0–100 m | 9 | 5 | 5.078 | 7.520 | 2.442 | 69.5 (n_null 1996); uninformative by Consequence 3 |
| 100–200 m | 17 | 20 | 5.851 | 4.102 | −1.749 | **16.4** (n_null 1999) |
| 200–400 m | 18 | 88 | 6.612 | 4.082 | −2.529 | **10.6** (n_null 1998) |
| 400–800 m | 2 | 90 | 4.182 | 4.203 | 0.020 | uninformative (n ≤ 3) |

Regression (n = 249, 46 same-stand): **beta_same +1.3415 m**, beta per 100 m −0.1836. Null median
−0.2655. **Stand-effect percentile 12.5** (n_null 1999).

Composition leans towards "same stand, more alike", but inside the null's central 90%. Height
leans the other way: in the two informative bands, same-stand pairs differ *more*. That is also
inside the central 90%.

**Pairs with both plots > 30 m from a boundary: set aside, and the pre-registered direction check
could not be made.** Only 14 plots qualify. They form **13 pairs under 800 m, 9 of them
same-stand**.

- Every distance band is uninformative by R4 (n ≤ 3), and the within-site shuffle is degenerate.
- The script prints regression percentiles for this subset: Bray–Curtis **24.2** and |ΔLorey's|
  **18.0**, from n_null 1671. These pass the script's estimability rule (R3: at least 100 null
  values), but they rest on 4 different-stand pairs, and **they are set aside by judgment**, not by
  a rule.
- As a result, the pre-registered surprise ("≥ p97.5, same direction in the > 30 m boundary
  subset") could not have been confirmed on the pilot even had a primary percentile reached p97.5.

### 6.3 Label agreement: typology, not delineation

This is a different question from 6.1 and 6.2. It asks whether the k-means `cluster_id` of a
plot's stand tracks a field forest type. It says nothing about where boundaries fall.

- **The pre-registered typology is NOT ESTIMABLE.** UPGMA on Bray–Curtis over all 274 plots,
  cut at k = 6, gives groups of 11 / 259 / 1 / 1 / 1 / 1. **All 60 pilot plots fall in one
  type**, so ARI, NMI and Cramér's V are undefined.
- **Sal-dominant rule (`sal_ba_frac > 0.5`), the transparent secondary.** No range was
  pre-registered for it: the 6.3 ranges in `PHASE2_PREDICTIONS.md` were set for the UPGMA 6-group
  typology. 6.3 uses 1129 of the 1999 rotations; the rest put a typed plot on a polygon with no
  `cluster_id`.

  | statistic | observed (n = 60) | null median | p95 | percentile |
  |---|---|---|---|---|
  | ARI | 0.132 | 0.093 | 0.156 | 83.2 |
  | NMI | 0.182 | 0.128 | 0.207 | 87.6 |
  | Cramér's V | 0.572 | 0.514 | 0.630 | 78.7 |

  None is above p95. 4 of the 10 contingency cells have expected count < 5.
- **Distant pairs (> 2 km, same district; 196 same-label, 1302 different-label).**
  - Bray–Curtis difference is **−0.053**, percentile **6.5**. Null median −0.020, p5 −0.054,
    p95 0.021. Same-label distant pairs are, if anything, slightly *less* alike in composition,
    just inside the central 90%.
  - |ΔLorey's| difference is **2.560 m**, percentile **51.5**. Null median 2.540. That is
    exactly what the rotated label map gives.

### What makes this weaker than it looks

Everything in this subsection is **SENSITIVITY analysis, not pre-registered.** It was added after
the adversarial review of the first run (corrections R6–R9). It qualifies the primary result; it
does not replace it.

**1. The rotation null does not have the observed partition's co-membership, and the mismatch
works against the stands in 6.1.** By the pre-registered size criterion (stand count off by
> 25%, or median area off by > 50%) the rotation null passes: it moves the same polygons, and the
restricted stand count is 13 against a null median of 12. It fails only on a post-hoc check of
how often plots share a stand. Restricted set, 1999 realisations:

| quantity | observed | null median | p5 | p95 | percentile |
|---|---|---|---|---|---|
| k (multi-plot stands) | 13 | 12 | 9 | 15 | 64.2 |
| n (plots in them) | 35 | 30 | 23.9 | 36 | 90.3 |
| E = (k − 1)/(n − 1), the R² expected from group sizes alone | 0.353 | 0.393 | 0.333 | 0.444 | 13.9 |
| largest multi-plot group | 8 | 4 | 3 | 7 | 98.6 |
| **same-stand within-part pairs** | **46** | **25** | 17 | 39 | **99.1** |

The observed map puts plots together far more than a rotated copy does: 46 same-stand pairs
against a null median of 25. It also puts more of them in one large group.

The file estimates the part of the bias that comes through E alone. It is **negative for every
variable**, which means the percentiles are biased low:

| variable | estimated bias via E (R² units) |
|---|---|
| `loreys_h_m` | −0.029 |
| `loreys_h_tree_m` | −0.028 |
| `crown_cover_pct` | −0.019 |
| `sal_ba_frac` | −0.007 |
| `n_species` | −0.014 |
| `dbh_mean_cm` | −0.009 |
| `h_top5_m` | −0.034 |

These are much smaller than the negative excesses for `dbh_mean_cm` (−0.172) and `sal_ba_frac`
(−0.140), so the E component alone does not account for them.

Adjusted R² against the same null, restricted set (13 stands, 35 plots):

| variable | adjusted R² percentile |
|---|---|
| `loreys_h_m` | 21.7 |
| `loreys_h_tree_m` | 19.2 |
| `crown_cover_pct` | 49.0 |
| `sal_ba_frac` | 7.3 |
| `n_species` | 93.6 |
| `dbh_mean_cm` | 4.8 |
| `h_top5_m` | 33.5 |

None is above p95 there either.

**2. One Kerijoli stand dominates the composition signal in 6.2.** Kerijoli has 10 plots in
8.3 ha. Its stand 81 holds 8 of them and contributes **28 of the 46** same-stand pairs. Kerijoli
as a site has 28 same-stand pairs against a null median of 9 (percentile 98.1).

Robustness of the Bray–Curtis stand effect (beta_same, all pairs):

| variant | n same | beta_same | stand-effect percentile |
|---|---|---|---|
| as pre-registered | 46 | −0.1426 | 86.7 |
| **drop Kerijoli** | **18** | **+0.0693** | **11.5** |
| site fixed effects | 46 | +0.0626 | 7.0 |
| stand-weighted (1/pairs per stand) | 46 | +0.0856 | 14.4 |
| drop any one of the other five sites | 40–45 | −0.1882 to −0.1103 | 77.0–92.9 |

In v120, removing Kerijoli, adding site fixed effects, or weighting each stand equally reverses
the direction.

The secondary `current` arm behaves differently, and more sharply. There the pooled Bray–Curtis
stand effect sits at **99.8**. It falls to **80.7 without Kerijoli** and to **69.1 with site fixed
effects**, but it **survives stand weighting at 99.1**, and dropping any one of the other five
sites leaves it at 99.5–99.9. Kerijoli stand 85 (9 plots) supplies 36 of that arm's 53 same-stand
pairs. The one composition signal in Phase 2 so far is a Kerijoli-site signal, not only one
stand's pair count.

**3. The restricted R² is mostly between-village variance.** Each village forest is its own AOI
part. R² computed *within* parts against the same null, restricted set (13 stands, 35 plots):

| variable | restricted R² | within-part R² | within-part percentile |
|---|---|---|---|
| `loreys_h_m` | 0.633 | **0.106** | 7.1 |
| `loreys_h_tree_m` | 0.629 | 0.106 | 7.3 |
| `crown_cover_pct` | 0.780 | 0.344 | 46.0 |
| `sal_ba_frac` | 0.613 | **0.047** | 4.1 |
| `n_species` | 0.890 | 0.729 | 94.9 |
| `dbh_mean_cm` | 0.601 | 0.239 | 25.5 |
| `h_top5_m` | 0.705 | 0.151 | 8.5 |

`n_species` is the one variable consistently near the top of the null, at 92.0 restricted,
93.6 adjusted and 94.9 within-part. It does not survive leave-one-site-out: without Balikurma its
percentile is **58.3**.

This sensitivity reading is consistent with the standing prediction in `PHASE2_PREDICTIONS.md`
that within-site explained variance is low. That file quotes ETH explaining R² 0.029 of Lorey's
height with habitation means removed, and `vh_iqr` 0.003. It is a different quantity from the
within-part R² above. **Those two figures appear in no committed Phase 1 results file**; the
R² 0.029 in `PHASE1_STATUS.md` and `odisha_phase1_results.txt` is a different test.

**4. No valid p-value supports anything above.** The naive permutation p-values pool sites. The
within-site shuffle (9999 shuffles of `same_stand` within part × band) gives:

| test, all pairs | Bray–Curtis | \|ΔLorey's\| |
|---|---|---|
| 0–100 m | 0.943 | 0.657 |
| 100–200 m | 0.755 | 0.636 |
| 200–400 m | 0.939 | 0.792 |
| beta_same | 0.973 | 0.837 |

---

## Predictions: what held, what failed, what could not be tested

The predictions are from `PHASE2_PREDICTIONS.md`. None of them was restricted to one arm, so both
hand-crafted arms' `stands_merged` layers are scored. v120 is the primary; `current` is secondary.

| prediction | observed, v120 (primary) | observed, current (secondary) | verdict |
|---|---|---|---|
| **Standing:** stands do not group field-similar plots better than a size-matched, spatially coherent random partition | no 6.1 percentile ≥ 95; 6.2 informative bands and regressions inside 5–95 | 6.1 one exceedance (`dbh_mean_cm` 95.4); 6.2 Bray–Curtis 98.8 / 99.6 / 99.8 | **held for v120; not for current's 6.2 composition test** |
| 6.1 raw restricted R² 0.4–0.8 | 0.601–0.780 for six variables; `n_species` 0.890 | 0.641–0.763 for five; `n_species` 0.859, `dbh_mean_cm` 0.907 | **held for 6 of 7 (v120), 5 of 7 (current)** |
| 6.1 excess −0.10 to +0.10 | `crown_cover_pct` −0.016, `h_top5_m` −0.050 inside. `loreys_h_m` −0.102, `loreys_h_tree_m` −0.112, `sal_ba_frac` −0.140, `dbh_mean_cm` −0.172 below. `n_species` +0.129 above | `dbh_mean_cm` +0.135 above, `h_top5_m` −0.110 below; the other five inside | **failed for 5 of 7 (v120)**, 4 of them on the negative side (see the null-shape bias). `loreys_h_m` at −0.102 is marginal: −0.10 at the pre-registered precision, which would make it 4 of 7. **Failed for 2 of 7 (current)** |
| 6.1 percentile < 95; one exceedance of 7 within prediction (0.35 expected by chance) | max 92.0 (`n_species`) | one: `dbh_mean_cm` 95.4 | **held, both arms** (current's single exceedance is within the allowance) |
| 6.1 chance level E[R²] ≈ 0.45–0.55 for restricted stands | E = **0.353** | E = **0.323** | **wrong**; see Corrections |
| 6.2 `d_field` rises with `d_geo`, both measures (does not depend on the partition) | Bray–Curtis within parts < 800 m: slope **+0.0411** per 100 m, Spearman ρ +0.263 (n = 249). \|ΔLorey's\|: slope **−0.3028** per 100 m, ρ −0.110. Mean \|ΔLorey's\| 4.61 m within parts vs 8.43 m for pairs > 2 km | same | **held for Bray–Curtis. Failed for \|ΔLorey's\| within 800 m**; holds only between the within-part and > 2 km scales |
| 6.2 raw within-band difference slightly in the "stands work" direction, predicted and not evidence | informative bands: Bray–Curtis 0.201, 0.086 positive; \|ΔLorey's\| −1.749, −2.529 negative. Excluded: 0–100 m (Consequence 3) and 400–800 m (2 same-stand pairs) | informative bands: Bray–Curtis 0.282, 0.315; \|ΔLorey's\| −1.227, −0.887 | **direction held for Bray–Curtis, not for height**, both arms. Magnitude is read only against the null |
| 6.2 band differences and the `same_stand` coefficient inside the null's central 90% (informative bands: 100–200 m, 200–400 m; and the regression) | Bray–Curtis 88.6 / 76.0, regression 86.7. \|ΔLorey's\| 16.4 / 10.6, regression 12.5 | Bray–Curtis **98.8 / 99.6, regression 99.8**. \|ΔLorey's\| 18.4 / 30.7, regression 29.3 | **held for v120. FAILED for Bray–Curtis in current** (a Kerijoli-site signal: 80.7 without Kerijoli, 69.1 with site fixed effects, but 99.1 stand-weighted and 99.5–99.9 dropping any other site; SENSITIVITY) |
| 6.2 > 30 m boundary subset: same, with fewer pairs | 13 pairs (9 same); every band n ≤ 3; regression 24.2 / 18.0 on 4 different-stand pairs | 10 pairs (4 same); every band n ≤ 3 | **could not be tested**: bands uninformative by R4; regressions set aside by judgment |
| 6.2 within-band label-permutation p > 0.05 | Bray–Curtis 100–200 m p **0.025**, regression p **0.009** | Bray–Curtis 100–200 m **0.004**, 200–400 m **0.000**, regression **0.000** | **FAILED as pre-registered for Bray–Curtis, both arms.** The script now labels this p INVALID (it pools sites), a post-hoc judgment (R6). Separately, SENSITIVITY: the within-site shuffle p is ≥ 0.636 in every v120 informative cell and regression, both measures; in current Bray–Curtis 0.477 / 0.141 / 0.291 |
| 6.3 UPGMA k = 6: ARI −0.05 to +0.10, NMI 0.05–0.25, V 0.25–0.45, none above p95 | all 60 pilot plots are one type | same | **not estimable** |
| 6.3 distant pairs inside the null's central 90% | Bray–Curtis 6.5, \|ΔLorey's\| 51.5 | Bray–Curtis 15.4, \|ΔLorey's\| 68.4 | **held, both arms** (v120 Bray–Curtis narrowly) |
| Arms: "the difference in excess-over-own-null falls inside either arm's null spread" | — | — | **failed for `dbh_mean_cm` under both readings, and also for `sal_ba_frac` under the committed wording.** See Arms comparison: the differenced-null operationalisation was chosen after the first run (R10) |
| Consequence 1: `stands_snic` holds 0–3 multi-plot superpixels | 4 | 5 | **missed**; recorded in the predictions file before any statistic |
| Consequence 2: `stands_merged` holds ~6–15 multi-plot stands with 12–35 plots | 13 stands / 35 plots | 11 / 32 | **held** |
| Consequence 3: the 0–100 m band is tiny and read as uninformative | 14 pairs; 9 same / 5 different | 14 pairs; 11 same / 3 different | **held**; read as uninformative throughout |
| Consequence 4: the pilot is underpowered for 6.1 and 6.2 | null p5–p95 for `loreys_h_m` 0.56–0.85 at (13, 35); 6.1 percentiles spread 3.2–92.0 | null p5–p95 for `loreys_h_m` 0.56–0.85 at (11, 32) | **held** |
| Surprise: primary `loreys_h_m` or `crown_cover_pct` ≥ p97.5, same direction in the > 30 m subset | 17.1 and 43.8 | — | did not occur (and the subset condition could not have been checked) |
| Surprise: primary ≤ p2.5 (stands split alike plots) | min 3.2 (`dbh_mean_cm`) | — | did not occur |
| Surprise: ARI ≥ 0.2 | UPGMA not estimable; Sal-rule secondary 0.132 | Sal-rule secondary 0.124 | not estimable as pre-registered; the Sal-rule secondary is below 0.2 in both arms |
| Surprise: fewer than 5 multi-plot merged stands | 13 | 11 | did not occur |
| Surprise: noise null not size-matched | median superpixel 4 px vs 82 px observed | — | **occurred, before any statistic**; rotation null read instead |
| AlphaEarth: excess within ±0.10, no directional prediction | — | — | **pending** |

---

## SECONDARY results

Raw R² is **never** compared across arms or layers. Each partition is read only as excess over its
own rotation null. Figure: `odisha_phase2_5_arms_excess.png`.

### current / `stands_merged`

Partition: 188 stands, area p10 1.23 / median 4.27 / p90 9.46 ha. 11 multi-plot stands hold 32
plots. 14 of 196 polygons (18.43 of 915.38 ha) carry no `cluster_id`.

| variable | R² all (k, n) | R² restricted (k, n) | null median | excess | percentile |
|---|---|---|---|---|---|
| `loreys_h_m` | 0.898 (39, 60) | 0.641 (11, 32) | 0.729 | −0.088 | 22.1 |
| `loreys_h_tree_m` | 0.899 (39, 60) | 0.653 (11, 32) | 0.737 | −0.083 | 23.5 |
| `crown_cover_pct` | 0.869 (39, 60) | 0.730 (11, 32) | 0.780 | −0.050 | 30.0 |
| `sal_ba_frac` | 0.866 (39, 60) | 0.763 (11, 32) | 0.738 | +0.025 | 62.5 |
| `n_species` | 0.895 (39, 60) | 0.859 (11, 32) | 0.766 | +0.093 | 84.9 |
| `dbh_mean_cm` | 0.954 (39, 60) | 0.907 (11, 32) | 0.772 | +0.135 | **95.4** |
| `h_top5_m` | 0.863 (39, 60) | 0.644 (11, 32) | 0.754 | −0.110 | 6.9 |

`dbh_mean_cm` at 95.4 is one exceedance of p95 in seven variables, within the pre-registered
chance allowance (0.35 expected).

This arm's null shape is further off than v120's (SENSITIVITY):

| quantity | observed | null median | percentile |
|---|---|---|---|
| E | 0.323 | 0.385 | 4.1 |
| largest group | 9 | 4 | 100.0 |
| same-stand pairs | 53 | 26 | 99.9 |

**6.2, Bray–Curtis.**

- 100–200 m sits at **98.8** and 200–400 m at **99.6**. The regression stand effect is at
  **99.8** (beta_same −0.2820). As pre-registered, **this fails the 6.2 against-null prediction.**
  The 0–100 m (11 / 3 pairs) and 400–800 m (3 same-stand pairs) bands are uninformative.
- SENSITIVITY: without Kerijoli the regression falls to **80.7**; with site fixed effects, to
  **69.1**. The stand-weighted variant stays at **99.1**, and the other five leave-one-site-out
  drops stay at 99.5–99.9. Kerijoli is the only single site whose removal takes it below p95.
- SENSITIVITY: the within-site shuffle p is 0.477 (100–200 m), 0.141 (200–400 m) and 0.291
  (beta_same).

**6.2, |ΔLorey's|.** The bands sit at 18.4 and 30.7; the regression at 29.3.

**6.3.**

- UPGMA k = 6 is not estimable.
- The Sal rule gives ARI 0.124 (percentile **96.4**), NMI 0.193 (**95.9**) and V 0.578 (88.7),
  from n_null 1247. No range was pre-registered for the Sal rule. If the UPGMA expectation "none
  above p95" is applied to it, ARI and NMI exceed it in this arm (and not in v120: 83.2, 87.6). If
  the UPGMA value ranges are applied, all four Sal-rule ARI and V values fall outside them in both
  arms (ARI 0.132 / 0.124 above +0.10; V 0.572 / 0.578 above 0.45). Either comparison is not
  pre-registered. It is a typology statement, not a delineation finding, and ARI 0.124 is under
  the 0.2 surprise threshold.
- Distant pairs: Bray–Curtis −0.068 (15.4), |ΔLorey's| 0.627 (68.4).

### Arms comparison, `stands_merged`

Difference = excess(v120) − excess(current).

The committed prediction reads "the difference in excess-over-own-null falls inside either arm's
null spread". It was operationalised two ways, both first computed in the corrected run, after the
first run's statistics had been seen (R10). They are given equal standing here.

- **Differenced null.** Each arm's null is centred on its own median, and the two are differenced
  index-wise.
- **Own-null reading.** The difference is checked against each arm's own centred p5–p95. The
  script labels this one SENSITIVITY, but it is the closer match to the committed wording.

| variable | excess v120 | excess current | difference | differenced null p5 | p95 | percentile | differenced null | own-null reading |
|---|---|---|---|---|---|---|---|---|
| `loreys_h_m` | −0.102 | −0.088 | −0.014 | −0.209 | 0.205 | 45.1 | inside | inside both |
| `loreys_h_tree_m` | −0.112 | −0.083 | −0.029 | −0.204 | 0.200 | 40.3 | inside | inside both |
| `crown_cover_pct` | −0.016 | −0.050 | 0.034 | −0.228 | 0.205 | 63.3 | inside | inside both |
| **`sal_ba_frac`** | −0.140 | 0.025 | **−0.165** | −0.183 | 0.168 | 6.6 | inside | **inside neither** |
| `n_species` | 0.129 | 0.093 | 0.036 | −0.231 | 0.253 | 57.6 | inside | inside both |
| **`dbh_mean_cm`** | −0.172 | 0.135 | **−0.306** | −0.192 | 0.206 | **0.9** | **OUTSIDE** | **inside neither** |
| `h_top5_m` | −0.050 | −0.110 | 0.060 | −0.185 | 0.168 | 69.9 | inside | inside both |

Beside it, the two partitions:

| arm | stands | area p10 / median / p90 (ha) | multi-plot stands | plots in them |
|---|---|---|---|---|
| v120 | 197 | 1.20 / 3.93 / 9.39 | 13 | 35 |
| current | 188 | 1.23 / 4.27 / 9.46 | 11 | 32 |

**The arms prediction fails for `dbh_mean_cm` under both readings, and for `sal_ba_frac` under the
own-null reading.** Removing `canopy_height_std` was predicted to change the partition without
changing its field relevance. On mean DBH, the current arm sits at 95.4 and v120 at 3.2.

These are two variables of seven on 32–35 plots, in arms whose null shape is off. They are
reported as a failed prediction, not as evidence that the removal helps.

### `stands_snic`: thin but estimable

v120 has 868 superpixels, area p10 0.16 / median 0.85 / p90 2.07 ha: **4 multi-plot superpixels
holding 10 plots**. Current has 872, p10 0.15 / median 0.85 / p90 1.99 ha: 5 holding 16.

- **6.1, v120 (4 stands, 10 plots).** Excess runs from −0.164 to +0.115. `crown_cover_pct` sits at
  **95.4** (n_null 1992). That is one exceedance of p95 in 7 variables, within the pre-registered
  chance allowance (0.35 expected), on a null spanning p5 0.13 to p95 0.99.
- **6.1, current (5 stands, 16 plots).** Excess runs from −0.320 to +0.132, percentiles 7.3–86.6.
  Its E-slope bias estimates reach −0.179.
- **6.2.** v120 has 8 same-stand pairs (regression percentiles 65.3 Bray–Curtis, 46.0
  |ΔLorey's|). Current has 27 (81.3 and 21.2).
- **> 30 m subset.** Only 1 pair (v120) and 0 pairs (current).

### `stands_dissolved`: effectively the site partition, not a delineation test

The dissolved layer (connected same-cluster regions) puts the 60 plots into 8 units in each arm.
v120 has 97 polygons, area p10 0.05 / median 0.20 / p90 6.90 ha; current has 126, 0.04 / 0.20 /
9.87 ha.

| arm | units holding plots, by part | ARI(unit, AOI part) |
|---|---|---|
| v120 | 1 / 1 / 1 / 1 / 2 / 2 | **0.932** |
| current | 1 / 2 / 1 / 1 / 1 / 2 | 0.915 |

The site-only partition reproduces its restricted R² almost exactly. For `loreys_h_m`, v120's
dissolved restricted R² is 0.518 (7 stands, 59 plots) and the site-only value is 0.512 (6 AOI
parts as groups, same restricted plots). This is an identity check that the two are nearly the
same partition, not a comparison of how well they perform (SENSITIVITY, R5).

Its statistics measure differences *between* village forests. Its 6.1 excesses are all small:

| arm | (k, n) restricted | excess range | percentile range |
|---|---|---|---|
| v120 | (7, 59) | −0.031 to +0.003 | 5.3–61.3 |
| current | (7, 59) | −0.031 to −0.018 | 8.4–27.1 |

One pre-registered 6.2 value falls outside the central 90%: current dissolved |ΔLorey's|
regression stand effect at **4.5** (n_null 1999). Given the identity with the site partition, it
too measures between-site difference.

These values are recorded, and they answer nothing about stand boundaries.

### Label drift: cached k-means labels vs a fresh run

This came out of verifying the clustering fix (`odisha_phase2_6_results.txt`, commit `faf645b`;
`docs/pending_decisions/clustering_rcc_neighbourhood.md`). The cached v120 `cluster_labels`
asset differs from a fresh recompute, under old and new clustering code alike. The metadata
floats differ only on terrain bands (elevation, slope, aspect), which points to changed upstream
terrain inputs.

- **Whole ROI.** v120: 50,216 of 77,338 pixel-weight units differ. After Hungarian matching
  (pairing up cluster numbers between the two runs) agreement is 0.772. Current: 1,698 of 77,335
  differ, agreement 0.982.
- **At the 60 pilot plots.** v120 raw agreement is 0.500, mostly renumbering. **After Hungarian
  matching it is 0.950: 3 plots change cluster** (Balikurma, Kampulei, Kerijoli; each cached 0 →
  fresh 3). Current is identical at all 60.
- **What the statistics used.** For both arms, the cached label equals the exported stand
  `cluster_id` at every plot, so the results use the pipeline's cached output as exported.
- **What it can move.**
  - ARI, NMI and V do not change under relabelling, so only those 3 v120 plots can move the
    observed 6.3 values.
  - The 6.3 null reads labels across the moved map, where v120 whole-ROI agreement is 0.772, so the
    v120 6.3 null percentiles could also move.
  - The dissolved layer is built from the labels, and it could change as well.
  - **Neither effect was measured.** 6.1 and 6.2 on the merged and SNIC layers do not read labels.
- **Open.** Whether to rebuild the cache or pin and document the cached version is still to be
  decided.

---

## Corrections to earlier figures

### The first run (`8d4c2ed`) → the corrected run (`9f5271e`)

The first run was committed as produced, marked NOT YET VERIFIED. An adversarial review found no
arithmetic errors in the primary numbers. **Every primary observed R², (k, n) and band count is
unchanged.** The table below lists every primary-layer change and every secondary change that
alters a reading, with the correction code from the results file's CORRECTIONS section. The
complete list, including fourth-decimal moves and secondary-layer reclassifications not repeated
here, is `odisha_phase2_5_results.txt`, CORRECTIONS section.

**Method and labelling**

| what | first run | corrected | why |
|---|---|---|---|
| rotation realisations | 999 | **1999** | R13. **This departs from the 999 in `PHASE2_PREDICTIONS.md`**; all percentiles were redrawn |
| **6.3 UPGMA k = 6, ARI and NMI (both arms)** | **0.000, percentile 50.0** | **NOT ESTIMABLE** (all pilot plots one type) | R2 |
| UPGMA group sizes over 274 plots | 10 / 260 / 1 / 1 / 1 / 1 | 11 / 259 / 1 / 1 / 1 / 1 | R15 species aliases; still one type in the pilot |
| naive within-band permutation p | printed as "perm p" | labelled **INVALID** (pools sites, pairs dependent) | R6 |
| figures | none; the figure code read only the (unused) noise null | redrawn from the rotation null | R16 |
| rotation null boundary search | capped at 600 m | 1000 m, with minimum stand id on multi-cover, matching the join | R14 |
| arms prediction; "`d_field` rises with `d_geo`" | not computed | computed (above) | R10, R11 |

**Primary layer, v120 / `stands_merged`: observed values**

| what | first run | corrected | why |
|---|---|---|---|
| Bray–Curtis, all pairs, 200–400 m diff | 0.0859 | 0.0857 | R15 |
| Bray–Curtis, all pairs, 400–800 m diff | 0.2325 | 0.2379 | R15 |
| Bray–Curtis, all pairs, beta_same | −0.1425 | −0.1426 | R15 + R18 (geodesic distance) |
| Bray–Curtis, > 30 m, beta_same; beta per 100 m; 400–800 m diff | 0.0667; 0.0556; −0.1871 | 0.0610; 0.0544; −0.1761 | R15 + R18 |
| \|ΔLorey's\|, all pairs, beta_same | 1.3416 | 1.3415 | R18 |
| \|ΔLorey's\|, > 30 m, beta_same | 3.4570 | 3.4568 | R18 |
| 6.3 distant_diff_bc | −0.0535 | −0.0528 | R15 |

**Primary layer, v120 / `stands_merged`: percentiles**

| what | first run | corrected | why |
|---|---|---|---|
| 6.1 `loreys_h_m` excess / percentile (example of Monte Carlo movement in 6.1) | −0.107 / 16.6 | −0.102 / 17.1 | new null draws |
| Bray–Curtis regression stand effect | 87.4 | 86.7 | new null draws |
| \|ΔLorey's\| regression stand effect | 11.2 | 12.5 | new null draws |
| > 30 m regression stand effect, Bray–Curtis / \|ΔLorey's\| | 22.1 / 15.9 | 24.2 / 18.0 | new null draws |
| Bray–Curtis, all pairs, 400–800 m | 84.1 | uninformative (n ≤ 3) | R4 |
| \|ΔLorey's\|, all pairs, 400–800 m | 37.4 | uninformative (n ≤ 3) | R4 |
| > 30 m subset: Bray–Curtis 200–400 m / 400–800 m; \|ΔLorey's\| 200–400 m / 400–800 m | 61.7 / 18.2; 5.8 / 31.8 | all uninformative (n ≤ 3) | R4 |

Other percentile moves, all layers: median 1.0 pp, max 4.1 pp (Monte Carlo).

**Secondary layers: changes that alter a reading**

| what | first run | corrected | why |
|---|---|---|---|
| **current Sal-rule ARI** | 0.0922, percentile 83.0 | **0.1237, percentile 96.4** | R1: GEE's mode reducer returned class 5 as 4.9999999999999885 for 6 plots, and the first run truncated it to 4 |
| **current Sal-rule NMI** | 0.1109, percentile 46.4 | **0.1931, percentile 95.9** | R1 |
| current Sal-rule Cramér's V | 0.4689, percentile 42.2 | 0.5778, percentile 88.7 | R1 |
| current distant same-label pairs | 160 | 198 | R1: the unrounded floats split class 5 |
| current distant_diff_lorey | −0.1705, percentile 50.8 | **+0.6272**, percentile 68.4 | R1 |
| current distant_diff_bc | −0.0322, percentile 62.2 | −0.0677, percentile 15.4 | R15 + R1 |
| **current Bray–Curtis regression stand effect** (quoted in the `8d4c2ed` commit message) | **99.9**, beta_same −0.2823 | **99.8**, beta_same −0.2820 | new null draws; R15 + R18 |
| current Bray–Curtis 0–100 m / 400–800 m | 71.4 / 81.9 | uninformative (n ≤ 3) | R4 |
| v120 SNIC Bray–Curtis 100–200 m / 200–400 m | 90.1 / 22.4 | uninformative (n ≤ 3) | R4 |
| current SNIC Bray–Curtis and \|ΔLorey's\| 400–800 m | 100.0 / 100.0 | uninformative (n ≤ 3) | R4 |
| v120 dissolved \|ΔLorey's\| 100–200 m | 98.5 | uninformative (n ≤ 3) | R4 |
| current dissolved Bray–Curtis 100–200 m | 96.2 | uninformative (n ≤ 3) | R4 |

The primary reading did not change. The v120 stands group field-alike plots no better than
rotated copies of the same map.

### Corrections to `PHASE2_PREDICTIONS.md` itself

- **The chance-level statement was wrong.** It said restricted stands "are mostly pairs, so
  g ≈ n/2 and E[R²] ≈ 0.45–0.55 from nothing".
  - Counted by stands, most restricted stands *are* pairs: 9 of 13 in v120 and 8 of 11 in current
    (`odisha_phase2_3_results.txt`, plots-per-stand histograms {1: 25, 2: 9, 3: 3, 8: 1} and
    {1: 28, 2: 8, 3: 1, 4: 1, 9: 1}).
  - But pairs hold only 18 of 35 plots (v120) and 16 of 32 (current). One 8-plot stand (v120) and
    one 9-plot stand (current) hold much of the rest, so g is well below n/2: 13 against 17.5, and
    11 against 16.
  - E = (k − 1)/(n − 1) is therefore **0.353** for v120 and **0.323** for current, not 0.45–0.55.
    The rotation null's median E is 0.393 and 0.385.
  - The predicted raw-R² band of 0.4–0.8 held for six of seven variables (v120) despite the wrong
    chance level.
- **Consequence 1 missed**, as the file already records: 4 and 5 multi-plot SNIC superpixels, not
  0–3.

### Departures from `PHASE2_PREDICTIONS.md` made after seeing the first run

Each was introduced in the corrected run, after the first run's statistics existed. None changes
an observed value.

- **1999 rotation realisations instead of the specified 999** (R13).
- **6.3 uses only the realisations that keep every typed plot on a polygon with a `cluster_id`**
  (R12): 1129 of 1999 for v120, 1247 for current. The file specified the rotation null without
  that restriction.
- **Cells with n ≤ 3 are marked uninformative and given no percentile** (R4).
- **The naive within-band label-permutation p is labelled INVALID** (R6). It was pre-registered
  with a predicted value (> 0.05), and that prediction failed for Bray–Curtis before the label
  was applied. The within-site shuffle p is a SENSITIVITY analysis, not its replacement.
- **The arms prediction was operationalised as a differenced centred null** (R10). The own-null
  reading is reported beside it with equal standing.
- **The > 30 m regression percentiles are set aside by judgment**, though they pass R3.

---

## Method and infrastructure findings

**The noise-SNIC null failed its size check before any statistic existed.** Recorded in
`odisha_phase2_4_results.txt`, commits `c4dc711` and `04d6b54`.

| partition | superpixels | median size (px) | share ≤ 4 px |
|---|---|---|---|
| observed v120 | 933 | **82** | 2.7% |
| observed current | 932 | 82 | 2.9% |
| observed AlphaEarth | 929 | 94 | 0.0% |
| noise SNIC, seeds 0 / 1 / 2 | 1026 / 1033 / 1034 | **4** (each seed) | 51.5–53.1% |

SNIC used the same size 10 and compactness 0.5 throughout. Only 45–60 of ~535 noise slivers per
seed touch the ROI edge.

- **Decision (Jaskaran, 2026-09-14):** the noise null is excluded, and the rotation null is the
  primary and only null.
- Smoothing the noise to force a match would have added a free parameter to the primary null.
  That was declined.
- Getting the null to run at all first needed a fix: `ee.Image.randomNormal` does not exist; the
  call is `ee.Image.random(seed, 'normal')`.

**Clustering memory fix: `maxSize` is an extent, not a count** (commit `71a0e42`;
`docs/pending_decisions/clustering_rcc_neighbourhood.md`, whose status line, "Code change is
uncommitted", predates the commit).

- **Symptom.** The AlphaEarth arm's k-means stage failed with "User memory limit exceeded (skew
  of A00)" on four attempts, with every input cached.
- **Cause.** `reduceConnectedComponents` reads `maxSize` as an extent in pixels and pads every
  tile by it. The pipeline passed `Config.max_component_pixels()`, a pixel *count* of 1200 at
  10 ha and 10 m.
  - Each 256 px tile was therefore evaluated over about 2656² px per band.
  - Memory scaled with bands × pad, so 64 embedding bands crossed the limit where the
    hand-crafted stack (~22 bands) did not.
- **Fix.** The stage now measures each unit's widest pixel extent in both grids and passes
  `min(cap, ceil(widest × 1.2) + 2)`:

  | arm | widest extent (px) | neighbourhood passed (px) | cap (px) |
  |---|---|---|---|
  | v120 | 91 | 112 | 1200 |
  | current | 103 | 126 | 1200 |
  | AlphaEarth | 128 | 156 | 1200 |

- **Evidence that nothing else changed.** Old and new code are **pixel-identical** on the
  hand-crafted arms over the whole ROI (neq 0, maskneq 0). Sample agreement is 1.0 (n 2389 and
  2388) and the discrete metadata are identical. Float differences are ≤ 2.4e-14 and training
  rows ≤ 1.94e-13.
- **Cache.** The cache fingerprint is unchanged, and nothing needed rebuilding.
- **AlphaEarth now completes clustering.** 153.7 s, 184 stands, 162 of 184 training units, all
  6 clusters populated.
- **Not yet fixed.** `metrics.py` and `components.explained_variance_r2` still pass the cap. They
  are not on the Phase 2 export path.

**Per-district split of the full set** (`odisha_phase2_0_results.txt`, commit `f8abf03`).

- **Why.** One AOI over the 20 habitation parts spans a 298 × 342 km box: 1.02 bn pixels at 10 m,
  over Earth Engine's 1.00 bn export cap. Every cache export failed.
- **Decision (Jaskaran, 2026-09-14).** Run the pipeline once per district, with the same hulls
  and buffer:

  | district | parts | plots | bounding box (M px) |
  |---|---|---|---|
  | ANGUL | 4 | 39 | 0.9 |
  | DHENKANAL | 8 | 75 | 9.5 |
  | KENDUJHAR | 1 | 8 | 0.1 |
  | KORAPUT | 7 | 145 | 2.4 |

  The four AOIs together hold exactly the 267 plots, none of them in two districts. That gives
  12 configs (4 districts × 3 arms), all with distinct fingerprints.
- **Consequence.** k-means is fitted per district, so type labels are comparable only within a
  district. The delineation tests compare plots within an AOI part and pool across parts.

**Hung task polls** (commit `34395ff`).

- **What happened.** The Earth Engine client has no default request timeout. A poll issued during
  a network drop never returned, and **two district passes hung for about 11 hours** with their
  exports already complete.
- **Fix.** `--wait` now bounds each poll with a 120 s deadline, and logs and retries a failed poll
  instead of hanging.

**Cached terrain and label drift.** See the Label drift section above. The cached v120
`cluster_labels` no longer match a fresh run. At the plots this moves 3 v120 labels. The 6.3 null
percentiles and the dissolved layer could also move; neither was measured. 6.1 and 6.2 on the
merged and SNIC layers do not read labels. The choice between rebuilding and pinning is open.

---

## Pending

The state lines in this section are as of 2026-09-15. They come from the running work session,
not from a committed results file.

### AlphaEarth arm — pending

**No statistics exist yet.** The clustering stage now runs (fixed and verified above). As of
2026-09-15 the arm's stand-layer export is queued, and its stand layers have not been produced.
The committed stats run records "arm alphaearth skipped — no vector files".

When its vectors are in `phase2_vectors/`, the plan is:

1. Rerun `odisha_phase2_3_join.py`.
2. Rerun `odisha_phase2_5_stats.py`.
3. Report 6.1, 6.2 and 6.3 against its own rotation null, and its difference in excess from v120,
   with stand count and area distribution beside it.

The pre-registered prediction stands:

- no directional prediction;
- excess within ±0.10;
- composition beyond p97.5 in this arm alone would be the first positive field evidence for the
  embedding, and would need the full set.

### Full set (267 plots, per district) — pending

**No statistics exist yet.** As of 2026-09-15, the twelve configs from commit `f8abf03` (four
district AOIs × three arms) are in progress, each through three pipeline passes. Stand vectors
for the v120 and current KENDUJHAR configs are on disk in `phase2_vectors/`, uncommitted and not
yet joined.

When all are in, the plan is:

1. `odisha_phase2_3_join.py --set districts`.
2. `odisha_phase2_5_stats.py --set districts`.
3. The same 6.1 / 6.2 / 6.3 tables, arms comparison and sensitivity checks, pooled over AOI
   parts.

What is already known about the full set:

- **The UPGMA typology is fixed by the field data.** 259 of the 274 plots are one type, so at most
  15 plots of any set carry another type, and 6.3 under the pre-registered typology will remain
  close to degenerate.
- Whether the full set makes the > 30 m boundary subset estimable is not known until it runs.

### Deliberately not done

- **Percentile tolerance for `MergeCriterion`: NOT BUILT.** This is the outstanding Phase 1
  recommendation. `calibrate_thresholds()` can *report* the percentile a tolerance reaches but
  cannot *accept* one. Building it now would change the merge rule mid-experiment, so the
  supervisor's test would have run against a method he did not ask for.
- **No replacement canopy-height source is installed.** Meta/WRI was DISQUALIFIED in Phase 1
  (`PHASE1_STATUS.md`). **Its absence is a decision, not an omission.**
- **The cached-label decision** (rebuild with `rebuild_cache.py --delete`, or pin and document)
  is open, as above.

---

## Reproducing

```bash
# needs live Earth Engine
python odisha_script/odisha_phase2_1_mask_retention.py          # 4 getInfo calls, no exports
python odisha_script/odisha_phase2_2_run_pipeline.py --config configs/odisha_v120_handcrafted.yaml --through segmentation --wait
python odisha_script/odisha_phase2_2_run_pipeline.py --config configs/odisha_v120_handcrafted.yaml --through clustering --wait
python odisha_script/odisha_phase2_2_run_pipeline.py --config configs/odisha_v120_handcrafted.yaml --through export
#   (same three passes for odisha_current_handcrafted, odisha_alphaearth, and the per-district configs)
python odisha_script/odisha_phase2_4_noise_null.py --size-check 3   # read-only; the size check that failed
python odisha_script/odisha_phase2_6_label_drift.py             # read-only; cached vs fresh labels

# fully offline
python odisha_script/odisha_phase2_0_aois.py                    # pilot, full and per-district AOIs
python odisha_script/odisha_phase2_3_join.py --set pilot        # field table and plot<->stand join
python odisha_script/odisha_phase2_5_stats.py --set pilot       # 6.1 / 6.2 / 6.3, rotation null, default --rotations 1999
```

Steps 0, 1, 3, 5 and 6, and step 4 with `--size-check`, write `odisha_phase2_<n>_results.txt`
beside themselves. Step 2 writes `phase2_vectors/<config>_*`. Step 5 also writes
`odisha_phase2_5_summary.csv` and the three figures. The first run used `--rotations 999`.

The first run's output can be compared with the corrected one without re-running anything:

```bash
git show 8d4c2ed:odisha_script/odisha_phase2_5_results.txt
```
