# Module status

Tracks each module's state. ⏳ Not started · 🔍 Under review · 🔒 Locked.

A module is **Locked** when the code is read, has tests (fast + live where
applicable), is documented, and is part of the smoke test. Modifications to
locked modules need a new `decisions.md` entry.

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
| 6 | `stages/masking.py` | 🔍 | v0.6 (pending) | habitat_mask + water_mask + landcover_summary; first real GEE stage |
| 7 | `stages/data_load.py` | ⏳ | — | S2 + S1 loading + cloud masking |
| 8 | Asset caching (cross-cutting) | ⏳ | — | Hash-based asset caching across stages; team.yaml ACL |
| 9 | `stages/features_optical.py` | ⏳ | — | NDVI/NIRv harmonics |
| 10 | `stages/features_radar.py` | ⏳ | — | S1 VV/VH percentiles |
| 11 | `stages/features_structure.py` | ⏳ | — | Canopy height |
| 12 | `stages/features_static.py` | ⏳ | — | Terrain, climate, distance-to-water |
| 13 | `stages/features_custom_csv.py` | ⏳ | — | User CSV hook |
| 14 | `stages/segmentation.py` | ⏳ | — | SNIC |
| 15 | `stages/clustering.py` | ⏳ | — | wekaKMeans |
| 16 | `stages/profiling.py` | ⏳ | — | Per-cluster centroids |
| 17 | `stages/export.py` | ⏳ | — | GeoTIFF + GEE asset |
| 18 | `metrics/*` | ⏳ | — | Stand stats, weak baselines, run report |
