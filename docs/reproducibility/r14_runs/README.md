# Round 14's runs: where each piece lives

The index the round 14 brief asks for ("Keep every run's data"): for each run of the round, its
records in the repo, its files off git (with SHA-256), its Drive files and its Earth Engine assets.
The round's record: `docs/handoff/2026-10-26-round14.md`.

Round 14 has run three batches: two live checks (Task 4) and a smoke test; the nineteen `_r14`
configs of R3 have not run. The first (`r14_live_check`, 27 Oct 2026, from the run tree `outputs/round14/run_tree` at
`2335d17`): both runs computed their features and segmentation from scratch and then stopped in
their k_elbow pass, in the merge. The second, after the merge's fix (`r14_live_check_2`, 27 Oct 2026,
from `outputs/round14/run_tree_2` at `2248184`): both runs computed their features, segmentation and
k elbow from scratch, and then the k elbow's cache table export failed on Earth Engine. Neither has a
clustering or export pass: no stand layers, no Drive export (the record: Done, Task 4; Blocked).
The smoke test (`r14_smoke_test`, 27 Oct 2026, from `outputs/round14/run_tree_3` at `d2fe144`), after
the table's fix, finished `_check_c` and `_check_d` from what the second check cached: their
features and segmentation read back, the k elbow made again, then clustering and export; it passed
(the record: Done, the round resumed again). It is not the live check.

## The live check: `odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_a` and `_check_b`

**In the repo**, `docs/reproducibility/r14_runs/live_check/`, per run (16 files): every pass's
manifest (`<run>_manifest_features_1.json`, the first, from scratch; `_features_2.json` and
`_features.json`, the second and third passes, which read it back; the same for segmentation),
each pass's `fmu.log` (`<run>_log_<kind>[_n].txt`; the three k_elbow passes, which failed before
writing a manifest, as `<run>_log_failed_1.txt` to `_3.txt`), and the first features pass's
`input_images` (`<run>_input_images_features_1.json`). Copied with `scripts/copy_run_results.py`'s
own `copy()`, its passes needed set to features and segmentation (its two modes ask for the
elbow's or the export's files); the manifests stripped of timings, every file checked for times.
Beside them: `cost_<run>.json` and `cost_<run>_run.json` (`scripts/eecu_by_stage.py`), and the
check's own `r14_live_check.json` (results only) and `r14_live_check_run.json`, made offline.

**Off git:** none (no file over 5 MB), so nothing to back up to Drive.

**On Drive:** none (no export pass).

**On Earth Engine** (kept, deleted by nothing), under
`projects/replicating-paper/assets/fmu/<run>/`, the same keys in both runs (the per-step layout),
each exported by the run's first pass of its kind:

| Stage / output | Asset (`<stage>/<output>__<key>`) |
|---|---|
| masking / habitat_mask, landcover_summary, mask_provenance, water_mask | `masking/<output>__s073c13df8c` |
| data_load / s2_composite | `data_load/s2_composite__s9249226467` |
| features_optical / optical_features | `features_optical/optical_features__s4ef0426c2c` |
| features_radar / radar_features | `features_radar/radar_features__s7bb26d198c` |
| features_structure / structure_features | `features_structure/structure_features__sc823e0cc39` |
| features_static / static_features | `features_static/static_features__s7483f4391a` |
| segmentation / snic_clusters, snic_means | `segmentation/<output>__s8d87a8f213` |

**In the run tree only** (`outputs/round14/run_tree`, git-ignored, with its own `.env`; not to be
copied anywhere): the same files in `runs/<run>_<time>/`; nothing else of these runs.

## The second live check: `odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_c` and `_check_d`

**In the repo**, `docs/reproducibility/r14_runs/live_check_2/`, per run (13 files), copied with
`scripts/copy_run_results.py --through k_elbow`: the manifests of the features, segmentation and
k elbow passes (`<run>_manifest_<kind>.json`), each pass's `fmu.log` (`<run>_log_<kind>.txt`), the
features pass's `input_images`, the k elbow's five files (`<run>_k_elbow.csv`, `_k_elbow_stand_table.csv`,
`_k_elbow_fit_rows.csv`, `_k_elbow_types.csv`, `_k_elbow_preprocessing.json`) and its run record
(`<run>_k_elbow_run.json`). Beside them: `cost_<run>.json` and `cost_<run>_run.json`, and the check's
`r14_live_check.json` and `r14_live_check_run.json`, made offline.

**Off git:** none (no file over 5 MB). **On Drive:** none (no export pass).

**On Earth Engine** (kept), under `projects/replicating-paper/assets/fmu/<run>/`, the same keys in
both runs, each exported by the run's first pass of its kind: the features and segmentation assets
of the table above, with the same keys (`masking/<output>__s073c13df8c`,
`data_load/s2_composite__s9249226467`, `features_optical/optical_features__s4ef0426c2c`,
`features_radar/radar_features__s7bb26d198c`, `features_structure/structure_features__sc823e0cc39`,
`features_static/static_features__s7483f4391a`, `segmentation/<output>__s8d87a8f213`). The k elbow's
table (`k_elbow/k_elbow__s91032dcd75`) does not exist: its export failed.

**In the run tree only** (`outputs/round14/run_tree_2`, git-ignored, with its own `.env`; not to be
copied anywhere): the same files in `runs/<run>_<time>/`.

## The smoke test: `_check_c` and `_check_d` finished through clustering and export

**In the repo**, `docs/reproducibility/r14_runs/smoke_test/`, per run (26 files), copied with
`scripts/copy_run_results.py` (export mode): the manifests of the five passes
(`<run>_manifest_<kind>.json`: features and segmentation, which read the second check's assets
back; k_elbow, clustering and export, which made theirs), each pass's `fmu.log`
(`<run>_log_<kind>.txt`), the k elbow's five files and run record, the clustering stage's three
(`<run>_clustering_stand_table.csv`, `_clustering_fit_rows.csv`, `_clustering_kmeans.json`), the
export pass's run record (`<run>_run.json`), its three stand layers (`<run>_stands_merged.geojson`,
`_stands_snic.geojson`, `_stands_dissolved.geojson`), `<run>_raster_at_plots.csv`, and the one
reading of its Drive states (`<run>_drive_exports.json`, read-only, and `_drive_exports_run.json`).
Beside them: `cost_<run>.json` and `cost_<run>_run.json`; the verdict, `r14_smoke_test.json`
(results only) and `r14_smoke_test_run.json`; rule 4's `r14_smoke_test_elbow_read_back.json`;
rule 5's `r14_smoke_test_live_check_rules.json` and `_run.json`; the elbows beside the second
check's, `r14_smoke_test_elbows_beside_the_second_check.json`; read-only call 13's
`r14_k_elbow_assets_before.json`; and, once the round has cancelled the export not ended at the
reading, `r14_smoke_test_cancelled_exports.json` and `_run.json`.

**Off git:** none (no file over 5 MB; the largest, `<run>_stands_snic.geojson`, 2.6 MB).

**On Drive**, folder `fmu_exports_kept_land_s1desc`, per run nine files: `<run>_cluster_labels.tif`,
`_features_raw.tif`, `_features_scaled.tif`, and each of the three stand layers as `.geojson` and
as a zipped shapefile (`.zip`); their task ids in `<run>_drive_exports.json`. All completed but
`_check_d`'s `features_raw.tif`, still running at the one reading and cancelled by the round, not
sent again (`_check_c`'s is there, and `_check_d`'s features are cached on Earth Engine).

**On Earth Engine** (kept), under `projects/replicating-paper/assets/fmu/<run>/`: the second
check's features and segmentation assets, read back (the keys above), and, made by the smoke test,
the same keys in both runs: `k_elbow/k_elbow__s91032dcd75` (the elbow table; read back by rule 4),
`clustering/cluster_labels__s36138a6cce` and `clustering/feature_stack__s36138a6cce`.

**In the run tree only** (`outputs/round14/run_tree_3`, git-ignored, with its own `.env`; not to
be copied anywhere): the same files in `runs/<run>_<time>/`, and the two Drive readings, made
read-only.
