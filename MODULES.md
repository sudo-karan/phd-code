# Module status

This file tracks every module in the package and its current state. Update this whenever a module is added, modified, or locked.

| # | Module | Status | Locked at version | Notes |
|---|---|---|---|---|
| 1 | Repo scaffold | ✅ In place | v0.1-scaffold | Directory layout, pyproject, env handling, .gitignore |
| 2 | `config.py` | ⏳ Not started | — | Pydantic v2 schema, YAML loader, .env integration |
| 3 | `utils/logging.py` | ⏳ Not started | — | Rich-based logger |
| 3 | `utils/gee.py` | ⏳ Not started | — | Auth wrapper, safe_get_info, common helpers |
| 4 | `stages/base.py` | ⏳ Not started | — | Stage abstract interface |
| 5 | `pipeline.py` (skeleton) | ⏳ Not started | — | Orchestrator with placeholder stages |
| 6 | Tests for 1–5 | ⏳ Not started | — | Config tests, smoke test |
| 7 | `stages/data_load.py` | ⏳ Not started | — | S2 + S1 loading, cloud masking |
| 8 | `stages/masking.py` | ⏳ Not started | — | Water, urban, non-veg masks |
| 9 | `stages/features_optical.py` | ⏳ Not started | — | NDVI/NIRv harmonics, amplitude, phase |
| 10 | `stages/features_radar.py` | ⏳ Not started | — | S1 VV/VH ratio + percentiles |
| 11 | `stages/features_structure.py` | ⏳ Not started | — | Lang canopy height + texture |
| 12 | `stages/features_static.py` | ⏳ Not started | — | Terrain, climate, disturbance |
| 13 | `stages/features_custom_csv.py` | ⏳ Not started | — | Bring-your-own-feature CSV ingestion |
| 14 | `stages/segmentation.py` | ⏳ Not started | — | SNIC |
| 15 | `stages/clustering.py` | ⏳ Not started | — | wekaKMeans with auto-K |
| 16 | `stages/profiling.py` | ⏳ Not started | — | Per-cluster centroids, area stats |
| 17 | `stages/export.py` | ⏳ Not started | — | GeoTIFF + GEE asset export |
| 18 | `metrics/stand_stats.py` | ⏳ Not started | — | Stand count, size distribution, variance |
| 19 | `metrics/weak_baselines.py` | ⏳ Not started | — | Kappa vs WorldCover, Dynamic World |
| 20 | `metrics/report.py` | ⏳ Not started | — | Per-run markdown report generator |

**Legend:** ⏳ Not started · 🚧 In progress · 🔍 Under review · ✅ In place · 🔒 Locked (frozen baseline)

## Locking policy

A module is "Locked" only when:
1. The code has been read and accepted by Jaskaran
2. It has at least one test
3. It is documented in the main README and `decisions.md`
4. It runs as part of the smoke test

Modules in "In place" status are functional and committed but not yet baseline-frozen. They can be modified freely.

Once a module is **Locked**, modifications require:
- A written justification (added to `decisions.md`)
- A new test or modification to existing tests
- A version bump

The point of locking is to prevent the "going in circles" pattern: settled decisions stay settled unless explicitly reopened.
