# Round 9's Task G and H runs (run in round 10)

The re-runs of round 9's Task G (`docs/handoff/2026-10-17-round9.md`, run in round 10,
`docs/handoff/2026-10-18-round10.md`): each config a copy named `<name>_r9` that changes only the
name (`tests/test_r9_configs.py`), run from an empty cache in the per-step cache layout (round 9),
one config at a time, through `odisha_script/run_passes_safely.py`, from a clean run tree. Results
only, apart from each run's `_run.json` record; copied by `scripts/copy_run_results.py`, which
strips run times. Timings are in the logs on the Mac (`outputs/round10/logs/`), not here.

| Run | Copy of | Run tree at | Superpixels | Stands | Stand polygons |
|---|---|---|---|---|---|
| `odisha_v120_3ha_squares_angul_keptland_s1desc_r9` | `odisha_v120_3ha_squares_angul_keptland_s1desc` | `acb5f8d` | 1,205 | 221 | 219 |
| `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc_r9` | `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc` | `acb5f8d` | 2,889 | 552 | 552 |
| `odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r9` | `odisha_v120_3ha_squares_kendujhar_keptland_s1desc` | `fb8e8ce` | 2,747 | 547 | 547 |
| `odisha_v120_3ha_squares_koraput_keptland_s1desc_r9` | `odisha_v120_3ha_squares_koraput_keptland_s1desc` | `acb5f8d` | 8,743 | 1,616 | 1,616 |
| `sanjay_van_baseline_keptland_r9` | `sanjay_van_baseline_keptland` | `acb5f8d` | 1,205 | 583 | 578 |
| `sanjay_van_alphaearth_keptland_r9` | `sanjay_van_alphaearth_keptland` | `acb5f8d` | 1,205 | 565 | 560 |

Task H's AlphaEarth arm (the change of 18 Oct 2026 to `odisha_script/PHASE_KEPTLAND_PREDECLARED.md`):
each config a copy of the district's `_r9` run changing only the feature description to AlphaEarth
(`tests/test_r9_configs.py`), run the same way.

| Run | Copy of | Run tree at | Superpixels | Stands | Stand polygons |
|---|---|---|---|---|---|
| `odisha_alphaearth_3ha_squares_angul_keptland_r9` | `odisha_v120_3ha_squares_angul_keptland_s1desc_r9` | `fcfc169` | 1,205 | 237 | 235 |
| `odisha_alphaearth_3ha_squares_dhenkanal_keptland_r9` | `odisha_v120_3ha_squares_dhenkanal_keptland_s1desc_r9` | `fcfc169` | 2,889 | 574 | 570 |
| `odisha_alphaearth_3ha_squares_kendujhar_keptland_r9` | `odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r9` | `fcfc169` | 2,747 | 555 | 555 |
| `odisha_alphaearth_3ha_squares_koraput_keptland_r9` | `odisha_v120_3ha_squares_koraput_keptland_s1desc_r9` | `fcfc169` | 8,743 | 1,644 | 1,641 |

Kendujhar's re-run is round 9's Task D run 1 (`docs/reproducibility/round9_cache_test/`): its
files here are byte-for-byte copies of those, so that the field check reads all four districts
from one folder. Its features were computed by a features pass of its own before the wrapper
ran (`_manifest_features_computed.json`), so the wrapper's features pass found them cached.

The stands and stand polygons are from each run's record (`merge_diagnostics` and
`export_vector_layers`): a stand under `export.vector_min_stand_pixels` (4) pixels has no polygon.

| File | What |
|---|---|
| `<run>_stands_merged.geojson`, `_stands_snic.geojson`, `_stands_dissolved.geojson` | the run's stands, superpixels and same-type regions, as its export pass wrote them |
| `<run>_files_off_git.json` | where a run has a layer over 5 MB: its size, SHA-256 and where it is on the Mac (`outputs/round10/results/`; Kendujhar's in `outputs/round9/results/`) |
| `<run>_run.json` | the run record: merge diagnostics, per-stand attributes and provenance, export counts, cache layout, step keys, git, environment |
| `<run>_manifest_features.json`, `_segmentation`, `_clustering`, `_export` | the manifests of the wrapper's four passes; the features pass computed and exported every feature asset |
