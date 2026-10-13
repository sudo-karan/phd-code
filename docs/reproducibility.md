# Reproducibility report: Odisha field validation, Phases 1, 2 and 3

Does each committed result file come out the same when its script is run again from a clean
checkout? This report has one row per committed result file under `odisha_script/`: the command
that writes it, and what happened when that command was run again.

## The answer

There are **170 committed result files** under `odisha_script/`.

- **42 reproduced exactly** (byte for byte).
- **14 differ.** No number differs in any of them except in the summary figures. The cause is
  demonstrated for each, with one part left open: why the one Phase 1 figure, identical in
  every pixel, is stored in a different number of bytes.
  - 6 text files differ only in lines that record run times: the Phase 2 pilot and full-set
    statistics and the four Phase 3 chance-test files. Every statistic in them is identical. (The four
    chance-test files have since been regenerated without their run times; see Problem 5.)
  - 1 Phase 1 text file was never regenerated after its script was changed to print a warning.
    No number differs.
  - 1 Phase 2 text file (the mask retention results) differs in the wording of its last line
    only. No number differs: 257 of 274 plots are kept, as committed.
  - 1 Phase 1 figure is the same picture, pixel for pixel, saved in a different software
    environment (the file names another Matplotlib version).
  - 1 Phase 3 text file is a hand-saved print of a check; the lines that differ name the git
    reference it was run against.
  - 4 Phase 3 summary figures differ because **the committed figures were drawn on
    24 September from the first Phase 3 analysis (PR #40) and were never redrawn after the
    results changed on 7 and 8 October.**
- **114 were not run.**
  - 105 need Earth Engine, which the offline check was not allowed to touch. 95 of them are the
    stand files and run records under `phase2_vectors/`. Those were not regenerated in place.
    Every config was instead re-run from scratch under a new name and compared: see "Earth
    Engine re-runs". None of the hand-crafted configs reproduces its committed stands exactly.
  - 4 summary figures could not be regenerated because their scripts stop with an
    error: they were written against the scripts and results of 24 September.
  - 4 are kept records of runs on stand files that no longer exist.
  - 1 is the deck's fact sheet, which no script writes. It was checked entry by entry.

**The main finding is about the summary deck, not the results.** The results files reproduce.
The eleven figures in `odisha_script/phase3_figures/`, the fact sheet `deck_facts.md` beside
them, and the deck builder `scripts/build_phase3_summary_deck.js` all show the state of
24 September (PR #40): the old field types, six stand types at 3 hectares, and the old scores.
They do not show the final results in `PHASE3_STATUS.md`. Details are in "Figures and deck
facts" below.

## How the check was done

- Every command was run in a clean clone of the repository at commit `a477ab1`, with no ignored
  files (no checkpoints, no caches), from the clone's root with the clone's own code on the
  path. Nothing was run in the working tree.
- After each command, `git status` and `git diff` in the clone show which committed files the
  command changed and how. A file the script rewrote and git reports as unchanged is
  "reproduced exactly".
- For every file that differs, the cause was tested, not guessed: by running an older version
  of the script, by comparing pixels, or by reading `git log -p` for the file. Each row says
  what the test was. Where a cause could not be shown, the row says "not established".
- Nothing here touched Earth Engine. A script that needs it is "not run".
- The inventory is `git ls-files odisha_script` on the work branch: 212 files (the 210 of
  `a477ab1` and two scripts added since, which write no result file here), of which 170 are
  results (anything a script writes, plus the deck's fact sheet), 34 are scripts,
  6 are write-ups and 2 are inputs (`Odisha_samples.csv`,
  `Odisha_sites.csv`). Every result file is in exactly one row below. The stand files under
  `phase2_vectors/` are grouped by config family.
- Machine used tonight: macOS, Python 3.13, Matplotlib 3.11.0, NumPy 2.5.1, SciPy 1.18.0,
  scikit-learn 1.9.0, pandas 3.0.3.

An outcome is one of three:

- **reproduced exactly**: the regenerated file is byte-identical to the committed one.
- **differs**: it is not, and the Detail column says how and why.
- **not run**: the command was not run, or stopped before writing the file. The Detail column
  says why.

## A second, independent check

The report above was then checked by a second agent, which did the following.

- **Inventory.** Listed `git ls-files odisha_script` again and matched every result file to a
  row: 170 result files, each in exactly one row, none missing.
- **Spot re-runs in a new clean clone** (`a477ab1`). For each command below the committed
  output files were deleted first, so a file that comes back identical was certainly written
  by the command. All 14 commands exited 0, wrote every file they should, and left
  `git status` empty: all 21 files **reproduced exactly**, and each command is complete and
  correct as written in the tables.
  - Phase 1 (from inside `odisha_script/`): `odisha_phase1_0_clean.py`,
    `odisha_phase1_2_analyse.py`, `odisha_phase1_6_closeout.py`,
    `odisha_phase1_11_survey_date_check.py`.
  - Phase 2: `odisha_phase2_0_aois.py`, `odisha_phase2_3_join.py --set pilot`,
    `odisha_phase2_3_join.py --set districts`.
  - Phase 3: `odisha_phase3_0_field_structure_types.py --k 4`,
    `odisha_phase3_2_stand_k_elbow.py --arm odisha_v120_handcrafted`,
    `odisha_phase3_1_pairwise_score.py --arm v120`, the same script for the 3 hectare stands
    with and without `--exclude-types 0`, `odisha_phase3_4c_sizes.py`, and the 3 hectare join
    into `phase3_3ha/`.
  - Skipped as too long: the chance tests and the Phase 2 statistics.
- **The rows marked "differs".** The Phase 1 text file: the old script (`5271ea5`) was run
  again in the new clone with the two committed outputs deleted, and wrote both back byte for
  byte. The Phase 1 figure: pixels compared again (none differs); the stored image data is a
  different size, and the cause of that is now marked "not established" (the first draft
  said the Matplotlib version; that was not shown). The run-time rows: every changed line was
  read, and each differs only in its seconds. The hand-saved check: compared line by line.
- **The figures.** The committed `chance_test.png`, `summary_scores.png`,
  `structure_boxplots.png`, `elbow_stands.png` and `method_steps.png` were opened and read
  against the results files regenerated tonight. They print 0.024 / 0.035 / 0.025 / 0.056,
  "0.074", type sizes 15 / 47 / 78 / 114 / 20 and "6 types"; the regenerated files say
  0.0257 / 0.0389 / 0.0244 / 0.0793, 0.0756 and 0.0887, sizes 15 / 53 / 77 / 111 / 18, and
  5 stand types at 3 hectares (elbow 5 in every district; `k: 5` in the 3 hectare configs).
  **The statement stands: the figures and the fact sheet show the earlier state (PR #40), not
  the final results.** One correction: there are eleven figures, not twelve, and nine of the
  eleven (not ten of twelve) come back byte for byte from PR #40's data.

## Earlier check, on another machine

These were done on 2026-10-13 by Claude (chat) on a different machine, before tonight's run.
They are recorded from the handoff brief and were not observed again here. Tonight's run on
this machine covers the same files in the Phase 3 table.

| File | Command | Outcome | Detail |
|---|---|---|---|
| the 6 `odisha_phase3_0_*` field-type files, the 8 `odisha_phase3_1_score_*` files, the 2 `odisha_phase3_2_k_elbow_*` files | the "Reproducing" commands of `PHASE3_STATUS.md`, on a fresh copy | **reproduced exactly** | All 16 files regenerated byte-identically. Recorded from the handoff brief; not re-observed here. Tonight's re-run on this machine is in the Phase 3 table and agrees. |
| `odisha_phase3_3_results.txt` | `python odisha_script/odisha_phase3_3_significance.py`, clean checkout of `phase3-consistency` | **differs** | Every statistic identical; only the two lines recording run times differed. Recorded from the handoff brief. |
| the six headline scores of the write-up's table | scikit-learn `adjusted_rand_score` directly, none of the repo's scoring code | **reproduced exactly** | All six match: 10 hectares 0.0121 / 0.0257 / 0.0389, 3 hectares 0.0060 / 0.0244 / 0.0793. Recorded from the handoff brief. Tonight's regenerated score files print the same six values. |

## Phase 1

Commands are run from inside `odisha_script/`. `PHASE1_STATUS.md`, "Reproducing", lists only
steps 7 to 11; the commands for steps 0 to 6 are from the scripts themselves.

| File | Command | Outcome | Detail |
|---|---|---|---|
| `odisha_plots_clean.csv` | `cd odisha_script && python odisha_phase1_0_clean.py` | **reproduced exactly** |  |
| `odisha_plots_sampled.csv` | `cd odisha_script && python odisha_phase1_1_sample_gee.py` | **not run** | Needs Earth Engine, which this check was not allowed to touch. |
| `odisha_phase1_results.txt` | `cd odisha_script && python odisha_phase1_2_analyse.py` | **reproduced exactly** |  |
| `odisha_phase1_figs.png` | `cd odisha_script && python odisha_phase1_2_analyse.py` | **reproduced exactly** |  |
| `odisha_plots_sampled_v2.csv` | `cd odisha_script && python odisha_phase1_3_sample_gee_v2.py, then odisha_phase1_5_meta_rerun.py (rewrites the file in place)` | **not run** | Needs Earth Engine, which this check was not allowed to touch. |
| `odisha_phase1_tests456_results.txt` | `cd odisha_script && python odisha_phase1_4_analyse_v2.py` | **differs** | No number differs. One line of the committed file is replaced by five. The committed file was written by the first version of the script (commit 5271ea5). Commit 36a0c73 then changed the script to print both GEDI counts and a warning that they disagree (0 against 10), and the results file was not regenerated. Tested: the 5271ea5 version of the script, run in a fresh clone on today's inputs, writes the committed file byte for byte. |
| `odisha_phase1_tests456_figs.png` | `cd odisha_script && python odisha_phase1_4_analyse_v2.py` | **reproduced exactly** |  |
| `odisha_phase1_closeout.txt` | `cd odisha_script && python odisha_phase1_6_closeout.py` | **reproduced exactly** |  |
| `odisha_phase1_7_results.txt` | `cd odisha_script && python odisha_phase1_7_meta_zero_diagnosis.py` | **not run** | Part B needs Earth Engine, and the script starts it whenever credentials are present, so the script was not run as a whole. Part A is offline and was run on its own (the module imported, `part_a` called, Earth Engine never imported): its 182 lines are identical to the first 182 lines of the committed 383-line file. Part B (the other 201 lines) was not run. |
| `odisha_phase1_8_results.txt` | `cd odisha_script && python odisha_phase1_8_separation_null.py` | **reproduced exactly** |  |
| `odisha_phase1_8_separation_null.png` | `cd odisha_script && python odisha_phase1_8_separation_null.py` | **differs** | The picture is the same: all 1,430,550 pixels are identical. The committed PNG was saved in a different software environment: its `Software` text field says Matplotlib 3.11.1, this machine has 3.11.0, and every other committed figure says 3.11.0. The compressed image data also differs (91,170 bytes committed, 78,555 regenerated). Which part of that other environment compresses the same pixels differently is not established. |
| `odisha_phase1_9_results.txt` | `cd odisha_script && python odisha_phase1_9_gedi_recount.py` | **not run** | Needs Earth Engine, which this check was not allowed to touch. |
| `odisha_plots_sampled_v3.csv` | `cd odisha_script && python odisha_phase1_9_gedi_recount.py` | **not run** | Needs Earth Engine, which this check was not allowed to touch. |
| `odisha_phase1_10_results.txt` | `cd odisha_script && python odisha_phase1_10_meta_offset_check.py` | **not run** | Needs Earth Engine, which this check was not allowed to touch. |
| `odisha_phase1_11_results.txt` | `cd odisha_script && python odisha_phase1_11_survey_date_check.py` | **reproduced exactly** |  |

## Phase 2

Commands are run from the repo root.

| File | Command | Outcome | Detail |
|---|---|---|---|
| `odisha_phase2_0_results.txt` | `python odisha_script/odisha_phase2_0_aois.py` | **reproduced exactly** | The study-area files it also writes under `aois/` came out unchanged too. |
| `odisha_phase2_1_results.txt` | `python odisha_script/odisha_phase2_1_mask_retention.py` | **differs** | Needs Earth Engine (read-only: four requests, nothing submitted). Regenerated in a clean clone of `1da0614` for the task 2 maps. No number differs: 257 of 274 plots kept, and every table is the same. One line differs, the last, and only in wording: the committed file ends "Proceed to step 2.", the script now writes "Proceed to the pipeline run (odisha_phase2_2_run_pipeline.py)." The committed file was not replaced. |
| `odisha_phase2_1_mask_retention.csv` | `python odisha_script/odisha_phase2_1_mask_retention.py` | **reproduced exactly** | Same run as the row above. Byte-identical. |
| phase2_vectors/odisha_v120_3ha_<district>_* (20 files: 4 districts x raster_at_plots.csv, run.json, stands_snic / stands_merged / stands_dissolved.geojson) | `bash odisha_script/run_config_passes.sh <logfile> configs/odisha_v120_3ha_<district>.yaml` | **not run** | Needs Earth Engine. A from-scratch re-run under `_repro` config names is queued tonight; the comparison with these committed files will be added by the orchestrator in the Earth Engine section below. |
| phase2_vectors/odisha_v120_handcrafted_<district>_* (20 files, same five kinds) | `python odisha_script/odisha_phase2_2_run_pipeline.py --config configs/<config>.yaml --through segmentation --wait; then --through clustering --wait; then --through export` | **not run** | Needs Earth Engine. A from-scratch re-run under `_repro` config names is queued tonight; the comparison with these committed files will be added by the orchestrator in the Earth Engine section below. |
| phase2_vectors/odisha_alphaearth_<district>_* (20 files, same five kinds) | `python odisha_script/odisha_phase2_2_run_pipeline.py --config configs/<config>.yaml --through segmentation --wait; then --through clustering --wait; then --through export` | **not run** | Needs Earth Engine. A from-scratch re-run under `_repro` config names is queued tonight; the comparison with these committed files will be added by the orchestrator in the Earth Engine section below. |
| phase2_vectors/odisha_current_handcrafted_<district>_* (20 files, same five kinds) | `python odisha_script/odisha_phase2_2_run_pipeline.py --config configs/<config>.yaml --through segmentation --wait; then --through clustering --wait; then --through export` | **not run** | Needs Earth Engine. Not among the configs being re-run tonight. |
| phase2_vectors/odisha_v120_handcrafted_*, odisha_current_handcrafted_*, odisha_alphaearth_* without a district (15 files: the three pilot configs x the same five kinds) | `python odisha_script/odisha_phase2_2_run_pipeline.py --config configs/<config>.yaml --through segmentation --wait; then --through clustering --wait; then --through export` | **not run** | Needs Earth Engine. Not among the configs being re-run tonight. |
| `odisha_phase2_3_results.txt` | `python odisha_script/odisha_phase2_3_join.py --set pilot` | **reproduced exactly** |  |
| `phase2_plots_joined.csv` | `python odisha_script/odisha_phase2_3_join.py --set pilot` | **reproduced exactly** |  |
| `odisha_phase2_3_results_districts.txt` | `python odisha_script/odisha_phase2_3_join.py --set districts` | **reproduced exactly** |  |
| `phase2_plots_joined_districts.csv` | `python odisha_script/odisha_phase2_3_join.py --set districts` | **reproduced exactly** |  |
| `odisha_phase2_4_results.txt` | `python odisha_script/odisha_phase2_4_noise_null.py --size-check 3` | **not run** | Needs Earth Engine, which this check was not allowed to touch. |
| `odisha_phase2_5_results.txt` | `python odisha_script/odisha_phase2_5_stats.py --set pilot` | **differs** | Every statistic identical. 10 lines differ and all 10 are run times: the nine `rotation null: 1999 realisations ...; N s; ...` lines (one per stand layer) and the last line, `total runtime N s`. With the seconds masked the two files are the same. |
| `odisha_phase2_5_summary.csv` | `python odisha_script/odisha_phase2_5_stats.py --set pilot` | **reproduced exactly** |  |
| `odisha_phase2_5_primary_r2_null.png` | `python odisha_script/odisha_phase2_5_stats.py --set pilot` | **reproduced exactly** |  |
| `odisha_phase2_5_arms_excess.png` | `python odisha_script/odisha_phase2_5_stats.py --set pilot` | **reproduced exactly** |  |
| `odisha_phase2_5_pairwise_bands.png` | `python odisha_script/odisha_phase2_5_stats.py --set pilot` | **reproduced exactly** |  |
| `odisha_phase2_5_results_districts.txt` | `python odisha_script/odisha_phase2_5_stats.py --set districts --jobs 4` | **differs** | Run-time fields only: the nine `rotation null:` lines carry the seconds each null took and the last line the total. With the seconds masked the file is the same as the committed one, so every statistic is identical. Run here with `--jobs 3`; the partitions are seeded by name, so the number of workers does not change a result. |
| `odisha_phase2_5_summary_districts.csv` | `python odisha_script/odisha_phase2_5_stats.py --set districts --jobs 4` | **reproduced exactly** | Same run as the row above (`--jobs 3`). |
| `odisha_phase2_5_primary_r2_null_districts.png` | `python odisha_script/odisha_phase2_5_stats.py --set districts --jobs 4` | **reproduced exactly** | Same run as the row above (`--jobs 3`). |
| `odisha_phase2_5_arms_excess_districts.png` | `python odisha_script/odisha_phase2_5_stats.py --set districts --jobs 4` | **reproduced exactly** | Same run as the row above (`--jobs 3`). |
| `odisha_phase2_5_pairwise_bands_districts.png` | `python odisha_script/odisha_phase2_5_stats.py --set districts --jobs 4` | **reproduced exactly** | Same run as the row above (`--jobs 3`). |
| `odisha_phase2_6_results.txt` | `python odisha_script/odisha_phase2_6_label_drift.py` | **not run** | Needs Earth Engine, which this check was not allowed to touch. |
| `odisha_phase2_6_plot_labels.csv` | `python odisha_script/odisha_phase2_6_label_drift.py` | **not run** | Needs Earth Engine, which this check was not allowed to touch. |

## Phase 3

Commands are run from the repo root, as in `PHASE3_STATUS.md`, "Reproducing".

| File | Command | Outcome | Detail |
|---|---|---|---|
| `odisha_phase3_0_field_types.csv` | `python odisha_script/odisha_phase3_0_field_structure_types.py` | **reproduced exactly** |  |
| `odisha_phase3_0_results.txt` | `python odisha_script/odisha_phase3_0_field_structure_types.py` | **reproduced exactly** |  |
| `odisha_phase3_0_field_types_k4.csv` | `python odisha_script/odisha_phase3_0_field_structure_types.py --k 4` | **reproduced exactly** |  |
| `odisha_phase3_0_results_k4.txt` | `python odisha_script/odisha_phase3_0_field_structure_types.py --k 4` | **reproduced exactly** |  |
| `odisha_phase3_0_field_types_allrows.csv` | `python odisha_script/odisha_phase3_0_field_structure_types.py --rows all` | **reproduced exactly** |  |
| `odisha_phase3_0_results_allrows.txt` | `python odisha_script/odisha_phase3_0_field_structure_types.py --rows all` | **reproduced exactly** |  |
| `odisha_phase3_2_k_elbow_odisha_v120_handcrafted.txt` | `python odisha_script/odisha_phase3_2_stand_k_elbow.py --arm odisha_v120_handcrafted` | **reproduced exactly** |  |
| `odisha_phase3_2_k_elbow_odisha_v120_3ha.txt` | `python odisha_script/odisha_phase3_2_stand_k_elbow.py --arm odisha_v120_3ha` | **reproduced exactly** |  |
| `odisha_phase3_1_score_v120_merged_districts.txt` | `python odisha_script/odisha_phase3_1_pairwise_score.py --arm v120` | **reproduced exactly** |  |
| `odisha_phase3_1_score_v120_merged_districts_excl0.txt` | `python odisha_script/odisha_phase3_1_pairwise_score.py --arm v120 --exclude-types 0` | **reproduced exactly** |  |
| `odisha_phase3_1_score_v120_merged_districts_ft-k4.txt` | `python odisha_script/odisha_phase3_1_pairwise_score.py --arm v120 --field-types odisha_script/odisha_phase3_0_field_types_k4.csv` | **reproduced exactly** |  |
| `odisha_phase3_1_score_v120_merged_districts_ft-allrows.txt` | `python odisha_script/odisha_phase3_1_pairwise_score.py --arm v120 --field-types odisha_script/odisha_phase3_0_field_types_allrows.csv` | **reproduced exactly** |  |
| `odisha_phase3_1_score_v120_3ha_merged_districts_3ha.txt` | `python odisha_script/odisha_phase3_1_pairwise_score.py --arm v120_3ha --tag _3ha --joined odisha_script/phase3_3ha/phase2_plots_joined_districts.csv` | **reproduced exactly** |  |
| `odisha_phase3_1_score_v120_3ha_merged_districts_3ha_excl0.txt` | `python odisha_script/odisha_phase3_1_pairwise_score.py --arm v120_3ha --tag _3ha --joined odisha_script/phase3_3ha/phase2_plots_joined_districts.csv --exclude-types 0` | **reproduced exactly** |  |
| `odisha_phase3_1_score_v120_3ha_merged_districts_3ha_ft-k4.txt` | `python odisha_script/odisha_phase3_1_pairwise_score.py --arm v120_3ha --tag _3ha --joined odisha_script/phase3_3ha/phase2_plots_joined_districts.csv --field-types odisha_script/odisha_phase3_0_field_types_k4.csv` | **reproduced exactly** |  |
| `odisha_phase3_1_score_v120_3ha_merged_districts_3ha_ft-allrows.txt` | `python odisha_script/odisha_phase3_1_pairwise_score.py --arm v120_3ha --tag _3ha --joined odisha_script/phase3_3ha/phase2_plots_joined_districts.csv --field-types odisha_script/odisha_phase3_0_field_types_allrows.csv` | **reproduced exactly** |  |
| `odisha_phase3_3_results.txt` | `python odisha_script/odisha_phase3_3_significance.py` | **differs** | Every statistic identical. Two lines differ and both are run times: the `[10 ha] rotation nulls: ... in N s ...` line and the `[3 ha]` one. |
| `odisha_phase3_3_results_excl0.txt` | `python odisha_script/odisha_phase3_3_significance.py --exclude-types 0` | **differs** | Every statistic identical. Two lines differ and both are run times, as in the primary file. |
| `odisha_phase3_3_results_ft-k4.txt` | `python odisha_script/odisha_phase3_3_significance.py --field-types odisha_script/odisha_phase3_0_field_types_k4.csv` | **differs** | Every statistic identical. Two lines differ and both are run times, as in the primary file. |
| `odisha_phase3_3_results_ft-allrows.txt` | `python odisha_script/odisha_phase3_3_significance.py --field-types odisha_script/odisha_phase3_0_field_types_allrows.csv` | **differs** | Every statistic identical. Two lines differ and both are run times, as in the primary file. |
| `odisha_phase3_stands_unchanged.txt` | `python odisha_script/check_stands_unchanged.py --ref cff45d9 --expect-new-run  (the script prints; the file is that print saved by hand)` | **differs** | Every comparison line is identical. Five lines differ because the committed file was saved from a run with `--ref main` (they name the reference and the folder), and the committed file ends with a blank line and a hand-added line that carries a date and time (quoted under Problems). `main` has moved since, so `--ref cff45d9` is the command that still means the same thing. |
| `phase3_3ha/phase2_plots_joined_districts.csv` | `python odisha_script/odisha_phase2_3_join.py --set districts --arms v120_3ha --out-dir odisha_script/phase3_3ha/` | **reproduced exactly** | Run three times tonight in three clean clones; the same each time. |
| `phase3_3ha/odisha_phase2_3_results_districts.txt` | `python odisha_script/odisha_phase2_3_join.py --set districts --arms v120_3ha --out-dir odisha_script/phase3_3ha/` | **reproduced exactly** | Run three times tonight in three clean clones; the same each time. |
| `phase3_before_regroup/odisha_phase3_3_results.txt` | `python odisha_script/odisha_phase3_3_significance.py  (on PR #40's 3 hectare stand files, which f4ca143 replaced)` | **not run** | A record of runs made on stand files that are no longer in the tree (see its README). Not a current result, so it was not re-run. It carries two run-time lines, like the files it was copied from. |
| `phase3_before_regroup/odisha_phase3_3_results_excl0.txt` | `python odisha_script/odisha_phase3_3_significance.py --exclude-types 0  (on PR #40's 3 hectare stand files, which f4ca143 replaced)` | **not run** | A record of runs made on stand files that are no longer in the tree (see its README). Not a current result, so it was not re-run. It carries two run-time lines, like the files it was copied from. |
| `phase3_before_regroup/odisha_phase3_3_results_ft-k4.txt` | `python odisha_script/odisha_phase3_3_significance.py --field-types odisha_script/odisha_phase3_0_field_types_k4.csv  (on PR #40's 3 hectare stand files, which f4ca143 replaced)` | **not run** | A record of runs made on stand files that are no longer in the tree (see its README). Not a current result, so it was not re-run. It carries two run-time lines, like the files it was copied from. |
| `phase3_before_regroup/odisha_phase3_3_results_ft-allrows.txt` | `python odisha_script/odisha_phase3_3_significance.py --field-types odisha_script/odisha_phase3_0_field_types_allrows.csv  (on PR #40's 3 hectare stand files, which f4ca143 replaced)` | **not run** | A record of runs made on stand files that are no longer in the tree (see its README). Not a current result, so it was not re-run. It carries two run-time lines, like the files it was copied from. |

All four chance-test files were regenerated twice tonight, in two clones at `a477ab1`. With the committed script, each file differs from the committed one in exactly two lines, the run-time lines. With the script edited to keep run times out of the file, the same two lines lose their seconds and nothing else changes. The two runs agree with each other line for line once the seconds are removed. The outcomes in the table are for the files as committed at `a477ab1`, compared with what the committed script writes. Those four files have since been replaced by the edited script's output (commits `20727c1` for the script and `a4a29b9` for the files; Problem 5), so a re-run with the current script should reproduce them exactly. That re-run has not been made.

## Other

| File | Command | Outcome | Detail |
|---|---|---|---|
| `gate_effect_results.txt` | `python scripts/gate_effect.py` | **not run** | Needs Earth Engine, which this check was not allowed to touch. The file also carries five run-time lines (see Problems). |

## Figures and deck facts

**The committed figures and `deck_facts.md` show an earlier state, not the final results.**
They show the first Phase 3 analysis (PR #40, merged 2026-09-24): field types built from all
plant records, six stand types at 3 hectares, and that analysis's scores. The final results
(`PHASE3_STATUS.md`, completed 2026-10-08) use field types built from trees only, five stand
types at 3 hectares (the regroup of commit `f4ca143`), and different scores.

The evidence:

1. **The fact sheet quotes the old results file, line for line.** `deck_facts.md` cites
   `odisha_phase3_3_results.txt:24` for "villages: 20", `:39` for a score of 0.0115 and `:112`
   for "0.036, which becomes 0.360". Those lines and values are exactly those of
   `git show 99f2f8f:odisha_script/odisha_phase3_3_results.txt` (the PR #40 file). In the
   current file the same facts are on lines 29, 46 and 119-120, and the values are 0.0121 and
   0.063 / 0.630.
2. **The figures print the old numbers.** `chance_test.png` prints scores 0.024, 0.035, 0.025
   and 0.056; the final scores are 0.0257, 0.0389, 0.0244 and 0.0793. `structure_boxplots.png`
   prints type sizes 15, 47, 78, 114 and 20, which are the sizes in
   `odisha_phase3_0_results_allrows.txt` (PR #40's grouping, now only check S3); the final
   sizes are 15, 53, 77, 111 and 18. `elbow_stands.png` and `method_steps.png` say "6 types";
   the 3 hectare stand files and configs now have 5.
3. **The figure scripts were written against the old code.** `odisha_phase3_4d_results.py`
   uses `G.OUT_NAME`, which existed in the chance-test script at commit `99f2f8f` and was
   removed in `fe80260` (2026-10-07). `odisha_phase3_4b_field.py` rebuilds the field types
   from all plant records and its own check now fails against the committed trees-only file.
4. **The files are dated 24 September.** All eleven figures, `deck_facts.md` and the four
   figure scripts were last modified on 2026-09-24 in the working tree, before the field types
   changed (2026-10-07) and before the regroup (2026-10-08). They were first committed, as
   they were, in `a477ab1`.
5. **Drawn again from PR #40's data, the committed figures come back.** The four figure scripts, unchanged, were run in a clean clone in which everything under `odisha_script/` and `aois/` except the figure scripts was taken from commit `cff45d9` (the merge of PR #40). `odisha_phase3_4b_field.py`, which fails on the final data, ran to the end and passed its own checks. Of the eleven figures, nine came out byte-identical to the committed files: `study_area`, `method_steps`, `stand_view_10_vs_3`, `species_groups`, `elbow_field`, `patch_sizes`, `stand_sizes`, `chance_test` and `summary_scores`. Six of those nine do not reproduce on the final data (three differ and three are never reached). `odisha_phase3_4d_results.py`, which stops with an error on the final code, ran to the end, passed its own check against PR #40's results file, and printed the numbers on the committed figures: scores 0.0236, 0.0354, 0.0253, 0.0560; "beats 1311, 908, 1497, 977 of 1999"; village score 0.0736. The other two, `structure_boxplots` and `elbow_stands`, show the same content as the committed files (same type sizes, same dots, same curves, "6 types used") but the image is a few pixels different in size (2587 against 2599 pixels wide; 2591 x 1071 against 2593 x 1069). The cause of that small layout difference is not established. Tried: same script, same data, same Matplotlib version; the other figures drawn by the same script in the same run are byte-identical.

### What each figure script does today, from a clean checkout

| File | Command | Outcome | Detail |
|---|---|---|---|
| `phase3_figures/study_area.png` | `python odisha_script/odisha_phase3_4a_maps.py` | **reproduced exactly** | The script fetches background satellite tiles over the network. |
| `phase3_figures/method_steps.png` | `python odisha_script/odisha_phase3_4a_maps.py` | **differs** | Pictures 1 to 3 are identical pixel for pixel; picture 4 and its legend differ (248,700 of 2,457,880 pixels). The committed figure colours the 3 hectare stands by PR #40's six stand types (it shows types 2, 4, 5 and 6); the stand files now hold five types (commit f4ca143) and the regenerated figure shows types 1, 2, 4 and 5. The caption "4 of its 6 types occur here" is typed into the script and is now wrong for these stands (5 types). Drawn again with the current script on PR #40's data (commit cff45d9), it comes out byte-identical to the committed figure. |
| `phase3_figures/stand_view_10_vs_3.png` | `python odisha_script/odisha_phase3_4a_maps.py` | **differs** | The maps and stand outlines are identical; only the ten plot dots differ (10,542 of 3,456,478 pixels, all inside the dots). The committed figure colours the dots by PR #40's field types (1 scrub, 5 low forest with few trees, 4 tall forest). The field types have since changed (trees only, the final rule), and so did their numbering, but `phase3_figstyle.py` still names the types by PR #40's numbers, so the regenerated figure gives the dots the wrong names. Drawn again with the current script on PR #40's data (commit cff45d9), it comes out byte-identical to the committed figure. |
| `phase3_figures/species_groups.png` | `python odisha_script/odisha_phase3_4b_field.py` | **differs** | The bars are identical. One sentence differs: committed "11 of the 15 fall in the scrub type", regenerated "1 of the 15". The script counts plots whose field type number is 2, which was scrub in PR #40's numbering and is "low forest, many trees" in the final one. The committed sentence is right in substance (11 of the 15 are in the final no-tree type, number 0); the regenerated one is wrong. The script then stopped at its own check. Drawn again with the current script on PR #40's data (commit cff45d9), it comes out byte-identical to the committed figure. |
| `phase3_figures/structure_boxplots.png` | `python odisha_script/odisha_phase3_4b_field.py` | **differs** | Different picture, and a different size (2599 against 2587 pixels wide). The committed figure shows PR #40's five types (15, 47, 78, 114 and 20 plots). The regenerated one reads the final field types (15, 53, 77, 111 and 18 plots) but labels them with PR #40's names, so it calls the 18 no-tree plots "Low, many trees" and the 77 low-forest plots "Scrub". Neither figure shows the final types correctly. Drawn again with the current script on PR #40's data (commit cff45d9), it shows the same content as the committed figure, but the image differs in size by a few pixels; the cause of that small layout difference is not established. |
| `phase3_figures/elbow_field.png` | `python odisha_script/odisha_phase3_4b_field.py` | **not run** | Not regenerated: the script stops at its own check before drawing it. It rebuilds the field types from all plant records (PR #40's rule) and compares with `odisha_phase3_0_results.txt`, which now holds the trees-only types: it computes 632.8, 502.6, 394.4 ... and the file says 669.9, 498.0, 391.9 .... The numbers it computes are exactly those of `odisha_phase3_0_results_allrows.txt`. Drawn again with the current script on PR #40's data (commit cff45d9), it comes out byte-identical to the committed figure. |
| `phase3_figures/elbow_stands.png` | `python odisha_script/odisha_phase3_4b_field.py` | **not run** | Not regenerated: the script stops (see elbow_field) before it reaches this figure. Drawn again with the current script on PR #40's data (commit cff45d9), it shows the same content as the committed figure, but the image differs in size by a few pixels; the cause of that small layout difference is not established. |
| `phase3_figures/patch_sizes.png` | `python odisha_script/odisha_phase3_4c_sizes.py` | **reproduced exactly** |  |
| `phase3_figures/stand_sizes.png` | `python odisha_script/odisha_phase3_4c_sizes.py` | **reproduced exactly** |  |
| `phase3_figures/chance_test.png` | `python odisha_script/odisha_phase3_4d_results.py` | **not run** | Not regenerated: the script stops on import with `AttributeError: module 'odisha_phase3_3_significance' has no attribute 'OUT_NAME'`. That name was removed from the chance-test script in commit fe80260. Drawn again with the current script on PR #40's data (commit cff45d9), it comes out byte-identical to the committed figure. |
| `phase3_figures/summary_scores.png` | `python odisha_script/odisha_phase3_4d_results.py` | **not run** | Not regenerated: same error as chance_test. Drawn again with the current script on PR #40's data (commit cff45d9), it comes out byte-identical to the committed figure. |
| `phase3_figures/deck_facts.md` | none: written by hand for the deck; no script writes it | **not run** | Checked entry by entry below. It records the state of 24 September (PR #40), not the final results: every score, every chance-test number and the five-type table are out of date. |

### Every number printed on the committed figures

"Final" means the value in the regenerated results files (byte-identical to the committed
ones), or a value re-derived tonight from the committed data where no results file holds it.

| Figure | Number printed | Final value | Verdict |
|---|---|---|---|
| `study_area.png` | Kendujhar 12 plots, 1 village forest | 12, 1 | matches |
| | Dhenkanal 76 plots, 8 village forests | 76, 8 | matches |
| | Angul 40 plots, 4 village forests | 40, 4 | matches |
| | Koraput 146 plots, 7 village forests | 146, 7 | matches |
| | 7 plots outside the village forests | 274 - 267 = 7 | matches |
| `method_steps.png` | 650 x 650 metre square; 200 metre scale bar | 650 m crop | matches |
| | "4 of its 6 types occur here" (types 2, 4, 5, 6) | 4 of 5 types (types 1, 2, 4, 5 in the same numbering) | **does not match** |
| `stand_view_10_vs_3.png` | the 10 plots fall in 2 stands (10 hectares) | 10 plots, 2 stands | matches |
| | the 10 plots fall in 6 stands (3 hectares) | 6 stands | matches |
| | "Its plots cover 3 of the 5 forest types" | 3 of 5 | matches in count |
| | dot colours: 1 scrub, 5 low forest with few trees, 4 tall forest with few big trees | 1 no-tree plot, 2 low forest with few trees, 7 tall forest with few big trees | **does not match** |
| `patch_sizes.png` | 3 hectare ceiling; patch centres about 100 and about 60 metres apart | `segmentation.size` 10 and 6 pixels of 10 m; `max_area_ha` 3.0 | matches |
| | 3,596 patches, middle patch 0.85 hectares | 3,596; 0.85 | matches |
| | 56 patches over 3 hectares, largest 6.74 | 56; 6.74 | matches |
| | 9,488 patches, middle patch 0.32 hectares, largest 2.02 | 9,488; 0.32; 2.02 | matches |
| `stand_sizes.png` | 1,039 stands, 529 (51%) larger than 3 hectares | 1,039; 529; 50.9% | matches |
| | 1,954 stands, 41 (2%) past 3 hectares, by at most 0.04 | 1,954; 41; 2.1%; 0.039 | matches |
| | Angul 96 \| 200, Dhenkanal 224 \| 462, Kendujhar 105 \| 183, Koraput 614 \| 1,109 | the same eight counts | matches |
| `species_groups.png` | 259 of 274 plots; other groups 11, 1, 1, 1, 1 | 259 of 274; 11, 1, 1, 1, 1 | matches |
| | "11 of the 15 fall in the scrub type" | 11 of the 15 are in the final no-tree type (type 0) | matches in count; the final write-up has no type called "scrub" |
| | "half are under 1.5 metres tall" | median height of the 15 is 1.52 m | matches to the rounding shown |
| `structure_boxplots.png` | Tall, many trees: 15 plots | 15 | matches |
| | Tall, few big trees: 47 plots | 53 | **does not match** |
| | Low, many trees: 78 plots | 77 | **does not match** |
| | Low, few trees: 114 plots | 111 | **does not match** |
| | Scrub: 20 plots | 18 (plots with no tree, or nearly none) | **does not match** |
| | All 274 field plots | 274 | matches |
| `elbow_field.png` | "The bend: 5 groups" | elbow k = 5 | matches |
| | the curve itself (no numbers printed): 100, 79, 62, 53 ... at 2, 3, 4, 5 groups | final curve: 100, 74, 59, 49 ... | **does not match**: it is the all-records curve |
| `elbow_stands.png` | "6 types used in the stand maps" | 6 at 10 hectares, 5 at 3 hectares | **does not match** for the 3 hectare stands |
| | "Both curves bend at 5" | pooled elbow 5 and 5 | matches |
| | where each district bends, 10 hectares: 6, 6, 6, 5; all four together 5 | 6, 6, 6, 5; 5 | matches |
| | where each district bends, 3 hectares: 5, 5, 5, 5; all four together 5 | 5, 5, 5, 5; 5 | matches |
| `chance_test.png` | 10 hectares, same stand: "Our score 0.024, beats 1,311 of 1,999" | 0.0257, 77.0th percentile (about 1,540 of 1,999; the file gives the percentile, not the count) | **does not match** |
| | 10 hectares, same type: "0.035, beats 908 of 1,999" | 0.0389, 66.8th percentile (about 1,335) | **does not match** |
| | 3 hectares, same stand: "0.025, beats 1,497 of 1,999" | 0.0244, 65.7th percentile (about 1,313) | **does not match** |
| | 3 hectares, same type: "0.056, beats 977 of 1,999" | 0.0793, 83.1st percentile (about 1,661) | **does not match** |
| `summary_scores.png` | "Knowing only the village: 0.074" (left, same stand) | 0.0756 (`odisha_phase3_3_results.txt` line 30; re-derived 0.0756) | **does not match** (0.074 is the value under PR #40's field types: re-derived 0.0736) |
| | "Knowing only the village: 0.074" (right, same stand type) | 0.0887 is the figure that takes the form labelling takes (same line of the file) | **does not match**: the left panel's number is reused on the right |
| | dots and grey bands (no numbers printed): dots near 0.024, 0.025, 0.035, 0.056 | 0.0257, 0.0244, 0.0389, 0.0793 | **does not match** |
| | "1,999 random shifts" | 1,999 | matches |

The four conclusions the figures carry are unchanged in the final results: every score sits
inside its chance range, and 0 of 10 tests survives. What is out of date is each number, and
the two statements about six stand types.

### Every entry of `deck_facts.md`

Line references: every `odisha_phase3_3_results.txt:N` and `odisha_phase3_0_results.txt:N`
reference in the fact sheet points at the PR #40 version of the file. The line numbers no
longer hold the fact quoted (for example `:24` is now line 29). The two config line
references are stale too (`segmentation.size` is on line 108, not 99; `max_area_ha` on 131,
not 122). They are not repeated row by row below.

**Section 1, the field data**

| Entry | Fact sheet | Final | Verdict |
|---|---|---|---|
| Plant records in the raw sheet | 5,910 | 5,910 | matches |
| Trees: raw / after the location filter | 2,872 / 2,729 | 2,872 / 2,729 | matches |
| Other record kinds, raw | sapling/seedling 1,613, shrub 964, climber 286+5, stump 169, seedling 1 | the same | matches |
| Records kept after the location filter | 5,679 | 5,679 | matches |
| Field plots | 274 | 274 | matches |
| Plots per district | 146 / 76 / 40 / 12 | 146 / 76 / 40 / 12 | matches |
| Village forests | 20: 4 / 8 / 1 / 7 | 20: 4 / 8 / 1 / 7 | matches |
| Named habitations | 30: 5 / 12 / 3 / 10 | 30: 5 / 12 / 3 / 10 | matches |
| Study-area size, hectares | 439 / 995 / 405 / 2,468; about 4,300 | 439 / 995 / 405 / 2,468; 4,308 | matches |
| Plots inside the study areas | 267: 145 / 75 / 39 / 8 | 267: 145 / 75 / 39 / 8 | matches |
| Plots per village forest | smallest 5, middle 10, largest 59 | 5, 10, 59 | matches |
| Plot pairs scored | 35,511 | 35,511 | matches |
| Survey dates | 25 April 2022 to 5 April 2023 | 2022-04-25 to 2023-04-05 | matches |
| Plot radius | still unknown | `odisha_phase3_0_results.txt` still says so | matches |
| Species recorded | 179 | 179 | matches |

**Section 2, species**

| Entry | Fact sheet | Final | Verdict |
|---|---|---|---|
| Biggest species group | 259 of 274 (94.5%) | 259 of 274 (94.5%) | matches |
| The other 15 | groups of 11, 1, 1, 1, 1 | 11, 1, 1, 1, 1 | matches |
| What the 15 are | 13 under 5 metres tall, 10 of them in Koraput; 2 low forest (Angul 10.4 m, Dhenkanal 9.3 m) | 13 under 5 m; 10 in Koraput; the two others 10.4 m and 9.3 m | matches |
| Average share of Sal | 12.1% | 12.1% | matches |
| Next most common | mango 9.2%, jamun 8.3%, kendu 4.4% | 9.2%, 8.3%, 4.4% | matches |
| Plots with any Sal / Sal-dominated | 80 / 32 | 80 / 32 | matches |

**Section 3, the five forest types**

| Entry | Fact sheet | Final (`odisha_phase3_0_results.txt`) | Verdict |
|---|---|---|---|
| Type sizes, all 274 plots | 20 / 114 / 78 / 47 / 15 | 18 / 111 / 77 / 53 / 15 | **does not match** (the fact sheet's are the all-records types, now check S3) |
| Type sizes, 267 scored plots | 18 / 111 / 77 / 46 / 15 | 16 / 108 / 76 / 52 / 15 | **does not match** |
| Type numbers | scrub 2, low-few 4, low-many 0, tall-few 1, tall-many 3 | numbered 0 to 4 from shortest to tallest: no-tree 0, low-few 1, low-many 2, tall-many 3, tall-few 4 | **does not match** |
| Middle height by type | 1.4 / 7.0 / 7.8 / 18.1 / 15.3 m | 0.0 / 7.1 / 8.1 / 18.3 / 15.4 m (tree height) | **does not match** |
| Middle crown cover by type | 1% / 40% / 33% / 48% / 48% | 0% / 38% / 33% / 53% / 48% | **does not match** |
| Middle trees per plot | 0 / 6.5 / 14 / 8 / 29 | 0 / 6 / 14 / 8 / 29 (as printed) | first four types changed membership; values close |
| Middle trunk area | 27 / 688 / 2,990 / 3,005 / 5,576 cm2 | 0 / 625 / 2,850 / 2,552 / 4,771 cm2 (trees only) | **does not match** |
| Largest type | 114 of 274 (41.6%) | 111 of 274 (40.5%) | **does not match** |
| Koraput | 75 low-few + 53 low-many of 146 | 74 + 54 | **does not match** |
| Dhenkanal | 30 tall-few + 8 tall-many of 76 | 31 + 8 | **does not match** |
| Elbow rule picks | 5 | 5 | matches |
| Silhouette picks | 3 (0.350) | 2 (0.581) | **does not match** |
| Calinski-Harabasz picks | 9 | 4 | **does not match** |
| Davies-Bouldin picks | 8 | 2 | **does not match** |
| Adding trunk diameter keeps the elbow at 5 | yes | yes | matches |

**Section 4, how many stand types**

| Entry | Fact sheet | Final | Verdict |
|---|---|---|---|
| 10 hectare elbows: Angul, Dhenkanal, Kendujhar, Koraput | 6 / 6 / 6 / 5 | 6 / 6 / 6 / 5 | matches |
| All four together; middle of the five answers | 5; 6 | 5; 6 | matches |
| Stand polygons per district | 99 / 232 / 108 / 629 = 1,068 | the same | matches |
| Satellite features | 22 | 22 | matches |
| Silhouette, all districts | 0.212 at 4 types | 0.212 at 4 | matches |
| The 3 hectare stands | not mentioned | their own elbow is 5 in every district and pooled, and they now use 5 types (`odisha_phase3_2_k_elbow_odisha_v120_3ha.txt`) | **missing from the fact sheet** |

**Section 5, the stands**

| Entry | Fact sheet | Final (re-derived from the stand files) | Verdict |
|---|---|---|---|
| Polygons, 10 hectares | 99 / 232 / 108 / 629 = 1,068 | the same | matches |
| Stands, 10 hectares | 96 / 224 / 105 / 614 = 1,039 | the same | matches |
| Polygons, 3 hectares | 203 / 473 / 186 / 1,131 = 1,993 | the same | matches |
| Stands, 3 hectares | 200 / 462 / 183 / 1,109 = 1,954 | the same | matches |
| Stands holding at least one plot | 144 / 198 | 144 / 198 | matches |
| 10 hectares: middle, 9-in-10, largest, share over 3 | 3.09 / 9.18 / 10.08 / 50.9% (529 of 1,039) | the same | matches |
| 3 hectares: middle, 9-in-10, largest, share over 3 | 2.35 / 2.94 / 3.04 / 2.1% (41 of 1,954), by at most 0.04 | the same; at most 0.039 | matches |
| Middle stand per district, 10 / 3 hectares | 3.62 / 2.37, 3.26 / 2.29, 2.69 / 2.36, 2.95 / 2.38 | the same | matches |
| Total area in stands | 4,314 hectares in both | 4,314 and 4,315 (rounded sums) | matches to within 1 hectare |
| Patches, 10 hectare stands | 3,596; 0.85; 2.00; 6.74 | the same | matches |
| Patches, 3 hectare stands | 9,488; 0.32; 0.67; 2.02 | the same | matches |
| Largest patch per district, old spacing | 4.49 / 6.74 / 5.20 / 5.08 | the same | matches |
| Settings | patch spacing 10 -> 6 pixels, cap 10.0 -> 3.0 | the same, and since `f4ca143` the number of stand types also differs (6 against 5) | values match; "the only two settings that differ" is **no longer true** |

**Section 6, how many plots share a stand**

| Entry | Fact sheet | Final | Verdict |
|---|---|---|---|
| 10 hectares | 61 stands, 184 plots, 247 pairs | 61, 184, 247 | matches |
| 3 hectares | 44 stands, 113 plots, 113 pairs | 44, 113, 113 | matches |

**Section 7, the scores**

| Entry | Fact sheet | Final (`odisha_phase3_3_results.txt`) | Verdict |
|---|---|---|---|
| Same-village pairs alike / other pairs / all pairs | 43.1% / 27.8% / 29.1% (3,032 same-village pairs) | 43.0% / 27.3% / 28.7% (3,032) | **does not match** |
| Random maps per test | 1,999 | 1,999 | matches |
| 10 hectares, drawing, all plots | 0.0115; chance 0.0097 (0.0073 to 0.0124); p 0.137; beats 1,727 | 0.0121; 0.0096 (0.0073 to 0.0124); p 0.063; 93.7th percentile | **does not match** |
| 10 hectares, drawing, shared stands | 0.0236; 0.0221 (0.0165 to 0.0292); p 0.344; beats 1,311 | 0.0257; 0.0228 (0.0172 to 0.0299); p 0.230; 77.0th percentile | **does not match** |
| 3 hectares, drawing, all plots | 0.0066; 0.0047 (0.0033 to 0.0064); p 0.036; beats 1,928 | 0.0060; 0.0045 (0.0031 to 0.0062); p 0.080; 92.1st percentile | **does not match** |
| 3 hectares, drawing, shared stands | 0.0253; 0.0218 (0.0144 to 0.0311); p 0.252; beats 1,497 | 0.0244; 0.0223 (0.0143 to 0.0321); p 0.344; 65.7th percentile | **does not match** |
| Same-stand pairs that are alike, 10 / 3 hectares | 53.4% (chance 54.6%) / 59.3% (55.0%); p 0.626 / 0.164 | 53.9% (53.4%) / 55.8% (53.1%); p 0.451 / 0.284 | **does not match** |
| Labelling, 10 hectares | 0.0354; 0.0368 (0.0164 to 0.0608); p 0.546; beats 908 | 0.0389; 0.0337 (0.0139 to 0.0564); p 0.332; 66.8th percentile | **does not match** |
| Labelling, 3 hectares | 0.0560; 0.0566 (0.0342 to 0.0822); p 0.511; beats 977 | 0.0793; 0.0665 (0.0475 to 0.0902); p 0.169; 83.1st percentile | **does not match** |
| Labelling by district, 10 hectares | 0.009 / 0.065 / 0.072 / 0.025 | 0.095 / 0.062 / -0.198 / 0.025 | **does not match** |
| Labelling by district, 3 hectares | 0.060 / 0.159 / 0.181 / -0.006 | 0.146 / 0.185 / 0.227 / -0.001 | **does not match** |
| Far-apart pairs, 10 / 3 hectares | -0.0185 (chance -0.0119) / +0.0140 (+0.0113); p 0.680 / 0.416 | -0.0118 (-0.0108) / +0.0143 (+0.0095); p 0.534 / 0.360 | **does not match** |
| Tests surviving the correction | 0 of 10 | 0 of 10 | matches |
| Smallest chance, and after correction | 3 hectares drawing all plots: 0.036 -> 0.360 | 10 hectares drawing all plots: 0.063 -> 0.630 (3 hectares: 0.080 -> 0.716) | **does not match** |
| Difference, drawing, all plots | -0.0050; chance -0.0050 (-0.0086 to -0.0016); villages -0.0129 to -0.0009 | -0.0061; -0.0050 (-0.0086 to -0.0016); -0.0153 to -0.0014 | **does not match** |
| Difference, drawing, shared stands | +0.0018; -0.0003 (-0.0126 to +0.0132); -0.0167 to +0.0171 | -0.0013; -0.0006 (-0.0129 to +0.0137); -0.0208 to +0.0132 | **does not match** |
| Difference, same-stand pair precision | +0.0585; +0.0055 (-0.1017 to +0.1144); -0.0217 to +0.2271 | +0.0191; -0.0024 (-0.1108 to +0.1118); -0.0457 to +0.1527 | **does not match** |
| Difference, labelling | +0.0206; +0.0190 (-0.0199 to +0.0602); -0.0766 to +0.0956 | +0.0404; +0.0334 (-0.0003 to +0.0694); -0.0599 to +0.1459 | **does not match** |
| Difference, far-apart | +0.0324; chance +0.0233 | +0.0260; chance +0.0202 | **does not match** |
| "Sits at the 50th percentile of the chance difference" | 50.0 | 27.7 | **does not match** |
| Measures that differ by no more than chance | 5 of 5 | 5 of 5 | matches |
| Village benchmark, drawing | 0.074 | 0.0756 | **does not match** (0.0736 under PR #40's field types) |
| Village benchmark, labelling | 0.089 (0.146 / 0.194 / 0.000 / 0.025) | 0.0887 (0.149 / 0.196 / 0.000 / 0.022) | total matches to three decimals; three district values do not |
| "Not in any committed results file" | so stated | both benchmark values are now on lines 30-31 of `odisha_phase3_3_results.txt` | **out of date** |
| "Beats N of 1,999": 1,311 / 908 / 1,497 / 977 | from a scratch script, `dump_nulls.py`, not in the repo | reproduced tonight by `odisha_phase3_4d_results.py` on PR #40's data: 1,311 / 908 / 1,497 / 977, no ties | traced, to the old scores; **does not match** the final results, whose files give percentiles, not counts |
| "Beats N of 1,999": the other six (1,727; 1,928 +4 ties; 747; 1,672 +4 ties; 639; 1,167) | the same scratch script | not printed by any committed script | **could not be traced** |

**Sections 8 and 9, and the two lists**

| Entry | Fact sheet | Final | Verdict |
|---|---|---|---|
| Scorer fix | commit `e261f3d` | the commit exists with that subject | matches |
| Pre-fix numbers 0.0093 / 0.0179 / 0.0293 | "replaced by those above" | the numbers "above" are themselves replaced | history only; not checked |
| Headline 1: 259 of 274 in one species group | | | matches |
| Headline 2: five forest types from structure | | five, but built from trees only | matches in count |
| Headline 3: "gave each stand one of six types" | six | six at 10 hectares, five at 3 hectares | **does not match** |
| Headline 4: 0 of 10 tests survive | | 0 of 10 | matches |
| Headline 5: the two stand sizes cannot be told apart | | 5 of 5 measures inside chance | matches |
| "Do not claim" list: 0.036, 1,928, 1,497, 0.056 vs 0.035, -0.0050 | | 0.080, (no count), (no count), 0.0793 vs 0.0389, -0.0061 | **out of date** |
| "Do not claim": 41 of 1,954 just over 3 hectares, by at most 0.04 | | 41 of 1,954; 0.039 | matches |

### What the deck builder uses

`scripts/build_phase3_summary_deck.js` (read, not run) places the eleven figures and types the
fact sheet's numbers into slide text and speaker notes. Among them, all out of date: "sorts
the stands into 6 types", "the maps use 6", "My maps beat between 908 and 1,497 of the 1,999
random maps", "0.074 from knowing only the village", "43.1% of same-village pairs ... against
27.8%", "scrub (20 ...", "middle height 1.4 metres", "they pick 3, 8 or 9". A deck built from
this script today would present the 24 September analysis as the result.

### What each figure script needs before it runs from a clean checkout

None of these was edited.

- **`phase3_figstyle.py`** names the five field types by PR #40's numbers (2 scrub, 4 low-few,
  0 low-many, 1 tall-few, 3 tall-many). The final types are numbered 0 to 4 from shortest to
  tallest: 0 no trees, 1 low with few trees, 2 low with many trees, 3 tall with many trees,
  4 tall with few big trees. `TYPE_ORDER`, `TYPE_NAME`, `TYPE_SHORT` and `TYPE_COLOUR` need
  re-keying. Until then every figure that names a field type mislabels it, silently. The names
  themselves need a decision (see Questions): type 0 is now "no trees", not "scrub".
- **`odisha_phase3_4b_field.py`**: (a) `field_elbow` builds its features from all plant
  records; it should take the trees-only features from
  `odisha_phase3_0_field_structure_types.py`, which is what the check compares against;
  (b) the species sentence counts `field_type == 2`; the no-tree type is now 0;
  (c) `K_USED_STANDS = 6` is typed in and drawn on both stand sizes; it is 6 at 10 hectares
  and 5 at 3 hectares.
- **`odisha_phase3_4d_results.py`**: `G.OUT_NAME` became `G.OUT_STEM` plus `.txt`;
  `G.load_all()` now takes the arms and the field-types file,
  `G.load_all(ARMS, G.FIELD_TYPES)`; the summary figure draws the pooled village score on the
  labelling panel, where the per-district one (already computed in the script) belongs.
- **`odisha_phase3_4a_maps.py`** runs, but the caption "of its 6 types" (line 392) is typed in
  and should come from the config's number of stand types; and it depends on
  `phase3_figstyle.py` for the plot colours.
- **`odisha_phase3_4c_sizes.py`** runs and reproduces both of its figures exactly.

## Earth Engine re-runs

This check did not touch Earth Engine. The facts below were established tonight by the
orchestrating session and are recorded here as given.

- Every config was copied under `<name>_repro` (same content and cache fingerprint, fresh asset
  namespace; commit `df45350`) and is being re-run from scratch.
- **Sanjay Van**, both pipelines, finished in one pass, on the code at `df45350`.
- **Sanjay Van cannot be compared stand for stand.** The cached assets of `sanjay_van_baseline`
  carry fingerprint `bbc3e3d624` (27 August). Commit `128b1c4` (10 September) dropped
  `canopy_height_std` from the SNIC stack and the merge criteria, which gives fingerprint
  `7f642cf2ca`, and nothing was cached under that fingerprint until this morning.
  `sanjay_van_alphaearth` had no cached assets at all. This morning's run of the current
  config gives 1,298 superpixels and 291 stands (hand-crafted) and 1,298 and 290 (AlphaEarth).
  The docs quote 1,249 superpixels and 269 stands, from the old stack.
- **Upstream of segmentation the settings are the same in both, so those assets were compared
  pixel for pixel** (`scripts/compare_cached_assets.py`; output in
  `docs/reproducibility/sanjay_van_baseline_assets_aug27_vs_repro.json`):

  | Asset | Pixel values compared | Values that differ | Largest difference |
  |---|---|---|---|
  | habitat mask | 148,630 | 0 | 0 |
  | land-cover summary | 148,630 | 0 | 0 |
  | water mask | 148,630 | 0 | 0 |
  | radar features (9 bands) | 1,337,670 | 0 | 0 |
  | structure features (3 bands) | 310,347 | 0 | 0 |
  | static features (5 bands) | 743,150 | 0 | 0 |
  | Sentinel-2 composite (26 bands) | 3,864,380 | 1,678,188 (43.4%) | 497, in `B8_median` |
  | optical features (6 bands) | 891,780 | 891,780 (all) | 7, in `ndvi_obs_count` |

  The masks, radar, structure and static features reproduce exactly. The Sentinel-2 composite
  and everything computed from it do not: the number of NDVI observations per pixel differs by
  up to 7. So the Sentinel-2 archive on Earth Engine changed for 2017-2022 between 27 August
  and 13 October. (`mask_provenance` was not cached under either name.)
- **The mask**, checked read-only today: for `odisha_v120_3ha_kendujhar`, today's recomputed
  mask reasons disagree with the `habitat_mask` asset cached weeks ago on 0.0 hectares.
- **`odisha_phase2_1_mask_retention.py`** (Phase 2 step 1) was regenerated for the task 2
  maps: 257 of 274 plots kept, as committed (rows in the Phase 2 table above). Of the 267 plots
  inside the district ROIs, the maps in `docs/transparency/` mark 253 kept and 14 dropped, the
  same plots as the regenerated table.
- **The mask maps reproduce.** Made again from a clean clone of their commit (`4d7f0d5`), all
  7 map images and all 5 `summary.md` files came out byte-identical.
- **All twelve Odisha configs** have been re-run from scratch: eleven in one batch, and
  `odisha_alphaearth_angul_repro` in a second start, because its export pass stopped on a
  network failure before anything was submitted. Each ran from a clean clone pinned to
  `df45350`, with `run_config_passes.sh` called one pass at a time and a wait for the task
  queue to drain in between (the logic of `odisha_script/run_passes_safely.py`).

### Odisha: the re-runs against the committed outputs

Every Odisha re-run has the same cache fingerprint as the committed run it copies, so every
stage can be compared. **No hand-crafted config reproduces its committed stands exactly.
The AlphaEarth superpixels reproduce exactly in all four districts.** What follows says where the
differences enter and how large they are.

#### 1. Where the difference enters

**Stage by stage** (`scripts/compare_cached_assets.py`: the committed run's cached assets against
the re-run's, pixel for pixel; one file per config, `docs/reproducibility/<config>_assets.json`).
Share of pixel values that differ; "exact" means none does:

| Config | masks (3) | structure, static | radar | Sentinel-2 composite | optical features | embedding | SNIC labels |
|---|---|---|---|---|---|---|---|
| `odisha_v120_3ha_angul` | exact | exact | exact | 15.6% | 87.1% | n/a | 3.9% |
| `odisha_v120_3ha_dhenkanal` | exact | exact | exact | 12.6% | 84.8% | n/a | 4.8% |
| `odisha_v120_3ha_kendujhar` | exact | exact | exact | 21.8% | 91.9% | n/a | 4.0% |
| `odisha_v120_3ha_koraput` | exact | exact | 6.2% (rounding, at most 1e-14) | 15.4% | 84.6% | n/a | 3.8% |
| `odisha_v120_handcrafted_angul` | exact | exact | exact | 36.9% | 99.9% | n/a | 8.1% |
| `odisha_v120_handcrafted_dhenkanal` | exact | exact | 3.9% (rounding, at most 1e-14) | 30.3% | 98.7% | n/a | 8.6% |
| `odisha_v120_handcrafted_kendujhar` | exact | exact | 8.5% (rounding, at most 1e-14) | 32.6% | 92.5% | n/a | 5.6% |
| `odisha_v120_handcrafted_koraput` | exact | exact | exact | 24.5% | 88.4% | n/a | 36.0% |
| `odisha_alphaearth_angul` | exact | exact | n/a | 36.9% | 99.9% | exact | exact |
| `odisha_alphaearth_dhenkanal` | exact | exact | n/a | 30.3% | 98.7% | exact | exact |
| `odisha_alphaearth_kendujhar` | exact | exact | n/a | 32.6% | 92.5% | exact | exact |
| `odisha_alphaearth_koraput` | exact | exact | n/a | 24.5% | 88.4% | exact | exact |

"n/a" means the config does not run that stage. For SNIC labels the figure is the share of pixels
whose superpixel label differs.

- The land-cover masks, the structure features (ETH canopy height) and the static features
  reproduce exactly in all twelve configs; radar reproduces exactly or to rounding.
- The Sentinel-2 composite does not, in any config, and the optical features built on it differ
  almost everywhere. The settings are identical, so the Sentinel-2 archive on Earth Engine has
  changed for 2017-2022 since the committed runs were cached. The share is larger for the
  10 hectare and AlphaEarth configs than for the 3 hectare ones in the same district: their
  committed assets are older.
- **SNIC is repeatable when its inputs are.** The AlphaEarth arm segments on the embedding, which
  did not change, and its superpixel labels are identical at every pixel in all four districts.
- Where the inputs changed (the hand-crafted arms), 3.8% to 8.6% of pixels carry another
  superpixel label, with one exception, `odisha_v120_handcrafted_koraput` at 36.0%. Section 4
  explains the exception.

#### 2. The stands

**Stand by stand** (`odisha_script/odisha_repro_compare.py`, which uses
`scripts/compare_stand_runs.py`; the committed stand files against the re-run's; nothing is matched
by id). IoU is intersection over union: each stand is paired with the stand of the other run that
overlaps it most, the overlap is divided by the area the two cover together, and the mean is weighted
by stand area; 1 means the same stands.

| Arm | District | Layer | Units, committed to re-run | Same outline | IoU, old to new | IoU, new to old | Area in units with IoU of 0.9 or more |
|---|---|---|---|---|---|---|---|
| 3 hectare | Angul | merged stands | 200 to 204 | 18 of 200 | 0.752 | 0.752 | 37.1% |
| 3 hectare | Angul | SNIC superpixels | 1062 to 1064 | 539 of 1062 | 0.929 | 0.927 | 79.0% |
| 3 hectare | Dhenkanal | merged stands | 462 to 462 | 43 of 462 | 0.686 | 0.688 | 33.9% |
| 3 hectare | Dhenkanal | SNIC superpixels | 2571 to 2571 | 1230 of 2571 | 0.917 | 0.916 | 74.7% |
| 3 hectare | Kendujhar | merged stands | 183 to 180 | 10 of 183 | 0.675 | 0.678 | 32.8% |
| 3 hectare | Kendujhar | SNIC superpixels | 935 to 934 | 437 of 935 | 0.930 | 0.929 | 79.3% |
| 3 hectare | Koraput | merged stands | 1109 to 1125 | 60 of 1109 | 0.707 | 0.706 | 33.5% |
| 3 hectare | Koraput | SNIC superpixels | 4920 to 4911 | 2355 of 4920 | 0.931 | 0.932 | 80.1% |
| 10 hectare | Angul | merged stands | 96 to 96 | 4 of 96 | 0.689 | 0.682 | 26.1% |
| 10 hectare | Angul | SNIC superpixels | 402 to 403 | 56 of 402 | 0.859 | 0.854 | 57.0% |
| 10 hectare | Dhenkanal | merged stands | 224 to 231 | 7 of 224 | 0.688 | 0.676 | 34.3% |
| 10 hectare | Dhenkanal | SNIC superpixels | 965 to 964 | 166 of 965 | 0.863 | 0.864 | 61.7% |
| 10 hectare | Kendujhar | merged stands | 105 to 103 | 6 of 105 | 0.837 | 0.840 | 58.8% |
| 10 hectare | Kendujhar | SNIC superpixels | 358 to 361 | 71 of 358 | 0.904 | 0.900 | 74.1% |
| 10 hectare | Koraput | merged stands | 614 to 617 | 0 of 614 | 0.507 | 0.498 | 1.6% |
| 10 hectare | Koraput | SNIC superpixels | 1871 to 1883 | 7 of 1871 | 0.530 | 0.525 | 1.3% |
| AlphaEarth | Angul | merged stands | 99 to 97 | 85 of 99 | 0.923 | 0.932 | 84.5% |
| AlphaEarth | Angul | SNIC superpixels | 405 to 405 | 405 of 405 | 1.000 | 1.000 | 100.0% |
| AlphaEarth | Dhenkanal | merged stands | 215 to 215 | 206 of 215 | 0.979 | 0.980 | 94.6% |
| AlphaEarth | Dhenkanal | SNIC superpixels | 953 to 953 | 953 of 953 | 1.000 | 1.000 | 100.0% |
| AlphaEarth | Kendujhar | merged stands | 121 to 118 | 113 of 121 | 0.978 | 0.979 | 92.8% |
| AlphaEarth | Kendujhar | SNIC superpixels | 361 to 361 | 361 of 361 | 1.000 | 1.000 | 100.0% |
| AlphaEarth | Koraput | merged stands | 626 to 623 | 560 of 626 | 0.949 | 0.949 | 86.9% |
| AlphaEarth | Koraput | SNIC superpixels | 1870 to 1870 | 1870 of 1870 | 1.000 | 1.000 | 100.0% |

- **AlphaEarth:** the superpixels are the same in every district, and the merged stands nearly so
  (IoU 0.92 to 0.98). They are not identical because the merge rule reads `ndvi_amplitude_annual`,
  an optical feature, and that changed.
- **3 hectares:** superpixels overlap with an IoU of 0.92 to 0.93, merged stands with 0.67 to 0.75.
  Between 5% and 9% of stands have exactly the same outline.
- **10 hectares:** superpixels 0.86 to 0.90 and merged stands 0.69 to 0.84 in three districts;
  in Koraput 0.53 and 0.51 (section 4).
- The stands are always less alike than the superpixels they are built from: the merge turns small
  differences in the superpixels into larger ones in the stands. Stand counts barely move
  (for example 462 to 462 in Dhenkanal at 3 hectares, with an IoU of 0.69), so a count alone
  would have hidden all of this.

#### 3. The plots and the Phase 3 scores

**The plots and the Phase 3 scores.** The plots were joined to the re-run's stands with the Phase 2
join code, and the Phase 3 scores computed from that new plot table with the options of
`PHASE3_STATUS.md`'s "Reproducing" section (primary analysis). The committed score is beside it.

| Arm | Quantity | Committed | Re-run |
|---|---|---|---|
| 3 hectare | drawing, all pairs: adjusted Rand index | +0.0060 | +0.0057 |
| 3 hectare | drawing, plots in stands that hold more than one plot: adjusted Rand index | +0.0244 | +0.0233 |
| 3 hectare | labelling, pairs within a district: adjusted Rand index | +0.0793 | +0.0478 |
| 3 hectare | stands holding the 267 plots | 198 | 192 |
| 3 hectare | stands holding more than one plot | 44 | 51 |
| 10 hectare | drawing, all pairs: adjusted Rand index | +0.0121 | +0.0157 |
| 10 hectare | drawing, plots in stands that hold more than one plot: adjusted Rand index | +0.0257 | +0.0364 |
| 10 hectare | labelling, pairs within a district: adjusted Rand index | +0.0389 | +0.0619 |
| 10 hectare | stands holding the 267 plots | 144 | 146 |
| 10 hectare | stands holding more than one plot | 61 | 57 |

How the plots are grouped into stands, committed run against re-run (adjusted Rand index of one
grouping against the other; 1 means every plot shares its stand with the same plots):

| Arm | Layer | Pairs of plots sharing a unit: committed, re-run, in both | Adjusted Rand index, old grouping against new |
|---|---|---|---|
| 3 hectare | merged stands | 113, 111, 79 | 0.7044 |
| 3 hectare | SNIC superpixels | 29, 26, 26 | 0.9454 |
| 10 hectare | merged stands | 247, 262, 149 | 0.5825 |
| 10 hectare | SNIC superpixels | 76, 72, 43 | 0.5802 |
| AlphaEarth | merged stands | 302, 302, 296 | 0.9800 |
| AlphaEarth | SNIC superpixels | 64, 64, 64 | 1.0000 |

- The scores stay small in the re-run, as they were. Nothing here changes what Phase 3 concluded.
- They move by amounts comparable to their own size. The labelling score goes from 0.0793 to
  0.0478 at 3 hectares and from 0.0389 to 0.0619 at 10 hectares, so **which stand size labels
  better flips between the committed run and the re-run.** A difference of that size between two
  stand sizes should not be read as a finding.
- The 10 hectare re-run includes the Koraput stands of section 4, drawn from features that were
  not yet cached; Koraput holds 145 of the 267 plots. So the 10 hectare column mixes two causes.
- Only the scores were recomputed. The chance tests were not re-run on the new stands.
- Phase 3 never scored the AlphaEarth arm, so there is no committed score to compare with and none
  was computed.
- The full output for each arm is in `docs/reproducibility/odisha_repro/<arm>/`: the results
  file, the new plot table, the new score files (primary analysis and the three declared checks)
  and one table per district and layer of every stand's best match.

#### 4. Superpixels depend on whether the features were cached when SNIC ran

With caching on, a stage that misses the cache runs live. On a cold cache the segmentation of a
small ROI usually succeeds at once, on feature images still being computed on the fly; for a
large ROI it fails with a memory limit and succeeds on the next pass, on the same features read
back as cached assets. In the re-run, three hand-crafted configs segmented in the first pass
(Kendujhar at 3 and at 10 hectares, and Koraput at 10 hectares); the other five segmented in the
second.

`scripts/snic_cached_vs_live.py` (read-only) recomputes SNIC now from a re-run's cached features
and compares the labels with the re-run's own cached SNIC asset and with the committed run's
(output in `docs/reproducibility/snic_cached_vs_live_<config>.json`):

| Config | The re-run segmented | Recomputed from cached features, against the re-run's own SNIC asset | against the committed run's SNIC asset |
|---|---|---|---|
| `odisha_v120_3ha_koraput` | in the second pass, from cached features | 0.1% of pixels differ | 3.8% |
| `odisha_v120_handcrafted_angul` | in the second pass, from cached features | 0.4% | 7.8% |
| `odisha_v120_handcrafted_koraput` | in the first pass, from live features | 35.4% | 6.3% |
| `odisha_v120_handcrafted_kendujhar` | in the first pass, from live features | 26.4% | 26.4% |

- Where the re-run segmented from cached features, recomputing from cached features gives the
  same superpixels again (0.1% and 0.4% of pixels differ).
- Where the re-run segmented from live features, the same features once cached give superpixels
  that differ at 26% to 35% of pixels. That is several times the effect of the Sentinel-2 change
  (4% to 9%).
- This accounts for Koraput at 10 hectares, the outlier in sections 1 and 2. The re-run drew its
  superpixels live (the batch log shows its segmentation succeeding in the first pass). The
  committed run's superpixels match a from-cache computation to 6.3%, which indicates they
  were drawn from cached features; no log of that run survives to confirm it. For Kendujhar at
  10 hectares the committed and re-run superpixels agree with each other (5.6% of pixels
  differ) and both differ from the from-cache computation by 26.4%, which indicates both were
  drawn live.

**So a config's superpixels, and with them its stands, depend on which pass its segmentation
happened to succeed in.** This is a property of the pipeline's cache path, not of any setting. It
was not changed tonight: making segmentation wait for cached features would move the stands of
every config that segmented live, Kendujhar's committed stands among them. It is a question for
Jaskaran in the PR.

#### 5. Mask and merge provenance of the re-runs

`docs/reproducibility/repro_runs/<config>_repro/` holds, for each of the fourteen re-runs, the
mask summary and the per-stand merge provenance, read from the re-run's own cached assets
without submitting anything.

<!-- ODISHA-REPRO-COMPARISONS: all twelve configs are in the tables above. -->

## Problems found

Each with its evidence and what should happen next.

1. **The Phase 3 summary figures, `deck_facts.md` and the deck builder show the PR #40
   analysis, not the final results.** Evidence: "Figures and deck facts" above. Next: fix the
   figure scripts as listed, regenerate all eleven figures, rewrite the fact sheet from the
   final results files, update the deck builder's typed-in numbers, and only then build a deck.
   Until then nothing in `phase3_figures/` should be shown as the Phase 3 result.
2. **`phase3_figstyle.py` mislabels the field types without any error.** Evidence: the
   regenerated `structure_boxplots.png` calls the 18 no-tree plots "Low, many trees" and the
   77 low-forest plots "Scrub"; the regenerated `stand_view_10_vs_3.png` and
   `species_groups.png` are wrong in the same way. Next: re-key the names, and have the figure
   scripts check the names against the medians in `odisha_phase3_0_results.txt`.
3. **Two of the four figure scripts do not run from a clean checkout.** Evidence:
   `odisha_phase3_4b_field.py` stops with `AssertionError` in `check_field`;
   `odisha_phase3_4d_results.py` stops with `AttributeError: ... no attribute 'OUT_NAME'`.
   `odisha_phase3_4b_field.py` overwrites two committed figures before it stops. Next: as
   listed above; and move its checks before its first `save`.
4. **`odisha_phase1_tests456_results.txt` is older than its script.** Evidence: the Phase 1
   row. The committed file lacks the warning that the GEDI row is withdrawn, which the script
   has printed since `36a0c73`. Next: commit the regenerated file, in its own commit, saying
   that no number changed.
5. **Run times in result files.** `CLAUDE.md` says result files hold results only.
   - `odisha_phase3_3_results*.txt` (4 files): two run-time lines each. The script has been changed (commit `20727c1`) so that these two lines no longer carry seconds; the timings go to a `.log` beside the results file (git-ignored). Confirmed for all four files: re-run with the edited script in a clean clone, the diff against each committed file is exactly those two lines (`2 2` in `git diff --numstat`), with every statistic identical; for example `[10 ha] rotation nulls: unconditional 1999 in 235 s, failures 0; ...` becomes `[10 ha] rotation nulls: unconditional 1999, failures 0; ...`. The four regenerated files are committed in `a4a29b9`; they are byte for byte the files that run wrote. Done.
   - `odisha_phase2_5_results.txt` and `odisha_phase2_5_results_districts.txt`: FIXED. The script
     was changed the same way and both files were regenerated with it in a clean clone (pilot and
     full set). In each file the only lines that changed are the nine `rotation null:` lines,
     which lose their seconds, and the closing blank line and `total runtime N s` line, which
     are gone. Every statistic is identical; the summary CSVs and figures are byte-identical.
   - `odisha_script/gate_effect_results.txt`: five lines such as
     `segmentation for gate_effect_arm_a took 94.8s`, written by `scripts/gate_effect.py`.
     That script needs Earth Engine, so the fix cannot be confirmed by a re-run tonight.
     Neither file was edited. Next: move the timings to a log in the script, and regenerate the
     file at the next Earth Engine run.
   - `odisha_script/phase3_before_regroup/*.txt` (4 files): two run-time lines each. They are a
     record and were not edited (see Questions).
6. **Dates in result files that are not data.**
   - `odisha_phase3_stands_unchanged.txt` ends with a hand-added line
     "(written 2026-10-08 15:40 by: ...)". Its first line also holds a folder path on the
     machine it was run on.
   - The 19 `phase2_vectors/*_run.json` run records hold `run_dir`, a folder name with the run's
     date and time in it (for example `runs/odisha_v120_3ha_angul_20261008_144007`). A re-run
     will always change that line.
   - Not problems: survey dates in the Phase 1 files, the image date range in
     `odisha_phase1_9_results.txt`, and the dates of rules and decisions quoted in
     `odisha_phase2_0_results.txt` and `odisha_phase3_0_results*.txt` are fixed text or data.
   Next: decide whether `run_dir` belongs in the committed run record (see Questions).
7. **`odisha_phase3_stands_unchanged.txt` cannot be reproduced by the command written in it.**
   It records `--ref main`; `main` has moved. Evidence: the Phase 3 row. Next: regenerate with
   `--ref cff45d9`, the command `PHASE3_STATUS.md` already gives, and drop the dated line.
8. **`PHASE1_STATUS.md`, "Reproducing", covers only steps 7 to 11.** Steps 0 to 6 write eight
   of the committed files and have no listed command. Next: add them (they are in the Phase 1
   table above).
9. **`odisha_phase1_7_meta_zero_diagnosis.py` cannot be run offline on purpose.** It calls
   Earth Engine whenever credentials are present, and rewrites the whole results file. Next:
   an option to run part A alone.
10. **One committed figure was made on a different library version.**
    `odisha_phase1_8_separation_null.png` says Matplotlib 3.11.1; the environment has 3.11.0.
    The picture is identical. Next: nothing needed, unless byte-identical figures are wanted,
    in which case pin Matplotlib and regenerate this one file.

## Still to do

Every offline job has finished and is in the tables above. Not started, and needed before the report is complete:

1. Decide whether segmentation should always run from cached features ("Earth Engine re-runs", section 4), and if so re-run the configs that segmented live. Re-run the chance tests on re-run stands if the stand-level differences are to be carried into Phase 3.
2. Fix the figure scripts and `phase3_figstyle.py`, regenerate the eleven figures and rewrite `deck_facts.md` from the final results (Problems 1 to 3).
3. Move run times out of `scripts/gate_effect.py` and regenerate `gate_effect_results.txt` at the next Earth Engine run (Problem 5).
4. Regenerate `odisha_phase1_tests456_results.txt` and `odisha_phase3_stands_unchanged.txt` in their own commits (Problems 4 and 7).
