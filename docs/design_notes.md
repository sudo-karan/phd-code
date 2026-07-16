# Design notes

Notes on why the code is the way it is. Companion to `decisions.md` in the
phd-notebook repo; `decisions.md` *locks* choices, this file *explains* them.
Keep entries short. If something needs more, write it up properly.

---

## Config: Pydantic v2 vs dataclasses / dicts

Pydantic gives clear error messages when a YAML field is wrong, type-checks at
load time, and supports `.env` integration via pydantic-settings. Plain
dataclasses would need a hand-rolled validator. Dicts lose all of this.

Cost: one more dependency. Worth it.

`extra="forbid"` on every model so a typo in YAML errors immediately instead
of silently using a default.

## Settings vs Config

Two separate Pydantic things on purpose:

- `Settings` (`settings.py`); per-machine, from `.env`, gitignored. Project
  ID, output paths, log level. Different per user.
- `Config` (`config.py`); per-experiment, from YAML, in git. ROI, dates,
  parameters. Same for everyone running the same experiment.

If two people run `python ... --config baseline.yaml` they should get the
same output. That only holds if scientific parameters are in the YAML, not
the env. See DEC-003.

## ROI: GeoJSON now, GEE asset path reserved

GeoJSON works for small ROIs and is version-controlled. GEE inline geometry
is capped around 5 MB. For complex / national-park-scale polygons we'd hit
that; the schema accepts `roi_asset` for that case but only `roi_file` is
implemented. See DEC-005.

## Logging: per-run folder, not single rolling log

`outputs/runs/<config>_<timestamp>/` per run, containing `fmu.log`,
`manifest.json`, and (later) GeoTIFFs and reports. Lets us tar/archive
individual runs and supports the longitudinal record of validation metrics.
See DEC-009.

## GEE: explicit init, not auto-on-import

`init_gee()` must be called explicitly. Auto-init on import would mean tests
that don't touch GEE can't import any module without authenticating, and
errors at import time are confusing. See DEC-008.

## `safe_get_info` wrapper

GEE errors fire at materialization (`.getInfo()`), not at construction.
Without context labels, error tracebacks point at the materialization line,
50+ lines away from the offending operation. The wrapper attaches a context
string so the error tells you which operation failed.

Pattern: any `.getInfo()` in stage code should go through `safe_get_info` or
the `safe_call` decorator. See DEC-010.

## Stage contract: context-dict + declared inputs/produces

Stages communicate through a shared `PipelineContext`, not via named
parameters. Each stage declares `required_inputs` and `produces` as class
attributes; the orchestrator validates these against the context before
running. This gets the flexibility of dict-passing (new keys don't break
existing signatures) with the readability of named params (the registry
can list what each stage needs without reading its body). See DEC-012.

## Stage failure: exceptions only, no soft-fail

A stage either succeeds or raises. `warnings` field on `StageResult` is
informational only. Research pipelines benefit from loud failures; silent
partial failures cause subtle wrong results that are hard to detect later.
See DEC-013.

## Two-tier testing

`pytest` runs fast mocked tests by default (~1 sec, no auth, runs in CI).
`pytest -m live_gee` runs real-API tests (~10-20 sec, needs auth, run before
locking a module). Both have to pass before locking. See DEC-011.

## Baseline matches the working notebook, not the aspirational design

`configs/sanjay_van_baseline.yaml` uses what the notebooks did:
S2_SR_HARMONIZED, k=6, zscore, single annual harmonic. HLS migration,
auto-K, robust scaling, and dual harmonic are deferred to separate config
files for comparison against the baseline.

The baseline is the reference, not the best version. New ideas become new
configs and have to beat it. This is the mechanism for stopping the
"going-in-circles" pattern. See DEC-006.

## Date windows: one shared time-series window

Phenology (S2), radar (S1), and the optical composite all use one shared
6-year window, 2017-01-01 to 2022-12-31. Climate is the only exception: a
30-year normal (1991-2020).

- **phenology**: harmonic regression needs many cycles for stable
  amplitude/phase. Six years lets year-to-year anomalies average out.
- **radar**: same 2017-2022 window, summarized with percentile statistics
  over the window rather than fit to a seasonal cycle.
- **optical composite**: one cloud-free median over the same window, for
  SNIC to draw boundaries on. Not a time series (a different reduction of
  the same data).

Sharing one window keeps the sensors temporally comparable and drops the
bookkeeping of separate per-sensor windows.

## Pydantic v1 vs v2

v2 throughout. Faster, better error messages, official pydantic-settings
companion, current standard. Don't accidentally install v1; they're not
compatible.

## Masking: IndiaSAT-primary, single-phase habitat

Habitat comes from the **IndiaSAT LULC** product (Bansal et al. 2021), a
30 m annual land-cover raster for 2017-2022 built specifically for Indian
landscapes. We keep class **6 (Trees)** and **12 (Shrubs/Scrubs)** as
habitat, and decide each pixel by a **majority vote over its usable
(non-cloud) years** — habitat if more usable years were Trees/Shrubs than
not — so a one-off annual misclassification can't flip a pixel in or out
of the mask.

Voting is done on the *binary* habitat question (is this year Trees/Shrubs?)
rather than on the multi-class mode. A multi-class mode would break a
habitat-vs-non-habitat tie by the smallest class code — an arbitrary,
ecology-free rule that quietly biases ties against habitat (since Trees=6
and Shrubs=12 carry high codes). Instead a **tie is broken by the most
recent usable year** (cascading to the next-latest where the newest is
cloud/no-data): an explicit, defensible "what was it most recently" rule.

The mask is **single-phase**: water, cropland, and built-up are excluded
simply because their classes are not in the habitat set. There is no
separate water-mask subtraction and no built-up mask. With a purpose-built
LULC that already distinguishes trees/shrubs from water, crops, and
built-up, a habitat definition is just "which classes count as habitat,"
and everything else falls out for free.

**ESA WorldCover v200** (classes 10/20/30) is kept only as a **fallback**,
used where IndiaSAT has no data (coverage gaps, or AOIs outside its
footprint). IndiaSAT covers all of India, so in practice the fallback
rarely fires. No WorldCover class is used for water.

**JRC Global Surface Water** is still loaded, but only to build
`water_mask` for the downstream distance-to-water feature (see
`features_static`). It plays no part in habitat masking. `water_mask` is
JRC occurrence ≥ threshold; nothing else is OR'd in.

There is no built-up mask any more, so the old concern about deriving that
layer from a source independent of the S2 features we later cluster on is
moot. Habitat now rests on IndiaSAT class labels — a categorical
land-cover signal, qualitatively different from the continuous phenology
features in the feature stack — the same reasoning that made a class-based
keep-list acceptable before, now applied to a product built for this
region.

## Asset caching: cross-cutting, opt-in

Stages that materialize ee.Image outputs can be expensive to recompute and
expensive to visualize (per-tile compute hits GEE's memory limit at high
zoom for compute-heavy stages). Caching solves both: compute once, save as
an asset, reuse forever.

Three design points:

1. **Off by default.** `Pipeline(stage_names, use_cache=False)`. Tests
   don't write assets; only real runs (via the inspect / run scripts) flip
   it on. This keeps the test suite clean and prevents accidental asset
   pollution.

2. **Stable paths, not hash-based.** Path is
   `{asset_root}/{config_name}/{stage_name}/{key}`. Changing config
   thresholds overwrites the asset. We accept this tradeoff for now; a
   future module can add config-hash-based paths if reproducibility of
   past runs becomes important.

3. **Fire-and-forget on cache miss.** Stage runs live AND submits an async
   export task. The current run returns the live computation; the next
   run benefits from the cache. No blocking on the (5-15 min) export.
   This is the standard GEE pattern.

The orchestrator handles caching transparently; individual stages don't
need to know. They produce `ee.Image` outputs as usual; the orchestrator
checks cache before running and submits exports after.

Sharing assets with collaborators (programmatic ACLs via `team.yaml`) is
deferred to a future module; for now anyone with the asset path can read
them if granted access manually.

## Caching: only ee.Image outputs, not collections

Asset export works for `ee.Image`, not for `ee.ImageCollection`. A collection
is a sequence of images, and "exporting it" would mean exporting each one as
a separate asset; many tasks, lots of storage, and the resulting assets
wouldn't be reusable as a collection anyway.

So stages that produce collections (`data_load`) declare which subset of
`produces` is actually cacheable via `cacheable_outputs`. The orchestrator
only checks/exports those, and re-runs the stage live each time to
regenerate the collections (which is cheap; filtering is just metadata).

For data_load specifically:
- `s2_collection`, `s1_collection`: re-filtered each run, ~1-2 sec
- `s2_composite`: cached. This is the expensive operation; it reduces
  potentially hundreds of S2 images through the SCL mask and reducer.

The pattern generalizes: any future stage that produces a mix of cheap
metadata (collections, geometries) and expensive materializations (images)
can declare its `cacheable_outputs` accordingly.

## features_optical: config-driven, single stage code

The same `FeaturesOpticalStage` runs both the NDVI + single-annual baseline
and the NIRv + dual-harmonic variant. The config tells it which index to
compute, which harmonic terms to include, and whether to add a linear
trend. No code branches on "is this a variant?"; the config drives the
exact regression structure dynamically.

This is the intended pattern for "improve, don't fork": new ideas become
new YAML files, not new modules. The framework checks both run cleanly
and produces comparable outputs. Module 18 (metrics) does the actual
comparison.

The regression is fit per-pixel using `ee.Reducer.linearRegression(numX, numY=1)`,
which returns coefficients as an array image plus the RMS residual. The stage
extracts each coefficient by name, derives amplitude / phase per harmonic
pair, squares the RMS residual into `residual_variance` (a diagnostic band,
excluded from clustering), and combines everything into one multi-band image
whose band names encode the config (e.g., `ndvi_mean` vs `nirv_mean`). Downstream stages
can read either via the `optical_features` context key without knowing
which index was used.

Per DEC-014, features are computed over the entire ROI. The `habitat_mask`
from Module 7 is not applied here; it's the clustering stage's job to
filter pixels before training. This keeps the feature stage flexible (you
can visualize phenology of built-up pixels alongside forest pixels for
context) at no computational cost (GEE is lazy).

## NIRv units: NIR_reflectance × NDVI (both 0-1)

Per Badgley et al. (2017), NIRv = NIR_reflectance × NDVI, where
NIR_reflectance is actual reflectance (0-1). Sentinel-2 SR stores
reflectance as integers scaled by 10000, so the stage divides B8 by
10000 before multiplying by NDVI. This keeps NIRv in [0, 1] like NDVI.

This isn't optional or stylistic; using the stored integers directly
produces values ~10000× too large and breaks the literature definition.
Discovered when NIRv visualizations rendered fully saturated against a
0-1 palette; fixing it in the feature stage (rather than adapting the
palette) was the right move because (a) the values are now physically
meaningful, (b) the clusterer treats both indices on the same scale
before z-scoring, and (c) future stages don't need to remember which
index is in which range.

NDVI is unaffected; the 10000 scaling cancels in the ratio.

## features_radar: no harmonic, no speckle filter

Unlike optical phenology, SAR backscatter doesn't have a clean seasonal
cycle to fit. Returns depend on surface geometry, soil moisture, and
biomass; not on photosynthesis. So we don't fit harmonics; we summarize
the 6-year time series with percentile statistics (p10, p50, p90),
temporal spread (p90 − p10), and one derived ratio (VV − VH in dB).

Two specific choices worth documenting because they deviate from the
notebook approach:

**VV − VH (dB), not VV / VH.** The notebook divided dB-scale values
directly: `vv.divide(vh)`. This isn't mathematically meaningful; dB is
log-scale, and a "ratio" of log values produces a number with no clean
physical interpretation. The right operation is either:
  - Difference in dB: `VV_dB − VH_dB`
  - Ratio in linear units: `VV_linear / VH_linear`
These are identical under the log transform: `VV − VH (dB) = 10·log10(VV_linear / VH_linear)`.
We use the dB difference because it has clean physical meaning ("VV is X dB
stronger than VH") and matches standard SAR vegetation literature.

**No speckle filter.** Per-image Lee filter or similar is a common
preprocessing step in SAR pipelines, but for our use case it's the wrong
tradeoff:
- We aggregate 100+ S1 images per pixel via median. The temporal variance
  reduction (~√N factor) is much stronger than any 3×3 or 5×5 spatial
  filter could provide.
- Spatial filters blur edges. SNIC segmentation downstream relies on
  visible edges in the data to draw superpixel boundaries; pre-blurring
  works against that.
- Filter parameter tuning (window size, damping) adds knobs we'd need to
  defend. ENG-006's "stop going in circles" concern applies.
If individual-scene speckle becomes a concern (e.g., for visualization),
that's a variant config (`features_radar.apply_lee_filter: true`), not a
baseline addition.

## features_structure: canopy height + neighborhood stats

ETH Global Canopy Height 2020 is the per-pixel input (10 m, derived from
GEDI + S2 fusion; DEC-009). The notebook used this as a single band.
This module adds two derived bands by default: standard deviation and
max within a small (3×3) window around each pixel.

The neighborhood stats capture structural heterogeneity that the point
value can't. A mature even-aged stand has uniform tall trees to low std,
max ≈ height. A regenerating patch has variable heights to high std. A
forest edge has tall and short pixels mixed to high std, max much larger
than the typical pixel.

A 3×3 window at 10 m resolution covers 30 × 30 m on the ground; small
enough to preserve stand boundaries (we don't want to blur across forest
edges before SNIC sees them). Window size is configurable via
`features_structure.neighborhood_kernel_size` (odd integers 3-11).

When `include_neighborhood_stats: false`, only canopy_height is emitted;
that's the notebook-faithful mode. Both baseline and nirv_dual default
to true to keep structure features identical between configs (so optical
variant comparison stays controlled at Module 18).

## features_static: terrain + distance + climate

Five bands: elevation, slope, aspect, distance_to_water, annual_rainfall.

`ee.Terrain.products()` computes slope and aspect from elevation. NASADEM
is in meters per pixel, so slope comes out in degrees correctly.

`distance_to_water` is the first stage that *requires* the masking stage's
output (it consumes `water_mask`). This is a deliberate dependency; using
the same water source for both exclusion (masking) and feature (here)
keeps the two notions consistent. The alternative (compute water freshly
inside this stage) would risk drift between the two definitions.

`fastDistanceTransform` returns squared-euclidean distance in pixels. Take
sqrt and multiply by analysis scale (10 m) to get distance in meters.

CHIRPS PENTAD provides 5-day rainfall totals. Sum over the 30-year window
(1991-2020 standard normal) divided by 30 gives mean annual rainfall in mm.
For Sanjay Van this will be ~600-800 mm; Delhi's monsoon-dominated regime.
The band will be nearly uniform within the AOI; included for cross-AOI
generality (when an AOI spans climate gradients).

Aspect is emitted as raw degrees 0-360. This is cyclic; north-facing
pixels at 0° and 359° look maximally different to a Euclidean clusterer.
A sin/cos decomposition would fix this; left as a future improvement to
match notebook behavior.

## segmentation: 5-band z-scored stack, NIRv for the optical signal

The SNIC input stack is hand-picked from the resolution analysis:
B4_median + B8_median + composite_nirv + canopy_height + vv_minus_vh_median.
All 10 m native, four orthogonal information sources (visible color, NIR,
structural height, microwave roughness).

`composite_nirv` is derived in the segmentation stage from B4/B8 of the
S2 composite (2017-2022): `(B8/10000) × NDVI`. Not the same as `nirv_mean`
from features_optical (that's a harmonic-regression intercept over 6 years).
This in-stage derivation has two advantages:
  1. Available identically to both baseline and nirv_dual configs without
     either re-export or per-config code branches
  2. Spatial signal from a single median composite over the 2017-2022
     window; good for boundaries

Why NIRv over NDVI for SNIC input: NDVI saturates in dense canopy. Sanjay
Van is exactly such a case; its forest interior would map to one NDVI
value, hiding within-forest structure SNIC needs to find boundaries on.
NIRv keeps responding because NIR alone is unbounded. The user pushed
back on a default-to-NDVI choice; the math is on their side here.

Pre-SNIC normalization (z-score per band over the ROI) is essential
because the 5 bands span 4 orders of magnitude (S2 reflectance 0-3000,
canopy_height 0-30, NIRv 0-1, dB ~0-15). Without normalization, raw S2
bands dominate SNIC's distance metric.

Same SNIC inputs across both configs means boundaries are bit-identical
between baseline and nirv_dual. Module 18's clustering comparison is
attributable to optical features alone; segmentation is not a confound.

## clustering: where the actual stand assignment happens

The clustering stage is the longest single stage in the pipeline because
it has the most distinct steps. Each step is a small, well-defined
operation; the complexity is in the orchestration.

**Why we average per superpixel before clustering** (DEC-001): clustering
on raw pixels gives salt-and-pepper output because of within-stand pixel
noise. SNIC superpixels are ~100 pixels each; averaging within them
yields stable per-stand feature vectors that the clusterer can group
sensibly.

**Why cyclic decomposition** (sin/cos for phase + aspect): a phase of 0
and 2π are identical angles but maximally distant in linear feature
space. K-means uses Euclidean distance. Without decomposition, two stands
peaking on Jan 1 and Dec 31 would look maximally different despite being
phenologically identical. sin/cos pairs are continuous across the cyclic
discontinuity.

**Why log-transform before scaling** (DEC-004): some feature distributions
are right-skewed (long tail of large values; typical for distance
metrics, IQR bands, biomass-related signals). Median/IQR scaling can
handle skewed distributions but k-means still treats outliers as
maximally distant points that pull centroids around. Log-transform
compresses the long tail; subsequent median/IQR scaling then puts the
de-skewed distribution on a comparable scale to the other bands.

**Why median/IQR over z-score** (DEC-003): outliers exist (occasional
unusual pixels; disturbed patches, gaps, anomalies). Mean and stddev
are sensitive to outliers; median and IQR aren't. The notebook used
zscore; we deviate here because the practical difference matters in
heterogeneous landscapes like Sanjay Van's edges.

**Why drop constant bands instead of silently dividing by zero**: some
bands genuinely have zero spread (e.g., annual_rainfall when the entire
ROI sits inside one CHIRPS pixel). We detect IQR ≤ 1e-9 and drop the
band rather than producing NaN/Inf garbage. The dropped band list is
recorded in clustering_metadata so we know what got excluded.

**Why cache preprocessing params as image properties** (ENG-022): they
are JSON-serializable scalars and short lists. Image properties travel
with the asset across machines and sessions. Profiling and metrics
stages can read these back to invert transformations (e.g., display
centroid values in original feature units) without recomputing the
medians, IQRs, etc.

**Stochastic clustering and reproducibility**: k-means initialization is
non-deterministic in general. We use `seed=42` for reproducibility, and
the GEE wekaKMeans seed argument propagates through KMeans++ init. With
the same inputs and same seed, runs are bit-identical.

**Same configuration, both variants**: both baseline and nirv_dual run
through identical clustering code. Their feature stacks differ (baseline
has 4 optical bands after dropping obs_count and residual_variance;
variant has 6 due to dual harmonic), and that's the entire experiment;
does NIRv+dual give better clusters? Module 18's metrics will answer that.
