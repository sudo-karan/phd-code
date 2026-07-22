# Datasets

Every external data source the pipeline pulls from Google Earth Engine,
what it's used for, and why it was chosen over alternatives. All dataset
IDs live in `configs/<config>.yaml` under `datasets:`. They're config
knobs, not hardcoded, so an AOI in a different region can swap them out
without code changes.

## Quick reference

| Dataset | GEE ID | Used by | Resolution | Window |
|---|---|---|---|---|
| Sentinel-2 SR Harmonized | `COPERNICUS/S2_SR_HARMONIZED` | data_load, features_optical, segmentation | 10 m | 2017-2022 (phenology + composite) |
| Sentinel-1 GRD | `COPERNICUS/S1_GRD` | data_load, features_radar, segmentation | 10 m | 2017-2022 |
| ETH Global Canopy Height 2020 | `users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1` | features_structure, segmentation | 10 m | static (2020 snapshot) |
| NASADEM HGT v001 | `NASA/NASADEM_HGT/001` | features_static | 30 m | static |
| CoRE Stack LULC (IndiaSAT) | `projects/corestack-trees/assets/LULC_v4` (folder of per-year images) | masking (primary habitat) | 30 m | 2017-2022 hydrological years |
| ESA WorldCover v200 | `ESA/WorldCover/v200` | masking (habitat fallback) | 10 m | 2021 |
| JRC Global Surface Water v1.4 | `JRC/GSW1_4/GlobalSurfaceWater` | masking (distance-to-water only), features_static | 30 m | 1984-2021 |
| CHIRPS Pentad | `UCSB-CHG/CHIRPS/PENTAD` | features_static | 5,500 m | 1991-2020 climatology |
| AlphaEarth Satellite Embedding | `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL` | features_embedding (embedding mode only) | 10 m | annual from 2017, collapsed over 2017-2022 |
| Tessera | `projects/<proj>/assets/tessera_…` (user upload, off-GEE via geotessera) | features_embedding (embedding mode only) | 10 m | 2017-2022 (uploaded) |

---

## Sentinel-2 SR Harmonized

`COPERNICUS/S2_SR_HARMONIZED`. Bottom-of-atmosphere surface reflectance,
harmonized across S2A/S2B to handle the 2022 processing baseline change.

- **Bands used:** `B4` (red), `B8` (NIR), `SCL` (scene classification)
- **Cloud masking:** SCL classes `[3, 8, 9, 10]` dropped (cloud shadow,
  cloud medium prob, cloud high prob, thin cirrus). Per-image
  `CLOUDY_PIXEL_PERCENTAGE` filter caps scene-level cloud at 20%.
- **Two uses of the same 6-year window (2017-2022):**
  - **phenology**: `dates.phenology`. Used for harmonic regression
    in `features_optical`. The 6-year window lets year-to-year anomalies average
    out when fitting the smooth seasonal cycle.
  - **optical_composite**: `dates.optical_composite`. Used to build a
    single static median composite that SNIC sees in `segmentation`.
    Different reduction from phenology (clean median snapshot, not a time
    series), computed over the same window.

**Why S2_SR_HARMONIZED over Landsat or HLS:** 10 m resolution captures
within-stand variation that 30 m can't. Harmonized variant avoids the
S2 baseline-change gotcha. HLS migration is a future variant config
(DEC-006 in `phd-notebook/decisions.md`).

## Sentinel-1 GRD

`COPERNICUS/S1_GRD`. Ground Range Detected, already in dB. C-band
SAR, sensitive to surface roughness, moisture, and biomass.

- **Bands used:** `VV`, `VH`
- **Filters:** instrument mode `IW`, single orbit direction (default `ASCENDING`)
- **Window:** 2017-01-01 to 2022-12-31. Shares the unified 6-year
  time-series window with the S2 phenology and composite; radar,
  phenology, and the SNIC composite all cover 2017-2022.

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

## CoRE Stack LULC (IndiaSAT)

`projects/corestack-trees/assets/LULC_v4`. A purpose-built Indian land-use /
land-cover product (CoRE Stack, lineage from IndiaSAT / Bansal et al. 2021):
30 m annual maps, one class label per pixel per year. The asset is a **folder
of per-year single-band images** (`lulc_v4_2017_2018` … `lulc_v4_2023_2024`,
class band `predicted_label`), not an ImageCollection, and the images carry no
`system:time_start`. `masking.py` builds the annual collection from them —
selecting the class band, keeping the configured hydrological-year window
(`masking.indiasat_year_min/max`, default start-years 2017-2021 = the deck's
"2017-2022 hydrological years"), and stamping each image with a timestamp
parsed from its asset-id year so the recency tie-break can sort by year.

> The original `projects/ee-indiasat/assets/LULC CombinedOutputs WithConfidence`
> is the same product but is private; `corestack-trees/LULC_v4` is the mirror
> readable by CoRE Stack accounts. Same legend, incl. `13` = Orchard/Plantation.

- **Primary habitat source in masking.** Classes `6` (Trees) and `12`
  (Shrubs/Scrubs), from `masking.indiasat_habitat_classes`, are kept as
  `habitat_mask`. The stage decides habitat per pixel by a **majority vote
  over the usable (non-masked) years** — habitat if more usable years were
  Trees/Shrubs than not — so a one-off yearly misclassification can't flip
  a pixel. A **tie** (equal habitat and non-habitat years) is broken by the
  **most recent usable year** (sorted by the year in each asset id, since the
  images carry no `system:time_start`), cascading to the next-latest where the
  newest year is no-data.
- **Single-phase exclusion.** Water, cropland, and built-up are dropped
  simply by *not* being in the habitat class set; there is no separate
  water or built-up subtraction. See
  [design_notes.md](design_notes.md#masking-indiasat-primary-single-phase-habitat).
- **Why IndiaSAT as primary over WorldCover:** it's an India-specific
  LULC with a class scheme built for Indian landscapes, and its
  Trees/Shrubs classes give a direct habitat definition. WorldCover is
  kept only as a fallback for coverage gaps.

## ESA WorldCover v200

`ESA/WorldCover/v200`. 11-class global landcover at 10 m, derived
from S2 + S1.

- **Habitat fallback only.** Where IndiaSAT has no data, the WorldCover
  keep-list (default classes `[10, 20, 30]` = tree cover / shrubland /
  grassland, from `masking.keep_worldcover_classes`) supplies the
  habitat value. IndiaSAT covers all of India, so this is a safety net
  for coverage gaps or AOIs outside its footprint. It is no longer the
  primary vegetation source, and no WorldCover class contributes to the
  water mask.

## JRC Global Surface Water

`JRC/GSW1_4/GlobalSurfaceWater`. Landsat-derived monthly water
observations 1984-2021. Per-pixel band `occurrence` (0-100%) is what we
use.

- **In masking:** builds `water_mask` only
  (`occurrence >= jrc_water_occurrence_threshold`, default 50%, = permanent
  water). This mask is **not** used for habitat exclusion — habitat comes
  from the IndiaSAT classes alone. `water_mask` exists solely to feed the
  downstream distance-to-water feature.
- **In features_static:** `water_mask` from masking is reused as the
  source for `distance_to_water`. `fastDistanceTransform` returns
  squared-euclidean distance in pixels; we sqrt and multiply by scale
  to get meters. Capped at `max_water_distance_pixels * analysis_scale_m`
  (default 10 km).

**Why JRC for the water layer:** a different sensor from S2 (Landsat), a
long baseline (1984-2021), and a confidence dimension (`occurrence` is
continuous, not binary), which makes it the right source for a
distance-to-water feature.

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

## AlphaEarth Satellite Embedding

`GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL`. A pretrained per-pixel embedding:
a 64-band annual ImageCollection (one image per year from 2017, bands
`A00`..`A63`) at 10 m, learned from multi-sensor satellite time series.

- **Embedding mode only.** Read solely by `features_embedding`, which
  runs only when `clustering.feature_source: embedding`. In the default
  hand-crafted arm this dataset is never touched.
- **Collapsed to one image over the feature window.** The annual images
  are filtered to `dates.phenology` (2017-2022) and reduced to a single
  embedding image by `features_embedding.collapse_reducer` (default
  `mean`; `median` available), matching the 2017-2022 averaging the
  hand-crafted features rest on.
- **All 64 bands by default.** `features_embedding.band_names: null`
  keeps every embedding dimension; the dimensions are jointly meaningful,
  so restricting to a subset is rarely useful.

**Why an embedding arm:** it swaps the four hand-crafted feature images
for a single pretrained embedding with segmentation held fixed, so the
metrics stage attributes any difference to the feature representation
alone. Google's own dataset guidance recommends grouping these embeddings
with unsupervised clustering — exactly what the clustering stage does.
Used by `configs/sanjay_van_alphaearth.yaml`.

## Tessera

An uploaded user Earth Engine Image. Tessera is a 128-channel, 10 m
pretrained embedding distributed CC0 through the `geotessera` library,
but it lives **off** Earth Engine — so it must be ingested to an EE asset
before the pipeline can read it. Its GEE ID is therefore whatever asset id
you upload to (placeholder `projects/REPLACE_ME/assets/tessera_sanjay_van_2017_2022`
in `configs/sanjay_van_tessera.yaml` until upload).

- **Embedding mode only.** Like AlphaEarth, read solely by
  `features_embedding` when `clustering.feature_source: embedding`.
- **Ingest once with `scripts/prep_tessera.py`.** The one-shot fetches
  the ROI's Tessera tiles via geotessera, mosaics them to a GeoTIFF
  (optionally averaging several years to match AlphaEarth's 2017-2022
  mean), and uploads the result to an EE asset. Paste the printed asset
  id into `datasets.embedding` in `configs/sanjay_van_tessera.yaml`.
  `geotessera` is the optional `tessera` extra and needs Python 3.12+.
- **Loaded as-is (single Image).** The stage sniffs the asset type; a
  single Image is used without any annual collapse, so `collapse_reducer`
  is ignored. `band_names: null` keeps all 128 dimensions.

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
  indiasat: "projects/corestack-trees/assets/LULC_v4"   # folder of per-year images
  worldcover: ESA/WorldCover/v200
  water: JRC/GSW1_4/GlobalSurfaceWater
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

- `masking.indiasat_habitat_classes` (default = [6, 12] = Trees,
  Shrubs/Scrubs; add classes if your habitat definition is broader)
- `masking.keep_worldcover_classes` (fallback only, default = [10, 20,
  30]; tropical AOIs may want to also include 40 if cropland is part of
  "habitat")
- `dates.radar` (2017-2022; shares the unified time-series window with
  phenology and the composite)
- `dates.climate` (30-year standard climatology is generally fine)
- `features_static.max_water_distance_pixels` (default 1000 = 10 km;
  for AOIs near coasts or large rivers, may need larger)
