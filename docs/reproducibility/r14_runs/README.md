# Round 14's runs: where each piece lives

The index the round 14 brief asks for ("Keep every run's data"): for each run of the round, its
records in the repo, its files off git (with SHA-256), its Drive files and its Earth Engine assets.
The round's record: `docs/handoff/2026-10-26-round14.md`.

Round 14 has run six batches: two live checks (Task 4), a smoke test, R3's two halves, and the third
live check (below). R3 is the eighteen `_r14` configs other than the 10 km tile, which Jaskaran dropped
from R3 before it ran (to run later): its first half (`r14_first_half`, 28 Oct 2026, from
`outputs/round14/run_tree_5` at `a099c57`) ran them through the k elbow, and its second half
(`r14_second_half`, 28 Oct 2026, from the same run tree moved to `11c700b`, the commit with each
config's k) through clustering, profiling and export. The first live check (`r14_live_check`, 27 Oct 2026, from the run tree `outputs/round14/run_tree` at
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
`_check_d`'s `features_raw.tif`, still running at the one reading (2 of the 6 work units of "Create
Local Files" from 15:29 UTC on 27 Oct) and cancelled by the round on 28 Oct at 00:35 IST (task
`PJQU2YNYL6ZAYGAMZ3PHAXDX`, CANCELLED at 00:40; `r14_smoke_test_cancelled_exports.json`), not sent
again (`_check_c`'s is there, and `_check_d`'s features are cached on Earth Engine).

**On Earth Engine** (kept), under `projects/replicating-paper/assets/fmu/<run>/`: the second
check's features and segmentation assets, read back (the keys above), and, made by the smoke test,
the same keys in both runs: `k_elbow/k_elbow__s91032dcd75` (the elbow table; read back by rule 4),
`clustering/cluster_labels__s36138a6cce` and `clustering/feature_stack__s36138a6cce`.

**In the run tree only** (`outputs/round14/run_tree_3`, git-ignored, with its own `.env`; not to
be copied anywhere): the same files in `runs/<run>_<time>/`, and the two Drive readings, made
read-only.

## R3's first half: the nineteen `_r14` configs through the k elbow

**In the repo**, `docs/reproducibility/r14_runs/first_half/`, per run (13 files), copied with
`scripts/copy_run_results.py --through k_elbow` as each part of the elbow report is made
(`odisha_script/r14_first_half/report_part.sh`; after the batch, `after_batch.sh`): the manifests
of its three passes (`<run>_manifest_<kind>.json`: features, segmentation, k_elbow), each pass's
`fmu.log` (`<run>_log_<kind>.txt`), the features pass's `input_images.json`
(`<run>_input_images_features.json`), and the k elbow's five files and run record
(`<run>_k_elbow.csv`, `_k_elbow_stand_table.csv`, `_k_elbow_fit_rows.csv`, `_k_elbow_types.csv`,
`_k_elbow_preprocessing.json`, `_k_elbow_run.json`). Beside them: `cost_<run>.json` and
`cost_<run>_run.json`. The eighteen (28 Oct): the ten of part 1 (Sanjay Van and the 3 ha boxes,
both arms) and the eight of part 2 (the 10 ha boxes, both arms). The hand-crafted Koraput 10 ha
box needed the wrapper's second pass (its first segmentation pass hung and was stopped by hand; the
round 14 record, Done, the elbow report, part 2): 15 files, its first features pass's manifest, log
and image list as `_manifest_features_1.json`, `_log_features_1.txt` and
`_input_images_features_1.json`. A config the batch does not finish is copied into
`first_half/unfinished/` instead, which the elbow report does not read; the tile, dropped from R3,
was stopped before its run folder, so it has no record: only `cost_<tile>.json` and its `_run.json`,
whose 0.0132 EECU-hours are the project's online use over the tile's two stage spans, not the
tile's (the round 14 record, Done, the full elbow report).

**The elbow report** (Task 6), in `odisha_script/keptland_scores/`: part 1,
`r14_elbow_part1_report.md`, `r14_elbow_part1.csv`, six figures in `r14_elbow_part1/`, and
`r14_elbow_part1_run.json`; part 2, over the eighteen, `r14_elbow_part2_report.md`,
`r14_elbow_part2.csv`, eleven figures in `r14_elbow_part2/`, and `r14_elbow_part2_run.json`; the
full report, after the batch, `r14_elbow_report.md`, `r14_elbow.csv`, eleven figures in
`r14_elbow/`, and `r14_elbow_run.json` (part 2 under the brief's names, byte for byte but the stem).

**Off git:** none so far (no file over 5 MB; the largest, AlphaEarth Koraput's
`_k_elbow_stand_table.csv`, 2.2 MB). A file over 5 MB goes to `outputs/round14/results/first_half/`,
its size and SHA-256 in `<run>_files_off_git.json`.

**On Drive:** nothing (the first half stops before the export pass).

**On Earth Engine** (kept), under `projects/replicating-paper/assets/fmu/<run>/`: the features,
segmentation and k elbow assets, each run's keys in its manifests.

**In the run tree only** (`outputs/round14/run_tree_5`, git-ignored, with its own `.env`; not to
be copied anywhere): the same files in `runs/<run>_<time>/`.

## R3's second half: the eighteen through clustering, profiling and export

**In the repo**, `docs/reproducibility/r14_runs/second_half/`, per run, copied with
`scripts/copy_run_results.py` (export mode) by the scorer as each set was exported, and again after
the batch with the Drive states (`odisha_script/r14_second_half/after_batch.sh`): the three stand
layers (`<run>_stands_merged.geojson`, `_stands_snic.geojson`, `_stands_dissolved.geojson`, but those
off git), the run record (`<run>_run.json`, without its run folder), `<run>_raster_at_plots.csv`, every
pass's manifest, `fmu.log` and image list of both halves (`<run>_manifest_<kind>.json`,
`_log_<kind>.txt`, `_input_images_<kind>.json`: the second half's passes under the plain names, the
first half's, which computed the cache, as `_1`), the clustering's files (`_clustering_stand_table.csv`,
`_clustering_fit_rows.csv`, `_clustering_kmeans.json`), the k elbow's files and run record, and how its
Drive exports ended (`<run>_drive_exports.json` and its `_run.json`). Beside them: `cost_<run>.json` and
`cost_<run>_run.json` (each config's batch tasks to date, both halves', and this batch's online use)
and `second_half_cost_shares.json` (each config's second-half share: 1.7577 EECU-hours in all).

**The scores** (Task 8), in `odisha_script/keptland_scores/`: for each set, the field check
(`keptland_<set>_r14_scores.json`, `_scores.txt`, `_joined.csv`, `_scores_run.json`) and its chance
test (`keptland_<set>_r14_chance.json`, `_chance.txt`, `_chance_run.json`; its `.log` beside them,
ignored by git), the sets `s1desc` and `alphaearth` at 3 ha and `s1desc_10ha` and `alphaearth_10ha`;
the sixteen side-by-side tables (`keptland_*_r14_beside_*.md` and `keptland_*_r14_chance_beside_*.md`);
Sanjay Van's description (`sanjay_van_r14_description.md`, `.json`, `_run.json`); and the
distance-to-water check (`sanjay_van_r14_water_cap_check.md`, `.json`, `_run.json`).

**Off git** (over 5 MB), in `outputs/round14/results/second_half/`, each named with its size and
SHA-256 in its run's `<run>_files_off_git.json`, and backed up to Drive (below): the superpixel layers
(`_stands_snic.geojson`) of the Dhenkanal, Kendujhar and Koraput 3 ha boxes and of the Koraput 10 ha
boxes, in both arms, and the merged layers (`_stands_merged.geojson`) of the Koraput 3 ha boxes in both
arms: ten files, 107,323,793 bytes.

**On Drive:** each run's export, nine files (the type raster, the raw and scaled feature rasters, and
the three vector layers as GeoJSON and Shapefile), every one COMPLETED; their names, folders and task
ids in each `<run>_drive_exports.json`. The ten files off git, copied to `fmu_results_backup/round14`,
each copy's SHA-256 checked: `docs/reproducibility/r14_runs/off_git_backup_second_half.json` (with each
copy's Drive file id; its `_run.json` beside it), and each entry of the off-git records holds its copy's
Drive path (`"drive"`).

**On Earth Engine** (kept), under `projects/replicating-paper/assets/fmu/<run>/`: the features,
segmentation, k elbow and clustering assets (`cluster_labels`, `feature_stack`), each run's keys in its
manifests.

**In the run tree only** (`outputs/round14/run_tree_5`, git-ignored, with its own `.env`; not to be
copied anywhere): the same files in `runs/<run>_<time>/` and `odisha_script/phase2_vectors/`.

## The third live check: `_check_e` and `_check_f`, from scratch, after R3's second half

The batch `r14_live_check_3` (28 Oct 2026, from `outputs/round14/run_tree_4` at `da20741`): both runs
computed every stage from scratch in pass 1, and the check passes every criterion (the round 14 record,
Done, the third live check).

**In the repo**, `docs/reproducibility/r14_runs/live_check_3/` (64 files), copied with
`scripts/copy_run_results.py` (export mode) by `odisha_script/r14_live_check_3/after_batch.sh`: each
run's three stand layers, run record, `raster_at_plots.csv`, every pass's manifest, `fmu.log` and image
list, the clustering's and the k elbow's files, and its Drive states (`<run>_drive_exports.json` and
its `_run.json`); the cost files (`cost_<run>.json`, `_run.json`); the check's verdict
(`r14_live_check.json` and `_run.json`); and the record of the Drive exports not ended at the reading,
none (`r14_live_check_3_cancelled_exports_<run>.json`).

**Off git:** none (no file over 5 MB).

**On Drive:** each run's nine exports, all COMPLETED (in each `<run>_drive_exports.json`).

**On Earth Engine** (kept), under `projects/replicating-paper/assets/fmu/<run>/`: every stage's
assets, computed from scratch.

**In the run tree only** (`outputs/round14/run_tree_4`, git-ignored, with its own `.env`; not to be
copied anywhere): the same files in `runs/<run>_<time>/` and `odisha_script/phase2_vectors/`.
