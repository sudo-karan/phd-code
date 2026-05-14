# fmu — Forest Management Units

Multi-sensor pipeline for delineating ecologically coherent forest stands from
open satellite data. Runs server-side on Google Earth Engine; the Python
package wires up config, orchestration, caching, and inspect/run scripts.

Pre-alpha. Scaffold, config, orchestrator, caching, and stages 1–9
(masking → profiling) are in place. Export and metrics modules are next —
see `MODULES.md` for the build-order roadmap and `docs/current_flow.md` for
runtime flow + per-stage details.

## Setup

One-time per machine:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
earthengine authenticate            # opens browser; produces a credentials file
cp .env.example .env                # then edit GEE_PROJECT_ID
```

`.env` is git-ignored. Required:

- `GEE_PROJECT_ID` — your Google Cloud project with the Earth Engine API enabled.

Optional:

- `GEE_ASSET_ROOT` — defaults to `projects/{GEE_PROJECT_ID}/assets/fmu`.
- `OUTPUT_DIR` — defaults to `./outputs`.
- `LOG_LEVEL` — `DEBUG` / `INFO` / `WARNING` / `ERROR` (default `INFO`).

Smoke check:

```bash
pytest                              # fast tier, ~1s, no GEE auth needed
pytest -m live_gee                  # real GEE tier, needs `earthengine authenticate`
```

If the live tests pass, `init_gee()` and the asset-cache layer are wired up
correctly and you can run the inspect scripts below.

## Repo layout

```
src/fmu/                package
  config.py             Pydantic YAML schema + loader
  settings.py           .env / per-machine settings (pydantic-settings)
  pipeline.py           orchestrator + cache integration + manifest writer
  stages/               pipeline stages (each one a Stage subclass)
    base.py             Stage contract + registry
    masking.py          stage 1
    data_load.py        stage 2
    features_optical.py stage 3
    features_radar.py   stage 4
    features_structure.py stage 5
    features_static.py  stage 6
    segmentation.py     stage 7
    clustering.py       stage 8
    profiling.py        stage 9
  metrics/              validation metrics (WIP — Module 18)
  utils/
    gee.py              init, safe_get_info, ROI loader, asset_path
    caching.py          asset cache: path scheme + asset_exists + start_export
    logging.py          Rich logging + per-run output dir
configs/                YAML configs, one per experiment
aois/                   GeoJSON polygons
scripts/                runnable inspect_*.py per stage + check_resolutions.py
tests/                  pytest tests (fast + `-m live_gee` tiers)
docs/
  current_flow.md       runtime order + per-stage details + lookup index
  design_notes.md       why the code is the way it is
legacy/                 pre-package Colab notebooks (read-only reference)
MODULES.md              build-order status and what's locked
```

## Running the pipeline

A pipeline is constructed in code from a list of stage names. Stages must
be imported (or `from fmu.stages.<name> import <Class>`) before the
orchestrator can resolve them — the import side-effect registers the stage.
Every stage needs `roi` seeded into the context up-front; the orchestrator
does not auto-load it (yet).

The minimal pattern (also used inside every `scripts/inspect_*.py`):

```python
from fmu.config import load_config
from fmu.pipeline import Pipeline
from fmu.stages.base import PipelineContext
from fmu.stages.masking import MaskingStage  # noqa: F401 — registers stage
from fmu.utils.gee import init_gee, load_roi_geometry
from fmu.utils.logging import init_logging

config = load_config("configs/sanjay_van_baseline.yaml")
init_gee()
roi = load_roi_geometry(config.roi.roi_file)

ctx = PipelineContext()
ctx.set("roi", roi)

run_dir = init_logging(config_name=config.name)
result = Pipeline(stage_names=["masking"], use_cache=True).run(
    config=config, run_dir=run_dir, initial_context=ctx,
)
```

`use_cache=True` makes the orchestrator look up each cacheable output as a
GEE asset under `{GEE_ASSET_ROOT}/{config_name}/{stage_name}/{key}`. On a
miss it submits an async export task and continues with the live-computed
image; the asset will be ready for the next run. Tests should leave caching
off.

Per-run artifacts (logs, manifest, any CSVs the inspect scripts emit) land
in `outputs/runs/<config>_<timestamp>/`. The `manifest.json` records every
stage, its elapsed time, what it produced, cache hit/miss per key, and any
export tasks submitted.

## Running individual modules

`scripts/inspect_*.py` runs each stage end-to-end (with all upstream stages
it depends on) and prints a summary plus a JavaScript snippet you can paste
into the GEE Code Editor to visualize the result. All scripts accept
`--config <path>` and default to `configs/sanjay_van_baseline.yaml`.

| Stage | Script | Upstream stages run | Cacheable outputs |
|---|---|---|---|
| 1. masking | `python scripts/inspect_masking.py` | (none) | `habitat_mask`, `water_mask`, `landcover_summary` |
| 2. data_load | `python scripts/inspect_data_load.py` | masking-free; loads collections + composite | `s2_composite` only (collections aren't cacheable) |
| 3. features_optical | `python scripts/inspect_features_optical.py` | masking, data_load | `optical_features` |
| 4. features_radar | `python scripts/inspect_features_radar.py` | masking, data_load | `radar_features` |
| 5. features_structure | `python scripts/inspect_features_structure.py` | (uses ROI only) | `structure_features` |
| 6. features_static | `python scripts/inspect_features_static.py` | masking (for `water_mask`) | `static_features` |
| 7. segmentation | `python scripts/inspect_segmentation.py` | masking, data_load, features_radar, features_structure | `snic_clusters`, `snic_means` |
| 8. clustering | `python scripts/inspect_clustering.py` | all of 1–7 | `cluster_labels`, `feature_stack` |
| 9. profiling | `python scripts/inspect_profiling.py` | all of 1–8 | not cached (fast to recompute); writes `cluster_profiles.csv` to the run dir |

Examples:

```bash
# Run masking against the baseline config and print a Code Editor JS snippet:
python scripts/inspect_masking.py

# Run the full pipeline through clustering with the NIRv + dual harmonic variant:
python scripts/inspect_clustering.py --config configs/sanjay_van_nirv_dual.yaml

# Print resolutions of every dataset / cached feature the pipeline reads:
python scripts/check_resolutions.py
```

First run of a stage with caching on usually triggers an export task — the
script tells you the task ID and the expected asset path; subsequent runs
hit the cache and skip the live computation.

### One-off helpers

- `python scripts/check_resolutions.py` — prints native scale of every
  dataset and cached feature output. No exports, no clustering. Useful when
  deciding which features to feed SNIC.
- `python create_folders_in_gee.py` — creates the asset-folder tree under
  `GEE_ASSET_ROOT` for every config. Run once per fresh GEE project so the
  cache layer has somewhere to write to.

## Configs

One YAML per experiment under `configs/`. The schema lives in
`src/fmu/config.py` (Pydantic — fail-loud on missing or wrong-typed fields).

- `sanjay_van_baseline.yaml` — locked reference: NDVI + single annual
  harmonic, k=6, robust scaling.
- `sanjay_van_nirv_dual.yaml` — NIRv + dual harmonic variant; everything
  else identical so Module 18 metrics can isolate the difference.

Don't edit a locked baseline in place. Copy it and change what you need —
the new config's outputs cache to their own asset folder.

## Tests

```bash
pytest                  # fast tier (~1s); no GEE auth, runs in CI
pytest -m live_gee      # live tier (~10–20s); needs `earthengine authenticate`
```

- **Fast tier** — pure-Python infrastructure: config, settings, pipeline
  orchestrator, stage base, caching utility (mocked), logging.
- **Live tier** — every GEE stage has a `tests/test_<stage>_live.py` that
  hits real Earth Engine.

CI runs only the fast tier. **GEE stages must be verified locally with
`pytest -m live_gee` before locking a module — CI can't do this.** See
`docs/current_flow.md` (testing policy) and ENG-014 / ENG-018 in
`decisions.md` for the rationale.

## Where to look next

- `docs/current_flow.md` — what the pipeline does, in order, with per-stage
  inputs/outputs, datasets, config knobs, and cross-references to decisions.
- `docs/design_notes.md` — why the code is shaped the way it is.
- `MODULES.md` — build-order status: what's locked, what's paused on
  caching, what's next.
- `legacy/` — the original Colab notebooks the package was extracted from.
  Read-only reference, kept so the new code can be diffed against the old.

## License

MIT — see `LICENSE`.
