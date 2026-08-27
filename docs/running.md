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
inspect_clustering.py         # everything through clustering (longest)
inspect_profiling.py          # everything + profiling
inspect_export.py             # everything + export (submits Drive task)
inspect_metrics.py            # everything + metrics (needs a reference config)
```

Run an upstream script before its downstream. They share the cache,
so each later script benefits from earlier exports.

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
  `{GEE_ASSET_ROOT}/{config_name}/{stage_name}/{output_key}` for every
  cacheable output. If all are present, the live computation is skipped
  and the cached assets are loaded into the context.
- **After each stage:** any cacheable output that missed the cache is
  submitted as an async export task. The current run keeps the live
  computation (so downstream stages don't block); subsequent runs hit
  the cache.

Cache asset path layout:
```
projects/<your-project>/assets/fmu/<config_name>/<stage_name>/<output_key>
```

Example after running the baseline through clustering:
```
.../fmu/sanjay_van_baseline/masking/habitat_mask
.../fmu/sanjay_van_baseline/masking/water_mask
.../fmu/sanjay_van_baseline/masking/landcover_summary
.../fmu/sanjay_van_baseline/data_load/s2_composite
.../fmu/sanjay_van_baseline/features_optical/optical_features
.../fmu/sanjay_van_baseline/features_radar/radar_features
.../fmu/sanjay_van_baseline/features_structure/structure_features
.../fmu/sanjay_van_baseline/features_static/static_features
.../fmu/sanjay_van_baseline/segmentation/snic_clusters
.../fmu/sanjay_van_baseline/segmentation/snic_means
.../fmu/sanjay_van_baseline/clustering/cluster_labels
.../fmu/sanjay_van_baseline/clustering/feature_stack
```

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

### Stable paths, not hashes

Cache paths are derived from `(config_name, stage_name, output_key)`,
not from a hash of the parameters that produced the output. So if you
change a threshold in the config without changing the config's `name`,
**the next run will overwrite the cached asset.** This is intentional;
config names ARE the version. To preserve an old run, give the new
experiment a new config file with a new `name`.

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
`canopy_height`, `canopy_height_std` and `ndvi_amplitude_annual`. What is held identical to the
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
└── metrics_<config>.json             # added by inspect_metrics
```

Plus three raster GeoTIFFs in your Google Drive under `fmu_exports/`:
`<config>_cluster_labels.tif`, `<config>_features_raw.tif`, and
`<config>_features_scaled.tif` (the two feature rasters carry a `cluster_id`
band alongside the feature bands).

Full output spec: [outputs.md](outputs.md).
