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

The pipeline runs a sequence of stages, each producing context keys consumed by later stages. As of v0.6, only the first real GEE stage exists; the rest are placeholder/planned.

```
[ROI loaded into context]
        ↓
1. masking          → habitat_mask, water_mask, landcover_summary
        ↓
2. data_load        (next module)
        ↓
3. features_optical
4. features_radar
5. features_structure
6. features_static
        ↓
7. segmentation     (SNIC)
        ↓
8. clustering
        ↓
9. profiling
        ↓
10. export
```

The orchestrator (`fmu.pipeline.Pipeline`) walks the stages, validates the context against each stage's declared inputs, and merges outputs back in. See ENG-013 in decisions.md.

---

## Stage details

### 1. masking — `src/fmu/stages/masking.py`

Builds the habitat mask, the water mask, and a labeled landcover summary from WorldCover and JRC Global Surface Water. Three-phase masking structure (DEC-006): static habitat layer first, time-series data comes later.

**Reads from context:** `roi`
**Writes to context:** `habitat_mask`, `water_mask`, `landcover_summary`

**Datasets:**
- ESA WorldCover v200 (`ESA/WorldCover/v200`) — used for vegetation classification
- JRC Global Surface Water 1.4 (`JRC/GSW1_4/GlobalSurfaceWater`) — used for permanent water

**Logic:**
- `habitat_mask` = WorldCover class ∈ {10, 20, 30} AND NOT permanent water
- `water_mask` = JRC occurrence ≥ `jrc_water_occurrence_threshold` (default 50%)
- `landcover_summary` = labeled image: 10/20/30 for kept WorldCover classes, 80 for water, 0 for everything else (urban, bare, crop, etc)

**Config knobs** (in `configs/*.yaml` under `masking:`):
- `keep_worldcover_classes` — which WorldCover classes count as vegetation (default `[10, 20, 30]`)
- `jrc_water_occurrence_threshold` — % of months a pixel must show water to count as permanent (default 50.0)

**Not used in this stage** (kept in config for future use):
- `ndvi_min` — would need S2 data; will be applied in a later stage if at all
- `nightlights_threshold` — VIIRS-based urban masking dropped from baseline

**Related decisions:** DEC-005 (ROI via GeoJSON), DEC-006 (three-phase masking), ENG-005, ENG-011, ENG-012.

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
| WorldCover class filter | `configs/sanjay_van_baseline.yaml` → `masking.keep_worldcover_classes` |
| JRC water threshold | `configs/sanjay_van_baseline.yaml` → `masking.jrc_water_occurrence_threshold` |
| Per-run output folder | `outputs/runs/<config>_<timestamp>/` (created by `init_logging`) |
| Manifest of a run | `outputs/runs/<config>_<timestamp>/manifest.json` |

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
