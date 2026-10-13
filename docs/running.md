# Running the pipeline

How to actually run fmu: single stage, full pipeline, comparison run.
For what each stage does, see [current_flow.md](current_flow.md). For
how to interpret output, see [outputs.md](outputs.md).

## Prerequisites

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
earthengine authenticate                  # one-time per machine
cp .env.example .env                      # then edit
```

In `.env`, set at minimum:
```
GEE_PROJECT_ID=your-gee-project-with-earth-engine-enabled
```

Optional:
```
GEE_ASSET_ROOT=projects/your-project/assets/fmu      # cache assets go here
OUTPUT_DIR=outputs                                    # where run dirs go
LOG_LEVEL=INFO                                        # or DEBUG
```

If you want clustering to write outputs to a non-default asset root,
set `GEE_ASSET_ROOT`. Otherwise the pipeline defaults to
`projects/{GEE_PROJECT_ID}/assets/fmu`.

Provision the asset folder hierarchy once per project:

```bash
python create_folders_in_gee.py
```

## Verify your install

```bash
pytest                                    # fast tier, no auth needed
```

If this passes, the package imports cleanly and the orchestrator works.
One test in `tests/test_evaluation_unsupervised.py` measures a run time; on a
loaded machine, `FMU_SKIP_TIMING_TESTS=1 pytest` skips it.
It does NOT verify GEE. That needs the live tier:

```bash
pytest -m live_gee                        # per-stage tests, need auth
```

The live tests connect to real GEE. They skip themselves cleanly with an
informative message if `GEE_PROJECT_ID` is empty or `earthengine
authenticate` hasn't been run.

## Two ways to run the pipeline

### A. Inspect scripts (recommended for development)

One script per stage in `scripts/`. Each script:

1. Runs the pipeline up to and including its named stage.
2. Prints a summary of the stage's output (band names, statistics, sample
   values, the GEE Code Editor JS snippet you can paste to visualize).
3. Writes intermediate artifacts to the run dir.

Each is invoked as:

```bash
python scripts/inspect_<stage>.py --config configs/sanjay_van_baseline.yaml
```

Available scripts (run them in roughly this order):

```
inspect_masking.py            # masking
inspect_data_load.py          # masking + data_load
inspect_features_optical.py   # ... + features_optical
inspect_features_radar.py     # ... + features_radar
inspect_features_structure.py # ... + features_structure
inspect_features_static.py    # ... + features_static
inspect_segmentation.py       # all of the above + segmentation
inspect_merge.py              # ... + merge; READ-ONLY by default (submits nothing)
inspect_clustering.py         # everything through clustering (longest)
inspect_profiling.py          # everything + profiling
inspect_export.py             # everything + export (submits Drive task)
inspect_metrics.py            # everything + metrics (needs a reference config)
```

Run an upstream script before its downstream. They share the cache,
so each later script benefits from earlier exports.

`inspect_merge.py` differs from the others: it runs
`Pipeline(..., use_cache=True, submit_exports=False)`, so it reads cached
assets, computes anything missing live and submits no Earth Engine task. Pass
`--submit-exports` for the other scripts' behaviour, and never while tasks from
an earlier run are still queued. It prints the merge summary numbers, the
threshold calibration, the stand-size distribution, a per-stand provenance table
(`--sort fallback|area|id`, `--rows N`, 0 for all) and the stands left below the
minimum size with their cause, and writes the table to the run directory as
`merge_provenance.csv` and `merge_provenance.json`.

```bash
python scripts/inspect_merge.py --config configs/sanjay_van_baseline.yaml
python scripts/inspect_merge.py --config configs/<config>.yaml --sort area --rows 50
```

### B. Programmatic (for batch / CI / your own driver)

```python
from fmu.config import load_config
from fmu.pipeline import Pipeline
from fmu.stages.base import PipelineContext
from fmu.utils.gee import init_gee, load_roi_geometry
from fmu.utils.logging import init_logging

# Make sure stages are registered (importing the module triggers @register_stage)
import fmu.stages.masking            # noqa: F401
import fmu.stages.data_load          # noqa: F401
import fmu.stages.features_optical   # noqa: F401
# ... etc, or use a single helper that imports them all

config = load_config("configs/sanjay_van_baseline.yaml")
init_gee()
roi = load_roi_geometry(config.roi.roi_file)

ctx = PipelineContext()
ctx.set("roi", roi)                  # the orchestrator does NOT load this for you

run_dir = init_logging(config_name=config.name)

result = Pipeline(
    stage_names=[
        "masking",
        "data_load",
        "features_optical",
        "features_radar",
        "features_structure",
        "features_static",
        "segmentation",
        "clustering",
        "profiling",
        "export",
    ],
    use_cache=True,
).run(config=config, run_dir=run_dir, initial_context=ctx)

print(f"Done. Manifest: {run_dir}/manifest.json")
```

## The cache layer

`Pipeline(stage_names, use_cache=True)` enables it. With cache on:

- **Before each stage:** the orchestrator checks
  `{GEE_ASSET_ROOT}/{config_name}/{stage_name}/{output_key}__{fingerprint}`
  for every cacheable output. If all are present, the live computation is
  skipped and the cached assets are loaded into the context.
- **After each stage:** any cacheable output that missed the cache is
  submitted as an async export task. The current run keeps the live
  computation (so downstream stages don't block); subsequent runs hit
  the cache.

Cache asset path layout:
```
projects/<your-project>/assets/fmu/<config_name>/<stage_name>/<output_key>__<fingerprint>
```

`<fingerprint>` is a 10-character hash of the config content
(`config_fingerprint()` in `src/fmu/utils/caching.py`). Example after running
the baseline through clustering, with `<fp>` standing for it:
```
.../fmu/sanjay_van_baseline/masking/habitat_mask__<fp>
.../fmu/sanjay_van_baseline/masking/water_mask__<fp>
.../fmu/sanjay_van_baseline/masking/landcover_summary__<fp>
.../fmu/sanjay_van_baseline/masking/mask_provenance__<fp>
.../fmu/sanjay_van_baseline/data_load/s2_composite__<fp>
.../fmu/sanjay_van_baseline/features_optical/optical_features__<fp>
.../fmu/sanjay_van_baseline/features_radar/radar_features__<fp>
.../fmu/sanjay_van_baseline/features_structure/structure_features__<fp>
.../fmu/sanjay_van_baseline/features_static/static_features__<fp>
.../fmu/sanjay_van_baseline/segmentation/snic_clusters__<fp>
.../fmu/sanjay_van_baseline/segmentation/snic_means__<fp>
.../fmu/sanjay_van_baseline/clustering/cluster_labels__<fp>
.../fmu/sanjay_van_baseline/clustering/feature_stack__<fp>
```

The merge stage caches nothing.

**Tests should leave `use_cache=False`** (the default). The unit tests do.

### Watching export tasks

Cache-miss exports are submitted via `ee.batch.Export.image.toAsset`.
Each one returns a task ID; the orchestrator logs the URL:

```
INFO Started cache export to projects/.../habitat_mask (task ABC123). Check progress at https://code.earthengine.google.com/tasks
```

The task takes 5-15 min for a typical 10 m image over an AOI the size of
Sanjay Van. The Python process does NOT wait; it moves on. Re-run the
same script after exports complete; the next run will hit the cache.

If a task fails (e.g., GEE quota, malformed image), the task page shows
an error, the asset never materializes, and the next run will keep
re-submitting until it succeeds.

### Paths carry a fingerprint of the config

Cache paths are derived from `(config_name, stage_name, output_key)` plus a
fingerprint of the config content. So if you change a threshold in the config
without changing its `name`, the fingerprint changes and **the next run
computes and exports new assets beside the old ones; nothing is overwritten
and the old assets are not read.** Two things follow:

- Editing almost any config block makes every stage of that config recompute.
  The fingerprint is one hash over the config, not one per stage. The blocks
  that do not change it are `name`, `description`, `metrics`, and `export`
  apart from `export.analysis_scale_m`.
- Running an unchanged config again reads its assets back. To recompute from
  scratch, see "Re-running a config from scratch" below.

Assets cached before fingerprints existed sit at the name-only path
(`.../<stage_name>/<output_key>`). The pipeline no longer reads them.

### Reading a cached run without submitting anything

`Pipeline(stage_names, use_cache=True, submit_exports=False)` reads the cache
without writing to it: cached outputs are read and used, outputs that miss are
computed live for this run only, no export task is submitted and no asset
folder is created. Their `cache_status` stays `"miss"` and `export_tasks` is
empty. Use it for anything that reads an existing run (maps, inspectors,
checks) and must add nothing to the task queue. It is safe while export tasks
from another run are queued.

It covers the orchestrator's cache exports only. The `export` stage submits its
own Drive tasks, so `Pipeline` raises `ValueError` if `export` is in the stage
list with `submit_exports=False`.

`summaries=False` (default `True`) skips each stage's summary numbers and the
Earth Engine round trip they can cost; masking's is one reduction over the ROI.

Two scripts run this way: `scripts/inspect_merge.py` (above) and
`scripts/transparency_masking.py`, which draws the land-cover mask of a config:

```bash
# any config; reads the cache, submits nothing
python scripts/transparency_masking.py --config configs/sanjay_van_baseline.yaml

# with points to mark as kept or dropped, and plain words on the map
python scripts/transparency_masking.py --config configs/<config>.yaml \
    --points plots.csv --id-col plot_id --lon-col lon --lat-col lat \
    --point-noun "field plot" --title "<site>: land-cover (habitat) mask"

# the four Odisha districts with the field plots
python odisha_script/odisha_transparency_masking.py            # or --district kendujhar

# redraw maps and summary.md from the saved rasters, no Earth Engine
python scripts/transparency_masking.py --config configs/<config>.yaml --redraw
```

Run from the repo root. The script runs `masking` and `data_load`, downloads the
mask, its reasons and the true-colour composite one ROI part at a time, and
writes maps and `summary.md` to `docs/transparency/<config>/` (committed) and
rasters to `outputs/transparency/<config>/` (git-ignored); the file list is in
[outputs.md](outputs.md). Unlike `scripts/inspect_masking.py`, it never fills
the cache. Other options: `--part-name-key` (the ROI file property that names
each part, default `name`), `--compare-mask-asset` (another cached
`habitat_mask` to compare with the one in use, repeatable), `--note` (a sentence
for `summary.md`, repeatable), `--map-note` (a sentence for the map caption,
repeatable), `--docs-dir`, `--data-dir`. `--redraw` refuses if the config's
fingerprint is no longer the one the saved rasters were made with, and takes
its title, notes and points from its own arguments: give it the same `--title`,
`--note`, `--map-note` and `--points` options as the run it redraws (the Odisha
wrapper does this itself). Drawing needs matplotlib
(`pip install -e ".[report]"`).

### Re-running a config from scratch

A second run of the same config is not a reproducibility test: it finds its own
assets in the cache and reads them back. To recompute every stage, copy the
config under a new name and change nothing else. The copy has the same
fingerprint in a fresh asset folder, so nothing is a cache hit.
`configs/<name>_repro.yaml` are such copies of fourteen configs (see
[configs.md](configs.md)).

Run the copy like any other config, with the inspect scripts or your own driver
(sections A and B above, `--config configs/<name>_repro.yaml`). This submits
Earth Engine export tasks.

For the Odisha configs the passes run through
`odisha_script/odisha_phase2_2_run_pipeline.py`, three times per config
(`--through segmentation`, `clustering`, `export`).
`odisha_script/run_config_passes.sh` loops over them, and a first pass on an
empty cache often hits Earth Engine's memory limit; the next pass completes
from cache. The shell script must never be started again while tasks from an
earlier start are still queued, or it submits a second copy of each, and its
own pass loop can break that rule on a slow queue: a stage that fails partway
returns without waiting for the exports it has already submitted. So run it
through the wrapper:

```bash
python odisha_script/run_passes_safely.py --label <name> \
    [--run-tree <clean checkout>] [--log-dir <dir>] [--passes 3] \
    configs/<config>_repro.yaml [configs/<another>_repro.yaml ...]
```

The wrapper runs one pass at a time and, before each, waits until Earth Engine
has no queued or running task whose description starts with the name of a
config it is about to run. It never re-runs a config that has finished (the
export stage would submit its Drive exports again), does not retry a config
whose export stage failed, allows one batch at a time (a lock file in the log
folder), and refuses a run tree with modified tracked files. Config paths are
relative to the run tree, which needs its own `.env`. It writes
`<log-dir>/<label>.log` and `<label>.state.json` (the commit it ran from and
each pass's per-stage exit codes); `--log-dir` defaults to `<run-tree>/logs`,
which is git-ignored. It needs live Earth Engine and submits tasks.

Then compare. Two general tools, and an Odisha wrapper:

```bash
# cached Earth Engine assets, stage by stage, pixel for pixel. Read-only on Earth Engine.
python scripts/compare_cached_assets.py --old configs/<name>.yaml --new configs/<name>_repro.yaml \
    [--old-fingerprint <fp>] [--stages masking data_load ...] [--out <file.json>]

# exported stand layers (GeoJSON). Offline.
python scripts/compare_stand_runs.py OLD.geojson NEW.geojson \
    [--id-field stand_lbl] [--new-id-field NAME] [--type-field cluster_id] \
    [--out results.txt] [--per-stand-csv stands.csv]

# one Odisha arm: stands, run records, plot join and Phase 3 scores against the committed ones. Offline.
python odisha_script/odisha_repro_compare.py --arm odisha_v120_3ha \
    --rerun-dir <folder with the _repro files> --out-dir <a new folder> [--checks] [--expect-identical]
```

`compare_cached_assets.py` says at which stage a difference enters. Label
images (SNIC ids, stand ids, cluster labels) have arbitrary numbering, so for
them only "0 pixels differ" is conclusive; otherwise use `compare_stand_runs.py`,
which reports counts, areas, identical outlines and area-weighted intersection
over union in both directions (definitions at the top of the script).
`--old-fingerprint` is for assets cached before the config's content changed;
compare only stages whose settings did not change. `compare_stand_runs.py`
refuses an `--out` or `--per-stand-csv` in a folder that holds committed files,
and the Odisha wrapper refuses such an `--out-dir`: name a new folder. The
wrapper looks for files named `<config>_repro_*` in `--rerun-dir`; `--suffix`
changes `_repro`.

Results of the re-runs made so far are in
[reproducibility.md](reproducibility.md) and `docs/reproducibility/`.

**One more segmentation pass on configs already run.** `mask_provenance` is a
new cached output of the masking stage. `odisha_phase2_2_run_pipeline.py`
refuses a `--through clustering` or `--through export` pass while any upstream
cacheable asset is missing, so a config whose three passes completed before
`mask_provenance` existed now needs one `--through segmentation --wait` pass
first. That pass reads everything else from the cache and exports only
`mask_provenance`.

## Running a comparison

The metrics stage (`stages/metrics.py`) compares the current config's
clustering against a reference config. Setup:

1. Run the baseline through clustering (so its `cluster_labels` and
   `feature_stack` are cached as assets):

   ```bash
   python scripts/inspect_clustering.py --config configs/sanjay_van_baseline.yaml
   # wait for asset exports to complete (5-15 min, check GEE Tasks)
   ```

2. Run the variant through clustering:

   ```bash
   python scripts/inspect_clustering.py --config configs/sanjay_van_nirv_dual.yaml
   # again wait for exports
   ```

3. In the variant's config, set `metrics.reference_config_name: sanjay_van_baseline`.

4. Run the metrics stage on the variant:

   ```bash
   python scripts/inspect_metrics.py --config configs/sanjay_van_nirv_dual.yaml
   ```

   The metrics stage loads BOTH the variant's and the reference's
   `cluster_labels` from the cache, computes ARI/NMI/silhouette/agreement,
   and writes the results to the run dir.

## Running the embedding arm

The embedding arm is a fully independent pipeline: a pretrained per-pixel
embedding (AlphaEarth or Tessera) supplies the feature vector for **both**
steps that see features — SNIC draws the boundaries on it and k-means labels
them — and the result is compared against the hand-crafted baseline. Two config
keys drive it: `clustering.feature_source: embedding` and
`segmentation.input_bands: [{source: embedding_features, band: "*"}]`.
`inspect_metrics.py` picks the stage list automatically —
`default_stage_names` takes the union of what clustering, segmentation and merge
each ask for. In the shipped embedding configs `features_radar` and
`features_static` drop out, while `features_optical` and `features_structure`
remain because the merge criteria (held identical across arms) read
`canopy_height` and `ndvi_amplitude_annual`. What is held identical to the
baseline is everything that is not the feature representation (SNIC
hyperparameters, `k`, `seed`, masking, analysis scale). There is no
`inspect_features_embedding.py`; the stage runs inside the pipeline that
`inspect_metrics.py` (or `inspect_clustering.py`) drives.

Because the arms now produce two different stand maps and there is no
ground-truth stand map, neither can be declared correct — they are compared on
stability, held-out predictive power at matched stand count, and geometry, not
on agreement with a reference.

### AlphaEarth

`configs/sanjay_van_alphaearth.yaml` already sets
`metrics.reference_config_name: sanjay_van_baseline`, so the only prerequisite
is a populated baseline cache.

1. Run the baseline through clustering (so its `cluster_labels` and
   `feature_stack` are cached), exactly as for any comparison:

   ```bash
   python scripts/inspect_clustering.py --config configs/sanjay_van_baseline.yaml
   # wait for asset exports to complete (5-15 min, check GEE Tasks)
   ```

2. Run metrics on the AlphaEarth config. This single command runs the full
   embedding pipeline (masking through clustering) live, then compares it
   against the cached baseline:

   ```bash
   python scripts/inspect_metrics.py --config configs/sanjay_van_alphaearth.yaml
   ```

   It prints the same ARI / NMI / agreement-rate table as any comparison, plus
   the per-stand `confidence` layer — each stand's fraction of pixels that
   agree with the baseline after Hungarian alignment (0..1; consensus between
   the two representations, not correctness) — and a scalar `confidence_summary`
   in `metrics_sanjay_van_alphaearth.json`.

### Tessera

Same recipe, but Tessera lives OFF Earth Engine (CC0, via the `geotessera`
library), so it must be ingested into an EE asset ONCE before its config can
run:

```bash
python scripts/prep_tessera.py --config configs/sanjay_van_tessera.yaml \
    --years 2017 2018 2019 2020 2021 2022 \
    --asset projects/<proj>/assets/tessera_sanjay_van_2017_2022
```

`geotessera` needs Python 3.12+ (the `tessera` optional extra), so run
`prep_tessera.py` in a separate 3.12+ environment
(`pip install -e ".[tessera]"`); it is a documented one-shot, not part of the
tested pipeline. The script fetches the ROI's Tessera tiles, mosaics them to
one GeoTIFF, and helps you upload it. Paste the printed asset id into
`datasets.embedding` in `configs/sanjay_van_tessera.yaml` (it ships as a
`projects/REPLACE_ME/...` placeholder), then run the same two steps as the
AlphaEarth arm with `--config configs/sanjay_van_tessera.yaml`.

## Reports and figures for slides

The export stage writes the `stands_*` vectors to a Google Drive folder
(`export.drive_folder`, default `fmu_exports`), and repeated runs leave `(1)`/`(2)`
duplicate copies there. Rather than download them by hand, pull the newest of each
straight into `fmu_exports_clean/`:

```bash
# one-time: grant a Drive read scope (you likely have gcloud from the GCS/Tessera steps)
gcloud auth application-default login \
    --scopes=openid,https://www.googleapis.com/auth/drive.readonly,https://www.googleapis.com/auth/cloud-platform
pip install -e '.[drive]'

python scripts/fetch_drive_vectors.py                                  # all configs found
python scripts/fetch_drive_vectors.py --configs sanjay_van_alphaearth  # just one
```
It keeps only the newest `<config>_stands_<layer>.geojson` (normalizing the `(n)`
suffixes) and skips the SHP/DBF.

Once the configs have run (their `cluster_profiles.csv`, `metrics_<config>.json`,
and exported `stands_*` vectors are on disk), `scripts/report.py` turns them into
PNG figures + a self-contained HTML dashboard — no Earth Engine needed. Three
modes:

```bash
# one version on its own (stand map, fingerprint, separating power, composition, ...)
python scripts/report.py --config sanjay_van_alphaearth

# a 2-way comparison (variant vs baseline: confusion matrix, confidence gauge, metrics)
python scripts/report.py --config sanjay_van_alphaearth --reference sanjay_van_baseline --compare

# an N-way comparison, all versions side by side (the slide-ready one)
python scripts/report.py --multi --reference sanjay_van_baseline \
    --configs sanjay_van_alphaearth sanjay_van_tessera
```

`--multi` writes `reports/multi_<baseline>/report.html` with a metrics-at-a-glance
matrix (silhouette per version; ARI / NMI / agreement / confidence per version vs
the baseline), an intrinsic-silhouette bar chart (the one number directly
comparable across versions), side-by-side stand maps + composition, and a
per-variant overlap matrix. Drop those PNGs straight into the deck. The spatial
agreement / confidence maps come from the Code-Editor JS that `inspect_metrics.py`
prints (screenshot them).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `RuntimeError: GEE_PROJECT_ID not set in .env` | `.env` missing or empty | `cp .env.example .env`, edit it |
| `ee.EEException: ... not authenticated ...` | Earth Engine auth missing or expired | `earthengine authenticate` |
| `KeyError: 'roi' not found` | Forgot to seed the context | `ctx.set("roi", load_roi_geometry(config.roi.roi_file))` |
| `KeyError: 'habitat_mask' not found` (or any other context key) | Ran a stage out of order, its `required_inputs` weren't produced yet | Run upstream stages first; the orchestrator validates this and tells you which input is missing |
| Stage fails with "image computation user memory limit exceeded" | Live tile rendering of a compute-heavy layer | Enable caching (`use_cache=True`). The next run loads the static asset |
| `ValueError: cluster_labels asset is missing the 'clustering_metadata' property` in export | The cached `cluster_labels` asset was produced by an older clustering stage | Re-run the clustering stage to overwrite the asset with a current-version one |
| Live tests skip with "Baseline cache not populated" | `test_pipeline_smoke_live.py` needs baseline assets first | Run `inspect_clustering.py --config configs/sanjay_van_baseline.yaml` |
| Drive export task never appears | GEE Tasks page shows the task with FAILED, usually GEE quota or permission issues | Check the task error message; may need to wait an hour for quota reset |

## Debug verbosity

```bash
LOG_LEVEL=DEBUG python scripts/inspect_clustering.py --config configs/sanjay_van_baseline.yaml
```

Adds per-band log lines (skewness values, log-transform offsets, scaling
parameters), per-cache-hit/miss decisions, and per-stage required-inputs
/ produces declarations. Verbose, but most useful when a stage is
producing nonsense values and you need to see which preprocessing step
broke.

## Where outputs go

```
outputs/runs/<config>_<YYYYMMDD-HHMMSS>/
├── fmu.log
├── manifest.json
├── export_manifest_<config>.json     # added by inspect_export
├── cluster_profiles.csv              # added by inspect_profiling
├── metrics_<config>.json             # added by inspect_metrics
└── merge_provenance.csv, .json       # added by inspect_merge
```

`manifest.json` records the git commit the run was made from and whether the
tree had uncommitted changes.

Plus three raster GeoTIFFs in your Google Drive under `fmu_exports/`:
`<config>_cluster_labels.tif`, `<config>_features_raw.tif`, and
`<config>_features_scaled.tif` (the two feature rasters carry a `cluster_id`
band alongside the feature bands).

Full output spec: [outputs.md](outputs.md).
