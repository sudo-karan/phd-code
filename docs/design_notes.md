# Design notes

Notes on why the code is the way it is. Companion to `decisions.md` in the
phd-notebook repo — `decisions.md` *locks* choices, this file *explains* them.
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

- `Settings` (`settings.py`) — per-machine, from `.env`, gitignored. Project
  ID, output paths, log level. Different per user.
- `Config` (`config.py`) — per-experiment, from YAML, in git. ROI, dates,
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
Without context labels, error tracebacks point at the materialization line —
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
informational only. Research pipelines benefit from loud failures — silent
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

## Date windows differ by sensor

Three separate windows for three jobs:

- **phenology (long, 8y)**: harmonic regression needs many cycles for stable
  amplitude/phase. Year-to-year anomalies have to average out.
- **radar (5y)**: Sentinel-1B operational 2016 – Dec 2021 (mission ended Aug
  2022). From late 2021 through 2024 only S1A operated, so revisit dropped
  from 6 to 12 days. We cap at 2021 to keep per-month image counts
  consistent. S1C launched Dec 2024, S1D Nov 2025; constellation back to
  full multi-satellite operation in 2025.
- **optical composite (1y)**: one cloud-free median, recent year, for SNIC
  to draw boundaries on. Not a time series.

## Pydantic v1 vs v2

v2 throughout. Faster, better error messages, official pydantic-settings
companion, current standard. Don't accidentally install v1 — they're not
compatible.

## Masking: avoiding circularity with the feature data

A mask that's derived from the same data we cluster on is at risk of
forcing the clustering to find what the mask put there. Strongest case:
NDVI mask + NDVI feature is pure leakage. Less obvious: anything S2-derived
used to mask data that will later be fed S2 features.

We accept moderate circularity for **WorldCover** (S2/S1-derived) because
the signal it extracts (categorical land cover) is qualitatively different
from the continuous phenology features we'll compute. Replacing it would
cost more (lose 10 m, lose convenient veg classes) than the residual bias
costs.

We avoid it for the **built-up mask** because that's the layer the
downstream urban-vs-vegetation distinction depends on. Built-up uses:
- **Google Open Buildings** (vector polygons from commercial high-res
  imagery — different sensor altogether), rasterized at 10 m
- **VIIRS Nightlights** (Day/Night Band — different sensor entirely)

Both are independent of S2/Landsat. Their failure modes (low confidence
polygons, coarse 463 m resolution) are different from each other and
different from WorldCover, so combining them recovers from each one's
weaknesses.

Water uses **JRC GSW** (Landsat-derived — different mission from S2)
OR **WorldCover class 80** for redundancy.

This is one of the few places where the framework explicitly does better
than the notebooks: in the notebooks, masking was a single-source
afterthought.

## Asset caching: cross-cutting, opt-in

Stages that materialize ee.Image outputs can be expensive to recompute and
expensive to visualize (per-tile compute hits GEE's memory limit at high
zoom for stages with lots of vector rasterization, like Open Buildings).
Caching solves both: compute once, save as an asset, reuse forever.

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

The orchestrator handles caching transparently — individual stages don't
need to know. They produce `ee.Image` outputs as usual; the orchestrator
checks cache before running and submits exports after.

Sharing assets with collaborators (programmatic ACLs via `team.yaml`) is
deferred to a future module — for now anyone with the asset path can read
them if granted access manually.

## Caching: only ee.Image outputs, not collections

Asset export works for `ee.Image`, not for `ee.ImageCollection`. A collection
is a sequence of images, and "exporting it" would mean exporting each one as
a separate asset — many tasks, lots of storage, and the resulting assets
wouldn't be reusable as a collection anyway.

So stages that produce collections (`data_load`) declare which subset of
`produces` is actually cacheable via `cacheable_outputs`. The orchestrator
only checks/exports those, and re-runs the stage live each time to
regenerate the collections (which is cheap — filtering is just metadata).

For data_load specifically:
- `s2_collection`, `s1_collection`: re-filtered each run, ~1-2 sec
- `s2_composite`: cached. This is the expensive operation — it reduces
  potentially hundreds of S2 images through the SCL mask and reducer.

The pattern generalizes: any future stage that produces a mix of cheap
metadata (collections, geometries) and expensive materializations (images)
can declare its `cacheable_outputs` accordingly.

## features_optical: config-driven, single stage code

The same `FeaturesOpticalStage` runs both the NDVI + single-annual baseline
and the NIRv + dual-harmonic variant. The config tells it which index to
compute, which harmonic terms to include, and whether to add a linear
trend. No code branches on "is this a variant?" — the config drives the
exact regression structure dynamically.

This is the intended pattern for "improve, don't fork": new ideas become
new YAML files, not new modules. The framework checks both run cleanly
and produces comparable outputs. Module 18 (metrics) does the actual
comparison.

The regression is fit per-pixel using `ee.Reducer.linearRegression(numX, numY=1)`,
which returns coefficients as an array image plus residual RMS. The stage
extracts each coefficient by name, derives amplitude / phase per harmonic
pair, and combines everything into one multi-band image whose band names
encode the config (e.g., `ndvi_mean` vs `nirv_mean`). Downstream stages
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

This isn't optional or stylistic — using the stored integers directly
produces values ~10000× too large and breaks the literature definition.
Discovered when NIRv visualizations rendered fully saturated against a
0-1 palette; fixing it in the feature stage (rather than adapting the
palette) was the right move because (a) the values are now physically
meaningful, (b) the clusterer treats both indices on the same scale
before z-scoring, and (c) future stages don't need to remember which
index is in which range.

NDVI is unaffected — the 10000 scaling cancels in the ratio.
