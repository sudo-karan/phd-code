# Module status

Tracks each module's state. ⏳ Not started · 🔍 Under review · 🔒 Locked.

A module is **Locked** when the code is read, has tests (fast + live where applicable), is documented, and is part of the smoke test. Modifications to locked modules need a new `decisions.md` entry.

**Build order ≠ runtime order.** This file is build order — what we'll work on next. Runtime order (what runs in a pipeline run) is in `docs/current_flow.md`.

| # | Module | Status | Locked at | Notes |
|---|---|---|---|---|
| 1 | Repo scaffold | 🔒 | v0.1-scaffold | Layout, pyproject, .env handling, .gitignore |
| 2 | `config.py` + baseline YAML | 🔒 | v0.2-config | Pydantic schema, locked baseline |
| 2 | `settings.py` | 🔒 | v0.2-config | Pydantic-settings, .env |
| 3 | `utils/logging.py` | 🔒 | v0.3-utils | Rich + per-run dirs |
| 3 | `utils/gee.py` | 🔒 | v0.3-utils | Init, safe_get_info, ROI loader, asset_path |
| 4 | `stages/base.py` | 🔒 | v0.4-stage | Stage contract, registry |
| 5 | `pipeline.py` | 🔒 | v0.5-orchestrator | Orchestrator + manifest |
| - | Voice pass cleanup | 🔒 | v0.5.1-voice | Knowledge moved to docs/design_notes.md |
| 6 | Asset caching (cross-cutting) | ⏳ | — | Stable asset paths; cache-first orchestrator; async export on miss; `use_cache` flag |
| 7 | `stages/masking.py` | 🔄 paused | — | Multi-source: WorldCover + JRC + Open Buildings + VIIRS. Locks AFTER caching is in place. |
| 8 | `stages/data_load.py` | 🔄 paused | — | S2 + S1 loading + cloud masking + static composite. Cacheable: `s2_composite`. |
| 9 | `stages/features_optical.py` | 🔄 paused | — | Harmonic regression on NDVI or NIRv. Single or dual harmonic + trend. Variant config for comparison. |
| 10 | `stages/features_radar.py` | 🔄 paused | — | S1 percentiles + IQR + VV-VH cross-pol contrast. No harmonics, no speckle filtering. |
| 11 | `stages/features_structure.py` | 🔄 paused | — | ETH canopy height + neighborhood stats (std, max). Improves on notebook's single-band approach. |
| 12 | `stages/features_static.py` | 🔄 paused | — | NASADEM (elevation, slope, aspect) + distance-to-water + CHIRPS rainfall climatology |
| 13 | `stages/features_custom_csv.py` | ⏳ | — | User CSV hook |
| 14 | `stages/segmentation.py` | 🔄 paused | — | SNIC superpixels. 5-band z-scored input stack (B4, B8, composite NIRv, canopy_height, VV-VH). Same inputs across both configs. |
| 15 | `stages/clustering.py` | 🔄 paused | — | wekaKMeans on per-superpixel feature stack. Cyclic decomposition, log-transform skewed bands (DEC-004), median/IQR scaling (DEC-003), preprocessing params cached as asset property. |
| 16 | `stages/profiling.py` | 🔄 paused | — | Per-cluster feature stats in original units. Mean+IQR per band. Saved to CSV in run dir. |
| 17 | `stages/export.py` | 🔄 paused | — | Drive GeoTIFF + comprehensive run manifest (config, asset paths, clustering metadata, distribution, decisions). |
| 18 | `stages/metrics.py` | 🔄 paused | — | ARI / NMI / silhouette / Hungarian correspondence / agreement map. The actual research deliverable. |

## Note on Module 7 (masking)

Module 7 (`stages/masking.py`) was originally Module 6 and is functionally complete (multi-source masking with WorldCover + JRC + Open Buildings + VIIRS, all tests passing). However, **rendering Open Buildings as a live rasterization hits GEE's per-tile memory limit at high zoom levels.** Locking masking is deferred until Module 6 (asset caching) is in place — once outputs cache as assets, the visualization issue goes away.
