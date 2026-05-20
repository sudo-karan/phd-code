# Module status

Tracks each module's state. Not started · Under review · Locked.

A module is **Locked** when the code is read, has tests (fast + live where applicable), is documented, and is part of the smoke test. Modifications to locked modules need a new `decisions.md` entry.

**Build order is not runtime order.** This file is build order, what was worked on in which order. Runtime order (what runs in a pipeline run) lives in `docs/current_flow.md`.

| # | Module | Status | Locked at | Notes |
|---|---|---|---|---|
| 1 | Repo scaffold | Locked | v0.1-scaffold | Layout, pyproject, .env handling, .gitignore |
| 2 | `config.py` + baseline YAML | Locked | v0.2-config | Pydantic schema, locked baseline |
| 2 | `settings.py` | Locked | v0.2-config | Pydantic-settings, .env |
| 3 | `utils/logging.py` | Locked | v0.3-utils | Rich + per-run dirs |
| 3 | `utils/gee.py` | Locked | v0.3-utils | Init, safe_get_info, ROI loader, asset_path |
| 4 | `stages/base.py` | Locked | v0.4-stage | Stage contract, registry |
| 5 | `pipeline.py` | Locked | v0.5-orchestrator | Orchestrator + manifest |
| - | Voice pass cleanup | Locked | v0.5.1-voice | Knowledge moved to docs/design_notes.md |
| 6 | Asset caching (cross-cutting) | Locked | v0.6-caching | Stable asset paths, cache-first orchestrator, async export on miss, `use_cache` flag |
| 7 | `stages/masking.py` | Locked | v0.7-masking | Multi-source: WorldCover + JRC + Open Buildings + VIIRS. v1.1.0: added `use_viirs` and `use_open_buildings` toggles |
| 8 | `stages/data_load.py` | Locked | v0.8-data_load | S2 + S1 loading + cloud masking + static composite. Cacheable: `s2_composite` |
| 9 | `stages/features_optical.py` | Locked | v0.9-features_optical | Harmonic regression on NDVI or NIRv. Single or dual harmonic + trend. Variant config for comparison. v1.1.0: `time_reference` is configurable (was a module-level constant) |
| 10 | `stages/features_radar.py` | Locked | v0.10-features_radar | S1 percentiles + IQR + VV-VH cross-pol contrast. No harmonics, no speckle filtering |
| 11 | `stages/features_structure.py` | Locked | v0.11-features_structure | ETH canopy height + neighborhood stats (std, max) |
| 12 | `stages/features_static.py` | Locked | v0.12-features_static | NASADEM (elevation, slope, aspect) + distance-to-water + CHIRPS rainfall climatology |
| 13 | `stages/features_custom_csv.py` | Not started | — | User CSV hook (deferred indefinitely) |
| 14 | `stages/segmentation.py` | Locked | v0.14-segmentation | SNIC superpixels. 5-band z-scored input stack (B4, B8, composite NIRv, canopy_height, VV-VH). Same inputs across both configs |
| 15 | `stages/clustering.py` | Locked | v0.15-clustering | wekaKMeans on per-superpixel feature stack. Cyclic decomposition, log-transform skewed bands (DEC-004), median/IQR scaling (DEC-003), preprocessing params cached as asset property |
| 16 | `stages/profiling.py` | Locked | v0.16-profiling | Per-cluster feature stats in original units. Mean + IQR per band. Saved to CSV in run dir |
| 17 | `stages/export.py` | Locked | v0.17-export · extended v1.1.0 | v0.17: Drive GeoTIFF + run manifest (config, asset paths, clustering metadata, distribution). Asset inventory auto-discovered from the stage registry. v1.1.0: added two vector layers (`stands_snic`, `stands_dissolved`) in SHP + GeoJSON, configurable `drive_folder`, manifest moved from singular `drive_export` to `drive_exports` dict + new `vector_layers` section |
| 18 | `stages/metrics.py` | Locked | v1.0.0 | ARI / NMI / silhouette / Hungarian correspondence / agreement map. The actual research deliverable |

Pipeline is at v1.1.0 with all 11 runtime stages implemented and tested. v1.1.0 extends the export stage with vector outputs (per mentor request: vectorized stands with per-stand attributes), adds masking source toggles, and makes the harmonic-regression reference epoch configurable. Module 13 (custom CSV hook) is deferred; no current use case.
