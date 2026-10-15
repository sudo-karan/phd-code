# phase3_demo: the comparison with the FES field plots, on the demo set

This folder holds the Phase 3 comparison run on the stands of the demo set: the Earth Engine
runs of 13 Oct 2026 (commit `df45350`), re-merged. The merge rule the stands were made under
is in `fes_manifest.json`. The committed Phase 3 results in `odisha_script/` are on the
earlier stands and are not touched.

Everything here is written by `odisha_script/odisha_phase3_demo_fes.py`. It runs the existing
scripts as they stand and computes nothing of its own.

## What is in it

| File | What it is |
|---|---|
| `phase2_plots_joined_districts.csv` | The plots joined to the new stands, all arms in one table (`odisha_phase2_3_join.py`). |
| `odisha_phase2_3_results_districts.txt` | The join's own report. |
| `odisha_phase3_1_score_v120_merged_districts*.txt` | Scores, hand-crafted features, stands of at most 10 hectares. |
| `odisha_phase3_1_score_v120_3ha_merged_districts_3ha*.txt` | Scores, hand-crafted features, stands of at most 3 hectares. |
| `odisha_phase3_1_score_alphaearth_merged_districts*.txt` | Scores, AlphaEarth, stands of at most 10 hectares. |
| `odisha_phase3_3_results*.txt` | The chance test for the two hand-crafted stand sizes together. |
| `odisha_phase3_3_results*_alphaearth.txt` | The chance test for AlphaEarth alone. |
| `fes_manifest.json` | The git commit and whether the tree had uncommitted changes, the command line, the merge rule, the sha256 and source of every stand file, and the result files written. |

A name without a suffix is the primary analysis. `_excl0` is check S1, `_ft-k4` is S2 and
`_ft-allrows` is S3. Run times are in the `.log` files, which git ignores. A file with `_rot`
or `_boot` in its name is a short test run, not a result.

## The hand-crafted analyses are Phase 3's, unchanged

The primary analysis and the three checks are the ones fixed in `PHASE3_PREDECLARED.md`. The
field types, the five measures, the rotation null with 1,999 realisations, and the Holm
correction over the 10 tests of the two stand sizes are all the same. The scripts are the
same files. Only the stands differ: they are the re-merged stands of the demo set.

**S3's regression clause does not apply here.** `PHASE3_PREDECLARED.md` says that under S3
the 3 hectare drawing scores must reproduce 0.0066 (all plots) and 0.0253 (shared stands)
exactly. That clause holds for unchanged stands only. These stands were re-merged, so the two
values are not expected to reproduce, and a different value is not a failure. S3 is reported
here as a check like S1 and S2.

## AlphaEarth

The AlphaEarth analysis is declared in `odisha_script/PHASE3_ALPHAEARTH_PREDECLARED.md`. The
script scores and tests the AlphaEarth stands only when that file is committed and on the
remote branch. AlphaEarth is tested alone, with Holm over its own five tests. The
hand-crafted Holm values are over ten tests, so the two Holm columns are not comparable.

## How to make it again

From the repo root, with the stand files in `<STANDS DIR>`:

```bash
python odisha_script/odisha_phase3_demo_fes.py --stands-dir <STANDS DIR> \
    --merge-rule "<as in the manifest>" --out-dir odisha_script/phase3_demo --dry-run   # checks only
python odisha_script/odisha_phase3_demo_fes.py --stands-dir <STANDS DIR> \
    --merge-rule "<as in the manifest>" --out-dir odisha_script/phase3_demo --replace-committed

# the rows for the UI and the tables for docs/demo/fes_comparison.md
python odisha_script/odisha_phase3_demo_fes.py --collect --out-dir odisha_script/phase3_demo \
    --json ui_data_fes.json --markdown fes_table.md
```

`--replace-committed` is needed once the results are committed: without it the script does
not overwrite a committed result. `fes_manifest.json` is the record of the runs and is
rewritten by every run. A run that joins again sets the earlier results aside in
`.fes_earlier/` and puts them back if the join fails. A re-run reproduces when `git diff` shows no change in the
result files. Offline; no Earth Engine.
