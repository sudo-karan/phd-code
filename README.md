# fmu — Forest Management Units

Multi-sensor pipeline for delineating ecologically coherent forest stands
from open satellite data. Everything runs server-side on Google Earth
Engine; the package itself orchestrates the GEE calls, manages config,
and writes a reproducibility manifest for each run.

Pipeline version: **0.18.0** (all 11 stages implemented; v1.0 milestone).

## What it does

Given a GeoJSON polygon (an Area of Interest), fmu:

1. **Masks** non-habitat pixels (water, buildings, bare/urban) using a
   multi-source mask designed to avoid circularity with downstream
   features (see [docs/design_notes.md](docs/design_notes.md)).
2. **Loads** Sentinel-2 (optical) and Sentinel-1 (radar) collections
   plus auxiliary datasets (canopy height, terrain, climate).
3. **Computes per-pixel features**:
   - phenology via harmonic regression on NDVI (or NIRv) over 8 years of S2
   - radar statistics (percentiles, IQR, cross-pol contrast) over 5 years of S1
   - structural heterogeneity from ETH canopy height + neighborhood stats
   - terrain (NASADEM), distance-to-water, mean annual rainfall (CHIRPS)
4. **Segments** the AOI into SNIC superpixels using a 5-band z-scored stack
   that combines visible, NIR, structural, and microwave information.
5. **Clusters** the per-superpixel feature vectors with k-means
   (preprocessing: cyclic decomposition, log-transform of skewed bands,
   median/IQR robust scaling).
6. **Profiles** each cluster (mean/IQR per feature in original units).
7. **Exports** a GeoTIFF of cluster labels to Google Drive plus a full
   reproducibility manifest.
8. **Compares** the result against a reference clustering with ARI / NMI /
   silhouette / Hungarian-aligned agreement map.

The whole sequence is config-driven. A new experiment is a new YAML file;
the framework runs both baseline and variant through identical code and
the metrics stage compares them.

## Quickstart

```bash
# 1. Setup (one-time)
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
earthengine authenticate           # one-time per machine
cp .env.example .env               # then edit: set GEE_PROJECT_ID

# 2. Run the fast (mocked) tests to confirm install
pytest                             # ~1s, no auth needed

# 3. Run a stage live against real GEE
python scripts/inspect_masking.py --config configs/sanjay_van_baseline.yaml

# 4. Run the full pipeline (caches outputs as GEE assets)
python scripts/inspect_clustering.py --config configs/sanjay_van_baseline.yaml
python scripts/inspect_export.py    --config configs/sanjay_van_baseline.yaml
python scripts/inspect_metrics.py   --config configs/sanjay_van_nirv_dual.yaml
```

See [docs/running.md](docs/running.md) for the full run guide, including
how to run a single stage, how the cache works, and how to recover from
common errors.

## Reading the output

Every run creates `outputs/runs/<config>_<timestamp>/` containing:

| File | What it is |
|---|---|
| `fmu.log` | Full log (also streamed to terminal) |
| `manifest.json` | Per-stage runtime, cache hit/miss, warnings, full config snapshot |
| `export_manifest_<config>.json` | (after export stage) reproducibility artifact — every parameter, every asset path, per-cluster pixel distribution, Drive task ID |
| `cluster_profiles.csv` | (after profiling stage) one row per cluster: feature means and IQRs in original units |
| `comparison_metrics_<config>.json` | (after metrics stage) ARI, NMI, silhouette, confusion matrix, Hungarian correspondence |

The clustered map itself goes to your **Google Drive** as a GeoTIFF
(folder `fmu_exports`, filename `<config>_cluster_labels.tif`). Check
https://code.earthengine.google.com/tasks for export progress
(typically 5–15 min). Once present, load it in QGIS / ArcGIS / rasterio
to see the per-pixel cluster ID (`uint8`, values `0..k-1`).

Full output spec: [docs/outputs.md](docs/outputs.md).

## Repository layout

```
src/fmu/              Python package
  config.py             Pydantic YAML schema (the "what to run")
  settings.py           .env / per-machine settings (the "where to write")
  pipeline.py           Orchestrator: walks stages, caches, writes manifest
  stages/               One file per pipeline stage (base.py is the contract)
  utils/                GEE init wrappers, logging, asset caching
configs/              YAML configs — one per experiment
aois/                 GeoJSON polygons (one per ROI)
scripts/              `inspect_*.py` — run one stage at a time, write artifacts
tests/                pytest tests (fast tier + live_gee tier)
docs/                 Detailed docs (see below)
legacy/               pre-package Colab notebooks (read-only reference)
outputs/runs/         per-run output directories (gitignored)
```

## Deeper docs

| You want to know... | Read |
|---|---|
| Why the code is structured the way it is | [docs/design_notes.md](docs/design_notes.md) |
| What each stage does and in what order | [docs/current_flow.md](docs/current_flow.md) |
| How to actually run things (inspect scripts, full pipeline, cache) | [docs/running.md](docs/running.md) |
| Format of every file fmu produces | [docs/outputs.md](docs/outputs.md) |
| Every GEE dataset used, what it contributes, why chosen | [docs/datasets.md](docs/datasets.md) |
| How config works; how to add a new experiment | [docs/configs.md](docs/configs.md) |
| Stage contract, registry, caching internals, how to add a stage | [docs/architecture.md](docs/architecture.md) |
| Module status (locked / paused / in progress) | [MODULES.md](MODULES.md) |

## Tests

```bash
pytest                  # fast (~1s, no auth, runs in CI)
pytest -m live_gee      # real-GEE tier (~10-20s, needs earthengine authenticate)
```

**CI runs only the fast tier.** Live tests must be run locally before
locking a module. See [docs/current_flow.md](docs/current_flow.md#testing-policy).

## License

MIT — see [LICENSE](LICENSE).
