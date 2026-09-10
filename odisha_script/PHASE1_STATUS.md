# Phase 1 status

Where the Odisha field validation stands, what changed in this session, what is still
open, and what the merge's structural criterion should be given the evidence.

Every number here comes from code that has been run. The two items that were BLOCKED on
Earth Engine credentials have since run against the live catalogue — step 7 part B, step 9
and step 10 — and **Task 1's verdict is now recorded: DISQUALIFIED.** Nothing below is
estimated.

---

## What each test now says

| test | measures | result | standing |
|---|---|---|---|
| 1 | ETH canopy height vs field Lorey's | r=+0.455, **R²=0.207**, slope 0.30, bias +7.2 m | **fails.** See below |
| 2 | NDVI amplitude vs Sal dominance | r=−0.171, **R²=0.029**; Mann-Whitney p=0.014 | weak; direction only |
| 3 | ETH 3×3 roughness vs crown cover | r=−0.011, **R²=0.000** | **fails outright** |
| 4a | Meta/WRI vs Lorey's | R²=0.241 as published, **0.142** with zeros excluded | **DISQUALIFIED** — see Task 1 |
| 4b | GLAD/Potapov vs Lorey's | R²=0.041; **flips to r=−0.121** with Meta-zeros excluded | out |
| 4c | GEDI rh98 vs Lorey's | **R²=0.088 at n=89** (was R²=0.404 at n=10) | re-sampled; **out** |
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
| **step 7** `odisha_phase1_7_meta_zero_diagnosis.py` | zero census, quantisation, zeros-excluded tables at plot and site level, aggregation re-test. **Part B RUN**: unmasked 1 m grids at 12 zero plots + 5 controls |
| **step 8** `odisha_phase1_8_separation_null.py` | null model for the separation-ratio chart; three nulls, 22 bands |
| **step 9** `odisha_phase1_9_gedi_recount.py` | GEDI root cause + fix + re-sample. **Re-sample RUN**: coverage 10 → 89, R² 0.404 → 0.088. Writes `odisha_plots_sampled_v3.csv`; v2 is an input and is left untouched |
| **step 10** `odisha_phase1_10_meta_offset_check.py` | the two confirmations that close the verdict: offset ladder at 15/50/100/200/500 m, and a `cover_code` frequency histogram over 554,745 px. **RUN** |
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

1. **Task 1 — VERDICT: DISQUALIFIED.** Steps 7B and 10 have both run against Earth Engine,
   over 12 zero plots and 5 non-zero controls. Taking the three outcomes in the order the
   diagnostic defines them:

   **NO DATA** — *"30 m box entirely masked / no intersecting tile."* **Closed by direct
   measurement.** At **all 12** zero plots: exactly 1 collection image intersects the box,
   `masked = 0` of 729–784 native pixels, and `mask()` at the plot point returns `1`. Nothing
   is masked anywhere. The box is not empty — it is full, and it reads zero.

   **RECOVERABLE** — *"box has values, the sample point does not"* → re-sample with a buffered
   reducer that ignores masked pixels. **Closed twice over.**

   - There are no masked pixels for such a reducer to skip. **10 of 12** boxes have
     `distinct values = [0]`: every one of ~780 one-metre pixels is present and equal to 0, so
     a buffered mean over them returns 0. The two exceptions are both ANGUL and top out at
     2 m, over 111 and 28 non-zero pixels of 784.
   - Step 10's offset ladder closes the one mechanism that could still put real values outside
     the box. Over discs of 15/50/100/200/500 m the zero plots read mean
     0.01 → 0.13 → 0.19 → 0.21 → 0.26 m and 1.2% → 5.6% → 8.9% → 9.8% → 11.5% non-zero.
     Canopy never appears. The same ladder at the 5 controls reads 11.62 m / 100% non-zero at
     15 m and is still 3.73 m / 62.1% at 500 m, so the ladder measures what it claims. **No
     offset below 500 m fits the zero plots, and one above 500 m would have to displace the
     controls too** — and four of the five controls sit in the same district as five of the
     zero plots. One raster cannot be half a kilometre out at one plot and registered at its
     neighbour.

   **DISQUALIFIED** — *"box is genuinely and validly 0 under high field crown cover."* **This
   is what the evidence supports.** The grid is unmasked, the values are present, the encoding
   is metres, and the product reads 0 over field-measured forest:

   - `20.760492_84.717751` (ANGUL) carries **33.57 m** of Lorey's height and 43% crown cover;
     its entire 784-pixel box reads 0 or 1.
   - `21.154502_85.365229` (DHENKANAL) carries **83% crown cover** and 12.07 m; all 784 pixels
     are exactly 0.

   The brief phrased the condition as "under 88% field crown cover". 88% is the top of the
   Pangatira range but belongs to a plot outside the diagnosed twelve; the highest crown cover
   among them is 83%. The condition is met at 83%.

   **Reading `cover_code` as metres is licensed, not assumed.** The asset carries **one band,
   `cover_code`, UINT8** (`PixelType int, 0..255`), native EPSG:3857 at a 1.194 m transform —
   so part A's integer-metre finding is the *storage type*, not an inference, and there is no
   second band to sample instead. Step 10 B histograms the band over the union of 274 discs of
   500 m: **554,745 pixels, 28 distinct values**, support contiguous over **0..25** with a
   smooth monotone decay (1 at 7.81% down to 19 at 0.01%), then 2 pixels in the whole region
   at 28 and 31. The only interior gaps are 26, 27, 29 and 30 — above which the region holds
   two pixels total. That is tail sparsity, not the empty space between class codes. A
   categorical code would spike on arbitrary integers; this does not.

   **How far the verdict generalises, stated precisely.** The 12 were chosen by sorted
   `plot_key` under district quotas, not by severity, so they are not the sharpest cases
   selected after the fact. They cover ANGUL 4, DHENKANAL 4, KORAPUT 4 and span 4.07–33.57 m
   of Lorey's height against the full zero population's 0.16–33.57 m. **Every one of the 12
   exhibits the mechanism and none is a counterexample.** Two limits travel with that:

   - **KENDUJHAR is not represented.** It has the highest zero rate of any district — 10 of
     its 12 plots — and was not sampled. The mechanism is established in 3 of 4 districts.
   - **The extreme cases are rare.** Of the 122 zero plots, only 2 exceed 20 m of Lorey's
     height and 11 reach 70% crown cover; the median zero plot carries 5.85 m and 28% crown
     cover, and the range runs down to 0.16 m and 0%. So some of the 122 are legitimately
     non-forest. But a Meta `0` means *"under half a metre"*, and the **median** zero plot at
     5.85 m is already a failure on a product quantised to integer metres — the verdict does
     not rest on the tall tail, the tall tail is only what makes it unarguable.

   Two bugs had to be fixed before part B could produce any of this, both now in the script:
   `sampleRectangle(defaultValue=-9999)` is rejected outright against a UINT8 band, and
   `ImageCollection.mosaic()` carries GEE's default 1-degree projection, which would have
   returned a single pixel rather than the 1 m grid the diagnostic claims to inspect.

   Two further confirmations, run as step 10 (`odisha_phase1_10_meta_offset_check.py`):
   an **offset ladder** at 15/50/100/200/500 m discs — the zero plots read mean 0.01 m and
   1.2% non-zero at 15 m and only 0.26 m and 11.5% at 500 m, while the controls read
   11.62 m and 100% at 15 m, so no georeferencing offset short of 500 m fits and one that
   large would scramble the controls; and a **frequency histogram** over 554,745 pixels,
   which shows contiguous integer support 0-25 with smooth monotone decay and a thin tail
   to 31. That is a height field in metres, not a class code. Of those 554,745 pixels
   **63.5% read zero**, at a non-zero mean of 4.82 m — which is a fact about the sampled
   pixels, not about forest cover. The sample is the union of 274 discs of 500 m radius
   around plot centres, and in rural Dhenkanal, Angul and Koraput that takes in farmland,
   fallow, settlement and roads. The control discs show the confound directly: 100%
   non-zero at 15 m, falling to 62.1% at 500 m as the disc widens into non-forest. The
   verdict rests on the plot-level grids above and does not depend on this share.

   **The failures are not independent, and this belongs with the verdict whichever way it
   goes.** Meta's 1 m model is supervised on aerial lidar from NEON sites in the United
   States only — Tolan et al. (2024) state the limitation, and their non-US data (Sao Paulo,
   CA-Brande) is validation, not training. Global applicability rests on a post-processing
   network trained on 13 million GEDI measurements supplying "a scalar multiplier that match
   percentiles of the CHM map with the GEDI model predicted value for GEDI RH95". So Meta's
   global correction is anchored on a product that scores **R2=0.088 at n=89** in this
   forest. Two caveats on that characterisation, both checked against the paper: the anchor
   metric is **RH95** and our corrected figure is against **rh98** — related, not identical;
   and Meta's headline MAE of 2.8 m is reported without a vegetation-height threshold
   attached to it, so it should not be quoted as "2.8 m for vegetation above 1 m". Note also
   that a multiplicative rescale applied to a prediction of zero returns zero, so the GEDI
   correction can neither be blamed for the zeros nor credited with fixing them: they
   originate in the RGB-to-height model itself.
2. **GEDI re-sample — DONE. n=10 was not the coverage; 89 is.** The three defects were
   real and the third was decisive: `reduceNeighborhood`'s `skipMasked` defaults to **True**,
   masking the output wherever the *centre* pixel is masked regardless of what the kernel
   found, so the 50 m search never ran and only plots whose own 25 m cell held a shot got a
   value. Re-sampled with an explicit buffered `reduceRegions` at `scale=25`:

   | | as published | corrected |
   |---|---|---|
   | coverage | 10 / 274 | **89 / 274** |
   | r | +0.635 | **+0.296** |
   | R² | 0.404 | **0.088** |
   | slope | +0.63 | **+0.27** |
   | RMSE | 4.59 | 7.45 |
   | bias | +3.19 | +1.67 |

   Both acceptance checks pass: `gedi_n_50m > 0` holds for exactly the 89 rows carrying an
   `rh98`, and the coverage line equals the regression's n. All 10 previously-published rows
   are still covered and their values barely move (e.g. 21.30 → 21.84, 12.13 → 11.73), so the
   old column was a 10-row *subset*, not a set of wrong values — the defect suppressed
   coverage, it did not corrupt what little it returned. Coverage is uneven by district:
   ANGUL 23/40, DHENKANAL 30/76, KENDUJHAR 4/12, KORAPUT 32/146.

   **This makes the structural conclusion stronger, not weaker.** R²=0.404 at n=10 was the
   best-looking number in the study and it was an artefact of a 10-plot subset; at honest
   coverage GEDI explains 8.8% of the variance in Lorey's height with a slope of 0.27 — the
   same compression failure as ETH, on a tenth of the plots. GEDI does not supply the
   structural criterion.
3. **Task 4 as briefed is void, and the verdict is why.** Task 4 was "remove ETH and install
   what Task 1 names". Task 1 names nothing. Removing both ETH bands from the three current
   criteria leaves one — below `min_defined_criteria: 2`, which must not be lowered — so with
   no replacement the full ETH removal cannot be executed at all. That is a finding, not a
   deferral: the criteria list cannot shrink to one, and there is nothing validated to grow it
   back with.

   **One piece of it does survive the verdict, because it never depended on it.**
   `canopy_height_std` should go regardless of Task 1: R²=0.000 against crown cover
   (r=−0.011) is not a weak criterion, it is a criterion measuring nothing it claims. Dropping
   it leaves exactly two — `canopy_height` and `ndvi_amplitude_annual` — which meets the floor
   without lowering it. **Not applied here**, because it is not a neutral edit and the
   consequences should be signed off rather than slipped into a verdict commit:

   - With three criteria and a floor of 2, one may be null and a merge is still admissible.
     With **exactly two and a floor of 2, both must be defined** for any merge to be admitted
     (`compare()` returns `(False, inf, n_defined)` below the floor). Wherever ETH or the NDVI
     amplitude is masked, merging stops. That is strictly stricter behaviour, not a like-for-
     like removal.
   - It changes `merge.criteria`, so it changes the cache fingerprint and every downstream
     number in every arm — which is the same reason item 4 holds the AlphaEarth arm.
   - `sanjay_van_nirv_dual.yaml` names all three criteria explicitly (with
     `nirv_amplitude_annual` in place of the default's `ndvi_amplitude_annual`), so the
     default and that config have to move together or the arms stop being comparable — one
     would gate on three criteria and the others on two.

   Note the two decisions are about different roles and do not have to agree:
   `canopy_height_std` is also a **SNIC input band**, where it contributes texture that carves
   the tessellation and survives the spatial null at +0.076. The R²=0.000 finding is about its
   fitness as a *measurement of crown cover*, which is what a merge criterion gates on. The
   recommendation is to drop it as a criterion and leave it as a SNIC input.
4. **AlphaEarth arm held.** Correct: changing `merge.criteria` changes the cache
   fingerprint and every number downstream.
5. `off_B5` (R²=0.140 vs Sal dominance) is a leaf-off seasonal composite band **no stage
   produces**. New work if it is wanted.
6. ~~Meta as a criterion would need new code~~ — **moot.** Meta is DISQUALIFIED, so the
   `features_structure.py` work it would have required (that stage does
   `ee.Image(canopy_asset).select(0)`, a single Image; Meta is a 1 m ImageCollection needing a
   mosaic and a `reduceResolution`) is not work to do. Recorded so the absence of that code is
   understood as a decision rather than an omission.

7. **One field record to raise with FES, either way.** Pangatira plot
   `21.156085_85.364999` reads **8% crown cover while carrying 16.19 m of Lorey's height**.
   The other nine Pangatira plots run 58–88%. It is either a data-entry error or a genuinely
   open canopy of tall emergents, and it sits inside the site whose ten zeros drove the
   site-level Meta question, so it is worth resolving before Pangatira is used to argue
   anything. Part B does not settle it: that plot's Meta box is uniformly 0 like its
   neighbours', and its ETH 3×3 is 11.22 m, so neither product distinguishes it from the
   other nine. Note the same pattern appears once among the controls —
   `21.045566_85.52362` reads 8% crown cover at 6.91 m Lorey's — so 8% is not unique to
   Pangatira and may be a recording convention rather than an error.

---

## What the merge's structural criterion should be

**There isn't one yet.** That is the answer the evidence supports, and it should be stated
rather than papered over.

The reasoning, in the order it matters:

**No available product measures stand height well enough to gate on in absolute units.**
The best plot-level R² was Meta at 0.241, which falls to 0.142 once its 44.5% zeros are
excluded — and **Meta is now DISQUALIFIED**, so 0.241 is void and 0.142 describes a biased
subset. ETH is 0.207 with slope 0.30 and a compressed range. GLAD inverts. **GEDI has now
been re-sampled and does not change the conclusion — it reinforces it**: at true coverage
(89/274, not 10) it falls to R²=0.088 with slope 0.27, so the one entry that could plausibly
have supplied a structural criterion does not. That leaves `vh_iqr` at 0.227 as the
best-validated free signal — and it is a radar texture proxy, not a height measurement, and
it is the one thing that gets *worse* under aggregation, which is the opposite of what a
stand-scale criterion needs.

**Both height products that a merge could be built on have now failed a direct test, not a
weak one.** ETH fails on dynamic range: it spans 8 m where the field spans 35. Meta fails on
validity: it returns 0 m on an unmasked grid over measured forest. These are different
failure modes and neither is fixed by a better tolerance.

**`canopy_height_std` should go regardless of Task 1.** R²=0.000 against crown cover
(r=−0.011) is not a weak criterion, it is a criterion measuring nothing it claims. With
`min_defined_criteria: 2` it can be one of the two that admits a merge. It survives the
separation null (+0.076), so it does affect the partition — which makes it worse, not
better: it is shaping stands on a quantity with no established meaning. This is the one part
of Task 4 the verdict leaves standing; **unresolved item 3 states what dropping it actually
changes** (a two-criterion list against a floor of 2 means both must be defined, not one of
three), and it is a recommendation there, not an applied edit.

**If ETH stays, the tolerance cannot stay in absolute metres.** This is the sharpest
actionable conclusion here. Spearman consistently beats Pearson — ETH 0.484 vs 0.455, Meta
0.541 vs 0.491 — so the products rank neighbours better than they calibrate, and ranking is
what a conjunctive neighbour gate actually needs. But `2.0 m` is a *calibrated* claim, and
on a product whose whole range is 8 m against a real 35 m it does not mean the 2 m it says.
A tolerance expressed as a percentile of the observed pair-difference distribution —
which `calibrate_thresholds()` already computes — would mean the same thing in every AOI
and on every product. That is also consistent with the standing rule that no Odisha number
becomes a default: it names a method, not a value.

**Task 1 has now resolved this, and it resolved against Meta.** The conditional read:

- **RECOVERABLE** → Meta is the candidate: best plot-level number, and the only product
  whose signal *improves* with aggregation (+0.361), which is the property a stand-scale
  criterion needs.
- **NO DATA or DISQUALIFIED** → Meta is out, and there is no validated structural
  criterion.

The verdict is **DISQUALIFIED**, so the second branch is the operative one. The +0.361
aggregation lift does not rescue it: that lift is computed on the zeros-excluded subset,
which is precisely the subset from which the product's failures have been removed. **No
replacement canopy-height source is installed.**

What follows is the honest position, and it is a narrowing rather than a substitution: keep
ETH *as a relative ordering only*, with a percentile tolerance rather than absolute metres,
and state in the methods that the structural axis is unvalidated in this forest type. Do not
substitute `vh_iqr` and imply it measures height — at R²=0.227 it is the best-validated free
signal here, but it is a radar texture proxy, and it is the one thing that gets *worse* under
aggregation, which is the opposite of what a stand-scale criterion needs.

**What must not happen**, restating the standing rules because this is where the pressure
will be: do not lower `min_defined_criteria` to fit a shorter criteria list; do not tune a
tolerance to hit a pass rate or an R²; do not put an Odisha-derived constant into
`config.py`.

---

## Reproducing

```bash
cd odisha_script
python odisha_phase1_7_meta_zero_diagnosis.py   # part A offline; part B needs GEE (has run)
python odisha_phase1_8_separation_null.py       # fully offline, reads b24fad3 via git show
python odisha_phase1_9_gedi_recount.py          # re-samples GEDI; needs GEE; writes v3 CSV
python odisha_phase1_10_meta_offset_check.py    # needs GEE; 4 getInfo calls, no exports
```

Each writes `odisha_phase1_<n>_results.txt` beside itself; step 8 also writes
`odisha_phase1_8_separation_null.png`. Step 10 imports `pick_plots` from step 7 rather than
reimplementing the selection, so the two cannot drift apart.

The verdict figures above can be re-derived from the committed artifacts without Earth
Engine:

```bash
cd odisha_script
# district coverage and height range of the 12 diagnosed plots vs all 122 zeros
python -c "
import pandas as pd; from odisha_phase1_7_meta_zero_diagnosis import pick_plots
df = pd.read_csv('odisha_plots_sampled_v2.csv'); z = df.meta_chm == 0
p, _ = pick_plots(df, z)
print('zeros', int(z.sum()), 'of', len(df))
print(df[z].district.value_counts().to_dict())
print('diagnosed', p.district.value_counts().to_dict())
print('zeros >20m:', int((df[z].loreys_h_m > 20).sum()), ' median:', df[z].loreys_h_m.median())"
# band-identity histogram: contiguity and where it breaks
grep -E '^ +[0-9]+ +[0-9,]+ +[0-9.]+%' odisha_phase1_10_results.txt
```
