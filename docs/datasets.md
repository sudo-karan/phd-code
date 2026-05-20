# Datasets

Every external data source the pipeline pulls from Google Earth Engine,
what it's used for, and why it was chosen over alternatives. All dataset
IDs live in `configs/<config>.yaml` under `datasets:`. They're config
knobs, not hardcoded, so an AOI in a different region can swap them out
without code changes.

## Quick reference

| Dataset | GEE ID | Used by | Resolution | Window |
|---|---|---|---|---|
| Sentinel-2 SR Harmonized | `COPERNICUS/S2_SR_HARMONIZED` | data_load, features_optical, segmentation | 10 m | 2017-2024 phenology, 2023 composite |
| Sentinel-1 GRD | `COPERNICUS/S1_GRD` | data_load, features_radar, segmentation | 10 m | 2017-2021 |
| ETH Global Canopy Height 2020 | `users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1` | features_structure, segmentation | 10 m | static (2020 snapshot) |
| NASADEM HGT v001 | `NASA/NASADEM_HGT/001` | features_static | 30 m | static |
| ESA WorldCover v200 | `ESA/WorldCover/v200` | masking | 10 m | 2021 |
| JRC Global Surface Water v1.4 | `JRC/GSW1_4/GlobalSurfaceWater` | masking, features_static | 30 m | 1984-2021 |
| Google Open Buildings v3 | `GOOGLE/Research/open-buildings/v3/polygons` | masking | vector, rasterized at 10 m | static |
| VIIRS Day/Night Band Monthly | `NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG` | masking | 463 m | most recent month |
| CHIRPS Pentad | `UCSB-CHG/CHIRPS/PENTAD` | features_static | 5,500 m | 1991-2020 climatology |

---

## Sentinel-2 SR Harmonized

`COPERNICUS/S2_SR_HARMONIZED`. Bottom-of-atmosphere surface reflectance,
harmonized across S2A/S2B to handle the 2022 processing baseline change.

- **Bands used:** `B4` (red), `B8` (NIR), `SCL` (scene classification)
- **Cloud masking:** SCL classes `[3, 8, 9, 10]` dropped (cloud shadow,
  cloud medium prob, cloud high prob, thin cirrus). Per-image
  `CLOUDY_PIXEL_PERCENTAGE` filter caps scene-level cloud at 20%.
- **Two separate windows on the same collection:**
  - **phenology** (long, 8y): `dates.phenology`. Used for harmonic regression
    in `features_optical`. Long window lets year-to-year anomalies average
    out when fitting the smooth seasonal cycle.
  - **optical_composite** (1y): `dates.optical_composite`. Used to build a
    single static median composite that SNIC sees in `segmentation`.
    Different problem from phenology (clean snapshot, not a time series).

**Why S2_SR_HARMONIZED over Landsat or HLS:** 10 m resolution captures
within-stand variation that 30 m can't. Harmonized variant avoids the
S2 baseline-change gotcha. HLS migration is a future variant config
(DEC-006 in `phd-notebook/decisions.md`).

## Sentinel-1 GRD

`COPERNICUS/S1_GRD`. Ground Range Detected, already in dB. C-band
SAR, sensitive to surface roughness, moisture, and biomass.

- **Bands used:** `VV`, `VH`
- **Filters:** instrument mode `IW`, single orbit direction (default `ASCENDING`)
- **Window:** 2017-01-01 to 2021-12-01. Hard cap at Dec 2021 because S1B
  failed in Dec 2021. From 2022 through Dec 2024 only S1A operated,
  halving revisit from 6 days to 12. Capping at 2021 keeps per-month
  image counts consistent across the analysis. S1C launched Dec 2024,
  S1D Nov 2025; full constellation will be available again from 2025.

**Why no speckle filter:** temporal median over 100+ S1 images reduces
variance much more than any 3x3 / 5x5 spatial filter could
(~sqrt(N) reduction), and spatial filters blur edges that SNIC needs.
Detailed reasoning in [design_notes.md](design_notes.md#features_radar-no-harmonic-no-speckle-filter).

**Why VV - VH in dB, not VV / VH:** dB is a log-scale quantity;
dividing dB values isn't physically meaningful. `VV - VH (dB) =
10*log10(VV_linear / VH_linear)`. The difference IS the log of the
linear-scale ratio. See DEC-016.

## ETH Global Canopy Height 2020

`users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1`. Global per-pixel
canopy height in meters, derived from GEDI L4A waveforms + S2 spectral
features via a CNN (Lang et al., 2023).

- **Why this over raw GEDI L2A:** GEDI is a sparse-sampling lidar (only
  the tracks the satellite flew over have measurements). The ETH product
  fills the gaps using S2 spectral information, giving us a continuous
  10 m raster instead of points-and-gaps. See DEC-009.
- **Used directly in segmentation** (one of the 5 SNIC input bands).
  Structural information, independent of S2/S1 spectral data.
- **Used with neighborhood stats in features_structure:** std-dev and max
  in a 3x3 window capture local heterogeneity. A mature even-aged stand
  has low std-dev; a regenerating patch or forest edge has high.

## NASADEM HGT

`NASA/NASADEM_HGT/001`. Reprocessed SRTM, 30 m global elevation in
meters.

- **Derived bands via `ee.Terrain.products()`:** `elevation`, `slope`
  (degrees), `aspect` (degrees 0-360).
- **Aspect is cyclic.** It's emitted as raw degrees in `features_static`;
  the clustering stage converts to `aspect_sin` / `aspect_cos`
  before k-means. Euclidean distance on raw degrees would treat 0 and
  359 as maximally different despite being identical compass directions.

## ESA WorldCover v200

`ESA/WorldCover/v200`. 11-class global landcover at 10 m, derived
from S2 + S1.

- **Used in masking** for two things:
  - Vegetation keep-list (default classes `[10, 20, 30]`, trees/shrubs/grass)
    contributes to `habitat_mask`.
  - Class 80 (permanent water) is a redundant water source layered with JRC.
- **Why accept the moderate circularity** (WorldCover is S2-derived,
  and we'll later feed S2 features to clustering): the signal WorldCover
  extracts is categorical (land-cover class), qualitatively different
  from the continuous phenology features in `features_optical`.
  Replacing it would cost more (lose 10 m, lose convenient classes) than
  the residual bias costs. See [design_notes.md](design_notes.md#masking-avoiding-circularity-with-the-feature-data).

## JRC Global Surface Water

`JRC/GSW1_4/GlobalSurfaceWater`. Landsat-derived monthly water
observations 1984-2021. Per-pixel band `occurrence` (0-100%) is what we
use.

- **In masking:** `occurrence >= jrc_water_occurrence_threshold` (default
  50%) means permanent water, which is excluded from `habitat_mask`.
- **In features_static:** `water_mask` from masking is reused as the
  source for `distance_to_water`. `fastDistanceTransform` returns
  squared-euclidean distance in pixels; we sqrt and multiply by scale
  to get meters. Capped at `max_water_distance_pixels * analysis_scale_m`
  (default 10 km).

**Why JRC over WorldCover class 80:** different sensor (Landsat vs S2),
longer baseline (1984 vs 2021 single year), and a confidence dimension
(`occurrence` is continuous, not binary). Combined with WorldCover class
80 for redundancy.

## Google Open Buildings v3

`GOOGLE/Research/open-buildings/v3/polygons`. Vector building
footprints derived from commercial high-resolution imagery (NOT
Sentinel/Landsat). Each polygon has a `confidence` score 0-1.

- **Used in masking** for the built-up exclusion: filter by
  `open_buildings_confidence` (default 0.7), rasterize at 10 m, add to
  `built_mask`.
- **Critical for the no-circularity property.** Built-up exclusion is
  what separates urban from vegetation, and the features we'll cluster
  on are S2-derived. Using an S2-derived built-up mask would let the
  mask's errors propagate directly into the clustering result. Open
  Buildings + VIIRS are both independent of S2.

**Known issue:** rasterizing all building polygons over a large AOI hits
GEE's per-tile memory limit at high zoom levels in the Code Editor. The
caching layer fixes this: once the masking outputs are exported to
assets, visualization reads the static raster instead of recomputing live.

## VIIRS Day/Night Band Monthly

`NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG`. 463 m monthly composite of
nighttime light radiance.

- **Used in masking:** `radiance >= nightlights_threshold` (default 30,
  Delhi-calibrated; won't generalize to other regions without recalibration)
  contributes to `built_mask`.
- **Why combine with Open Buildings:** different failure modes. Open
  Buildings can miss recent / informal construction (poly confidence too
  low); VIIRS misses dark / low-electrification settlements but catches
  bright urban cores at coarse resolution. Combining them recovers from
  each one's weaknesses.

**This threshold needs region-specific calibration.** For non-Delhi
AOIs, sample VIIRS over known built-up and known rural pixels and
choose a threshold that separates them.

## CHIRPS Pentad

`UCSB-CHG/CHIRPS/PENTAD`. 5-day rainfall totals at ~5,500 m,
1981-present. Combines satellite estimates with station data.

- **Used in features_static** as `annual_rainfall`: sum over the 30-year
  standard climatology window (1991-01-01 to 2020-12-31), divide by 30,
  unit = mm/year.
- **Coarse resolution caveat:** for an AOI smaller than ~5 km, the
  CHIRPS band will be nearly constant. It's kept in the static features
  for cross-AOI generality. When an AOI spans climate gradients
  (e.g., elevation transects, monsoon margins), rainfall is informative.
  The clustering stage drops it automatically if IQR <= 1e-9 (zero
  spread, uninformative, dropped via DEC-004).

---

## Swapping a dataset

All dataset IDs are config knobs:

```yaml
datasets:
  phenology_collection: COPERNICUS/S2_SR_HARMONIZED   # change this
  optical_composite_collection: COPERNICUS/S2_SR_HARMONIZED
  radar_collection: COPERNICUS/S1_GRD
  canopy_height: users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1
  dem: NASA/NASADEM_HGT/001
  worldcover: ESA/WorldCover/v200
  water: JRC/GSW1_4/GlobalSurfaceWater
  nightlights: NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG
  open_buildings: GOOGLE/Research/open-buildings/v3/polygons
  climate: UCSB-CHG/CHIRPS/PENTAD
```

To swap a dataset:
1. Find the new dataset's GEE ID (Earth Engine Data Catalog).
2. Check that band names match what the consuming stage expects. If they
   don't, edit the stage. For example, features_optical hardcodes
   `B4`/`B8` for S2; using Landsat would need `SR_B4`/`SR_B5`.
3. Verify the time window in `dates.*` is covered by the new dataset.
4. Run the relevant `inspect_*.py` script to confirm the stage still
   produces sensible output.

Most stage code reads band names from the config, but some bands
(SCL, B4, B8, VV, VH) are referenced by name. For non-trivial swaps,
read the stage source. Most stages are under 300 lines.

## Adding a new dataset

If a new feature wants a dataset not yet on the list:

1. Add an entry to the `datasets:` block in your config YAML.
2. Add the field to `DatasetsConfig` in `src/fmu/config.py`. Pydantic
   will reject any field not declared because `extra="forbid"`.
3. Read it in the consuming stage via `ee.ImageCollection(config.datasets.<key>)`
   or `ee.Image(...)` as appropriate.
4. Document it here.

---

## Region-specific calibration notes

The defaults in `sanjay_van_baseline.yaml` are tuned for Sanjay Van,
Delhi. Before running on a different AOI, review:

- `masking.nightlights_threshold` (30.0 is Delhi-calibrated)
- `masking.keep_worldcover_classes` (default = [10, 20, 30]; tropical
  AOIs may want to also include 40 if cropland is part of "habitat")
- `dates.radar` end (2021-12-01 caps at S1B end-of-life; if you only
  need post-2024 data, the constraint can be relaxed)
- `dates.climate` (30-year standard climatology is generally fine)
- `features_static.max_water_distance_pixels` (default 1000 = 10 km;
  for AOIs near coasts or large rivers, may need larger)
