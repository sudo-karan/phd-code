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

*Not yet built.* Will load S2 and S1 collections, apply per-image cloud masking, and build the static optical composite used by SNIC. Will read `roi` from context; produce `s2_collection`, `s1_collection`, `s2_composite`.

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
