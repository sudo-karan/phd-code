# current_flow.md

What the pipeline does, in order, and where each piece lives in the code.

This file is the lookup index: "I want to find where X happens." For *why* we made a choice, see `docs/design_notes.md`. For locked decisions, see `decisions.md` in the phd-notebook repo.

**Update this whenever a new stage lands.** Stale flow docs are worse than no flow docs.

## Testing policy

- **GEE stages** (masking, data_load, feature stages, etc.) have **live tests only** — `tests/test_<stage>_live.py`. Run them locally with `pytest -m live_gee` before locking a module. These tests need `earthengine authenticate` to be set up.
- **Pure-Python infrastructure** (config, settings, pipeline, base, utils) has mocked unit tests that run in CI on every push.
- CI (GitHub Actions) runs only the fast/mocked tier. **CI passing ≠ GEE stages working.** You have to run live tests locally.

See ENG-014 and ENG-018 in `decisions.md` for the rationale.

---

## Pipeline flow (current state)

The pipeline runs a sequence of stages, each producing context keys consumed by later stages. Asset caching (Module 6 in build order) is **cross-cutting** — it doesn't have its own runtime step; it wraps every stage's read/write to GEE.

```
[ROI loaded into context]
        ↓
1. masking          → habitat_mask, water_mask, landcover_summary    [cached]
        ↓
2. data_load        → roi, s2_collection, s1_collection, s2_composite [cached]
        ↓
3. features_optical → optical_features                                [cached]
4. features_radar   → radar_features                                  [cached]
5. features_structure → structure_features                            [cached]
6. features_static  → static_features                                 [cached]
        ↓
7. segmentation     → snic_clusters                                   [cached]
        ↓
8. clustering       → cluster_labels                                  [cached]
        ↓
9. profiling        → cluster_stats
        ↓
10. export          → final GeoTIFF, GEE asset, manifest
```

The orchestrator (`fmu.pipeline.Pipeline`) walks the stages, validates the context against each stage's declared inputs, and merges outputs back in. With Module 6 in place, the orchestrator also checks the asset cache before running each stage. See ENG-013 (orchestrator) and the asset-caching ENG entry (TBD) in decisions.md.

---

## Stage details

### 1. masking — `src/fmu/stages/masking.py`

Builds the habitat mask, water mask, and labeled landcover summary. Multi-source masking: WorldCover for vegetation, JRC GSW + WorldCover class 80 for water, Google Open Buildings + VIIRS for built-up. Three-phase masking structure (DEC-006): static habitat layer first, time-series data comes later.

**Reads from context:** `roi`
**Writes to context:** `habitat_mask`, `water_mask`, `landcover_summary`

**Datasets:**
- ESA WorldCover v200 (`ESA/WorldCover/v200`) — vegetation classification
- JRC Global Surface Water 1.4 (`JRC/GSW1_4/GlobalSurfaceWater`) — permanent water from occurrence
- Google Open Buildings v3 (`GOOGLE/Research/open-buildings/v3/polygons`) — building polygons, rasterized for the built mask
- VIIRS Nightlights monthly (`NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG`) — broad urban / bright-light areas

**Logic:**
- `veg` = WorldCover class ∈ keep list
- `water_mask` = (JRC occurrence ≥ threshold) OR (WorldCover == 80)
- `built_mask` = (Open Buildings polygons rasterized) OR (VIIRS ≥ threshold)
- `habitat_mask` = `veg` AND NOT `water_mask` AND NOT `built_mask`
- `landcover_summary` = labeled image: 10/20/30 for veg, 50 for built, 80 for water, 0 for other

**Config knobs** (in `configs/*.yaml` under `masking:`):
- `keep_worldcover_classes` — vegetation classes (default `[10, 20, 30]`)
- `jrc_water_occurrence_threshold` — % months water observed (default 50.0)
- `open_buildings_confidence` — drop building polygons below this (default 0.7)
- `nightlights_threshold` — VIIRS radiance threshold (default 30.0, Delhi-calibrated)

**Not used in this stage** (kept in config for future use):
- `ndvi_min` — applied later in a feature stage; requires S2 data, doesn't belong in static masking

**Why these data sources** (see also `docs/design_notes.md`):
The built mask uses Open Buildings (vector, derived from commercial imagery — not S2) and VIIRS (different sensor) rather than e.g. GHSL Built-up. This avoids using S2-derived products to mask data that will later be fed S2 features — reduces circularity between mask and features.

**Related decisions:** DEC-005 (ROI via GeoJSON), DEC-006 (three-phase masking), ENG-005, ENG-011, ENG-012, ENG-017 (new — multi-source masking).

### 2. data_load — `src/fmu/stages/data_load.py`

Loads Sentinel-2 and Sentinel-1 collections, applies S2 cloud masking (SCL-based), and builds the static optical composite SNIC will see. The phenology and radar windows are different from the composite window — each serves a different downstream stage.

**Reads from context:** `roi`
**Writes to context:** `s2_collection`, `s1_collection`, `s2_composite`

**Cacheable outputs:** `s2_composite` only. Image collections can't be exported as single assets, so they're recomputed each run (filtering is cheap — composite calculation is the expensive part).

**Datasets:**
- Sentinel-2 SR Harmonized (`COPERNICUS/S2_SR_HARMONIZED`) — phenology + composite
- Sentinel-1 GRD (`COPERNICUS/S1_GRD`) — radar

**Logic:**
- S2 collection: filter by ROI + phenology window + `CLOUDY_PIXEL_PERCENTAGE ≤ max_cloud_pct`. Per-image SCL masking drops classes 3 (cloud shadow), 8 (cloud medium prob), 9 (cloud high prob), 10 (thin cirrus).
- S1 collection: filter by IW mode, single orbit direction (default ASCENDING), VV+VH polarizations. **No dB conversion needed** — `COPERNICUS/S1_GRD` is already in dB ([source](https://developers.google.com/earth-engine/guides/sentinel1)).
- S2 composite: re-filter S2 by the optical_composite window, apply SCL mask, reduce by `s2_composite_reducer` (default median).
- Empty windows → `RuntimeError` (fail-loud per ENG-012).

**Config knobs** (in `configs/*.yaml`):
- `cloud_mask.max_cloud_pct` — drop S2 images with cloud % above this (default 20)
- `cloud_mask.drop_scl_classes` — which SCL pixel classes to mask out (default [3, 8, 9, 10])
- `data_load.s1_orbit` — `ASCENDING` or `DESCENDING` (default ASCENDING)
- `data_load.s1_polarizations` — list of `VV` / `VH` (default both)
- `data_load.s1_instrument_mode` — `IW` / `EW` / `SM` (default IW)
- `data_load.s2_composite_reducer` — `median` / `p25` / `p50` / `p75` (default median)

**Related decisions:** DEC-005 (union mask sampling, handles missing bands), ENG-012 (fail-loud), ENG-018 (caching).

### 3. features_optical — `src/fmu/stages/features_optical.py`

Per-pixel phenology features via harmonic regression on a vegetation index (NDVI or NIRv) over the 8-year S2 phenology window. The output is the dominant input to clustering downstream.

**Reads from context:** `s2_collection`, `roi`
**Writes to context:** `optical_features` (single multi-band image)
**Cacheable:** yes (one image with named bands)

**Regression model:**

```
y(t) = a + b·cos(2π·t) + c·sin(2π·t)
     + [d·cos(4π·t) + e·sin(4π·t)]   # dual harmonic only
     + [f·t]                          # if include_trend
```

Where `y` is the vegetation index (NDVI or NIRv) and `t` is years since 2017-01-01.

**Derived metrics extracted from the coefficients** (per DEC-002):
- `<prefix>_mean = a` (intercept)
- `<prefix>_amplitude_annual = sqrt(b² + c²)`
- `<prefix>_phase_annual = atan2(c, b)` — radians, when peak greenness happens
- `<prefix>_amplitude_semi`, `<prefix>_phase_semi` — dual harmonic only
- `<prefix>_trend = f` — per-year change
- `<prefix>_residual_variance` — RMS of regression residuals; high = pixel poorly fit by smooth seasonal cycle
- `<prefix>_obs_count` — number of valid observations per pixel (metadata, not for clustering)

Where `<prefix>` is `ndvi` or `nirv` depending on the config.

**Config knobs:**
- `features_optical.index` — `ndvi` (default, baseline) or `nirv`
- `features_optical.harmonic_mode` — `single` (default, baseline) or `dual`
- `features_optical.include_trend` — bool (default `true`)

**Two configs run through this same stage:**
- `sanjay_van_baseline.yaml`: NDVI + single annual harmonic + trend (6 bands)
- `sanjay_van_nirv_dual.yaml`: NIRv + dual harmonic + trend (8 bands)

The metrics module (Module 18) will compare their outputs (see DEC-013).

**Related decisions:** DEC-002 (derived metrics not raw coefficients), DEC-013 (baseline vs variant), DEC-014 (compute over full ROI, mask at clustering), DEC-015 (which features included/skipped and why).

### 4. features_radar — `src/fmu/stages/features_radar.py`

Per-pixel radar features via statistical reducers over the 5-year S1 collection. No harmonic regression — SAR backscatter doesn't have a clean seasonal cycle (returns depend on geometry, moisture, biomass, not photosynthesis).

**Reads from context:** `s1_collection`, `roi`
**Writes to context:** `radar_features` (single multi-band image)
**Cacheable:** yes

**Reducers applied:**
- Per-percentile (default [10, 50, 90]): `vv_p10`, `vv_p50`, `vv_p90`, `vh_p10`, `vh_p50`, `vh_p90`
- IQR (interquartile range, p75 - p25): `vv_iqr`, `vh_iqr` — variability metric
- Cross-pol contrast: `vv_minus_vh_median` (VV_p50 − VH_p50 in dB) — vegetation structure proxy

Total: 9 bands with default config.

**On the cross-pol contrast (DEC-016):** Uses `VV − VH` in dB, equivalent to `10·log10(VV_linear / VH_linear)`. The notebook computed `VV / VH` on dB-scale values directly, which isn't mathematically meaningful — dB is a log-scale quantity, not a magnitude. This module fixes that.

**On no speckle filtering:** Temporal median over 100+ S1 images suppresses speckle more strongly than any 3×3 or 5×5 spatial filter (variance reduction scales with the number of independent samples). Spatial filters would also blur edges, hurting the downstream SNIC segmentation. If individual-scene speckle becomes a concern, it's a variant config, not a baseline addition.

**Config knobs:**
- `features_radar.percentiles` — list of percentiles to compute (default `[10, 50, 90]`)
- `features_radar.include_iqr` — bool (default `true`)
- `features_radar.include_cross_pol_contrast` — bool (default `true`)

**Related decisions:** DEC-014 (compute over full ROI, mask at clustering), DEC-016 (VV−VH in dB, no speckle filter), ENG-018 (caching).

### 5. features_structure — `src/fmu/stages/features_structure.py`

Per-pixel structural features from canopy height. Uses ETH Global Canopy Height 2020 (10 m, GEDI + S2 fusion — see DEC-009 for why over raw GEDI).

**Reads from context:** `roi`
**Writes to context:** `structure_features` (single multi-band image)
**Cacheable:** yes

**Bands (default):**
- `canopy_height` — point value from the ETH dataset (meters)
- `canopy_height_std` — std-dev in a 3×3 window — local structural heterogeneity
- `canopy_height_max` — max in 3×3 window — tallest neighbor (catches edges where short pixels neighbor tall trees)

When `include_neighborhood_stats` is false, only `canopy_height` is emitted (notebook approach).

**Config knobs:**
- `features_structure.include_neighborhood_stats` — bool (default `true`)
- `features_structure.neighborhood_kernel_size` — odd int 3-11 (default 3)

**Related decisions:** DEC-009 (ETH over GEDI L2A), DEC-014 (compute over full ROI, mask at clustering).

### 6. features_static — `src/fmu/stages/features_static.py`

Per-pixel features that don't change meaningfully over the analysis time window: terrain, distance to water, long-term rainfall climatology.

**Reads from context:** `roi`, `water_mask`
**Writes to context:** `static_features` (single multi-band image)
**Cacheable:** yes

**Bands (default):**
- `elevation` — meters above sea level (NASADEM)
- `slope` — degrees (derived from elevation via `ee.Terrain.products`)
- `aspect` — degrees 0-360, cyclic raw (derived from elevation)
- `distance_to_water` — meters to nearest water pixel (uses `water_mask` from masking stage, via `fastDistanceTransform`)
- `annual_rainfall` — mm/year mean from CHIRPS PENTAD over 1991-2020 climatology

When `include_climate` is false, only the first 4 bands are emitted.

**On aspect:** emitted as raw degrees (0-360). Cyclic, so 0° and 359° look maximally different to a Euclidean clusterer despite being identical. Future improvement: emit `aspect_sin`, `aspect_cos` instead. Left as raw to match notebook approach (ENG-006).

**On distance to water:** uses `water_mask` from masking, not a fresh JRC pull, so the water source is consistent between exclusion (masking) and feature (here). Cap at `max_water_distance_pixels` × analysis scale (default 10 km).

**On rainfall:** 30-year standard climatology (1991-2020). Long enough to smooth out year-to-year variation. For a small AOI like Sanjay Van, this band will be nearly constant; included for cross-AOI generality.

**Config knobs:**
- `features_static.include_climate` — bool (default `true`)
- `features_static.max_water_distance_pixels` — int 100-10000 (default 1000)
- `datasets.climate` — CHIRPS pentad path (default `UCSB-CHG/CHIRPS/PENTAD`)
- `dates.climate` — climatology window (default 1991-01-01 → 2020-12-31)

**Related decisions:** DEC-014 (compute over full ROI, mask at clustering).

### Later stages

Each one will get its own section here as it's built.

---

## Where to find specific things

| What you want | Where it lives |
|---|---|
| Pipeline config schema | `src/fmu/config.py` |
| Baseline config values | `configs/sanjay_van_baseline.yaml` |
| Per-machine settings (`.env`) | `src/fmu/settings.py` |
| Sanjay Van ROI polygon | `aois/sanjay_van.geojson` (placeholder; needs replacement) |
| GEE init / safe_get_info | `src/fmu/utils/gee.py` |
| Logging setup | `src/fmu/utils/logging.py` |
| Stage abstract / registry | `src/fmu/stages/base.py` |
| Pipeline orchestrator | `src/fmu/pipeline.py` |
| Masking logic | `src/fmu/stages/masking.py` |
| Data load logic | `src/fmu/stages/data_load.py` |
| Optical features logic | `src/fmu/stages/features_optical.py` |
| Radar features logic | `src/fmu/stages/features_radar.py` |
| Structure features logic | `src/fmu/stages/features_structure.py` |
| Static features logic | `src/fmu/stages/features_static.py` |
| Phenology config knobs | `configs/*.yaml` → `features_optical.{index, harmonic_mode, include_trend}` |
| Radar config knobs | `configs/*.yaml` → `features_radar.{percentiles, include_iqr, include_cross_pol_contrast}` |
| Structure config knobs | `configs/*.yaml` → `features_structure.{include_neighborhood_stats, neighborhood_kernel_size}` |
| Static config knobs | `configs/*.yaml` → `features_static.{include_climate, max_water_distance_pixels}` |
| Climate dataset + window | `configs/*.yaml` → `datasets.climate`, `dates.climate` |
| NIRv + dual variant config | `configs/sanjay_van_nirv_dual.yaml` |
| S2 cloud mask SCL classes | `configs/sanjay_van_baseline.yaml` → `cloud_mask.drop_scl_classes` |
| S2 max cloud % | `configs/sanjay_van_baseline.yaml` → `cloud_mask.max_cloud_pct` |
| S1 orbit direction | `configs/sanjay_van_baseline.yaml` → `data_load.s1_orbit` |
| S1 polarizations | `configs/sanjay_van_baseline.yaml` → `data_load.s1_polarizations` |
| S2 composite reducer | `configs/sanjay_van_baseline.yaml` → `data_load.s2_composite_reducer` |
| WorldCover dataset ID | `configs/sanjay_van_baseline.yaml` → `datasets.worldcover` |
| JRC water dataset ID | `configs/sanjay_van_baseline.yaml` → `datasets.water` |
| Open Buildings dataset ID | `configs/sanjay_van_baseline.yaml` → `datasets.open_buildings` |
| VIIRS nightlights dataset ID | `configs/sanjay_van_baseline.yaml` → `datasets.nightlights` |
| WorldCover class filter | `configs/sanjay_van_baseline.yaml` → `masking.keep_worldcover_classes` |
| JRC water threshold | `configs/sanjay_van_baseline.yaml` → `masking.jrc_water_occurrence_threshold` |
| Open Buildings confidence | `configs/sanjay_van_baseline.yaml` → `masking.open_buildings_confidence` |
| VIIRS threshold | `configs/sanjay_van_baseline.yaml` → `masking.nightlights_threshold` |
| Per-run output folder | `outputs/runs/<config>_<timestamp>/` (created by `init_logging`) |
| Manifest of a run | `outputs/runs/<config>_<timestamp>/manifest.json` |
| Asset caching utility | `src/fmu/utils/caching.py` |
| Cache integration in orchestrator | `src/fmu/pipeline.py` (`Pipeline(use_cache=True)`, `_try_load_cache`, `_submit_exports`) |
| Cache asset path format | `{asset_root}/{config_name}/{stage_name}/{key}` |

---

## Key decisions affecting current flow

| Decision | Affects | Where to read more |
|---|---|---|
| DEC-005 | ROI loaded from GeoJSON | `decisions.md` |
| DEC-006 | Three-phase masking; masking runs first | `decisions.md` |
| ENG-005 | `roi_file` in YAML, `roi_asset` reserved | `decisions.md` |
| ENG-007 | Explicit GEE init (`init_gee()`) | `decisions.md` |
| ENG-009 | `safe_get_info` wrapper for materialization | `decisions.md` |
| ENG-011 | Stage contract: context-dict + declared inputs/produces | `decisions.md` |
| ENG-012 | Fail-loud, no soft-fail | `decisions.md` |

---

## How to seed the ROI into the context

Masking needs `roi` in the context. The orchestrator does not auto-load it (yet); the run script seeds it. Pattern:

```python
from fmu.config import load_config
from fmu.pipeline import Pipeline
from fmu.stages.base import PipelineContext
from fmu.utils.gee import init_gee, load_roi_geometry
from fmu.utils.logging import init_logging

config = load_config("configs/sanjay_van_baseline.yaml")
init_gee()
roi = load_roi_geometry(config.roi.roi_file)

ctx = PipelineContext()
ctx.set("roi", roi)

run_dir = init_logging(config_name=config.name)
result = Pipeline(stage_names=["masking"]).run(
    config=config, run_dir=run_dir, initial_context=ctx
)
```

(This pattern will move into a CLI entry point or run script in a later module.)

---

*Last updated: v0.6-masking (Module 6).*
