# Phase 1: field validation of the structural axis

Odisha field campaign, FES plots. Every figure below comes from a run recorded in
`odisha_script/odisha_phase1_*_results.txt`.

---

## 1. What was tested, and against what

274 field plots carrying 5,910 individual tree records across four Odisha districts —
Koraput (146), Dhenkanal (76), Angul (40), Kendujhar (12) — of which 60 plots fall inside
six Dhenkanal village-forest polygons that give a second, coarser unit of comparison. The
reference quantities are **Lorey's height** (basal-area-weighted mean height, the standard
stand-height statistic and the quantity a delineation merge rule claims to hold constant)
and **crown cover percent**. Field Lorey's height spans 0.16–37.75 m. Each candidate remote
product was sampled at the plot coordinate and regressed against Lorey's height at plot
level, and against the plot-mean at site level. The question the phase was built to answer
is narrow and prior to everything else in the thesis: *is there a freely available product
that measures stand height in this forest well enough to gate a merge on?*

## 2. The products, and how each one fails

Plot-level R² against field Lorey's height, n=274 unless stated.

| product | R² | failure mode |
|---|---|---|
| `vh_iqr` — Sentinel-1 radar texture | **0.227** | not a height measurement; a backscatter-variability proxy |
| Meta/WRI 1 m | 0.241 → **0.142** excl. zeros | reads 0 over 12–33 m of measured canopy |
| ETH 10 m | **0.207** | range compressed to 14.30–22.47 m against a real 3.45–37.75 m; slope 0.30 |
| GEDI rh98 (n=89) | **0.088** | reproduces ETH's compression; slope 0.27 |
| GLAD | **0.041** | inverts to r=−0.121 once Meta-zero plots are excluded |

Three of these need a sentence more than the table gives them.

**ETH is compressed, not noisy.** Binned by field height, ETH's mean prediction runs 14.30 m
in the 0–5 m bin to 22.47 m in the 30–60 m bin. Its entire usable span is about 8 m against
a real 35 m, with a +10.85 m bias on the shortest plots and −15.29 m on the tallest. A 2 m
merge tolerance is therefore roughly a quarter of the product's whole range, not a fine
structural distinction. Aggregating to site level makes it worse, not better: R² 0.207 →
0.100.

**Meta reads zero over closed canopy, and the zeros are not missing data.** `meta_chm` is
exactly 0 at 122 of 274 plots (44.5%). Sampling the raw 1 m grid in a 30 m box at twelve of
those plots: exactly one collection image intersects every box, **zero pixels are masked**
of roughly 780, and the mask returns 1 at every plot point. Ten of the twelve boxes contain
nothing but zeros. One plot carrying **33.57 m** of Lorey's height and 43% crown cover reads
max 0.0 m out to a 50 m radius and mean 0.44 m over a 78-hectare disc, which rules out a
georeferencing offset — an offset would have to exceed 500 m, and would have scrambled the
five non-zero control plots, which instead read 11.62 m mean at 100% non-zero coverage. A
frequency histogram over 554,745 pixels confirms the band is a height field in metres
(contiguous integer support 0–25, smooth monotone decay, thin tail to 31) and *not* a class
code. Of those pixels **63.5% read 0**, at a non-zero mean of 4.82 m. That is a statement
about the sampled pixels and not about forest cover: the sample is the union of 274 discs of
500 m radius around plot centres, which in rural Dhenkanal, Angul and Koraput takes in
farmland, fallow, settlement and roads. The control discs show the confound directly — they
run 100% non-zero at 15 m and fall to 62.1% at 500 m, so widening the disc brings in
non-forest exactly as expected. The disqualification rests on the plot-level evidence above
and does not depend on this share.

**GEDI's published number was an artefact and has been corrected.** The 50 m neighbourhood
search never executed: Earth Engine's `reduceNeighborhood` masks its output wherever the
centre pixel is masked, so only plots whose own 25 m cell contained a shot ever received a
value. That produced 10 plots, R²=0.404 — the best-looking number in the study. Re-sampled
with an explicit buffered reduction, true coverage is **89 of 274** and R² is **0.088**.
The ten original rows all survive with values essentially unchanged, so the defect
suppressed coverage rather than corrupting values.

## 3. Why these failures are not independent

Meta's 1 m model is supervised on aerial lidar from NEON sites **within the United States
only**; the paper states the limitation directly, and its non-US data (São Paulo, CA-Brande)
was used for validation, not training. To extend the model beyond that geography, Tolan et
al. (2024) apply a post-processing network trained on 13 million GEDI measurements, which
supplies *"a scalar multiplier that match percentiles of the CHM map with the GEDI model
predicted value for GEDI RH95."*

Two consequences follow. First, the correction that is supposed to make Meta valid outside
the United States is anchored on the same instrument that scores **R²=0.088** in this
forest, so the two failures share a cause rather than being two independent strikes.
Second — and this is why the correction cannot be blamed for the zeros or credited with
fixing them — the adjustment is a **multiplicative rescale**. A scalar multiplier applied to
a prediction of zero returns zero, whatever GEDI says locally. Meta's zeros over closed
canopy originate in the RGB-to-height model itself, and nothing downstream in its published
pipeline can lift them.

One metric caveat for accuracy: Meta's anchor is GEDI **RH95**; our test measured **rh98**.
Related, not identical. Meta's headline MAE of 2.8 m is reported without a vegetation-height
threshold attached to that figure.

## 4. What this does to the thesis

This is a sharper result than the one originally planned, and should be presented as the
finding rather than as an obstacle.

Twelve of the twenty delineation papers surveyed for this thesis use **measured** ALS canopy
height as a delineation input. That assumption is available in Scandinavia, central Europe
and the United States, and it is not available here. What Phase 1 now has is field evidence
— 274 plots, 5,910 trees, Lorey's height and crown cover — that **every free global
substitute for measured canopy height fails in Indian dry deciduous forest, with a distinct
and documented failure mode for each**: compression for ETH and GEDI, systematic zeros for
Meta, sign inversion for GLAD.

That converts the contribution from "another stand-delineation method" into "stand
delineation where the structural axis the literature assumes is not available" — which is
the situation across most of tropical Asia, and which no paper in the surveyed set
addresses. The negative result is transferable in a way a method comparison on Sanjay Van
would not have been.

## 5. The separation-null result

Against a spatial null model (k-means on centroids alone, which controls for the fact that
any spatially autocorrelated band beats a random-feature partition), the bands doing most of
the delineation work are the bands the field data trusts least: `canopy_height` clears the
null by **+0.268** (observed 0.570 vs null p95 0.302) and `canopy_height_max` by **+0.264**,
leading all survivors by a wide margin — while measuring field height at R²=0.207.
`elevation`, meanwhile, **fails the null outright** (observed 0.556 vs p95 0.615), despite
ranking third among raw separation scores. A band can carve consistent groups out of a
landscape while being a poor estimator of the quantity it is named for; but that means any
claim the resulting stands are *structurally meaningful* rests on the measurement, not on
the carving.

## 6. Three decisions

**(a) Status of the negative result.** Either it becomes a first-class contribution — the
thesis is restructured around the unavailability of the structural axis, with Phase 1's
product validation as a standalone chapter and the delineation method presented as a
response to it — or it stays a methods footnote justifying the choice of merge criteria,
and the thesis remains a delineation-method contribution. The first is a larger claim and
requires the validation to carry a chapter's weight on 274 plots in four districts. The
second leaves the strongest empirical result in the work as a parenthesis.

**(b) Tolerance in metres, or as a percentile.** The merge gate currently admits two
neighbouring units if their mean canopy heights differ by at most 2.0 m — a calibrated claim
in physical units, which is what a forester expects and what the comparator paper reports.
The alternative is to express the tolerance as a percentile of the observed pair-difference
distribution, which the existing calibration routine already computes, making it mean the
same thing in every area of interest and on every product. The evidence for it: Spearman
exceeds Pearson on every product tested (ETH 0.484 vs 0.455; Meta 0.541 vs 0.491; `vh_iqr`
0.484 vs 0.458; GLAD 0.305 vs 0.202), so these products rank neighbours better than they
calibrate, and ranking is what a conjunctive neighbour gate actually needs. The cost: it
converts the gate from a calibrated claim into a ranking claim, and "stands differ by less
than the 55th percentile of local differences" is not a statement a forest manager can act
on.

**(c) Radar as the structural axis.** `vh_iqr` is the best-validated free signal at plot
scale (R²=0.227, rising rather than falling when the Meta-zero plots are excluded — the only
candidate whose relationship to field height does not depend on the short-plot anchor). It
is also a backscatter-texture proxy rather than a height measurement, so a tolerance on it
has no physical interpretation; no paper in the surveyed twenty uses radar for stand
delineation; and it is the one signal that gets **worse** under aggregation (site-level lift
−0.111, and −0.157 with zeros excluded), which is the opposite of what a stand-scale
criterion needs. The options are to adopt it as the structural axis with those caveats
stated, to keep ETH as a relative ordering only and declare the structural axis unvalidated
in this forest type, or to drop the structural axis and delineate on composition and optical
bands alone.

## 7. What is blocked, and on whom

**ORSAC / the Divisional Forest Officer — Dhenkanal compartment vectors.** Unanswered. This
is the only route to a reference stand map, and without it the delineation output can be
characterised but not scored against an independent ground truth. Nothing in the current
data substitutes for it.

**FES — three outstanding enquiries.** (i) *Plot radius*, which sets the ground area each
plot represents and therefore the correct sampling support for every product comparison
above; all figures currently assume the plot coordinate is representative of a 30 m
neighbourhood. (ii) *Survey year*, which determines whether the field campaign and Meta's
source imagery — 2009–2020, chiefly 2018–2020 — are contemporaneous, and therefore whether
any part of the Meta zero pattern is temporal rather than model failure. (iii) *One plot
record*: Pangatira plot `21.156085_85.364999` reads **8% crown cover while carrying 16.19 m
of Lorey's height**, where the other nine Pangatira plots run 58–88%. Either a data-entry
error or a genuinely open canopy of tall emergents. It sits inside the site whose ten zeros
drive the site-level Meta result, so it should be resolved before Pangatira is used to argue
anything. Note that an 8% reading also appears outside Pangatira, at 6.91 m Lorey's height,
so it may be a recording convention rather than an error — which is itself the thing to ask.

---

**Reference.** Tolan, J. et al. (2024). Very high resolution canopy height maps from RGB
imagery using self-supervised vision transformer and convolutional decoder trained on aerial
lidar. *Remote Sensing of Environment*. arXiv:2304.07213.
