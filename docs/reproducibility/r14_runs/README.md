# Round 14's runs: where each piece lives

The index the round 14 brief asks for ("Keep every run's data"): for each run of the round, its
records in the repo, its files off git (with SHA-256), its Drive files and its Earth Engine assets.
The round's record: `docs/handoff/2026-10-26-round14.md`.

Round 14 ran one batch, the live check (Task 4: `r14_live_check`, 27 Oct 2026, from the run tree
`outputs/round14/run_tree` at `2335d17`). Both of its runs computed their features and
segmentation from scratch and then stopped in their k_elbow pass, in the merge (the record: Done,
Task 4; Blocked). So they have no k_elbow, clustering or export pass: no stand layers, no stage
files, no run record of the export pass and no Drive export. The nineteen `_r14` configs of R3 have
not run.

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
