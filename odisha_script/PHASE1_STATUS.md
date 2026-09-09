# Phase 1 status

Where the Odisha field validation stands, what changed in this session, what is still
open, and what the merge's structural criterion should be given the evidence.

Every number here comes from code run in this session. Two things could not be
computed because this environment has no Earth Engine credentials, and they are
marked BLOCKED rather than estimated.

---

## What each test now says

| test | measures | result | standing |
|---|---|---|---|
| 1 | ETH canopy height vs field Lorey's | r=+0.455, **R²=0.207**, slope 0.30, bias +7.2 m | **fails.** See below |
| 2 | NDVI amplitude vs Sal dominance | r=−0.171, **R²=0.029**; Mann-Whitney p=0.014 | weak; direction only |
| 3 | ETH 3×3 roughness vs crown cover | r=−0.011, **R²=0.000** | **fails outright** |
| 4a | Meta/WRI vs Lorey's | R²=0.241 as published, **0.142** with zeros excluded | **BLOCKED** on the zeros |
| 4b | GLAD/Potapov vs Lorey's | R²=0.041; **flips to r=−0.121** with Meta-zeros excluded | out |
| 4c | GEDI rh98 vs Lorey's | R²=0.404 at n=10 | **WITHDRAWN** pending re-sample |
| 5 | S1 backscatter vs Lorey's | `vh_iqr` **R²=0.210 → 0.227** with zeros excluded | best free signal at plot scale |
| 6 | leaf-off / seasonal vs composition | `off_B5` R²=0.140; `ndvi_seasonal_diff` R²=0.001 | `off_B5` is the only one worth keeping |

### The ETH problem is dynamic range, not noise

Field means run 3.45 → 37.75 m across the height bins. ETH runs **14.30 → 22.47 m**. Its
entire span over a real 3–38 m range is about 8 m, with slope 0.30. So a 2.0 m tolerance
is roughly a quarter of the product's whole usable range, not a fine structural
distinction — and the Sanjay Van calibration (`tol 2.0 = p54.5 of pair differences`)
looked reasonable only because the pair differences are small. The product is compressed;
the forest is not homogeneous.

Aggregation does not rescue it. Plot-level R² 0.207 → site-level 0.100 → **0.013** with
Meta-zero plots excluded. Of every product tested, ETH is the one aggregation destroys.

### Meta is quantised to integer metres — new this session

`meta_chm` is integral at every plot, range 0–15, median 4. `meta_chm_3x3` values are
exact multiples of 1/9 (max deviation 3.8e-06), which a 3×3 mean can only hit if all nine
inputs are integers.

Two consequences. A Meta `0` means *"predicted under half a metre"* — neither "no data"
nor "no canopy". And **a 2.0 m tolerance on an integer-metre product gates 2 of 16
levels**: there is no sub-metre structure for any threshold to resolve.

### The exclusion moves everything except radar

Excluding the 122 `meta_chm == 0` plots drops every height product by almost exactly the
same amount (−0.097 to −0.103): the zero plots sit at the short end of the field range,
and removing them shrinks the spread each product is asked to track.

**The two radar bands rise instead** — `vh_iqr` 0.210 → 0.227, overtaking every height
product. Radar is the only structural signal here whose relationship to field height does
not depend on the short-plot anchor.

**`glad_chm` flips sign**, +0.202 → −0.121. Its entire positive correlation was the zero
plots.

### Aggregation: the claim survives, with two cautions

Excluding zeros *strengthens* the lift — `meta_chm_3x3` +0.206 → **+0.361**,
`meta_mean_15m` +0.220 → +0.391. The zeros were suppressing it via Pangatira, whose ten
zeros dragged one of six site means to 0.

Cautions that must travel with that sentence: the excluded column is **n=5 sites**, and
aggregation makes **radar worse** (`vh_iqr` −0.111 → −0.157). "Aggregation recovers what
plot noise hides" is a statement about these height products, not about stand-scale
averaging in general.

---

## What changed this session

| | |
|---|---|
| **step 7** `odisha_phase1_7_meta_zero_diagnosis.py` | zero census, quantisation, zeros-excluded tables at plot and site level, aggregation re-test. GEE half BLOCKED |
| **step 8** `odisha_phase1_8_separation_null.py` | null model for the separation-ratio chart; three nulls, 22 bands |
| **step 9** `odisha_phase1_9_gedi_recount.py` | GEDI root cause + fix + re-sample harness. Re-sample BLOCKED |
| step 3 | GEDI construction fixed at source (explicit un-normalized kernel, `Reducer.count()`) |
| step 4 | coverage line now prints both counts and fails loudly if they disagree |

### Corrections to the brief's own figures

- The zero census is on **`meta_chm`** (single pixel), not `meta_chm_3x3`. 122/274 vs
  93/274 — worth 29 plots and 0.04 of R². Every figure in the brief reproduces exactly
  once the column is right.
- Pangatira crown cover is **8–88%, not 58–88%**. Nine of ten are 58–88%; one reads 8%
  while carrying 16.19 m of Lorey's height.
- "mypy is dead" does not reproduce here (Python 3.11.15, mypy completes, 22 real errors).
  Changing `python_version` does not fix it either. All 22 are now fixed and mypy is green.

### The separation-ratio chart was not what its label said

The unit is the **k-means cluster (k=6)**, not the stand, and it scores **22 bands, not
20**. One of them — `distance_to_water` — was never fed to k-means, making it a control
already inside the published figure.

That control **failed the null the brief specified**: a random-feature partition let it
clear p95, and passed 22 of 22 bands. The cause is structural — the observed partition is
spatially coherent, a random-feature one is not, so anything spatially autocorrelated
beats it. Added a **spatial null** (k-means on centroids only). Under it,
`distance_to_water` scores +0.012, and **`elevation` fails outright** (observed 0.556 vs
p95 0.615).

**And the finding that bears on this document:** the bands that dominate the partition are
the bands the field data trusts least. `canopy_height` (+0.268) and `canopy_height_max`
(+0.264) lead the survivors by a wide margin, at R²=0.207 in the field.
`canopy_height_std` survives at +0.076 while measuring crown cover at R²=0.000.

Not a contradiction. A band can carve consistent groups out of a landscape while being a
poor estimator of the quantity it is named for. But it means the current criteria are
doing real delineation work on quantities we cannot defend as measurements — and any claim
that the stands are *structurally meaningful* rests on the measurement, not the carving.

---

## Unresolved

1. **Task 1 verdict — BLOCKED, and it gates Task 4.** Whether `meta_chm == 0` at 122 plots
   is NO DATA, RECOVERABLE, or DISQUALIFIED needs the raw 1 m grid, the mask state and the
   band encoding. Run `python odisha_phase1_7_meta_zero_diagnosis.py` where
   `earthengine authenticate` has been done.
2. **GEDI re-sample — BLOCKED.** The published R²=0.404 is withdrawn, not corrected.
3. **Task 4 not started.** ETH removal is written up but not applied, because removing two
   of three criteria leaves one, below `min_defined_criteria: 2`, and the replacement is
   Task 1's to decide. `min_defined_criteria` must not be lowered to accommodate this.
4. **AlphaEarth arm held.** Correct: changing `merge.criteria` changes the cache
   fingerprint and every number downstream.
5. `off_B5` (R²=0.140 vs Sal dominance) is a leaf-off seasonal composite band **no stage
   produces**. New work if it is wanted.
6. Meta as a criterion would need new code: `features_structure.py` does
   `ee.Image(canopy_asset).select(0)` — a single Image. Meta is a 1 m ImageCollection
   needing a mosaic and a `reduceResolution`.

---

## What the merge's structural criterion should be

**There isn't one yet.** That is the answer the evidence supports, and it should be stated
rather than papered over.

The reasoning, in the order it matters:

**No available product measures stand height well enough to gate on in absolute units.**
The best plot-level R² is Meta at 0.241, which falls to 0.142 once its 45% zeros are
excluded — and Meta is BLOCKED. ETH is 0.207 with slope 0.30 and a compressed range. GLAD
inverts. GEDI is withdrawn. `vh_iqr` at 0.227 is the best-validated free signal, and it is
a radar texture proxy, not a height measurement — and it is the one thing that gets *worse*
under aggregation, which is the opposite of what a stand-scale criterion needs.

**`canopy_height_std` should go regardless of Task 1.** R²=0.000 against crown cover
(r=−0.011) is not a weak criterion, it is a criterion measuring nothing it claims. With
`min_defined_criteria: 2` it can be one of the two that admits a merge. It survives the
separation null (+0.076), so it does affect the partition — which makes it worse, not
better: it is shaping stands on a quantity with no established meaning.

**If ETH stays, the tolerance cannot stay in absolute metres.** This is the sharpest
actionable conclusion here. Spearman consistently beats Pearson — ETH 0.484 vs 0.455, Meta
0.541 vs 0.491 — so the products rank neighbours better than they calibrate, and ranking is
what a conjunctive neighbour gate actually needs. But `2.0 m` is a *calibrated* claim, and
on a product whose whole range is 8 m against a real 35 m it does not mean the 2 m it says.
A tolerance expressed as a percentile of the observed pair-difference distribution —
which `calibrate_thresholds()` already computes — would mean the same thing in every AOI
and on every product. That is also consistent with the standing rule that no Odisha number
becomes a default: it names a method, not a value.

**Conditional on Task 1:**

- **RECOVERABLE** → Meta is the candidate. Best plot-level number, and the only product
  whose signal *improves* with aggregation (+0.361), which is the property a stand-scale
  criterion needs. Caveat that must ship with it: integer-metre quantisation means any
  tolerance below ~1 m is meaningless, and the 16-level range is narrow.
- **NO DATA or DISQUALIFIED** → Meta is out, and there is no validated structural
  criterion. Then the honest position is to keep ETH *as a relative ordering only*, with a
  percentile tolerance, and to state in the methods that the structural axis is unvalidated
  in this forest type — not to substitute `vh_iqr` and imply it measures height.

**What must not happen**, restating the standing rules because this is where the pressure
will be: do not lower `min_defined_criteria` to fit a shorter criteria list; do not tune a
tolerance to hit a pass rate or an R²; do not put an Odisha-derived constant into
`config.py`.

---

## Reproducing

```bash
cd odisha_script
python odisha_phase1_7_meta_zero_diagnosis.py   # part A offline; part B needs GEE
python odisha_phase1_8_separation_null.py       # fully offline, reads b24fad3 via git show
python odisha_phase1_9_gedi_recount.py          # reports current state; re-sample needs GEE
```

Steps 8 and 9 write `odisha_phase1_8_results.txt` / `odisha_phase1_9_results.txt` and step
8 also writes `odisha_phase1_8_separation_null.png`.
