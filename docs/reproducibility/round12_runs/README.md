# Round 12's runs (Task 4: the 10 ha box runs; Task 5: the 30 km tile)

The runs of round 12 (`docs/handoff/2026-10-19-round12.md`), each from an empty cache in the
per-step cache layout, one config at a time, through `odisha_script/run_passes_safely.py`, from
the clean run tree `outputs/round12/run_tree` on the Mac. Results only, apart from each run's
`_run.json` record; copied by `scripts/copy_run_results.py`, which strips run times. Timings are
in the logs on the Mac (`outputs/round12/logs/`), not here.

Task 4, the 10 ha size check on the boxes, both arms (the change of 19 Oct 2026 to
`odisha_script/PHASE_KEPTLAND_PREDECLARED.md`): each config a copy of a 3 ha `_r9` box run
changing only `segmentation.size` (6 to 10) and `merge.max_area_ha` (3 to 10)
(`tests/test_r9_configs.py`).

| Run | Copy of | Run tree at | Superpixels | Stands | Stand polygons |
|---|---|---|---|---|---|
| `odisha_v120_10ha_squares_kendujhar_keptland_s1desc_r9` | `odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r9` | `3db501b` | 1,088 | 354 | 355 (352 stands) |
| `odisha_v120_10ha_squares_angul_keptland_s1desc_r9` | `odisha_v120_3ha_squares_angul_keptland_s1desc_r9` | `3db501b` | 466 | 136 | 134 |
| `odisha_v120_10ha_squares_koraput_keptland_s1desc_r9` | `odisha_v120_3ha_squares_koraput_keptland_s1desc_r9` | `3db501b` | 3,332 | 988 | 990 (983 stands) |
| `odisha_v120_10ha_squares_dhenkanal_keptland_s1desc_r9` | `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc_r9` | `3db501b` | 1,119 | 334 | 330 (329 stands) |
| `odisha_alphaearth_10ha_squares_kendujhar_keptland_r9` | `odisha_alphaearth_3ha_squares_kendujhar_keptland_r9` | `3db501b` | 1,088 | 352 | 350 |

| File | What |
|---|---|
| `<run>_stands_merged.geojson`, `_stands_snic.geojson`, `_stands_dissolved.geojson` | the run's stands, superpixels and same-type regions, as its export pass wrote them |
| `<run>_files_off_git.json` | where a run has a layer over 5 MB: its size, SHA-256 and where it is on the Mac (`outputs/round12/results/`) |
| `cost_<run>.json` (and `_run.json`) | the run's EECU-hours, batch by stage and online by pass, and per 1,000 ha (`scripts/eecu_by_stage.py`); the record holds the pass spans and when they were read |
| `<run>_run.json` | the run record: merge diagnostics, per-stand attributes and provenance, export counts, cache layout, step keys, git, environment |
| `<run>_manifest_features.json`, `_segmentation`, `_clustering`, `_export` | the manifests of the wrapper's four passes |
