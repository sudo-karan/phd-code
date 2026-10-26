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
features_optical: { index, harmonic_mode, include_trend, time_reference, mean_over_window }
features_radar: { percentiles, include_iqr, include_cross_pol_contrast }
features_structure: { include_neighborhood_stats, neighborhood_kernel_size }
features_static: { include_climate, max_water_distance_pixels, cap_distance_to_water }
features_embedding: { collapse_reducer, band_names }
segmentation: { size, compactness, connectivity, neighborhood_size, normalize_inputs, normalize_distance_scale, input_bands, mask_before_snic, drop_kept_patches_below_min_area }
merge: { enabled, criteria, relax_factor, min_area_ha, max_area_ha, min_defined_criteria, min_frac_valid, tie_break, max_pass2_iterations, max_superpixels, pass2_skip_at_min_area, pass2_soft_ceiling }
clustering: { k, seed, feature_source, skewness_threshold, fit_excludes_stands_below_min_area, fit_outside_earth_engine, log_rule }
normalization: { method }
features: { optical_harmonic, radar, canopy_height, terrain }
export: { export_geotiff, export_gee_asset, analysis_scale_m, drive_folder, export_vector_merged, export_vector_snic, export_vector_dissolved, vector_formats, vector_min_stand_pixels }
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
| `masking` | Habitat class definition (IndiaSAT primary, WorldCover fallback) + water threshold | `masking`; the water threshold also `features_static` |
| `features_*` | Per-feature-stage toggles and parameters | The matching `features_*` stage |
| `segmentation` | SNIC parameters *and its input band stack* | `segmentation`, `pipeline.default_stage_names` |
| `merge` | Stand-aggregation rules and area bounds | `merge`; also derives the `reduceConnectedComponents` cap used by `metrics` (and by `clustering` until round 13) |
| `clustering` | k-means hyperparameters and preprocessing | `clustering` |
| `normalization` | `robust` vs `zscore` scaling | `clustering` |
| `features` | High-level on/off toggles per feature family | Read by nothing: a `false` changes no stage and no per-step key, only the legacy fingerprint (review C20) |
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

**AlphaEarth supplies the feature vector for both steps that see features:**
SNIC draws the boundaries and k-means labels them. So `features_radar` and
`features_static` drop out — nothing in the arm reads them.

`features_optical` and `features_structure` **do** still run, for one reason:
the **merge criteria are held identical across arms** and read `canopy_height` and
`ndvi_amplitude_annual`. "What makes two adjacent
patches one stand" is a fact about forestry, not about the sensor pipeline, and
holding the merge rule constant is what leaves *delineation* as the only thing
differing between the arms — the thesis question. If each arm merged on its own
features, differences in stand geometry would confound "different boundaries"
with "different merge rules", and the thresholds would lose their physical units
along with their meaning.

`default_stage_names()` derives the stage list from the union of what
clustering, segmentation and merge each ask for, so all of this follows from
config rather than a hardcoded branch.

**What is controlled** is everything that is *not* the feature representation:
same AOI, same 2017-2022 window, same SNIC hyperparameters (`size`,
`compactness`, `connectivity`, `neighborhood_size`), same `clustering.k` and
`seed`, same masking, same `export.analysis_scale_m`. `normalize_distance_scale`
is what makes `compactness: 0.5` mean the same thing at 5 bands and at 64.

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

## The `_repro` copies

`configs/<name>_repro.yaml` exists for fourteen configs: `sanjay_van_baseline`,
`sanjay_van_alphaearth`, and `odisha_v120_3ha_<district>`,
`odisha_v120_handcrafted_<district>` and `odisha_alphaearth_<district>` for the
four districts. Each is its original with `name` changed to `<name>_repro` and a
header note; nothing else differs. They are not experiments. A re-run of a
config reads its cached assets back, so it does not test reproducibility; a copy
under a new name has the same cache fingerprint in a fresh asset folder, so
every stage is recomputed. `tests/test_cache_fingerprint.py` pins this: each
copy differs from its original in `name` only, has the same fingerprint, and
resolves to a different asset path. How to run and compare them is in
[running.md](running.md), "Re-running a config from scratch".

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
  limit (~5 MB). The path is read relative to the working directory, so
  run from the repo root (or the run tree's root). Nothing checks the file
  when the config is loaded. The per-step cache keys hash its content, and a
  file they cannot read hashes as nothing, with no warning: from another
  folder every per-step key changes while the legacy fingerprint, which
  hashes the path, does not (the 10 km tile config: masking `s354522a974`
  from the repo root, `s4a47c8b2cc` from `docs/`, fingerprint `5772fb6133`
  from both). A run then stops when it loads the ROI (`FileNotFoundError`),
  or the pass runner reports every upstream asset as missing (exit 3), which
  names the wrong cause (review C40).

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
  water for it to count as permanent water (default 50.0). Defines the
  water of masking's `water_mask` and of the **distance-to-water
  feature**, which `features_static` builds itself over the ROI buffered by
  the transform's reach (round 13, review A1); it does not affect the
  habitat mask.

### `features_optical`

- `index`: `ndvi` or `nirv`.
- `harmonic_mode`: `single` or `dual` (annual only, or annual + semi-annual).
- `include_trend`: add a linear-in-time term to the regression.
- `time_reference`: date (default `2017-01-01`). Reference epoch for the
  time variable `t` in the harmonic regression (`t` = years since this
  date). Moving it leaves the amplitudes and the trend coefficient as they
  are and shifts `phase_*` by the same angle at every pixel. With
  `include_trend` on (every shipped config) it also changes `<index>_mean`
  by trend × the shift in years, a different amount at each pixel: that
  band is the intercept, the trend line's value on this date, not the mean
  over the window. Both reach the clustering, so a different reference
  date **can** change the stand types (review C9 and B13; until round 13
  this entry said it could not). Keep identical across configs you intend
  to compare — the metrics stage relies on this for phases.
- `mean_over_window` (round 14, Task 2.3; review C9, round 13's question 31,
  answered (c)): `false` (default, every run before round 14) leaves
  `<index>_mean` the intercept, the trend line's value on `time_reference`.
  `true` makes it the fitted curve's mean over the dates window
  (`dates.phenology`, its start to the day after its end, as `data_load`
  filters the collection), computed analytically as a weighted sum of the
  regression's coefficients, the same whatever `time_reference` is: for a
  window of a whole number of years it is a + trend × the window's middle. In
  the regression's own unit of time, Earth Engine's average year of 365.2425
  days, the 2017-2022 window is 5.9988 years, so its harmonic terms are not
  quite zero (at most about 2e-4 × the amplitude). Only the mean band changes:
  amplitude, phase, trend and the residual variance are the fit's as before.
  The stage's metadata records the window and the weights. Register entry
  `spec-optical-mean-over-the-window`. Left out of the fingerprint and the
  per-step keys while `false`; `true` moves the features_optical key and those
  after it.

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
- `max_water_distance_pixels`: int 100-10000 (default 1000, 10 km at 10 m
  scale): how far the distance transform looks for water, and off the axes a
  little further (real distances up to 12.3 km in the Odisha box runs). Where it
  finds none, the band holds the transform's fill value, 463,409.5 m at 10 m, not
  a distance, unless `cap_distance_to_water` is on.
- `cap_distance_to_water`: bool (default `false`, the behaviour of every earlier
  run). True caps `distance_to_water` at `max_water_distance_pixels` x
  `export.analysis_scale_m`. Left out of the cache fingerprint while false, so
  existing configs keep their cached assets; a config that sets it to `true`
  gets a new fingerprint, and the reuse tool computes its static features rather
  than copying them (register entry `spec-static-cap-distance-to-water`).

### `features_embedding`

Only read when `clustering.feature_source: embedding`; ignored otherwise. In
embedding mode this single pretrained per-pixel image replaces the four
hand-crafted feature images (optical / radar / structure / static).

- `collapse_reducer`: `mean` (default) or `median`. How an annual embedding
  ImageCollection (AlphaEarth ships one image per year for each tile it covers,
  so a ROI over two tiles reads two a year; review C11) is collapsed, per pixel,
  to a single image over the `dates.phenology` window. `mean` matches the 2017-2022
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
  a 64-band embedding arm than in a 5-band hand-crafted one, and the two are not
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
  `s2_composite`; `canopy_height` from `structure_features`;
  `ndvi_amplitude_annual` from `optical_features`; `vv_minus_vh_median` from
  `radar_features`. Five bands over ~four independent axes — optical colour,
  vertical structure, phenology, radar. `canopy_height_std` was a sixth
  ("canopy roughness") until the Odisha field validation measured it at R²=0.000
  against crown cover; see `docs/datasets.md`.

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
`n_training_samples` **no longer exists** and a config still carrying it will
fail to load. It sampled 10,000 *pixels* — roughly 37 per superpixel — from a
stack that is **constant within a unit**, so it drew each unit's vector once per
pixel and area-weighted every statistic computed from it: skewness, median, IQR,
and the k-means fit itself. A 10 ha stand outweighed a 0.1 ha stand 100 to 1,
which is a property of stand size, not of what a stand is, and nothing in the
output declared it. k-means now fits on one row per unit (~327 stands x ~21
dims), via `stratifiedSample(numPoints=1)`.

"Every unit" is the intent, not a guarantee. Two things still remove one:
a unit outside the habitat mask (correct — it should not be typed as forest),
and `dropNulls=True` removing a unit where some active band has no data. The
second is a **non-random** exclusion: it follows input coverage rather than
forest character, and because `cluster()` masks wherever an input band is
masked, those units are absent from `cluster_labels` too — holes in the map,
not mistyped stands. The stage logs the split and the manifest records it as
`n_training_units`, `n_units_total`, `n_units_in_habitat`,
`n_units_outside_habitat` and `n_units_dropped_null_band`, alongside
`training_unit_key`. In the runs of record `n_units_dropped_null_band` counted
the stands at the ROI's edge with no pixel whose centre is inside the ROI,
which have no row and no polygon, not units with a band gap (review C15;
`docs/outputs.md`). Since round 14 those stands are counted apart, as
`n_units_no_pixel_centre_in_roi`, and `n_units_dropped_null_band` counts the
band gaps only (round 13's question 35). Read the shortfall before reading a silhouette: a cluster
definition rests only on the units that reached the fit. With
`fit_excludes_stands_below_min_area` on (below) there is a third, made on
purpose: the stands below `merge.min_area_ha` are left out of the fit, though
not out of the map, and are counted apart from the other two.

This also retires the "10,000 superpixels" figure that appears in older docs and
decks — that number was always 10,000 pixels.
- `seed`: random seed (default 42).
- `feature_source`: `handcrafted` (default) or `embedding`. `handcrafted`
  clusters the multi-sensor hand-engineered stack (optical + radar + structure
  + static); `embedding` clusters a single pretrained per-pixel image from the
  `features_embedding` stage (AlphaEarth or Tessera). Everything downstream of
  the raw stack (superpixel means, skew/log-transform, robust scaling, k-means)
  is band-name-agnostic and runs identically for both, so the two arms are
  directly comparable through the metrics stage.
- `skewness_threshold`: bands with `|skew|` above this get log-transformed
  (default 1.0 per DEC-004). The sin and cos of a harmonic phase band are not
  tested and never logged (review B13).
- `fit_excludes_stands_below_min_area`: whether the stands the merge leaves
  below `merge.min_area_ha` are rows of the k-means fit. `false` (default, and
  the behaviour of every run made before the setting existed): every stand is a
  row of its own, however small. `true`: the stands the merge marks below the
  minimum (`below_min` in `stand_provenance`, whatever its cause) are left out of
  the k-means training rows, and only out of those. The skewness, the log
  offsets and the scaling still take a row from every stand: the log offset
  comes from the minimum of its sample, and a stand left out of that sample
  could lie further below that minimum than the 0.001 the transform adds, and
  get the log of a negative number. The stands left out stay on the map as
  stands of their own, and the trained clusterer, which is applied to every
  unit, gives each the type of the nearest fitted cluster. How many were left
  out, and their area, is recorded in `clustering_metadata` (`docs/outputs.md`,
  under `export_manifest_<config>.json`, where its keys are listed). It needs
  `merge.enabled`: a config with the merge off and this on fails to load. The
  case it is for is `segmentation.mask_before_snic: true` with the small patches
  kept, where each isolated patch of kept land below the minimum is a stand of
  its own (register entry `spec-clustering-fit-excludes-stands-below-min-area`).
  `true` has not run in batch: `tests/test_clustering_fit_excludes_ee_graph.py`
  checks offline that its requests are valid, and a read-only check on Earth
  Engine saw it leave out the rows intended
  (`docs/reproducibility/fit_excludes_stands_kendujhar.json`, 15 Oct 2026). The default is left out of the cache fingerprint, so
  existing configs keep their cached assets; a config that sets it to `true`
  gets a new fingerprint.
- `fit_outside_earth_engine` (round 14, Task 2.1; reviews A2 and B15): where
  k-means is fitted. `false` (default, and every run before round 14):
  `ee.Clusterer.wekaKMeans` in Earth Engine, one start, which min-max normalises
  each band over its training rows. `true`: the stage reads its table of units
  back from Earth Engine in one request (one row per unit with a habitat pixel
  centre in the ROI and data in every candidate band, the rows its preprocessing
  statistics take), does the declared preprocessing there (the log rule of the
  stage, then median/IQR scaling with exact quartiles), and fits k-means with
  scikit-learn on the rows of the fit: k-means++, 25 starts from `seed`, the start
  with the lowest within-cluster sum of squares kept, on one thread. The stands
  left out of the fit (`fit_excludes_stands_below_min_area`) get the nearest
  centre. Each unit's type is written back to the image by its label (`remap`,
  masked to the habitat mask). `clustering_metadata` then also holds the best
  start's within-cluster sum of squares (`kmeans_wcss`) and how much the 25
  starts agree with each other (`kmeans_starts_ari_median`, `kmeans_starts_ari_min`,
  the adjusted Rand index of every pair of starts; a diagnostic of the
  clustering, not a field score), and the stage writes the table, the rows after
  the preprocessing with each unit's type, and the fit into its run folder
  (`clustering_stand_table.csv`, `clustering_fit_rows.csv`,
  `clustering_kmeans.json`). It needs `normalization.method: robust`. The code is
  `fmu.utils.stand_table`; register entry
  `spec-clustering-kmeans-outside-earth-engine`. While `false` it is left out of
  the cache fingerprint and the per-step keys, so no existing config's assets
  move; `true` moves the clustering and k_elbow keys.
- `log_rule` (round 14, Task 2.2; reviews A3 and B12, round 13's question 8):
  which bands are logged before the scaling, and how. `abs_skew` (default, the
  rule of every run before round 14, DEC-004 as built since round 13): a band
  whose |skew| is above `skewness_threshold` becomes log(x - min + 0.001), min
  over every unit; the sin and cos of a harmonic phase are not skew-tested
  (review B13), aspect's are; each band is then scaled by its own median and
  IQR. `right_skew`: a band whose IQR is 0 (at most 1e-9) is dropped as constant
  first; only a right-skewed band (skew above the threshold) is logged, as
  log1p((x - min) / IQR), with min over every unit, the stands left out of the
  fit included, and IQR the band's own before the log, so the log is defined for
  every unit; a left-skewed band is not transformed; the sin and cos of an angle
  (a harmonic phase, aspect) are never skew-tested or logged, and each such pair
  is centred by its own medians and divided by one shared spread, the root mean
  square of the two IQRs, so the circle is scaled alike along both axes and not
  stretched (a pair is dropped only when that spread is 0); `clustering_metadata`
  records each band's skew before and after the log (`skew_before`,
  `skew_after`), the log's minimum and IQR per band (`log1p_params`) and the
  pairs' shared spreads (`angle_pairs`). The skew is the moment coefficient g1,
  as Earth Engine's `Reducer.skew` computes it. `right_skew` is applied off Earth
  Engine, so it needs `fit_outside_earth_engine: true`. Register entry
  `spec-clustering-log-rule-right-skewed-bands`. Left out of the fingerprint and
  the per-step keys at its default; `right_skew` moves the clustering and k_elbow
  keys.

`superpixel_max_size` **no longer exists** and a config still carrying it will
fail to load. It was the `maxSize` argument to `reduceConnectedComponents`,
which does not clamp — it **masks any component larger than it**, deleting those
regions with no error. Hand-set, the shipped configs drifted apart (1024
baseline vs 256 embedding), and the embedding arm silently lost 15 superpixels
totalling 43.9 ha — 3.8% of its segmented area — in a two-arm comparison. It is
now derived as `ceil(merge.max_area_ha × 10000 / analysis_scale_m²) × 1.2`
(1200 px at the defaults), with `merge.max_area_ha + merge.min_area_ha` in place
of `merge.max_area_ha` when `merge.pass2_soft_ceiling` is on (1320 px at the
defaults), and asserted against the actual labels at stage entry, so an
undersized cap raises instead of deleting stands. Since round 13 the clustering
stage's unit means no longer call `reduceConnectedComponents` (review B14): it
takes one mean per stand label with a grouped reduction, which has no size cap,
so the cap is the metrics stage's alone.

### `merge`

Aggregates SNIC superpixels into stands, between `segmentation` and
`clustering`. Follows Xiong et al. 2024 §2.6: two passes, hard area bounds, and
a two-tier threshold scheme.

- `enabled`: run the merge stage (default `true`).
- `criteria`: mapping of band name to tolerance, **in the band's own physical
  units**. Defaults `{canopy_height: 2.00, ndvi_amplitude_annual: 0.030}`, the
  closest analogues available without ALS or a species map. Xiong's merging rule
  (Eq. 1) has five conditions: the pair's area under the maximum, the same
  dominant species, canopy closure within 0.2, dominant-species proportion
  within TP1 and mean height within SH1; the eliminating rule (Eq. 2) drops
  closure and relaxes TP and SH. FMU has analogues of three: `max_area_ha` for
  the area bound, `canopy_height` for the stand height and
  `ndvi_amplitude_annual` for the species proportion. It has **none for closure
  or for the same species**. Closure was carried by `canopy_height_std` until
  the Odisha field validation measured that band at R²=0.000 against crown
  cover, so the analogue was nominal rather than real. See `docs/datasets.md`.
  Measured from this AOI's own
  adjacent-superpixel difference distribution (1249 superpixels, 3569 adjacent
  pairs, in the run the tolerances were set on). Demo set, 13 Oct 2026: 1,298
  superpixels and 3,615 adjacent pairs; `canopy_height` differences have a
  median of 1.85 m and a 75th percentile of 3.27 m, `ndvi_amplitude_annual`
  0.017 and 0.031, so the two tolerances sit at the 53rd and 74th percentiles.
  The tolerances were not changed. The demo set carries the open cache-grid
  issue (`docs/reproducibility.md`, "Superpixels depend on whether the features
  were cached when SNIC ran").

  Note that with two criteria and `min_defined_criteria: 2` the gate is **fully
  conjunctive**: both must be defined for a pair, where with three one could be
  missing and the pair still qualified.

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
  respects it too. The one exception is `pass2_soft_ceiling`, below, and the cap
  then allows for it.
- `min_defined_criteria`: a merge needs at least this many criteria defined on
  both sides (default 2), in pass 1 and under pass 2's relaxed tolerances
  alike. One criterion is too weak a similarity test. A pair that falls short
  never merges on its attributes: a region below `min_area_ha` can still join
  such a neighbour by the shared-edge fallback, which ignores attributes, and
  two regions both at or above the minimum do not merge. (Corrected 20 Oct
  2026, review C13: this said that pairs that fall short drop to pass 2.)
- `min_frac_valid`: below this fraction of valid pixels for a band, profiling
  emits null for that band rather than a mean over territory that has none
  (default 0.5).
- `tie_break`: `shared_edge_length` (the only value): the second pass's
  fallback when no neighbour passes the relaxed tolerances, and what prevents
  orphans. Xiong's eliminating rule (Eq. 2) ends on the longest common side
  too, but takes its conditions one at a time, where the second pass here
  applies the relaxed tolerances at once and takes the closest neighbour that
  passes; that order of choice is this pipeline's own (the module docstring of
  `src/fmu/utils/region_merge.py`; corrected 20 Oct 2026, review C62, from
  "Xiong's eliminate-pass fallback"). Shared edge is counted with
  4-connectivity even though SNIC runs `connectivity: 8` — a diagonal contact
  has zero shared boundary length.
- `max_pass2_iterations`: cap so a pathological AOI logs its stragglers instead
  of looping (default 60).
- `pass2_skip_at_min_area`: what pass 2 does with a region that was undersized
  when the sweep listed it and has reached `min_area_ha` by the time its turn
  comes. `false` (default, and the behaviour of every run made before the
  setting existed): it can be merged once more. `true`: it is skipped, since it
  is no longer undersized (register entry `spec-merge-pass2-skip-at-minimum`).
  The default is left out of the cache fingerprint, so existing configs keep
  their cached assets; a config that sets it to `true` gets a new fingerprint.
- `pass2_soft_ceiling`: whether pass 2 may take a region over `max_area_ha`.
  `false` (default, and the behaviour of every run made before the setting
  existed): `max_area_ha` binds in both passes, and a region below the minimum
  whose neighbours are all close to `max_area_ha` stays below the minimum,
  area-blocked.
  `true`: a region whose area is still below `min_area_ha` when its turn comes
  may join a neighbour even if the result is over `max_area_ha`, but never over
  `max_area_ha + min_area_ha`. It takes, in this order: (1) a neighbour that
  passes the relaxed tolerances and keeps the result at most `max_area_ha`, the
  closest; (2) one that passes them with the result over `max_area_ha`, the
  closest; (3) the neighbour sharing the longest edge with the result at most
  `max_area_ha`; (4) the one sharing the longest edge with the result over it.
  Pass 1, and a region that has reached the minimum by its turn, keep
  `max_area_ha`. A stand still below the minimum is then area-blocked only if no
  neighbour could take it under `max_area_ha + min_area_ha`. The merge
  diagnostics add how many merges went over `max_area_ha` and how many stands
  end over it, by how much (`docs/outputs.md`), and the component-size cap is
  derived from `max_area_ha + min_area_ha` (register entry
  `spec-merge-pass2-soft-ceiling`). The default is left out of the cache
  fingerprint, so existing configs keep their cached assets; a config that sets
  it to `true` gets a new fingerprint.
- `max_superpixels`: fail loudly above this many superpixels (default 50000),
  where the client-side `remap` label list stops being reasonable.

### `normalization`

- `method`: `robust` (default; median/IQR per DEC-003) or `zscore`
  (mean/stddev, the notebook approach, kept for comparison configs).

### `features`

High-level on/off toggles, read by nothing. No stage, script or test reads
`Config.features` except the test of its defaults (`tests/test_config.py`).
Which feature stages run is set by `clustering.feature_source`,
`segmentation.input_bands` and `merge.criteria`. A `false` loads without a
warning and changes no stage and no per-step cache key; it moves only the
legacy fingerprint, which hashes the block (all four `false` on the 10 km tile
config: `5772fb6133` becomes `7a438bf989`, every per-step key the same). Every
config that sets them sets all four `true`. Until round 13 this section said
all four are read by the stage code (review C20). Removing the block would move
every legacy fingerprint, the 14 pinned `_repro` ones among them.

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
- `export_vector_merged`: bool (default `true`). Emit the `stands_merged`
  layer: one polygon per merged stand, the pipeline's primary deliverable.
  Written only when `merge.enabled` — without merge the stand *is* the
  superpixel and `stands_snic` already is that layer, so the stage logs a
  skip instead of writing a duplicate.
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

A missing or unreadable `roi.roi_file` is **not** caught when the config is
loaded: nothing checks it then (review C40; until round 13 this section showed
a `ValidationError: roi.roi_file -> file does not exist` that no code raises).
It shows up when a run loads the ROI (`FileNotFoundError: ROI file not found:
...`), or, from the wrong working directory, as every upstream asset reported
missing by the pass runner (exit 3), because the per-step keys then hash no
ROI file (see `roi_file` above).

```
ValidationError: dates.phenology -> end must be after start
```
Date validators enforce ordering.

Look for the field name in the error; the error message points exactly
at the wrong key.
