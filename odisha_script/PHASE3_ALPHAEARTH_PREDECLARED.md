# AlphaEarth against the field plots: what was fixed in advance

Committed **before any AlphaEarth score was computed**. Its date is the date of its commit.
Written by Claude Code from the defaults of the round 2 brief (task A4; PR #42, question 3).
It records the one primary analysis, the three checks that will be reported whatever they show, and
what happens when a test cannot be made. Nothing here was chosen after seeing an AlphaEarth
result, and nothing may be added to the "primary" line afterwards.

`odisha_phase3_demo_fes.py` does not score or test the AlphaEarth stands until this file
is committed, unchanged on disk, and on the remote branch.

## What is already known

- The hand-crafted results of Phase 3 (`PHASE3_STATUS.md`): at 10 hectares and at 3 hectares,
  0 of the 10 tests survive the Holm correction, in the primary analysis and in each of the
  three checks. The best of the ten is drawing on all plots at 10 hectares (p = 0.063).
- The AlphaEarth join. The committed plot table (`phase2_plots_joined_districts.csv`) has
  held the AlphaEarth columns since Phase 2: 267 of the 274 plots have an AlphaEarth stand
  and all 267 have a stand type. This says where the plots fall. It relates no field
  measurement to a stand.
- The hand-crafted results on the stands of the demo set, and the join of all three arms to
  those stands (`odisha_script/phase3_demo/`). The driver's first run makes them, skips the
  AlphaEarth arm and exits with status 3. That run can come before this file is pushed. The
  join says where the plots fall on the AlphaEarth stands. It computes no AlphaEarth score.
- The AlphaEarth stand files that will be scored (they are this analysis's input, so they
  exist already; `docs/demo/remerge/`). Stands, and stands with a type: Angul 99 and 93,
  Dhenkanal 220 and 208, Kendujhar 122 and 110, Koraput 642 and 465. All 267 plots inside the
  mapped areas fall in a stand with a type (39, 75, 8 and 145). The elbow on these stands is
  5, 5, 6 and 5, against k = 6.
- Three things about stand types, found while making those files (`docs/demo/remerge/README.md`).
  They bear on measures 4 and 5 only; measures 1 to 3 do not use stand types.
  - The types the four runs saved on 13 Oct are not the types a second fit gives, in three of the
    four districts, because the pass that fitted them had computed the merge criteria live. The
    types scored here are from a fit made on the stands scored here, with every input read from
    the cache. That fit repeats exactly when it is run again.
  - The type map moves a great deal when the stands move a little. Between the fit on the
    stands as the runs merged them and the fit on the re-merged stands, the agreement over
    pixels (adjusted Rand index) is 0.41, 0.57, 0.56 and 0.53 in the four districts, although
    only 2.9% to 6.1% of the stand area changed stand.
  - The export stage gives some stands with no habitat pixel of their own a neighbour's type
    (10, 6, 8 and 31 stands in the four districts). They are scored with that type, because it
    is what a run writes.
- **No AlphaEarth score.** `odisha_phase3_1_pairwise_score.py` has never been run on the
  AlphaEarth columns, on any stand files, and neither has the chance test.

## The stands

- The four AlphaEarth runs of the demo set: `odisha_alphaearth_<district>_repro` for Angul,
  Dhenkanal, Kendujhar and Koraput. Earth Engine runs of 13 Oct 2026, commit `df45350`.
- Their saved superpixels, merged again from their saved features under the merge rule below,
  and typed again on the result, by `scripts/remerge_demo_set.py` at commit `5c8dcad`. The
  stand files are `outputs/demo/vectors_new/odisha_alphaearth_<district>_repro_stands_merged.geojson`
  on the Mac; the manifest the driver writes holds the sha256 of each.
- Largest stand allowed: 10 hectares. Stand types: k = 6, as the configs set it. The elbow
  on these stands is reported beside the results and changes nothing.
- The merged layer. A polygon without a stand type stays without one.
- Merge rule: spec-merge-pass2-skip-at-minimum

The driver is given the merge rule with `--merge-rule`. It compares that text with the line
"Merge rule:" above. If the two differ it skips the AlphaEarth arm, says why and exits with
status 3. The hand-crafted arms still run.

## Primary analysis (one, fixed)

- Field types: `odisha_phase3_0_field_types.csv`, unchanged. Trees-only measurements, five
  types, 274 plots.
- Scores: `odisha_phase3_1_pairwise_score.py` as it stands, with `--arm alphaearth`.
- The five headline measures, the same as Phase 3:
  1. Drawing, all plots (`delineation ARI, all plots`).
  2. Drawing, only stands that hold two or more plots (`delineation ARI, multi-plot stands`).
  3. Same-stand precision (`same-stand pair precision`).
  4. Labelling (`labelling ARI, per-district wmean`).
  5. Far-apart labelling (`far-apart same-label rate, alike - differ`).
- Chance test: `odisha_phase3_3_significance.py` as it stands, run on the AlphaEarth arm
  alone. The same rotation null as Phase 3, 1,999 realisations for each null. Measures 1 to 3
  are read against the unconditional null. Measures 4 and 5 are read against the conditional
  null, which keeps only the polygons that carry a stand type.
- One-sided p for each measure. Holm correction over these five tests and no others. A test
  counts if its Holm p is below 0.05.

The chance test is not edited. `odisha_phase3_demo_sigwrap.py` points it at the new stand
files and the new plot table and adds the arm name `alphaearth` for a run of that arm alone.
Two sentences the script prints do not fit this run. It calls a one-arm run "NOT THE PRIMARY
ANALYSIS", and it says the primary file corrects over both arms' tests. For AlphaEarth the
one-arm file is the primary analysis, and five is the declared number of tests.

## Checks, declared now

The same three as Phase 3. Each is run and reported whatever it shows.

- **S1. Without the no-tree type.** `--exclude-types 0`.
- **S2. Four field types instead of five.** `--field-types odisha_phase3_0_field_types_k4.csv`.
- **S3. The all-rows field types.** `--field-types odisha_phase3_0_field_types_allrows.csv`.
  Phase 3 attached a regression clause to S3: the 3 hectare scores had to reproduce two
  committed values. There is no such clause here. No committed AlphaEarth score exists to
  reproduce.

Each check has its own Holm correction over its own five tests.

## Descriptive only

- The per-district labelling rows.
- A side-by-side of the two arms at 10 hectares: AlphaEarth beside the hand-crafted 10 hectare
  stands of the same demo set, score by score, with percentile and p. There is no test of the
  difference and no claim that one arm is better. The two Holm columns are not comparable:
  the hand-crafted one corrects over 10 tests, the AlphaEarth one over 5. The two arms can
  also score slightly different plots, because a plot scores in labelling only where its
  stand has a type.

## Seeds

- Unconditional null: `crc32("alphaearth/stands_merged/phase3_ari")`.
- Conditional null: `crc32("alphaearth/stands_merged/phase3_ari_labelled")`.

These are the script's own seed strings with the arm name filled in. No bootstrap is drawn:
a one-arm run has no arm comparison.

## If a null is not estimable

- A null with fewer than 100 usable realisations is printed as `NOT ESTIMABLE`. That test
  counts as not beating chance. It is reported as it is.
- The script then applies Holm to the tests that remain. The number of tests corrected over
  is stated beside the result.
- If one village cannot be placed, the script discards the whole null. Every test read
  against that null is then not estimable.
- If the identity check fails, the script stops and there is no result. That is reported
  as a failure.
- In none of these cases are the realisations increased, the seeds changed, the null
  replaced or a village dropped.

## The exact commands

From the repo root. `<STANDS DIR>` is the folder holding the stand files named above,
`outputs/demo/vectors_new`.
`$RULE` is the text of the line "Merge rule:" in "The stands", and nothing else.

Either of two forms is run. Which one depends on what `odisha_script/phase3_demo/` holds
when this file is pushed.

The folder already holds the join and the hand-crafted results (the driver's first run).
Then only the AlphaEarth arm is run, on the plot table that is there:

```bash
python odisha_script/odisha_phase3_demo_fes.py --stands-dir <STANDS DIR> \
    --merge-rule "$RULE" --out-dir odisha_script/phase3_demo \
    --arms alphaearth --steps score,significance
```

The folder holds nothing yet. Then one run makes the join and all three arms:

```bash
python odisha_script/odisha_phase3_demo_fes.py --stands-dir <STANDS DIR> \
    --merge-rule "$RULE" --out-dir odisha_script/phase3_demo
```

The one-run form makes the join again. If results in the folder are already committed, it
is refused unless `--replace-committed` is added. The AlphaEarth commands are the same in
both forms.

For the AlphaEarth arm the driver runs, in `odisha_script/`:

```bash
# join: the plots to the staged stands (all three arms in one table; not run again in the first form)
python odisha_phase2_3_join.py --set districts --arms v120,v120_3ha,alphaearth \
    --vectors-dir <staged> --out-dir phase3_demo

# scores: primary, then S1, S2, S3
S="odisha_phase3_1_pairwise_score.py --arm alphaearth \
   --joined phase3_demo/phase2_plots_joined_districts.csv --out-dir phase3_demo"
python $S
python $S --exclude-types 0
python $S --field-types odisha_phase3_0_field_types_k4.csv
python $S --field-types odisha_phase3_0_field_types_allrows.csv

# chance test: primary, then S1, S2, S3
G="odisha_phase3_demo_sigwrap.py --vectors-dir <staged> \
   --joined phase3_demo/phase2_plots_joined_districts.csv --single-arm alphaearth -- \
   --arms alphaearth --rotations 1999 --boot 4000 --out-dir phase3_demo"
python $G
python $G --exclude-types 0
python $G --field-types odisha_phase3_0_field_types_k4.csv
python $G --field-types odisha_phase3_0_field_types_allrows.csv
```

Result files, in `odisha_script/phase3_demo/`:

- `odisha_phase3_1_score_alphaearth_merged_districts.txt`, and the same name with `_excl0`,
  `_ft-k4` and `_ft-allrows` for the checks.
- `odisha_phase3_3_results_alphaearth.txt`, and `odisha_phase3_3_results_excl0_alphaearth.txt`,
  `_ft-k4_alphaearth.txt` and `_ft-allrows_alphaearth.txt` for the checks.

## What Claude Code expects, stated so it can be wrong

I expect none of the five tests to survive the correction. The hand-crafted stands did not,
at either size, and 20 villages give the test little power. For the two labelling measures I
expect, besides, that whatever they show will not be stable: the type map they rest on moved a
great deal for a small change of the stands. I have no expectation for S1, S2 and S3. If any
primary test survives, that is a finding about the AlphaEarth 10 hectare stands of this demo
set. It will be reported as one and checked again on the final re-run.
