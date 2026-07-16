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
segmentation: { size, compactness, connectivity, neighborhood_size, normalize_inputs }
clustering: { k, n_training_samples, seed, skewness_threshold, superpixel_max_size }
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
| `segmentation` | SNIC parameters | `segmentation` |
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

### `segmentation`

- `size`: SNIC seed spacing in pixels (default 10, ~100 m on 10 m grid).
- `compactness`: 0 = boundaries follow image edges, high = circular
  blobs (default 0.5).
- `connectivity`: 4 or 8 (default 8).
- `neighborhood_size`: SNIC search window (default 128).
- `normalize_inputs`: z-score per band before SNIC (default `true`).

### `clustering`

- `k`: number of clusters (default 6).
- `n_training_samples`: pixels sampled for k-means training (default 10000).
- `seed`: random seed (default 42).
- `skewness_threshold`: bands with `|skew|` above this get log-transformed
  (default 1.0 per DEC-004).
- `superpixel_max_size`: max pixels per SNIC superpixel; must exceed the
  largest superpixel in the image (default 1024).

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
