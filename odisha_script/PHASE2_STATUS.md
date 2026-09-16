# Phase 2 status

Stand-level field validation on Odisha: whether the method's stands group plots that are alike
on the ground, what was run to test it, what the pre-registered predictions said, and what is
still pending.

Every number here comes from code that has been run. Nothing is estimated. There are two runs, and
every statement below names which one it comes from.

- **Full set, 267 plots, four districts** — `odisha_phase2_5_results_districts.txt`,
  `odisha_phase2_5_summary_districts.csv` and three `*_districts.png` figures (commit `e6c4d6b`).
  The join is at `2cd076e`, the stand layers at `1b920d7`.
- **Pilot, 60 plots, six Dhenkanal village forests** — `odisha_phase2_5_results.txt` and
  `odisha_phase2_5_summary.csv` (corrected run, commit `9f5271e`). The AlphaEarth figures come
  from commit `09369f8`, which added that arm to the same run; there, all 266 v120 and current
  summary rows equal `9f5271e` with zero numeric differences (commit message). The three-arm
  figure is from commit `874c5eb`. The first, unverified run is kept at `8d4c2ed`.

The predictions were committed before any statistic existed (`PHASE2_PREDICTIONS.md`, commit
`78ba075`).
**Corrections lists every primary-layer figure that changed since the first run, and every change
that alters a reading. The complete list, secondary layers included, is the CORRECTIONS section of
`odisha_phase2_5_results.txt`.**

**Both runs are in.** The full set is the primary evidence and is reported first; the pilot
follows, and its numbers are unchanged. All three arms (v120, current and AlphaEarth) have
statistics for both.

---

## The answer to the supervisor's question

*Do plots that are ecologically alike end up in the same stand, and plots that differ in
different ones?*

**No, in both runs.** On the full set — 267 plots, 61 multi-plot stands holding 184 of them — the
primary partition's stands group field-alike plots no better than rotated and translated copies of
the same stand map do. No 6.1 percentile reaches p95 (max 73.4). The one statistic that exceeds its
null, Bray–Curtis composition at 99.7, measures the difference *between* village forests rather
than the placement of boundaries within them: it falls to 83.7 under site fixed effects and to 67.8
when one village is dropped. **The full set is the primary evidence** and is reported first; the
pilot agrees, and its section follows unchanged.

How to read the numbers. The **rotation null** moves the real stand map 1999 times by a random
rotation and shift, leaving the plots and their field values in place. **Excess** = observed
value minus the median over those moves. **Percentile** = where the observed value falls among
them. 95 or above would mean the stands do better than chance; 5 or below, worse.

### On the pilot (60 plots, six Dhenkanal village forests)

**Not distinguishably more often than chance, on a pilot that was pre-registered as
underpowered for this test** (`PHASE2_PREDICTIONS.md`, Consequence 4). The primary partition is
`stands_merged` from `odisha_v120_handcrafted`: 197 stands, median 3.93 ha. Its stands group
field-alike plots no better than rotated and translated copies of the same stand map do.

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
- **The secondary AlphaEarth arm reads the same as v120.** No 6.1 percentile reaches p95 (18.0 to
  88.3). Its Bray–Curtis stand effect sits at 94.4, inside the central 90%, and that value also
  rests on Kerijoli: 70.3 without Kerijoli, 57.8 with site fixed effects.

The last five are set out below the primary tables. None of them turns the answer into a positive
result.

---

## What was run

| step | what | result | source |
|---|---|---|---|
| configs | three method versions written as configs, not as reverts. `odisha_v120_handcrafted`: the pre-Odisha method (six-band SNIC, three-criterion merge). `odisha_current_handcrafted`: the same with `canopy_height_std` removed. `odisha_alphaearth`: embedding delineation with the same merge rule as v120 | — | commit `aa4d647` |
| AOIs | **pilot:** six Dhenkanal site polygons, +200 m, 6 parts, 912.0 ha, **60 plots**. **Full:** 21 habitations with ≥ 5 plots, hull +300 m, 4298.7 ha, **267 plots** (261 intended plus 6 from smaller habitations inside the hulls; included by decision) | exit conditions PASS | `odisha_phase2_0_results.txt` |
| habitat mask | MaskingStage run over discs around every plot | **257 of 274 plots kept = 93.8%** (floor 80%). Pilot 60 of 60. KENDUJHAR lowest at 8 of 12 (66.7%). `meta_chm == 0` plots 106 of 122. 15 of the 17 dropped plots are IndiaSAT cropland, 2 are built-up | `odisha_phase2_1_results.txt` |
| pipeline passes | three cache passes per config (segmentation → clustering → export), so each cached asset is computed from the asset upstream of it. The full set runs **per district** — twelve configs, four district AOIs × three arms — because one combined AOI's bounding box exceeds the 1 bn-pixel export cap (decision of 2026-09-14) | **Pilot:** v120 933 superpixels → **197 merged stands**; current 932 → 188; AlphaEarth 929 → 184. **Full set**, four districts combined: v120 3596 → **1039**; current 3604 → 975; AlphaEarth 3589 → 1061 | `odisha_phase2_2_run_pipeline.py`, `odisha_phase2_3_results.txt` |
| field table and join | plots joined to stand polygons by geometry, never by name. Field table reproduces Phase 1 Lorey's height, top-5 height and crown cover exactly (max \|Δ\| = 0) | **Pilot:** vector stand id equals the raster at the plot pixel for **60 of 60** plots in every merged and SNIC layer; 0 boundary-ambiguous plots. **Full set:** 267 plots over 20 AOI parts, all assigned on every merged layer (per-layer counts in the table below) | `odisha_phase2_3_results.txt`, join commit `2cd076e` |
| null | **rotation null, 1999 realisations**, offline: rigid rotation plus translation of the stand map within each AOI part. Plots and their field values stay in place; draws that leave a plot off every polygon are redrawn. **Size-matched by construction** (the same stand polygons, moved), but **not matched on how often plots share a stand**: pilot 46 same-stand pairs observed vs null median 25; full set **247 vs 201** (primary arm, both). On the full set it **cannot be built at all** for the dissolved layer, in the same two AOI parts in every arm. The noise-SNIC null **failed its size check** before any statistic existed and is excluded by recorded decision | — | `PHASE2_PREDICTIONS.md` (Null models), `odisha_phase2_4_results.txt`, `odisha_phase2_5_results.txt`, `odisha_phase2_5_results_districts.txt` |

What the join gave on the **pilot** (v120 and current rows from `PHASE2_PREDICTIONS.md`, before any
field statistic; AlphaEarth rows from `odisha_phase2_3_results.txt`, commit `09369f8`, joined after
the hand-crafted statistics existed):

| arm / layer | stands | multi-plot stands | plots in them | plots > 30 m from a boundary |
|---|---|---|---|---|
| **v120 / `stands_merged`** | **197** | **13** | **35** | **14** |
| v120 / `stands_snic` | 868 | 4 | 10 | 4 |
| v120 / `stands_dissolved` | 97 | 7 | 59 | 52 |
| current / `stands_merged` | 188 | 11 | 32 | 15 |
| current / `stands_snic` | 872 | 5 | 16 | 3 |
| AlphaEarth / `stands_merged` | 184 | 13 | 36 | 20 |
| AlphaEarth / `stands_snic` | 872 | 5 | 12 | 6 |

And on the **full set**, 267 plots over 20 AOI parts in four districts (partition sizes from
`odisha_phase2_5_results_districts.txt`; assigned and boundary-distance counts recomputed from
`phase2_plots_joined_districts.csv`). The merged layer assigns every plot; the SNIC and dissolved
layers do not, and the rotation null forces only the observed-assigned plots onto a stand:

| arm / layer | stands | plots assigned | multi-plot stands | plots in them | plots > 30 m from a boundary |
|---|---|---|---|---|---|
| **v120 / `stands_merged`** | **1039** | **267** | **61** | **184** | **65** |
| v120 / `stands_snic` | 3596 | 265 | 38 | 93 | 13 |
| v120 / `stands_dissolved` | 493 | 252 | 33 | 241 | 190 |
| current / `stands_merged` | 975 | 267 | 59 | 183 | 73 |
| current / `stands_snic` | 3604 | 267 | 40 | 96 | 8 |
| current / `stands_dissolved` | 539 | 253 | 35 | 237 | 183 |
| AlphaEarth / `stands_merged` | 1061 | 267 | 57 | 186 | 96 |
| AlphaEarth / `stands_snic` | 3589 | 266 | 33 | 80 | 15 |
| AlphaEarth / `stands_dissolved` | 497 | 253 | 40 | 242 | 183 |

The 61 multi-plot stands holding 184 of 267 plots are what makes the full set's 6.1 test
adequately powered where the pilot's 13 stands holding 35 plots were not.

---

## PRIMARY RESULT — the full set (267 plots, four districts)

Primary partition: `stands_merged` from `odisha_v120_handcrafted`. **1039 stands**, area p10 1.22 /
median 3.09 / p90 9.18 ha, all 267 plots assigned, **61 multi-plot stands holding 184 of the 267
plots** (the pilot had 13 holding 35). 187 of 1068 polygons (486.81 of 4313.70 ha) carry no
`cluster_id`. Rotation null: 1999 realisations, seed `crc32('v120/stands_merged')`, 184 s, every
AOI part placed. Figures: `odisha_phase2_5_{primary_r2_null,arms_excess,pairwise_bands}_districts.png`.

**Verification.** Every *observed* quantity in this section was recomputed by an independent
re-implementation — own AOI-part assignment, own point-in-polygon join, own geodesic `d_geo`, own
Bray–Curtis, own OLS, own R² — and matched: 267 plots over 20 parts, 3032 within-part pairs, bands
[130, 298, 557, 901], all seven R² with their (k, n), 61 multi-plot stands holding 184 plots, 247
same-stand pairs, every band count/mean/diff, `beta_same` −0.0883 / −0.1873 / +0.3115, site-FE
−0.0181, stand-weighted −0.0548, drop-Kerijoli −0.0113, ARI(unit, part) 0.603. The null *draws*
were regenerated from the script's own seeded rotation sampler — that sampler was not
independently re-implemented — and the percentiles recomputed from them with independent statistic
code, matching digit for digit. One claim made in a commit message did **not** survive: see the
Kerijoli correction below.

### The answer, on the full set

**No. The stands do not group field-alike plots better than a rotated copy of the same stand map —
and this time the test had the power to say so.**

- **6.1 is a clean null.** No variable reaches p95 (64.2 / 73.4 / 46.9 / 65.5 / 47.6 / 67.5, and
  `h_top5_m` at 3.2). Every excess is inside the pre-registered ±0.10, at **−0.072 to +0.029**.
- **6.2 composition exceeds its null, but it is a between-village contrast, not a delineation
  result.** `beta_same` −0.0883 sits at **99.7** and the 200–400 m band at **99.6**. It does not
  survive site fixed effects (**83.7**) and it does not survive dropping one village
  (**67.8** without dhenkanal:Kerijoli).
- **6.2 height is null**: regression 22.6, every band inside the central 90%.
- **6.3 is answerable for angul and dhenkanal only**, and it asks a different question — typology,
  not delineation.

**The pilot's answer is not overturned; it is sharpened.** 6.1 goes from underpowered-and-mixed to
adequately powered and clearly null. The composition signal the pilot found in `current` and
AlphaEarth, and traced to one village, now appears in **v120 as well — and traces to the same
village again.**

### 6.1 Within- vs between-stand variance, R² = 1 − SS_within / SS_total

"Restricted" means multi-plot stands only; the null median, p5, p95, excess and percentile all
refer to the restricted R². (k, n) = (stands, plots).

| variable | R² all (k, n) | R² restricted (k, n) | null median | p5 | p95 | **excess** | **percentile** |
|---|---|---|---|---|---|---|---|
| `loreys_h_m` | 0.880 (144, 267) | 0.738 (61, 184) | 0.719 | 0.64 | 0.79 | **+0.018** | **64.2** |
| `loreys_h_tree_m` | 0.898 (142, 254) | 0.760 (59, 171) | 0.730 | 0.66 | 0.81 | **+0.029** | **73.4** |
| `crown_cover_pct` | 0.812 (144, 267) | 0.740 (61, 184) | 0.743 | 0.69 | 0.80 | **−0.003** | **46.9** |
| `sal_ba_frac` | 0.872 (144, 267) | 0.830 (61, 184) | 0.817 | 0.76 | 0.87 | **+0.013** | **65.5** |
| `n_species` | 0.781 (144, 267) | 0.683 (61, 184) | 0.685 | 0.62 | 0.74 | **−0.002** | **47.6** |
| `dbh_mean_cm` | 0.722 (142, 254) | 0.641 (59, 171) | 0.625 | 0.56 | 0.69 | **+0.017** | **67.5** |
| `h_top5_m` | 0.788 (144, 267) | 0.622 (61, 184) | 0.694 | 0.63 | 0.76 | **−0.072** | **3.2** |

**None is above p95, and none falls to the pre-registered p2.5.** All seven excesses are inside
±0.10 — the excess prediction held 7 of 7, where the pilot's v120 failed 5 of 7.

**`h_top5_m` is the one variable in the low tail, and it is reported here rather than left behind
"none ≥ p95".** Its pre-registered statistic sits at **3.2**, above the p2.5 "stands *split* alike
plots" threshold, so **that surprise did not occur** — but by 0.7 of a percentile. Its
non-pre-registered variants sit lower: adjusted R² 6.0, within-part 4.8, and leave-one-site-out
spanning **1.8 to 16.2**. Those variants are SENSITIVITY, they are not stable (the same variable
reaches 16.2 dropping dhenkanal:Mahabirod and 13.7 dropping koraput:HATIMUNDA), and they are **not
scored as a crossing of the pre-registered threshold.** Read them with the null-shape bias below,
which pushes percentiles down.

### 6.2 Pairwise boundary test at matched distance

Pairs are taken within an AOI part. `diff` = mean over different-stand pairs − mean over same-stand
pairs, so positive means same-stand pairs are more alike. Cells with n ≤ 3 on either side are
uninformative (R4) and get no percentile. The naive within-band permutation p pools sites and its
pairs are not independent; the script labels it **INVALID**.

**Bray–Curtis on relative basal-area composition, all pairs**

| band | n same | n diff | mean same | mean diff | diff | rotation percentile | within-site shuffle p |
|---|---|---|---|---|---|---|---|
| 0–100 m | 81 | 49 | 0.669 | 0.738 | 0.069 | 92.9 (n_null 1999) | 0.230 |
| 100–200 m | 96 | 202 | 0.655 | 0.710 | 0.055 | 83.9 (n_null 1999) | 0.745 |
| 200–400 m | 64 | 493 | 0.578 | 0.740 | 0.162 | **99.6** (n_null 1999) | 0.008 |
| 400–800 m | **6** | 895 | 0.395 | 0.785 | 0.390 | **97.7** (n_null 1889) — **thin** | 0.008 |

Regression `d_field ~ d_geo + same_stand` (pairs < 800 m, n = 1886, 247 same-stand):
**beta_same −0.0883**, beta per 100 m 0.0139, null median +0.0014,
**stand-effect percentile 99.7** (n_null 1999).

**The only well-populated exceedance is the 200–400 m band (64 / 493).** The 400–800 m cell clears
the MIN_CELL = 3 rule by three pairs and is undefined in 110 of 1999 realisations; read it as
uninformative in substance. The same applies to the 200–400 m cell of the > 30 m subset (4 same
pairs) and to the |ΔLorey's| 400–800 m cell (76.0), which rests on those same 6 pairs.

**|ΔLorey's height| (m), all pairs**

| band | n same | n diff | mean same | mean diff | diff | rotation percentile |
|---|---|---|---|---|---|---|
| 0–100 m | 81 | 49 | 3.714 | 3.036 | −0.678 | 6.5 |
| 100–200 m | 96 | 202 | 3.634 | 3.365 | −0.269 | 25.9 |
| 200–400 m | 64 | 493 | 3.848 | 3.642 | −0.206 | 46.2 |
| 400–800 m | 6 | 895 | 2.038 | 4.396 | 2.359 | 76.0 (thin, as above) |

Regression (n = 1886, 247 same): **beta_same +0.3115 m**, null median +0.0135,
**stand-effect percentile 22.6**. Height is null throughout.

**Pairs with both plots > 30 m from a boundary: estimable for the first time.** 104 pairs, 24
same-stand. Bray–Curtis **beta_same −0.1873**, percentile **97.8**; bands 91.4 (11 / 14) and
70.2 (**4** / 27), the other two uninformative. |ΔLorey's| beta_same +1.3243, percentile 17.7.
The subset points the same way as the all-pairs statistic, but both of its informative cells are
thin and its within-site shuffle p is 0.135.

### What the composition signal actually is (SENSITIVITY, not pre-registered)

**The 99.7 is real, and it is neither a null artefact nor a distance artefact — but it is a
between-village composition contrast concentrated in one village.**

*What is ruled out.* Same-stand pairs do sit much nearer (mean `d_geo` 157.7 m vs 440.2 m), but
controlling distance more finely makes the effect **stronger**: `beta_same` −0.1102 with 50 m
distance-bin dummies and −0.1139 with 25 m, against −0.0883 linear. And the rotation null's
co-membership mismatch does not manufacture it: against realisations matched on same-stand pair
count the percentile stays at 100.0 (N 35 at ±5, N 77 at ±10, N 196 at ±20), with corr(null
n_same, null beta) = +0.032. **The raw exceedance must not be dismissed as a broken null.**

*What it is.*

| check | value |
|---|---|
| pooled same-vs-different Bray–Curtis contrast | **+0.1276** |
| same-stand-pair-weighted mean of **within-village** contrasts | **+0.0234** (unweighted +0.0178) |
| villages pointing the "stands work" way | **10 of 19** (the 20th has no same-stand pairs) |
| pairs supplied by one stand (dhenkanal:Kerijoli id 62, 9 plots, 6.87 ha) | **36 of 247** |
| beta_same dropping the top-1 / top-3 / top-5 contributing stands | **−0.0039 / −0.0337 / −0.0377** |
| **inside Kerijoli**: mean BC same-stand vs different-stand | **0.163 vs 0.101** (difference **−0.0625**, the wrong direction) |
| Kerijoli mean within-part BC vs the rest of the set | **0.151 vs 0.759** |
| Kerijoli within-part pairs < 800 m that are same-stand | **80.0%** (most villages 5–15%) |
| corr(village same-pair share, village mean BC) over 20 parts | **−0.569** |

Kerijoli's 36 pairs enter the pooled regression as "same-stand **and** very low Bray–Curtis" only
because the whole village forest is compositionally uniform — not because its boundaries separate
unlike plots. Inside it, the effect runs backwards.

Robustness of the Bray–Curtis stand effect (`beta_same`, all pairs):

| variant | n same | beta_same | stand-effect percentile |
|---|---|---|---|
| as pre-registered | 247 | −0.0883 | **99.7** |
| site fixed effects | 247 | −0.0181 | **83.7** |
| stand-weighted (1 / pairs per stand) | 247 | −0.0548 | **95.3** (marginal) |
| **drop dhenkanal:Kerijoli** | **211** | **−0.0113** | **67.8** |
| drop any one of the other 19 villages | 190–247 | −0.1167 to −0.0821 | 99.3–99.8 |

**Kerijoli is the only village whose removal takes the result below p95.** Of the three dominance
checks, drop-one-village fails outright, site fixed effects fail, and stand weighting is marginal.

> **Correction to the `e6c4d6b` commit message.** That message reported the leave-one-site-out
> range as "99.5–99.8 for every site including dropping Kerijoli". It is wrong on both counts. The
> committed results file (line 134) has always said `drop dhenkanal:Kerijoli … beta_same −0.0113 …
> pctile 67.8`, and the other 19 span 99.3–99.8, not 99.5–99.8. **The full set does not clear the
> pilot's Kerijoli trap; the primary arm falls into it.** No number changed — only the summary of
> them was wrong.

Same-stand pairs by AOI part, observed / null median / percentile: **dhenkanal:Kerijoli 36 / 9 /
100.0** (no realisation matches it), angul:JOGI BANDHA 20 / 10 / 98.6, angul:ANANDA PUR 16 / 7 /
98.5, koraput:BARAKANTI 27 / 18 / 92.7. The large koraput parts sit far lower: HANDAPUR 45.6,
HATIMUNDA 40.4, BARIGUDA 38.3, KHASUGUDA 38.2, SAKIAGUDA 36.5 (KONDASRIMUNDA, the smallest at 5
plots, 60.2).

**The within-site shuffle p is not a stable result.** The committed value for `beta_same` is
**0.038**; re-running the same specification independently (9999 shuffles, different seed) gives
**0.042**, and grouping on part × 50 m bins gives **0.081**. Band width alone moves it across 0.05.

### The rotation null still does not have the observed partition's co-membership (SENSITIVITY)

By the pre-registered size criterion the null passes — it moves the same polygons. It fails only on
the post-hoc check of how often plots share a stand, and the mismatch is **larger than in the
pilot**:

| quantity | observed | null median | p5 | p95 | percentile |
|---|---|---|---|---|---|
| k (multi-plot stands) | 61 | 60 | 54 | 67 | 58.9 |
| n (plots in them) | 184 | 170 | 159 | 182 | **97.3** |
| E = (k − 1)/(n − 1) | 0.328 | 0.351 | 0.327 | 0.374 | 6.6 |
| largest multi-plot group | 9 | 7 | 6 | 10 | 83.6 |
| **same-stand within-part pairs** | **247** | **201** | 171 | 234 | **98.3** |

The E-slope bias is **negative for every variable** (−0.005 to −0.015 R² units), so the 6.1
percentiles are biased low. It is smaller than the pilot's (−0.007 to −0.034). The mismatch is
worse in the secondary arms: `current` 281 vs 210 (99.9), AlphaEarth 302 vs 201 (100.0).
**This mismatch belongs beside the 6.2 headline — but it is not what produces the 99.7**, per the
matched-null check above.

### Between-village variance and the alternatives to raw R² (SENSITIVITY)

Adjusted R² percentiles: 71.0 / 77.6 / 57.0 / 72.2 / 58.6 / 74.7 / **6.0**. Within-part R²
(SS_total about AOI-part means, so between-village difference cannot count as stand signal):
0.352 / 0.369 / 0.356 / 0.301 / 0.437 / 0.297 / 0.302, percentiles
44.4 / 52.4 / 43.5 / 63.0 / 56.8 / 33.3 / **4.8**. **None is above p95 in any form**, and the only
values near an edge are `h_top5_m`'s, in the low tail.

### 6.3 Label agreement: typology, not delineation

A different question from 6.1 and 6.2: whether the k-means `cluster_id` of a plot's stand tracks a
field forest type. It says nothing about where boundaries fall. k-means is fitted **per district**,
so labels are comparable only within a district, and 6.3 uses only realisations that keep every
typed plot on a typed polygon (R12).

| district | typed plots | realisations used | ARI | NMI | Cramér's V |
|---|---|---|---|---|---|
| angul | 39 of 39 | 798 of 1999 | 0.075 (**99.9**) | 0.147 (**98.7**) | 0.386 (89.0) |
| dhenkanal | 75 of 75 | 601 of 1999 | 0.018 (**99.2**) | 0.062 (**99.0**) | 0.569 (94.9) |
| kendujhar | 8 of 8 | 1582 of 1999 | NOT ESTIMABLE (one field type) | — | — |
| koraput | 144 of 145 | **52 of 1999** | 0.038 **NOT ESTIMABLE** | 0.080 **NOT ESTIMABLE** | 0.473 **NOT ESTIMABLE** |

**6.3 is answerable for angul and dhenkanal only.** koraput retains 52 realisations after the R12
filter yet holds 145 of the 267 plots, so **no null-based typology inference exists for 54% of the
set**. The set-level null is the c-th valid realisation of each district combined index-wise and
therefore rests on those **52 combined draws**, so every set-level percentile, and both
distant-pair statistics (`distant_diff_bc` 0.018, `distant_diff_lorey` −0.285), print NOT
ESTIMABLE.

**The pre-registered "none above p95" now fails** in angul (ARI, NMI) and dhenkanal (ARI, NMI) —
new, since the pilot's UPGMA was wholly not estimable. The ARI and NMI *value* ranges held; V is
outside its range in dhenkanal (0.569) and koraput (0.473). Contingency tables are thin throughout
(9 of 12 cells with expected count < 5 in angul, 6 of 10 in dhenkanal).

**Label-stability caveat.** `odisha_phase2_6_results.txt` measures cached-vs-fresh label drift for
the **60-plot pilot, and for v120 and current only**. The 267-plot run uses twelve per-district
configs with distinct fingerprints whose drift was never measured, and AlphaEarth was never
measured at all. The districts results file mentions drift nowhere. Both 6.3 and the dissolved
layer read labels; 6.1 and 6.2 on the merged and SNIC layers do not.

### `stands_dissolved`: rotation null NOT BUILT in all three arms

**All three dissolved partitions report the rotation null NOT BUILT, and every null-based statistic
is NOT ESTIMABLE (n_null 0).** The same **two AOI parts** fail in each arm, and the draws reached
the cap of 450,200:

| arm | angul:ANANDA PUR (9 plots, 8 forced; plain sampler; geometric acceptance 0.249) | koraput:HATIMUNDA (59 plots, 54–55 forced; feasible-region; 0.002) |
|---|---|---|
| v120 | accepted 992 of 1999; 110,922 draws inside the part | accepted 418 of 1999; 449,663 inside |
| current | accepted 932 of 1999; 110,148 inside | accepted 375 of 1999; 449,679 inside |
| AlphaEarth | accepted 1039 of 1999; 110,397 inside | accepted 422 of 1999; 449,617 inside |

No part was dropped and the acceptance rule is unchanged (Jaskaran's decision of 2026-09-15).
Observed values are printed and recorded as usual: v120 `loreys_h_m` R² all 0.627 (44, 252),
restricted 0.579 (33, 241).

**The pilot's reason for setting this layer aside no longer applies and is not carried over.**
ARI(unit, AOI part) is **0.603** (v120), 0.570 (current) and 0.528 (AlphaEarth) — all below the
script's own 0.7 "effectively the site partition" threshold, which does **not** fire here, and
koraput:HATIMUNDA alone splits into 11 / 18 / 9 units (the pilot's values were 0.932 / 0.915 /
0.922). **The layer is set aside here solely because its rotation null is unbuildable** — that, and
nothing more.

*Caveat on the identity check (R5).* The dissolved-sens block compares the dissolved restricted R²
(241 plots, 33 groups) against a site-only R² computed over all 267 plots in 20 groups. The group
counts differ, so the comparison is confounded, and more groups mechanically raise R². The
identical `site_r2` row across all three arms is the tell. The fix — restrict the site-only R² to
the layer's assigned plots, or drop the comparison — is a code change and is listed under Pending;
it is not applied retroactively to a committed run.

### SECONDARY arms and layers, full set

Raw R² is **never** compared across arms or layers; each partition is read only as excess over its
own rotation null. Figure: `odisha_phase2_5_arms_excess_districts.png`.

**current / `stands_merged`.** 975 stands, p10 1.25 / median 3.49 / p90 9.17 ha; 59 multi-plot
stands hold 183 plots. 6.1 percentiles 63.0 / 61.8 / 66.0 / 79.9 / **98.2** / 67.4 / 68.5, excesses
+0.013 to +0.072 (all inside ±0.10).

- **`n_species` at 98.2** is one exceedance in seven variables, inside the pre-registered 0.35
  chance allowance. SENSITIVITY: adjusted 99.5, within-part 99.3, and it survives dropping any
  village **except koraput:HATIMUNDA, where it falls to 51.5** — a single-site dependency of its
  own.
- **6.2 Bray–Curtis**: bands 97.8 / 89.1 / 98.4 / 67.8, regression **98.5** (`beta_same` −0.0615).
  SENSITIVITY: site fixed effects **80.1**, drop-Kerijoli **55.7** (beta +0.0069), stand-weighted
  98.3. Kerijoli stand 59 (9 plots) again supplies 36 same-stand pairs.
- **6.2 |ΔLorey's|**: regression 71.9 raw, but **99.4 with site fixed effects** (beta −0.7433) —
  the one place in the set where adding site FE strengthens rather than collapses a 6.2 value. It
  is a SENSITIVITY variant of a pre-registered statistic that was null, and it wants explaining
  rather than averaging.
- Null shape: same-stand pairs 281 vs null median 210 (**99.9**), E 0.319 vs 0.346 (3.7).

**alphaearth / `stands_merged`.** 1061 stands, p10 1.28 / median 3.11 / p90 8.63 ha; 57 multi-plot
stands hold 186 plots. 6.1 percentiles 60.4 / 61.9 / 21.7 / 84.3 / 54.8 / 53.2 / 74.8, excesses
−0.026 to +0.036 — **held 7 of 7**, where the pilot failed for `n_species`.

- **6.2 Bray–Curtis**: bands 93.5 / 85.8 / 83.9 (400–800 m uninformative, 3 same pairs), regression
  **94.8**, inside the central 90%. SENSITIVITY: site FE 82.0, drop-Kerijoli 82.7, but
  **stand-weighted 99.8** — the opposite direction to v120 (95.3) and current (98.3). Not averaged
  across arms; recorded as unexplained.
- Null shape is the worst of the three: same-stand pairs **302 vs 201 (100.0)**, E 0.303 vs 0.352
  (**0.2**), n in multi-plot stands 186 vs 166 (99.5).
- **The pre-registered AlphaEarth-only composition surprise did not occur, and could not**: no
  AlphaEarth merged-layer value exceeds p97.5 while v120's does, so the "AlphaEarth only"
  condition fails from the other side.

**`stands_snic`.** v120: 3596 stands, 265 of 267 plots assigned, 38 multi-plot superpixels holding
93 plots. 6.1 percentiles 30.3 / 36.3 / 20.6 / 69.2 / **2.8** / 23.6 / 14.6. **6.2 Bray–Curtis
`beta_same` +0.0304, percentile 38.7** on 76 same-stand pairs — **the ~1 ha layer, which is far too
small to express a village, shows nothing in the primary arm.** That is the cleanest corroboration
that the merged layer's composition exceedance is a village-scale contrast. current gives 97.5 and
AlphaEarth 83.2 on the same layer.

**Arms comparison, `stands_merged`.** v120 − current: all seven differences fall **inside** the
differenced null (lowest `h_top5_m` 5.5, `n_species` 7.6). Under the own-null reading (the closer
match to the committed wording), `n_species` (−0.074) and `h_top5_m` (−0.091) fall **inside
neither** arm's spread. v120 − AlphaEarth (no difference prediction was pre-registered for this
pair): `h_top5_m` −0.098 falls **OUTSIDE** the differenced null (percentile **4.0**) and inside
neither own null; the other six are inside. Both failures fall on `h_top5_m`, the one variable in
v120's low tail.

### Predictions on the full set: what held, what failed, what could not be tested

Consequences 1–4 of `PHASE2_PREDICTIONS.md` were written for the 60-plot pilot and are **not
scored here**. Consequence 3 in particular does not transfer: the full set's 0–100 m band holds 130
pairs (81 same / 49 different) and is informative.

| prediction | observed, v120 (primary) | observed, current (secondary) | observed, AlphaEarth (secondary) | verdict |
|---|---|---|---|---|
| **Standing:** stands do not group field-similar plots better than a size-matched, spatially coherent random partition | no 6.1 percentile ≥ 95 (max 73.4); **6.2 Bray–Curtis bands 99.6 / 97.7 and regression 99.7** | 6.1 one exceedance (`n_species` 98.2); **6.2 Bray–Curtis 97.8 / 98.4, regression 98.5** | no 6.1 percentile ≥ 95 (max 84.3); 6.2 bands 93.5 / 85.8 / 83.9, regression 94.8 | **held for 6.1 in all three arms. FAILED on the 6.2 composition statistic for v120 and current**; held for AlphaEarth. Both failures are between-village contrasts (SENSITIVITY) |
| 6.1 raw restricted R² 0.4–0.8 | 0.622–0.830 | 0.641–0.844 | 0.636–0.855 | **held 7 of 7, all three arms** (pilot: 6 of 7, 5 of 7) |
| 6.1 excess −0.10 to +0.10 | −0.072 to +0.029 | +0.013 to +0.072 | −0.026 to +0.036 | **held 7 of 7, all three arms** (pilot v120 failed 5 of 7) |
| 6.1 percentile < 95; one exceedance of 7 within prediction (0.35 expected) | max 73.4 (`loreys_h_tree_m`) | one: `n_species` 98.2 | max 84.3 (`sal_ba_frac`) | **held, all three arms** (current's single exceedance is inside the allowance) |
| 6.1 chance level E[R²] ≈ 0.45–0.55 for restricted stands | E = **0.328** | E = **0.319** | E = **0.303** | **wrong again**, in all three arms, as in the pilot |
| 6.2 `d_field` rises with `d_geo`, both measures | Bray–Curtis slope **+0.0199** per 100 m, ρ +0.174; \|ΔLorey's\| **+0.2043** per 100 m, ρ +0.119 (n = 1886). Mean \|ΔLorey's\| 4.06 m within parts vs 4.81 m > 2 km | same (partition-independent) | same | **held for both measures** — an improvement on the pilot, which failed it for \|ΔLorey's\| within 800 m |
| 6.2 raw within-band difference slightly in the "stands work" direction, predicted and not evidence | Bray–Curtis +0.069 / +0.055 / +0.162 / +0.390; \|ΔLorey's\| −0.678 / −0.269 / −0.206 / +2.359 | Bray–Curtis all four positive | Bray–Curtis all four positive | **direction held for Bray–Curtis, not for height**, as in the pilot |
| 6.2 band differences and the `same_stand` coefficient inside the null's central 90% | Bray–Curtis **99.6** (200–400 m) and **97.7** (400–800 m, 6 same pairs), regression **99.7**. \|ΔLorey's\| 6.5 / 25.9 / 46.2 / 76.0, regression 22.6 | Bray–Curtis **97.8 / 98.4**, regression **98.5**. \|ΔLorey's\| regression 71.9 (but **99.4** with site FE) | Bray–Curtis 93.5 / 85.8 / 83.9, regression 94.8. \|ΔLorey's\| regression 57.9 | **FAILED for Bray–Curtis in v120 and current; held for AlphaEarth; held for height in all three.** SENSITIVITY: site FE 83.7 / 80.1 / 82.0, drop-Kerijoli 67.8 / 55.7 / 82.7 |
| 6.2 > 30 m boundary subset: same, with fewer pairs | 104 pairs (24 same); regression **97.8**; bands 91.4 (11 / 14) and 70.2 (4 / 27), two uninformative | 117 pairs (35 same); regression 83.0 | 192 pairs (54 same); regression 93.1 | **estimable for the first time** (the pilot could not test it). It points the same way as the all-pairs statistic; both informative cells are thin |
| 6.2 within-band label-permutation p > 0.05 | 0.057 / 0.048 / 0.000 / 0.000, regression 0.000 | 0.022 / 0.041 / 0.000 / 0.132, regression 0.000 | 0.111 / 0.046 / 0.036 / 0.000, regression 0.001 | **FAILED as pre-registered for Bray–Curtis in all three arms.** The script labels this p INVALID (pools sites, pairs dependent), a post-hoc judgment (R6) |
| 6.3 UPGMA k = 6: ARI −0.05 to +0.10, NMI 0.05–0.25, V 0.25–0.45, **none above p95** | ARI 0.075 (**99.9**) angul, 0.018 (**99.2**) dhenkanal, 0.038 koraput NOT ESTIMABLE; NMI 0.147 (98.7) / 0.062 (99.0) / 0.080 NE; V 0.386 (89.0) / **0.569** (94.9) / **0.473** NE | ARI 0.015 (89.6) / 0.006 (64.1) / 0.053 NE | ARI 0.013 (70.7) / 0.007 (47.3) / −0.018 NE | **value ranges held for ARI and NMI; V outside the range in dhenkanal and koraput. "None above p95" FAILED for v120 in angul and dhenkanal** — new, since the pilot's UPGMA was wholly not estimable |
| 6.3 distant pairs inside the null's central 90% | `distant_diff_bc` 0.018, `distant_diff_lorey` −0.285, both **NOT ESTIMABLE** (n_null 52) | both NOT ESTIMABLE (n_null 71) | both NOT ESTIMABLE (n_null 22) | **not estimable in any arm**: the set-level null rests on the koraput realisation count |
| Arms: "the difference in excess-over-own-null falls inside either arm's null spread" (committed for current vs v120 only) | — | v120 − current: all seven **inside** the differenced null (min 5.5). Own-null reading: `n_species` (−0.074) and `h_top5_m` (−0.091) **inside neither** | v120 − AlphaEarth: `h_top5_m` −0.098 **OUTSIDE** (differenced-null percentile 4.0) and inside neither own null; the other six inside | **held under the differenced null for v120 − current; fails for 2 of 7 under the own-null reading.** No difference prediction was pre-registered for v120 − AlphaEarth |
| Surprise: primary `loreys_h_m` or `crown_cover_pct` ≥ p97.5, same direction in the > 30 m subset | 64.2 and 46.9 | — | — | did not occur |
| Surprise: primary ≤ p2.5 (stands *split* alike plots) | min **3.2** (`h_top5_m`), on the pre-registered statistic | — | — | **did not occur**, but by 0.7 of a percentile. SENSITIVITY variants of the same variable fall to 1.8 (leave-one-site-out range 1.8–16.2); they are not pre-registered and are not scored as a crossing |
| Surprise: composition beyond p97.5 in the **AlphaEarth arm only** | v120 Bray–Curtis regression 99.7, 200–400 m band 99.6 | — | `sal_ba_frac` 84.3; Bray–Curtis 93.5 / 85.8 / 83.9 / regression 94.8 — no AlphaEarth merged-layer value beyond p97.5 | **did not occur, and could not**: the "AlphaEarth only" condition fails because v120 exceeds p97.5 while AlphaEarth does not |
| Surprise: ARI ≥ 0.2 | UPGMA max 0.075; Sal-rule 2-district mean 0.036 | Sal-rule kendujhar 0.355 (8 plots) | Sal-rule kendujhar 0.556 (8 plots) | **did not occur in the primary arm.** The two kendujhar values rest on 8 plots with 5–6 of 6 cells expected < 5, and the 2-district Sal-rule mean reaches 95.2 in both secondary arms on 83 of 267 plots. Not read as a typology finding |
| Surprise: fewer than 5 multi-plot merged stands | 61 | 59 | 57 | did not occur; the full set is adequately powered for 6.1 where the pilot was not |

### How the full set changes the pilot's answer

- **6.1: the pilot's null is confirmed with real power.** 61 multi-plot stands holding 184 plots
  against the pilot's 13 holding 35. No percentile ≥ p95, none ≤ p2.5 on a pre-registered
  statistic, and the excess prediction held 7 of 7 in every arm where the pilot's v120 failed 5 of
  7. The pilot's caveat "a real but modest effect could sit inside the null" is much weaker now.
- **6.2 composition: the pilot's trap persists, and has spread to the primary arm.** The pilot
  found a Kerijoli-dependent composition signal in `current` (99.8 → 80.7 without Kerijoli) and
  AlphaEarth (94.4 → 70.3). The full set finds the same thing in **v120** (99.7 → 67.8). One stand
  in one compositionally uniform village supplies 36 of 247 same-stand pairs, and inside that
  village the effect runs backwards. **The full set reproduces the pilot's finding rather than
  overturning it.**
- **What is genuinely new.** The > 30 m boundary subset is estimable for the first time (104 pairs)
  and points the same way; the pre-registered "`d_field` rises with `d_geo`" now holds for both
  measures; the dissolved layer is no longer the site partition but is unusable for a different
  reason (unbuildable null); and 6.3 produces its first estimable UPGMA values, which exceed p95 in
  two districts and are not estimable for the district holding most of the plots.
- **What has not improved.** The rotation null still does not reproduce the observed partition's
  co-membership, and the mismatch is larger than in the pilot. No valid p-value supports any 6.2
  cell: the naive permutation p remains INVALID, and the within-site shuffle p crosses 0.05 on band
  width alone.

**The one-line reading: the stands do not group field-alike plots better than a rotated copy of the
same map, and the one statistic that exceeds its null measures the difference between village
forests, not the placement of boundaries within them.**

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
stand's pair count. The secondary AlphaEarth arm's Bray–Curtis stand effect (94.4) also rests on
Kerijoli (70.3 without Kerijoli, 57.8 with site fixed effects), and unlike current it does not
survive stand weighting (74.4); see its section.

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
percentile is **58.3**. Across arms, `n_species` sits near the top of the null in all three:
restricted percentiles 92.0 (v120), 84.9 (current) and 88.3 (AlphaEarth), none above p95.

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

## Predictions on the pilot: what held, what failed, what could not be tested

The full set is scored separately, above. The predictions are from `PHASE2_PREDICTIONS.md`. None of
them was restricted to one arm, so both
hand-crafted arms' `stands_merged` layers are scored. v120 is the primary; `current` is secondary.
The secondary AlphaEarth arm is scored in its own table below; its arm-specific prediction and
surprise are in the main table.

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
| Arms: "the difference in excess-over-own-null falls inside either arm's null spread" (committed for current vs v120 only) | — | — | **v120 − current: failed for `dbh_mean_cm` under both readings, and also for `sal_ba_frac` under the committed wording.** No difference prediction was pre-registered for v120 − AlphaEarth; the script applies the same test to that pair, and the difference falls outside for `dbh_mean_cm` (both readings; differenced-null percentile 2.3) and `sal_ba_frac` (own-null reading only, marginal). Both fall on v120's own low excesses (−0.172, −0.140). See Arms comparison: the differenced-null operationalisation was chosen after the first run (R10) |
| Consequence 1: `stands_snic` holds 0–3 multi-plot superpixels | 4 | 5 | **missed**; recorded in the predictions file before any statistic |
| Consequence 2: `stands_merged` holds ~6–15 multi-plot stands with 12–35 plots | 13 stands / 35 plots | 11 / 32 | **held** |
| Consequence 3: the 0–100 m band is tiny and read as uninformative | 14 pairs; 9 same / 5 different | 14 pairs; 11 same / 3 different | **held**; read as uninformative throughout |
| Consequence 4: the pilot is underpowered for 6.1 and 6.2 | null p5–p95 for `loreys_h_m` 0.56–0.85 at (13, 35); 6.1 percentiles spread 3.2–92.0 | null p5–p95 for `loreys_h_m` 0.56–0.85 at (11, 32) | **held** |
| Surprise: primary `loreys_h_m` or `crown_cover_pct` ≥ p97.5, same direction in the > 30 m subset | 17.1 and 43.8 | — | did not occur (and the subset condition could not have been checked) |
| Surprise: primary ≤ p2.5 (stands split alike plots) | min 3.2 (`dbh_mean_cm`) | — | did not occur |
| Surprise: ARI ≥ 0.2 | UPGMA not estimable; Sal-rule secondary 0.132 | Sal-rule secondary 0.124 | not estimable as pre-registered; the Sal-rule secondary is below 0.2 in both arms |
| Surprise: fewer than 5 multi-plot merged stands | 13 | 11 | did not occur |
| Surprise: noise null not size-matched | median superpixel 4 px vs 82 px observed | — | **occurred, before any statistic**; rotation null read instead |
| Surprise: composition (`sal_ba_frac`, Bray–Curtis) beyond p97.5 in the AlphaEarth arm only | — | — | **did not occur** on AlphaEarth `stands_merged`: `sal_ba_frac` 48.0; Bray–Curtis bands 83.6 / 91.6, regression 94.4 (70.3 without Kerijoli). One AlphaEarth-only composition value beyond p97.5 exists: the dissolved-layer > 30 m Bray–Curtis 200–400 m cell (98.5, 7 different-unit pairs; v120's same cell 28.7, current's uninformative). **It is set aside by judgment, not by a rule**, because that layer is the site partition (ARI(unit, AOI part) 0.922) and is built from labels whose drift was not measured for this arm |
| AlphaEarth: excess within ±0.10, no directional prediction | — | — | **held for 6 of 7** (−0.087 to +0.064). **FAILED for `n_species`**: +0.106, which is +0.11 at the pre-registered precision (percentile 88.3). No 6.1 percentile ≥ 95 |

**AlphaEarth `stands_merged` (secondary)**

| prediction | observed, AlphaEarth | verdict |
|---|---|---|
| **Standing:** stands do not group field-similar plots better than a size-matched, spatially coherent random partition | no 6.1 percentile ≥ 95 (max 88.3); 6.2 informative bands Bray–Curtis 83.6 / 91.6, \|ΔLorey's\| 61.4 / 17.1; regressions 94.4 / 40.1 | **held.** The Bray–Curtis regression at 94.4 is a Kerijoli signal, not near-evidence of an embedding composition signal: 70.3 without Kerijoli, 57.8 with site fixed effects, 74.4 stand-weighted (SENSITIVITY) |
| 6.1 raw restricted R² 0.4–0.8 | 0.697–0.747 for five variables; `n_species` 0.877, `dbh_mean_cm` 0.839 | **held for 5 of 7** |
| 6.1 excess −0.10 to +0.10 | six inside (−0.087 to +0.064); `n_species` +0.106 | **failed for 1 of 7** (`n_species`, +0.11 at the pre-registered precision) |
| 6.1 percentile < 95; one exceedance of 7 within prediction | max 88.3 (`n_species`) | **held** |
| 6.1 chance level E[R²] ≈ 0.45–0.55 for restricted stands | E = **0.343** | **wrong**, as for v120 and current |
| 6.2 raw within-band difference slightly in the "stands work" direction | informative bands: Bray–Curtis 0.155, 0.164; \|ΔLorey's\| 1.470, −1.975 | **held for Bray–Curtis; mixed for height** |
| 6.2 band differences and the `same_stand` coefficient inside the null's central 90% | Bray–Curtis 83.6 / 91.6, regression 94.4. \|ΔLorey's\| 61.4 / 17.1, regression 40.1 | **held** (Bray–Curtis regression near the edge; a Kerijoli signal, as above) |
| 6.2 > 30 m boundary subset: same, with fewer pairs | 20 plots; 26 pairs under 800 m (8 same-stand); every band has ≤ 3 same-stand or ≤ 3 different-stand pairs; regressions 91.2 / 5.2 (n_null 1817) | **could not be tested**: bands uninformative by R4; regressions set aside by judgment. The \|ΔLorey's\| regression at 5.2 and the 200–400 m cell (1 same-stand pair) are not read as a splitting signal |
| 6.2 within-band label-permutation p > 0.05 | Bray–Curtis 100–200 m p 0.073, 200–400 m p **0.032**, regression p **0.006**. \|ΔLorey's\| 0.253 / 0.855, regression 0.526 | **FAILED as pre-registered for Bray–Curtis.** The script labels this p INVALID (it pools sites), a post-hoc judgment (R6). Separately, SENSITIVITY: the within-site shuffle p for Bray–Curtis is 0.231 / 0.219 / 0.166 |
| 6.3 UPGMA k = 6: ARI, NMI, V ranges, none above p95 | all 60 pilot plots are one type | **not estimable** |
| 6.3 distant pairs inside the null's central 90% | Bray–Curtis 72.8, \|ΔLorey's\| 92.7 | **held** (label drift not measured for this arm) |
| Arms, v120 − AlphaEarth (no difference prediction pre-registered for this pair; the script applies the current-vs-v120 test) | `dbh_mean_cm` −0.235, differenced-null percentile 2.3, outside both own nulls. `sal_ba_frac` −0.136, differenced null 9.8, outside both own nulls (edges −0.134 and −0.128) | **outside for `dbh_mean_cm` (both readings) and `sal_ba_frac` (own-null reading only, marginal)**; see Arms comparison |
| Consequence 1: `stands_snic` holds 0–3 multi-plot superpixels | 5 | **missed**, as in the other arms |
| Consequence 2: `stands_merged` holds ~6–15 multi-plot stands with 12–35 plots | 13 stands / 36 plots | **held for stands; 36 plots is one above the range** |
| Consequence 3: the 0–100 m band is tiny and read as uninformative | 14 pairs; 11 same / 3 different | **held** |
| Consequence 4: the pilot is underpowered for 6.1 and 6.2 | null p5–p95 for `loreys_h_m` 0.56–0.85 at (13, 36) | **held** |
| Surprise: composition beyond p97.5 in the AlphaEarth arm only | `sal_ba_frac` 48.0; Bray–Curtis 83.6 / 91.6 / 94.4 | **did not occur** (see the main table) |
| Surprise: ARI ≥ 0.2 | UPGMA not estimable; Sal-rule secondary 0.032 | not estimable as pre-registered; the Sal-rule secondary is below 0.2 |
| Surprise: fewer than 5 multi-plot merged stands | 13 | did not occur |

---

## SECONDARY results (pilot)

The full set's secondary arms and layers are reported above. Raw R² is **never** compared across
arms or layers. Each partition is read only as excess over its own rotation null. Figure:
`odisha_phase2_5_arms_excess.png` (three arms, commit `874c5eb`).

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

### AlphaEarth / `stands_merged`

Embedding delineation: SNIC on the 64 AlphaEarth bands, with the same merge rule as v120. The
statistics are the "SECONDARY — alphaearth" sections of `odisha_phase2_5_results.txt` (commit
`09369f8`). Adding the arm left every v120 and current row unchanged.

Partition: 929 superpixels → 184 stands, area p10 1.29 / median 4.79 / p90 9.11 ha. All 60 plots
assigned. **13 multi-plot stands hold 36 plots** (plots-per-stand histogram {1: 24, 2: 7, 3: 5,
7: 1}). 20 plots are > 30 m from a boundary. 12 of 188 polygons (16.18 of 914.76 ha) carry no
`cluster_id`.

| variable | R² all (k, n) | R² restricted (k, n) | null median | excess | percentile |
|---|---|---|---|---|---|
| `loreys_h_m` | 0.812 (37, 60) | 0.709 (13, 36) | 0.733 | −0.024 | 40.5 |
| `loreys_h_tree_m` | 0.814 (37, 60) | 0.710 (13, 36) | 0.739 | −0.029 | 38.3 |
| `crown_cover_pct` | 0.812 (37, 60) | 0.697 (13, 36) | 0.785 | −0.087 | 18.0 |
| `sal_ba_frac` | 0.824 (37, 60) | 0.747 (13, 36) | 0.751 | −0.004 | 48.0 |
| `n_species` | 0.905 (37, 60) | 0.877 (13, 36) | 0.771 | **+0.106** | 88.3 |
| `dbh_mean_cm` | 0.914 (37, 60) | 0.839 (13, 36) | 0.775 | +0.064 | 77.7 |
| `h_top5_m` | 0.796 (37, 60) | 0.732 (13, 36) | 0.752 | −0.020 | 39.6 |

**No variable reaches p95, and none falls to p2.5.** Six of seven excesses are inside ±0.10.
**`n_species` at +0.106 is outside**: +0.11 at the pre-registered precision, so the AlphaEarth
excess prediction fails for 1 of 7. `n_species` sits near the top of the null in all three arms
(92.0 / 84.9 / 88.3), none above p95.

This arm's null shape is off in the same direction as the hand-crafted arms' (SENSITIVITY):

| quantity | observed | null median | p5 | p95 | percentile |
|---|---|---|---|---|---|
| k (multi-plot stands) | 13 | 12 | 9 | 16 | 61.6 |
| n (plots in them) | 36 | 30 | 24 | 37 | 92.1 |
| E | 0.343 | 0.387 | 0.333 | 0.440 | 7.6 |
| largest multi-plot group | 7 | 4 | 3 | 6 | 97.8 |
| **same-stand within-part pairs** | **43** | **26** | 17 | 37 | **99.2** |

The E-slope bias estimates are negative for every variable, −0.011 (`sal_ba_frac`) to −0.041
(`h_top5_m`), so the 6.1 percentiles are biased low.

**6.2, Bray–Curtis, all pairs.**

| band | n same | n diff | mean same | mean diff | diff | rotation percentile |
|---|---|---|---|---|---|---|
| 0–100 m | 11 | 3 | 0.329 | 0.188 | −0.141 | uninformative (n ≤ 3; and by Consequence 3) |
| 100–200 m | 18 | 19 | 0.343 | 0.498 | 0.155 | **83.6** (n_null 1999) |
| 200–400 m | 11 | 95 | 0.387 | 0.551 | 0.164 | **91.6** (n_null 1999) |
| 400–800 m | 3 | 89 | 0.269 | 0.612 | 0.343 | uninformative (n ≤ 3) |

Regression (pairs < 800 m, n = 249, 43 same-stand): **beta_same −0.1663**, beta per 100 m 0.0260.
Null median −0.0365. **Stand-effect percentile 94.4** (n_null 1999).

- The naive permutation p is 0.073 (100–200 m), **0.032** (200–400 m) and **0.006** (regression).
  It is labelled INVALID; as pre-registered (p > 0.05) it fails for Bray–Curtis.
- SENSITIVITY: the within-site shuffle p is 0.231, 0.219 and 0.166.

**6.2, |ΔLorey's height|, all pairs.** The informative bands are 100–200 m (18 / 19 pairs, diff
1.470 m, **61.4**) and 200–400 m (11 / 95, diff −1.975 m, **17.1**). Regression: beta_same
+0.0503 m, beta per 100 m −0.2982, null median −0.2622, **stand-effect percentile 40.1**.
SENSITIVITY: the within-site shuffle p is 0.133, 0.595 and 0.288.

Every informative cell and both regressions are inside the null's central 90%. Composition leans
towards "same stand, more alike"; height is mixed.

**The Bray–Curtis 94.4 is a Kerijoli signal, not near-evidence that the embedding delineates
composition** (SENSITIVITY). Kerijoli supplies **24 of the 43** same-stand pairs (null median 10,
percentile 99.3), and **21 of them come from one 7-plot stand** (stand 83).

| variant | n same | beta_same | stand-effect percentile |
|---|---|---|---|
| as pre-registered | 43 | −0.1663 | 94.4 |
| **drop Kerijoli** | **19** | **−0.0419** | **70.3** |
| site fixed effects | 43 | −0.0126 | 57.8 |
| stand-weighted (1/pairs per stand) | 43 | −0.0134 | 74.4 |
| drop any one of the other five sites | 38–43 | −0.1837 to −0.1541 | 91.8–94.9 |

The robustness variants are computed for the regression only; the 200–400 m band at 91.6 has
none, and is read with the same caution.

**Pairs with both plots > 30 m from a boundary: could not be tested.** 20 plots qualify. They
form **26 pairs under 800 m, 8 of them same-stand**. Every band has ≤ 3 same-stand or ≤ 3
different-stand pairs, so every band is uninformative by R4.
The printed regression percentiles, Bray–Curtis **91.2** and |ΔLorey's| **5.2** (n_null 1817), are
set aside by judgment, as for v120. The |ΔLorey's| 5.2 is not read as a splitting signal, and
neither is its 200–400 m cell, which holds a single same-stand pair.

**6.3.**

- UPGMA k = 6 is **not estimable**: all 60 pilot plots are one type.
- Sal-dominant rule, from 1316 of 1999 realisations. 3 of the 8 contingency cells have expected
  count < 5.

  | statistic | observed (n = 60) | null median | p95 | percentile |
  |---|---|---|---|---|
  | ARI | 0.032 | 0.052 | 0.112 | 25.5 |
  | NMI | 0.043 | 0.081 | 0.141 | 8.3 |
  | Cramér's V | 0.281 | 0.397 | 0.520 | 6.4 |

  None is above p95.
- Distant pairs (> 2 km; 323 same-label, 1175 different-label): Bray–Curtis difference −0.014
  (percentile 72.8); |ΔLorey's| difference 0.479 m (percentile 92.7). Both are inside the central
  90%.
- **Label drift was not measured for this arm.** `odisha_phase2_6_results.txt` covers v120 and
  current only, so these 6.3 values carry an unquantified label-stability caveat.

**Between-village variance (SENSITIVITY).** Within-part R² runs from 0.273 to 0.668, with
percentiles 49.7 / 49.8 / 33.4 / 65.8 / 86.8 / 88.4 / 38.5 (variables in the table order above);
none is above p95. Adjusted-R² percentiles run from 23.7 to 90.9. `n_species` is again nearest the
top: 88.3 restricted, 90.9 adjusted, 86.8 within-part.

### Arms comparison, `stands_merged`

The stats script computes two differences: excess(v120) − excess(current) and excess(v120) −
excess(AlphaEarth).

The committed prediction reads "the difference in excess-over-own-null falls inside either arm's
null spread". It was committed for current vs v120 only; for AlphaEarth, `PHASE2_PREDICTIONS.md`
makes no directional prediction, so no difference prediction exists for v120 − AlphaEarth, and
the script applies the same test to that pair. It was operationalised two ways, both first computed in the corrected run, after the
first run's statistics had been seen (R10). They are given equal standing here.

- **Differenced null.** Each arm's null is centred on its own median, and the two are differenced
  index-wise.
- **Own-null reading.** The difference is checked against each arm's own centred p5–p95. The
  script labels this one SENSITIVITY, but it is the closer match to the committed wording.

**v120 − current.**

| variable | excess v120 | excess current | difference | differenced null p5 | p95 | percentile | differenced null | own-null reading |
|---|---|---|---|---|---|---|---|---|
| `loreys_h_m` | −0.102 | −0.088 | −0.014 | −0.209 | 0.205 | 45.1 | inside | inside both |
| `loreys_h_tree_m` | −0.112 | −0.083 | −0.029 | −0.204 | 0.200 | 40.3 | inside | inside both |
| `crown_cover_pct` | −0.016 | −0.050 | 0.034 | −0.228 | 0.205 | 63.3 | inside | inside both |
| **`sal_ba_frac`** | −0.140 | 0.025 | **−0.165** | −0.183 | 0.168 | 6.6 | inside | **inside neither** |
| `n_species` | 0.129 | 0.093 | 0.036 | −0.231 | 0.253 | 57.6 | inside | inside both |
| **`dbh_mean_cm`** | −0.172 | 0.135 | **−0.306** | −0.192 | 0.206 | **0.9** | **OUTSIDE** | **inside neither** |
| `h_top5_m` | −0.050 | −0.110 | 0.060 | −0.185 | 0.168 | 69.9 | inside | inside both |

**v120 − AlphaEarth.**

| variable | excess v120 | excess AlphaEarth | difference | differenced null p5 | p95 | percentile | differenced null | own-null reading |
|---|---|---|---|---|---|---|---|---|
| `loreys_h_m` | −0.102 | −0.024 | −0.078 | −0.213 | 0.216 | 26.5 | inside | inside both |
| `loreys_h_tree_m` | −0.112 | −0.029 | −0.083 | −0.213 | 0.213 | 24.7 | inside | inside both |
| `crown_cover_pct` | −0.016 | −0.087 | 0.071 | −0.214 | 0.202 | 72.2 | inside | inside both |
| **`sal_ba_frac`** | −0.140 | −0.004 | **−0.136** | −0.175 | 0.176 | 9.8 | inside | **inside neither** (centred lower edges: v120 −0.134, AlphaEarth −0.128) |
| `n_species` | 0.129 | 0.106 | 0.022 | −0.231 | 0.249 | 55.1 | inside | inside both |
| **`dbh_mean_cm`** | −0.172 | 0.064 | **−0.235** | −0.190 | 0.213 | **2.3** | **OUTSIDE** | **inside neither** |
| `h_top5_m` | −0.050 | −0.020 | −0.029 | −0.179 | 0.185 | 39.9 | inside | inside both |

Beside it, the two partitions:

| arm | stands | area p10 / median / p90 (ha) | multi-plot stands | plots in them |
|---|---|---|---|---|
| v120 | 197 | 1.20 / 3.93 / 9.39 | 13 | 35 |
| current | 188 | 1.23 / 4.27 / 9.46 | 11 | 32 |
| AlphaEarth | 184 | 1.29 / 4.79 / 9.11 | 13 | 36 |

**The arms prediction fails for `dbh_mean_cm` under both readings, and for `sal_ba_frac` under the
own-null reading.** Removing `canopy_height_std` was predicted to change the partition without
changing its field relevance. On mean DBH, the current arm sits at 95.4 and v120 at 3.2.

These are two variables of seven on 32–35 plots, in arms whose null shape is off. They are
reported as a failed prediction, not as evidence that the removal helps.

**v120 − AlphaEarth, which had no pre-registered difference prediction, falls outside for
`dbh_mean_cm` under both readings (differenced-null percentile 2.3), and for `sal_ba_frac` under
the own-null reading only.** The `sal_ba_frac` case is marginal: −0.1356 against centred lower
edges of −0.134 (v120) and −0.128 (AlphaEarth), and 9.8 in the differenced null. Both fall on the
two variables where v120's own excess is lowest (−0.172, −0.140), the same two on which v120 −
current failed.

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
- **AlphaEarth.** 872 superpixels, p10 0.50 / median 0.96 / p90 1.52 ha: **5 multi-plot
  superpixels holding 12 plots** (Consequence 1 missed, as in the other arms). 6.1 excess runs
  from +0.038 to +0.158, percentiles 57.9–88.9, with null p5 at 0.00 for every variable.
  `sal_ba_frac` (+0.158) and `n_species` (+0.141) are outside ±0.10 on (5 stands, 12 plots). 6.2
  has 10 same-stand pairs (regression percentiles 30.6 Bray–Curtis, 20.3 |ΔLorey's|). The > 30 m
  subset has 1 pair.

### `stands_dissolved`: effectively the site partition, not a delineation test

The dissolved layer (connected same-cluster regions) puts the 60 plots into 8 units in each
hand-crafted arm and 9 in AlphaEarth. v120 has 97 polygons, area p10 0.05 / median 0.20 / p90
6.90 ha; current has 126, 0.04 / 0.20 / 9.87 ha; AlphaEarth has 110, 0.05 / 0.39 / 9.30 ha.

| arm | units holding plots, by part | ARI(unit, AOI part) |
|---|---|---|
| v120 | 1 / 1 / 1 / 1 / 2 / 2 | **0.932** |
| current | 1 / 2 / 1 / 1 / 1 / 2 | 0.915 |
| AlphaEarth | 1 / 2 / 1 / 3 / 1 / 1 | 0.922 |

The site-only partition reproduces its restricted R² almost exactly. For `loreys_h_m`, v120's
dissolved restricted R² is 0.518 (7 stands, 59 plots) and the site-only value is 0.512 (6 AOI
parts as groups, same restricted plots). This is an identity check that the two are nearly the
same partition, not a comparison of how well they perform (SENSITIVITY, R5).

Its statistics measure differences *between* village forests. Its 6.1 excesses are all small:

| arm | (k, n) restricted | excess range | percentile range |
|---|---|---|---|
| v120 | (7, 59) | −0.031 to +0.003 | 5.3–61.3 |
| current | (7, 59) | −0.031 to −0.018 | 8.4–27.1 |
| AlphaEarth | (7, 58) | −0.028 to +0.029 | 23.4–71.3 |

In the hand-crafted arms, one pre-registered 6.2 value falls outside the central 90%: current
dissolved |ΔLorey's| regression stand effect at **4.5** (n_null 1999). Given the identity with the
site partition, it too measures between-site difference.

AlphaEarth's dissolved layer has several |ΔLorey's| values beyond p97.5: the all-pairs regression
stand effect at **99.8**, the 200–400 m and 400–800 m bands at **99.4** and **99.7**, and the
> 30 m regression at **98.5** and 200–400 m band at **99.4** (n_null 1992). Its > 30 m
Bray–Curtis 200–400 m cell sits at 98.5, on 7 different-unit pairs. The layer is the site
partition (ARI(unit, AOI part) 0.922), and its null shape is off (k percentile 5.3, E 1.6,
same-stand pairs 99.7). These values are between-site differences, not a delineation result. The
Bray–Curtis cell is AlphaEarth-only and beyond p97.5, so it is **set aside by judgment, not by a
rule**, as the pre-registered AlphaEarth composition surprise. The layer is built from k-means
labels whose drift was not measured for this arm.

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
- **AlphaEarth: not measured at all.** `odisha_phase2_6_results.txt` covers v120 and current only.
  AlphaEarth's 6.3 values and its dissolved layer carry an unquantified label-stability caveat.
- **Open.** Whether to rebuild the cache or pin and document the cached version is still to be
  decided.

---

## Corrections to earlier figures (pilot)

The full set has only ever had one run (`e6c4d6b`), so nothing below applies to it; the code
corrections R1–R18 were already in force when it ran.

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
  (R12): 1129 of 1999 for v120, 1247 for current, 1316 for AlphaEarth. The file specified the rotation null without
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
merged and SNIC layers do not read labels. Drift was not measured for the AlphaEarth arm. The
choice between rebuilding and pinning is open.

---

## Pending

Both runs are complete, so nothing statistical is pending. What remains is a set of open decisions
and two code changes, listed below. Every number elsewhere in this document comes from a committed
results file, not from a commit message.

### Open code changes

- **The dissolved-layer identity check (R5) is confounded.** It compares a layer's dissolved
  restricted R² against a site-only R² computed over all 267 plots in 20 groups, so the group
  counts differ and more groups mechanically raise R². Either restrict the site-only R² to the
  layer's assigned plots or drop the comparison. Not applied retroactively to the committed runs.
- **Label drift is unmeasured for the twelve per-district configs**, and for AlphaEarth in either
  set. `odisha_phase2_6_label_drift.py` covers the pilot's v120 and current only. 6.3 and the
  dissolved layer read labels; 6.1 and 6.2 on the merged and SNIC layers do not.

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

# the full set, four districts (4624 s wall clock at --jobs 4)
python odisha_script/odisha_phase2_3_join.py --set districts
python odisha_script/odisha_phase2_5_stats.py --set districts --jobs 4
```

Steps 0, 1, 3, 5 and 6, and step 4 with `--size-check`, write `odisha_phase2_<n>_results.txt`
beside themselves. Step 2 writes `phase2_vectors/<config>_*`. Step 5 also writes
`odisha_phase2_5_summary.csv` and the three figures. The first run used `--rotations 999`.

`--set districts` writes the same outputs with a `_districts` suffix and computes the nine
arm × layer partitions in parallel, checkpointing each to `phase2_5_checkpoints/districts/` as it
finishes, so an interrupted run resumes instead of restarting. The checkpoints are a resume cache,
not a record: they are git-ignored, and `--fresh` discards them. A partition whose rotation null
cannot be built is reported and skipped rather than aborting the run.

The first run's output can be compared with the corrected one without re-running anything:

```bash
git show 8d4c2ed:odisha_script/odisha_phase2_5_results.txt
```
