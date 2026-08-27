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
| 14 | `stages/segmentation.py` | Locked · reworked v1.2.0 | v0.14-segmentation | SNIC superpixels. v1.2.0: input stack is **config-driven** (`segmentation.input_bands`), default six bands (B4, B8, canopy_height, canopy_height_std, ndvi_amplitude_annual, VV-VH) — `composite_nirv` dropped as an algebraic function of B4/B8, phenology and canopy roughness added. Boundaries are **no longer held identical across arms**: each arm segments on its own feature space. New `normalize_distance_scale` makes `compactness` comparable across stacks of different width |
| 14b | `stages/merge.py` | Locked | v1.2.0 | **NEW.** SNIC superpixels → forest stands, Xiong et al. 2024 §2.6: two passes, hard conjunctive gate on canopy_height / canopy_height_std / ndvi_amplitude_annual in physical units, hard area bounds, shared-edge fallback. Runs client-side over the adjacency graph, returns `snic_clusters.remap(...)`. Merge rule held identical across arms so delineation is the only difference. Not cached (thresholds are the iteration variable) |
| 15 | `stages/clustering.py` | Locked · reworked v1.2.0 | v0.15-clustering | wekaKMeans on the per-**stand** feature stack (per-superpixel when `merge.enabled: false`). Cyclic decomposition, log-transform skewed bands (DEC-004), median/IQR scaling (DEC-003), preprocessing params cached as asset property. v1.2.0: fits on **every unit, one row each** — `n_training_samples` retired, since a pixel sample area-weighted every statistic computed from it |
| 16 | `stages/profiling.py` | Locked | v0.16-profiling | Per-cluster feature stats in original units. Mean + IQR per band. Saved to CSV in run dir |
| 17 | `stages/export.py` | Locked | v0.17-export · extended v1.1.0 | v0.17: Drive GeoTIFF + run manifest (config, asset paths, clustering metadata, distribution). Asset inventory auto-discovered from the stage registry. v1.1.0: added two vector layers (`stands_snic`, `stands_dissolved`) in SHP + GeoJSON, configurable `drive_folder`, manifest moved from singular `drive_export` to `drive_exports` dict + new `vector_layers` section |
| 18 | `stages/metrics.py` | Locked · extended v1.2.0 | v1.0.0 | ARI / NMI / Hungarian correspondence / agreement map. v1.2.0: adds **stand geometry** (area distribution, Polsby-Popper, sub-minimum count, largest-decile area share) and **held-out explained variance R²** with `n_stands` beside it, computed at pixel level. Silhouette demoted from cross-arm headline to internal diagnostic — it is dimensionality-dependent and the arms have different feature spaces |

Pipeline is at v1.2.0 with all 13 runtime stages implemented and tested.

**v1.2.0 is a reframing, not an increment: SNIC + merge produces the stand, and
clustering is demoted to attaching a type label to a finished one.** It adds the
`merge` stage, makes the SNIC band stack config-driven, stops holding
segmentation identical across arms (that was called the experiment's control and
was in fact the flaw — it never put the delineation question to the embedding),
fits k-means on every stand rather than a pixel sample, adds stand-geometry and
held-out R² metrics, derives the `reduceConnectedComponents` cap instead of
hand-setting it, and keys cache assets on config *content* rather than name.

v1.1.0 extended the export stage with vector outputs (per mentor request:
vectorized stands with per-stand attributes), added masking source toggles, and
made the harmonic-regression reference epoch configurable. Module 13 (custom CSV
hook) is deferred; no current use case.
