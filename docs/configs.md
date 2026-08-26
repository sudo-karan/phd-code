# Configs

How fmu's experiment-via-config pattern works, what each config field
does, and how to add a new experiment.

## The two-layer split

fmu separates **what to run** (per-experiment, in git) from **where to
run it** (per-machine, gitignored). See
[design_notes.md](design_notes.md#settings-vs-config) for the full
rationale.

| Layer | Lives in | Loaded by | Validates with |
|---|---|---|---|
| `Config` | `configs/<name>.yaml` (git) | `fmu.config.load_config(path)` | Pydantic schema in `src/fmu/config.py` |
| `Settings` | `.env` (gitignored) | `fmu.settings.get_settings()` | Pydantic-settings in `src/fmu/settings.py` |

If two people run the same `configs/X.yaml`, they should produce
identical scientific output. Per-machine paths (output dir, GEE project
ID) come from `.env`; per-experiment knobs (k, thresholds, dataset IDs)
come from the YAML.

## Config schema overview

A config has these top-level keys (every field is validated; typos are
rejected because every model uses `extra="forbid"`):

```yaml
name: <string, no slashes or whitespace>
description: <string>
roi: { name, roi_file }
dates: { phenology, radar, optical_composite, climate }
datasets: { phenology_collection, radar_collection, ... }
cloud_mask: { max_cloud_pct, drop_scl_classes }
data_load: { s1_orbit, s1_polarizations, s1_instrument_mode, s2_composite_reducer }
masking: { indiasat_habitat_classes, indiasat_class_band, keep_worldcover_classes, jrc_water_occurrence_threshold }
features_optical: { index, harmonic_mode, include_trend, time_reference }
features_radar: { percentiles, include_iqr, include_cross_pol_contrast }
features_structure: { include_neighborhood_stats, neighborhood_kernel_size }
features_static: { include_climate, max_water_distance_pixels }
features_embedding: { collapse_reducer, band_names }
segmentation: { size, compactness, connectivity, neighborhood_size, normalize_inputs, normalize_distance_scale, input_bands }
merge: { enabled, criteria, relax_factor, min_area_ha, max_area_ha, min_defined_criteria, min_frac_valid, tie_break, max_pass2_iterations, max_superpixels }
clustering: { k, n_training_samples, seed, feature_source, skewness_threshold }
normalization: { method }
features: { optical_harmonic, radar, canopy_height, terrain }
export: { export_geotiff, export_gee_asset, analysis_scale_m, drive_folder, export_vector_snic, export_vector_dissolved, vector_formats, vector_min_stand_pixels }
metrics: { reference_config_name, n_comparison_samples, n_silhouette_samples_per_cluster }
```

For the canonical field list and validators, read `src/fmu/config.py`
directly. It's around 300 lines and self-documenting.

### What each block does

| Block | Controls | Consumed by |
|---|---|---|
| `roi` | Which polygon to operate over | All stages (via context `roi`) |
| `dates` | Time windows for each sensor / dataset | `data_load`, `features_static` |
| `datasets` | GEE dataset IDs | All stages that hit a specific collection |
| `cloud_mask` | S2 cloud filtering | `data_load` |
| `data_load` | S1 acquisition geometry, S2 composite reducer | `data_load` |
| `masking` | Habitat class definition (IndiaSAT primary, WorldCover fallback) + water threshold | `masking` |
| `features_*` | Per-feature-stage toggles and parameters | The matching `features_*` stage |
| `segmentation` | SNIC parameters *and its input band stack* | `segmentation`, `pipeline.default_stage_names` |
| `merge` | Stand-aggregation rules and area bounds | `merge`; also derives the `reduceConnectedComponents` cap used by `clustering` and `metrics` |
| `clustering` | k-means hyperparameters and preprocessing | `clustering` |
| `normalization` | `robust` vs `zscore` scaling | `clustering` |
| `features` | High-level on/off toggles per feature family | Currently informational; future use |
| `export` | Whether to export GeoTIFF, target scale | `export` |
| `metrics` | Reference config to compare against, sampling sizes | `metrics` |

## The locked baseline

`configs/sanjay_van_baseline.yaml` is the reference. Not necessarily
the best version. It approximates the working notebook approach
(S2_SR_HARMONIZED, k=6, single annual harmonic, NDVI) while applying
the locked engineering decisions from `phd-notebook/decisions.md`,
most notably robust scaling per DEC-003. New ideas become new configs
that have to beat this one.

This is deliberate. It's the mechanism for stopping the "endlessly
tweaking parameters, never deciding what worked" pattern. See
[design_notes.md](design_notes.md#baseline-matches-the-working-notebook-not-the-aspirational-design).

**Don't edit the baseline in place.** Copy it, change what you need,
give it a new `name`, run both, let the metrics stage compare.

## The variant: `sanjay_van_nirv_dual.yaml`

The variant config differs from baseline in three ways:

1. `features_optical.index: nirv` (was `ndvi`)
2. `features_optical.harmonic_mode: dual` (was `single`)
3. `metrics.reference_config_name: sanjay_van_baseline` (was `null`)

Everything else is identical. This is the intended pattern: one
controlled change at a time, the framework computes both, the metrics
stage quantifies the difference.

## The embedding variants: `sanjay_van_alphaearth.yaml` / `sanjay_van_tessera.yaml`

Two further variants isolate a different question: do the clusters change when
the feature vector is a **pretrained per-pixel embedding** instead of the
hand-crafted stack? They swap the feature representation and nothing else. See
[design_notes.md](design_notes.md#embedding-arm-cluster-a-pretrained-embedding-instead-of-the-hand-stack)
for the framing — this is a *methods comparison under label scarcity*, not a
claim that either representation is more correct (there is no ground-truth stand
map).

Both differ from baseline in the same three ways:

1. `clustering.feature_source: embedding` (was `handcrafted`) — clusters one
   image from the `features_embedding` stage instead of the
   optical + radar + structure + static stack.
2. `datasets.embedding` — the embedding source. `sanjay_van_alphaearth.yaml`
   uses `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL` (AlphaEarth, a 64-band annual
   ImageCollection the stage collapses by `mean` over 2017-2022).
   `sanjay_van_tessera.yaml` points at an uploaded Tessera Image (a placeholder
   `projects/REPLACE_ME/assets/tessera_sanjay_van_2017_2022` until you ingest it
   with `scripts/prep_tessera.py` and paste in the printed asset id).
3. `metrics.reference_config_name: sanjay_van_baseline` (was `null`).

4. `segmentation.input_bands: [{source: embedding_features, band: "*"}]` — SNIC
   segments on the embedding too.

**The embedding arm is a fully independent pipeline, not a variant of the
baseline.** AlphaEarth supplies the feature vector for both steps that see
features: SNIC draws the boundaries and k-means labels them. Consequently none
of the hand-crafted feature stages run — not `features_optical` or
`features_static`, and (unlike the earlier design) not `features_radar` or
`features_structure` either. `default_stage_names()` derives the stage list from
the union of what clustering and segmentation ask for, so this follows from
config rather than a hardcoded branch.

**What is controlled** is everything that is *not* the feature representation:
same AOI, same 2017-2022 window, same SNIC hyperparameters (`size`,
`compactness`, `connectivity`, `neighborhood_size`), same `clustering.k` and
`seed`, same masking, same `export.analysis_scale_m`. `normalize_distance_scale`
is what makes `compactness: 0.5` mean the same thing at 6 bands and at 64.

Segmentation used to be held byte-identical across arms and that was called the
control. It was in fact the flaw: under the merge design SNIC + `merge`
*produces the stand*, so a shared tessellation reduced the embedding arm to
"which labels does k-means give inside boundaries the hand-crafted stack drew" —
never putting the delineation question, which is the thesis question, to the
embedding at all.

The cost is that the two arms now produce two **different stand maps**, so
ARI/NMI against a shared tessellation is no longer the comparison. There is no
ground-truth stand map, so neither can be declared correct; they are compared on
stability, held-out predictive power at matched stand count, and geometry.

## Adding a new experiment

1. **Copy** `configs/sanjay_van_baseline.yaml` to `configs/<your_name>.yaml`.

2. **Change `name`** to `<your_name>`. This name becomes the cache asset
   subdirectory, the run-dir prefix, and the manifest's `config_name`.
   Restrictions:
   - alphanumeric + `_` + `-` only (no slashes, no whitespace)
   - validated by `Config.name` field validator

3. **Change only the field you're experimenting with.** If you change
   five things at once and the result is better, you don't know which
   change caused the improvement.

4. **Set `metrics.reference_config_name`** to whichever config you want
   to compare against (usually `sanjay_van_baseline`).

5. **Run it:**
   ```bash
   python scripts/inspect_clustering.py --config configs/<your_name>.yaml
   # wait for cache exports (5-15 min)
   python scripts/inspect_metrics.py --config configs/<your_name>.yaml
   ```

6. **Document the experiment.** Add a one-liner to `phd-notebook/decisions.md`
   (or your equivalent log) explaining what you tested and why.

## Adding a new field to the schema

If your experiment needs a parameter the existing schema doesn't have:

1. **Add a Pydantic field** to the relevant block in `src/fmu/config.py`:

   ```python
   class FeaturesOpticalParams(BaseModel):
       model_config = ConfigDict(extra="forbid")
       index: Literal["ndvi", "nirv"] = "ndvi"
       harmonic_mode: Literal["single", "dual"] = "single"
       include_trend: bool = True
       # NEW:
       detrend_method: Literal["linear", "none"] = "linear"
   ```

2. **Set a default** that preserves current behavior (so existing configs
   still validate).

3. **Add a YAML entry** to your new experiment's config.

4. **Read it in the stage** via `config.features_optical.detrend_method`.

5. **Add a fast-tier test** in `tests/test_config.py` confirming the
   field validates as expected (accepted values, rejected invalid values).

Because `extra="forbid"` is set on every model, a typo in YAML (e.g.,
`detrent_method`) errors at load time with a clear message rather than
silently using a default.

## Field-by-field reference

Below is each config field grouped by block. For why a default is what
it is, see [design_notes.md](design_notes.md).

### `name` / `description`

- `name`: short identifier; becomes part of the asset cache path and
  output directory.
- `description`: free-text human description.

### `roi`

- `name`: short tag for the ROI (informational; appears in manifest).
- `roi_file`: path to a GeoJSON polygon in EPSG:4326. Loaded via
  `fmu.utils.gee.load_roi_geometry`. Capped at GEE's inline-geometry
  limit (~5 MB).

### `dates`

One shared 6-year time-series window, plus a separate climatology window:

- `phenology` (default 2017-2022, 6 years): for harmonic regression.
  The 6-year window lets year-to-year anomalies average out.
- `radar` (default 2017-2022): shares the unified time-series window.
  See [datasets.md](datasets.md#sentinel-1-grd).
- `optical_composite` (default 2017-2022): the same 6-year window,
  reduced to a single static composite SNIC sees.
- `climate` (default 1991-2020): standard 30-year climatology window
  for CHIRPS.

### `datasets`

Dataset IDs for every external source. See [datasets.md](datasets.md)
for the full inventory.

- `embedding`: the pretrained per-pixel embedding source, read **only** when
  `clustering.feature_source: embedding` (default
  `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL` = AlphaEarth's 64-band annual Satellite
  Embedding, bands `A00..A63`). Point it at an uploaded Tessera Image to run
  that arm instead; the `features_embedding` stage handles both an annual
  ImageCollection (collapsed over the feature window) and a single Image
  (loaded as-is).

### `cloud_mask`

- `max_cloud_pct` (default 20.0): drop S2 scenes with `CLOUDY_PIXEL_PERCENTAGE`
  above this.
- `drop_scl_classes` (default `[3, 8, 9, 10]`): per-pixel SCL classes
  masked out (cloud shadow, cloud medium, cloud high, thin cirrus).

### `data_load`

- `s1_orbit`: `ASCENDING` or `DESCENDING`. Single direction to keep
  geometry consistent.
- `s1_polarizations`: list of `VV` / `VH` (default both).
- `s1_instrument_mode`: `IW` / `EW` / `SM` (default `IW`).
- `s2_composite_reducer`: `median` / `p25` / `p50` / `p75` (default
  `median`).

### `masking`

- `indiasat_habitat_classes`: IndiaSAT LULC classes kept as habitat
  (default `[6, 12]` = Trees, Shrubs/Scrubs). Every other class (water,
  cropland, built-up, barren, ...) is excluded simply by not being in
  this set — the mask is single-phase.
- `indiasat_class_band`: which band of each annual IndiaSAT image holds
  the class label (default `null` = use the first band of each image;
  the collection also carries a confidence band we don't use). Set
  explicitly only if the asset names its class band differently.
- `keep_worldcover_classes`: WorldCover classes used as the habitat
  **fallback**, applied only where IndiaSAT has no data (default
  `[10, 20, 30]` = tree cover, shrubland, grassland).
- `jrc_water_occurrence_threshold`: minimum % of months a pixel was
  water for it to count as permanent water (default 50.0). Builds
  `water_mask` for the **distance-to-water feature only**; it does not
  affect the habitat mask.

### `features_optical`

- `index`: `ndvi` or `nirv`.
- `harmonic_mode`: `single` or `dual` (annual only, or annual + semi-annual).
- `include_trend`: add a linear-in-time term to the regression.
- `time_reference`: date (default `2017-01-01`). Reference epoch for the
  time variable `t` in the harmonic regression (`t` = years since this
  date). Shifts the numeric value of `phase_*` features by a constant
  but does **not** affect amplitudes, the trend coefficient, or any
  clustering outcome. Keep identical across configs you intend to
  compare phases between — the metrics stage relies on this.

### `features_radar`

- `percentiles`: which percentiles to compute (default `[10, 50, 90]`).
- `include_iqr`: bool (default `true`). Adds `vv_iqr` / `vh_iqr` bands.
- `include_cross_pol_contrast`: bool (default `true`). Adds
  `vv_minus_vh_median`.

### `features_structure`

- `include_neighborhood_stats`: bool (default `true`). False emits only
  `canopy_height`; true also emits `canopy_height_std` and
  `canopy_height_max`.
- `neighborhood_kernel_size`: odd int 3-11 (default 3, a 30 m x 30 m
  window at 10 m resolution).

### `features_static`

- `include_climate`: bool (default `true`). False omits `annual_rainfall`.
- `max_water_distance_pixels`: int 100-10000 (default 1000, a 10 km
  cap at 10 m scale).

### `features_embedding`

Only read when `clustering.feature_source: embedding`; ignored otherwise. In
embedding mode this single pretrained per-pixel image replaces the four
hand-crafted feature images (optical / radar / structure / static).

- `collapse_reducer`: `mean` (default) or `median`. How an annual embedding
  ImageCollection (AlphaEarth ships one image per year) is collapsed to a single
  image over the `dates.phenology` window. `mean` matches the 2017-2022
  averaging the hand-crafted arm rests on. Ignored for a single uploaded Image
  (Tessera), which is loaded as-is.
- `band_names`: list of band names, or `null` (default) to keep every band the
  source provides (AlphaEarth: 64 bands `A00..A63`). Set a list only to restrict
  to a subset — the embedding dimensions are jointly meaningful, so this is
  rarely needed.

### `segmentation`

- `size`: SNIC seed spacing in pixels (default 10, ~100 m on 10 m grid).
- `compactness`: 0 = boundaries follow image edges, high = circular
  blobs (default 0.5).
- `connectivity`: 4 or 8 (default 8).
- `neighborhood_size`: SNIC search window (default 128).
- `normalize_inputs`: z-score per band before SNIC (default `true`).
- `normalize_distance_scale`: after z-scoring, divide the stack by the
  empirical RMS feature distance between 4-adjacent pixels over the ROI
  (default `true`). SNIC trades a summed squared colour distance against a
  spatial-compactness term, and that sum grows with the number of *effective*
  axes — so without this, `compactness: 0.5` buys a much weaker spatial term in
  a 64-band embedding arm than in a 6-band hand-crafted one, and the two are not
  comparable. Dividing by `sqrt(n_bands)` would assume the bands are
  independent; for an embedding they are not. The value actually used is
  recorded in the run manifest as `distance_scale`. This makes `compactness`
  *comparable* across arms; it does not make any particular value correct.
- `input_bands`: the bands SNIC segments on, as a list of
  `{source, band}` pairs, in order. `source` is a pipeline context key —
  one of `s2_composite`, `optical_features`, `radar_features`,
  `structure_features`, `static_features`, `embedding_features`.

  Two special `band` values:
    - `"*"` — every band of that image. Use this for embedding arms rather
      than listing 64 dimensions by hand; it costs one extra `bandNames()`
      call and keeps working if the dimensionality changes. A source using
      `"*"` may not also list named bands.
    - `composite_nirv` — exists on no upstream image; the segmentation stage
      derives it from the composite's B4/B8 as `(B8/10000) × NDVI`.

  Default (used by `sanjay_van_baseline.yaml`, which deliberately does not
  repeat it so the two cannot drift): `B4_median`, `B8_median` from
  `s2_composite`; `canopy_height`, `canopy_height_std` from
  `structure_features`; `ndvi_amplitude_annual` from `optical_features`;
  `vv_minus_vh_median` from `radar_features`. Six bands over ~four independent
  axes — optical colour, vertical structure, canopy roughness, phenology, radar.

  Band names must be unique after `"*"` expansion, since SNIC names its
  per-cluster means `<band>_mean`. Two further checks run at config load: a
  source cannot mix `"*"` with named bands, and an `optical_features` band
  prefixed `ndvi_`/`nirv_` must match `features_optical.index` — otherwise an
  `index: nirv` arm using the default stack would fail with a GEE
  band-not-found error only after the feature stages had already been billed.

  **This list also decides which feature stages run.** `default_stage_names()`
  takes the union of what clustering asks for (via `feature_source`) and what
  segmentation asks for (via `input_bands`), so a config that segments only on
  the embedding does not run the hand-crafted feature stages at all.

### `clustering`

- `k`: number of clusters (default 6).
- `n_training_samples`: pixels sampled for k-means training (default 10000).
- `seed`: random seed (default 42).
- `feature_source`: `handcrafted` (default) or `embedding`. `handcrafted`
  clusters the multi-sensor hand-engineered stack (optical + radar + structure
  + static); `embedding` clusters a single pretrained per-pixel image from the
  `features_embedding` stage (AlphaEarth or Tessera). Everything downstream of
  the raw stack (superpixel means, skew/log-transform, robust scaling, k-means)
  is band-name-agnostic and runs identically for both, so the two arms are
  directly comparable through the metrics stage.
- `skewness_threshold`: bands with `|skew|` above this get log-transformed
  (default 1.0 per DEC-004).

`superpixel_max_size` **no longer exists** and a config still carrying it will
fail to load. It was the `maxSize` argument to `reduceConnectedComponents`,
which does not clamp — it **masks any component larger than it**, deleting those
regions with no error. Hand-set, the shipped configs drifted apart (1024
baseline vs 256 embedding), and the embedding arm silently lost 15 superpixels
totalling 43.9 ha — 3.8% of its segmented area — in a two-arm comparison. It is
now derived as `ceil(merge.max_area_ha × 10000 / analysis_scale_m²) × 1.2`
(1200 px at the defaults) and asserted against the actual labels at stage entry,
so an undersized cap raises instead of deleting stands.

### `merge`

Aggregates SNIC superpixels into stands, between `segmentation` and
`clustering`. Follows Xiong et al. 2024 §2.6: two passes, hard area bounds, and
a two-tier threshold scheme.

- `enabled`: run the merge stage (default `true`).
- `criteria`: mapping of band name to tolerance, **in the band's own physical
  units**. Defaults `{canopy_height: 2.00, canopy_height_std: 0.45,
  ndvi_amplitude_annual: 0.030}` — Xiong's stand height / canopy closure /
  species axes, using the closest analogue available without ALS or a species
  map. Measured from this AOI's own adjacent-superpixel difference distribution
  (1249 superpixels, 3569 adjacent pairs).

  Absolute units are the contract, percentiles are the calibration tool: "merge
  below the 60th percentile of neighbour differences" merges the same fraction
  of pairs whether the forest is uniform or wildly heterogeneous, and a forester
  wants "stands differ by less than 2 m in mean canopy height", not a quantile.
  Xiong reports SH1 = 3 m for the same reason.

  These are per-band marginals and the gate is conjunctive, so they do **not**
  describe the joint admit rate. Do not loosen a threshold to hit a target pass
  rate — pass rate is a diagnostic, not an objective.

  `elevation` is deliberately absent despite being the rank-3 separator (0.52):
  Sanjay Van has ~20 m of total relief and a within-cluster elevation IQR of
  10–12 m, so including it means two structurally identical patches refuse to
  merge over 10 m of altitude. `vv_minus_vh_median` is a supported optional
  fourth criterion, off by default because no paper in the 20-paper survey uses
  radar for stand delineation — add it and report the ablation.
- `relax_factor`: tolerances are multiplied by this in the eliminate pass
  (default 1.75; Xiong's SH2/SH1 is 5/3 = 1.67).
- `min_area_ha` / `max_area_ha`: hard bounds (defaults 1.0 / 10.0). Xiong uses
  20 ha max for plantation, 50 ha for natural forest, 0.5 ha min. Area is a
  first-class term in the merge rule, not a post-filter. `max_area_ha` is also
  what the component-size cap above is derived from, so the pass-2 fallback
  respects it too.
- `min_defined_criteria`: a pass-1 merge needs at least this many criteria
  defined on both sides (default 2). One criterion is too weak a similarity
  test; pairs that fall short drop to pass 2.
- `min_frac_valid`: below this fraction of valid pixels for a band, profiling
  emits null for that band rather than a mean over territory that has none
  (default 0.5).
- `tie_break`: `shared_edge_length` (the only value). Xiong's eliminate-pass
  fallback, and what prevents orphans. Shared edge is counted with
  4-connectivity even though SNIC runs `connectivity: 8` — a diagonal contact
  has zero shared boundary length.
- `max_pass2_iterations`: cap so a pathological AOI logs its stragglers instead
  of looping (default 60).
- `max_superpixels`: fail loudly above this many superpixels (default 50000),
  where the client-side `remap` label list stops being reasonable.

### `normalization`

- `method`: `robust` (default; median/IQR per DEC-003) or `zscore`
  (mean/stddev, the notebook approach, kept for comparison configs).

### `features`

High-level on/off toggles. Currently informational. All four are read
by the stage code but with `true` defaults rarely changed:

- `optical_harmonic`, `radar`, `canopy_height`, `terrain`

### `export`

- `export_geotiff`: submit the raster Drive tasks — the cluster-label map
  plus the raw and scaled feature rasters (default `true`).
- `export_gee_asset`: reserved for future use; cache layer already
  exports to GEE assets.
- `analysis_scale_m`: pixel size in meters for the GeoTIFF export
  (default 10).
- `drive_folder`: folder under My Drive where all Drive exports land
  (default `"fmu_exports"`). Was a hardcoded class constant on
  ExportStage pre-v1.1.0.
- `export_vector_snic`: bool (default `true`). Emit the `stands_snic`
  vector layer (one polygon per SNIC superpixel).
- `export_vector_dissolved`: bool (default `true`). Emit the
  `stands_dissolved` vector layer (one polygon per connected
  same-cluster region, the forester-facing layer).
- `vector_formats`: list of formats to export each vector layer in
  (default `["shp", "geojson"]`; allowed values: `shp`, `geojson`;
  rejects duplicates and unknown values). One Drive task per layer per
  format, so the default settings can submit up to 7 Drive tasks total
  (3 rasters + 2 layers × 2 formats).
- `vector_min_stand_pixels`: int 1-1000 (default 4). Minimum pixel
  count for a `stands_dissolved` polygon to survive filtering. SNIC
  layer is unfiltered because SNIC enforces its own minimum via
  `segmentation.size`.

### `metrics`

- `reference_config_name`: another config's `name`, or `null` for
  baseline (intrinsic silhouette only).
- `n_comparison_samples`: paired pixels for ARI/NMI (default 10,000).
- `n_silhouette_samples_per_cluster`: stratified sample for silhouette
  (default 833, ~5000 total at k=6).

## Schema validation

Every config is validated at load time. Common errors:

```
ValidationError: extra fields not permitted (clustring)
```
Typo in a field name. `clustering` is misspelled.

```
ValidationError: clustering.k -> ensure this value is greater than 1
```
Invalid value. `k=1` is meaningless for clustering.

```
ValidationError: roi.roi_file -> file does not exist
```
The path is wrong, or you're running from a different cwd than where
the YAML expects.

```
ValidationError: dates.phenology -> end must be after start
```
Date validators enforce ordering.

Look for the field name in the error; the error message points exactly
at the wrong key.
