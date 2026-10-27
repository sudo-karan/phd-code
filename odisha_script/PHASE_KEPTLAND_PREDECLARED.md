# Odisha on kept land: what is fixed before the runs

Written 15 Oct 2026 by Claude (chat), from Jaskaran's decisions of 14 and 15 Oct, and committed
while round 6 was at its first, offline step: before any of the four Odisha kept-land runs was
started, so before any kept-land stand or score in Odisha exists. It fixes the primary analysis
and the checks that will be reported whatever they show, on the pattern of
`PHASE_SQUARES_PREDECLARED.md`. Nothing may be added to the primary line afterwards. If any of it
is changed later (Jaskaran plans to go over the settings at the weekend), the change is made in a
new commit that says whether any kept-land score existed by then.

## What changes from the box runs, and what does not

The four 3 ha box runs of 13 Oct (`configs/odisha_v120_3ha_squares_<district>.yaml`) are run
again with the stands drawn on kept land only. The configs are
`configs/odisha_v120_3ha_squares_<district>_keptland.yaml`; `tests/test_keptland_configs.py`
checks which keys differ. What changes (each a register entry in `docs/decisions.yaml`):

1. **Mask before SNIC** (`segmentation.mask_before_snic: true`, D1). Superpixels and stands lie on
   trees and scrub only (IndiaSAT classes 6 and 12, majority vote, WorldCover where IndiaSAT has
   no data), with kept land clipped to the box before SNIC. Small patches of kept land are not
   dropped: each one that touches no other kept land stays a stand of its own.
2. **Soft ceiling in the merge's second pass** (`merge.pass2_soft_ceiling: true`, D2). A piece
   still under 1 ha may join a neighbour even if the stand then passes 3 ha, up to 4 ha, in
   Jaskaran's order of choice (`spec-merge-pass2-soft-ceiling`).
3. **Stands under 1 ha left out of the k-means fit** (`clustering.fit_excludes_stands_below_min_area:
   true`, D3). They get the type of the nearest fitted cluster.
4. **Distance to water capped at 10 km** (round 6), in place of the fill value past 10 km.

Everything else is the box runs as they ran: the same 20 boxes, the v120 features, SNIC seed
spacing 6, stands of 1 to 3 ha, k = 5 stand types fitted per district, seed 42,
`merge.pass2_skip_at_min_area: true`.

Why: Jaskaran's decision of 14 Oct ("we need to mask before snic and merge only where possible")
and the decisions that followed from it. None was taken to improve a score: no kept-land score in
Odisha exists.

## Primary analysis (one, fixed)

- **Field types:** the Phase 3 primary typology, `odisha_phase3_0_field_types.csv` (trees only,
  5 types). Not refitted.
- **Plots:** the 267 inside the boxes.
- **Joining plots to stands.** A plot takes the stand that covers it; where several do, the
  lowest stand id (the Phase 2 rule, `odisha_phase2_3_join.py`). **New:** a plot that no stand
  covers takes the nearest stand whose edge lies within 30 m of it, ties broken by the lowest
  stand id. A plot with no stand within 30 m is left out of every score, and the number left out
  is reported per district.
  - Why: the land-cover map has 30 m pixels and plot positions in forest carry some metres of
    GPS error, while the field check needs every plot FES measured in forest. Jaskaran's rule (15
    Oct): count as forest what holds most, if not all, of the FES plots. The current classes hold
    253 of the 267 plots; of the other 14, Claude (chat) measured on the simplified land-cover
    shapes of `ui_data/` that 9 lie within 11 m of trees or scrub, 11 within 30 m, 13 within 45 m
    and one at 71 m. Widening the mask by 30 m instead would add about 956 ha of fields to the
    stands; Jaskaran chose the 30 m rule in the field check (option (b)). The rule was chosen from
    the plots' positions only, never from a score, and is the same in all four districts.
- **Scores:** the five Phase 3 statistics, computed as `odisha_phase3_1_pairwise_score.py`
  computes them (stands keyed by district, labelling within district, far-apart pairs over 2 km):
  1. drawing: adjusted Rand index (ARI), all plots;
  2. drawing: ARI, stands holding two or more plots;
  3. drawing: same-stand pair precision;
  4. labelling: ARI, the plot-weighted mean of the per-district ARIs;
  5. labelling: far-apart same-label rate, alike minus differ.
- **Chance: not run now** (Jaskaran, 15 Oct: the 1,999 placements take too long for now). Until
  it runs, the five scores are reported as numbers only: no pass or fail, and no claim that they
  are more, or less, than chance would give. When it runs, it is the rotation null of
  `odisha_phase3_3_significance.py` as declared for the boxes (1,999 realisations, the
  unconditional null for 1 to 3 and the conditional one for 4 and 5, Holm over the five tests,
  a pass at a Holm-corrected p of at most 0.05), with two changes:
  - each placed plot joins a stand by the same rule as above, 30 m included;
  - a placed plot with no stand within 30 m is left out of that one realisation, not forced onto a
    stand. Forcing every plot onto a stand makes the null unbuildable on kept land: for
    Bilaput-Hatimunda (59 plots, 55 on kept land), about 1 placement in 4,800 qualifies, against a
    cap of about 225 attempts per realisation (Claude (chat), 14 Oct, simulation on the box
    land-cover shapes).

## Checks, declared now

- **S1. Without the no-tree type.** Every score again with field type 0 left out, as in Phase 3.
- **S2. Four field types**, as in Phase 3.
- **How the plots join.** Per district: plots on a stand, plots joined by the 30 m rule, plots
  left out. Every score again with only the plots a stand covers (no 30 m rule).
- **Beside the box runs, descriptive only.** The five scores of each district's 13 Oct box run
  next to the kept-land run's, on the same plots. No test of the difference.

## What Claude (chat) expects, stated so it can be wrong

The box runs at 3 ha drew stands over fields and villages too; the kept-land runs draw them on
trees and scrub only, and most plots sit in forest. That should make the stands around the plots
more alike inside, but most plots will still sit alone in a stand of 1 to 3 ha, and with many
small cut-off patches the stand count rises. I expect the five scores to stay small (every ARI
under 0.1), much as on the hulls and the boxes, and the plots joined by the 30 m rule to be about
11 of the 14 off kept land. A clear rise in any score would be a change of conclusion and is
reported as one, but without the chance test it cannot be called more than chance.

## Change of 15 Oct 2026 (round 7): the runs that are scored

Made by Claude Code on Jaskaran's instruction of 15 Oct 2026 (round 7,
`docs/handoff/2026-10-15-round7.md`).

- **The scored runs are the four descending-orbit kept-land runs,**
  `configs/odisha_v120_3ha_squares_<district>_keptland_s1desc.yaml`: the kept-land configs above
  with `data_load.s1_orbit: DESCENDING` (Jaskaran's answer (b) to question 4 of
  `docs/handoff/2026-10-15-round6.md`; register entry `spec-odisha-keptland-s1-orbit-descending`).
  Over the boxes the ascending orbit has 1 to 3 Sentinel-1 images in 2017 to 2022 in Koraput,
  Kendujhar and Angul, against 188 to 204 descending, so the radar statistics of the round-6 runs
  rest on one to three dates. The orbit was chosen by these image counts, not by any score.
- Everything else above is unchanged: the field types, the plots, the join with the 30 m rule,
  the five scores, the chance test not run now, and the checks. "Beside the box runs" still means
  each district's box run of 13 Oct.
- **No kept-land score existed when this was changed.** The four round-6 kept-land runs
  (`configs/odisha_v120_3ha_squares_<district>_keptland.yaml`,
  `docs/reproducibility/keptland_runs/`) were never scored, and `ui_data/` showed their plots
  without a stand. The `_s1desc` runs are not run yet.

## Change of 18 Oct 2026 (round 10): an AlphaEarth arm

Made by Claude Code on Jaskaran's instruction (round 9's Task H, `docs/handoff/2026-10-17-round9.md`,
run in round 10, `docs/handoff/2026-10-18-round10.md`). It adds a second arm and changes nothing
above: the primary analysis, the field types, the plots, the join, the five scores, the checks and
the chance test stay as they are, and so does Claude (chat)'s amendment
`PHASE_KEPTLAND_AMENDMENT_chance_checks.md`. This change is committed before any config of the arm
exists.

- **The arm's runs** are four configs, `configs/odisha_alphaearth_3ha_squares_<district>_keptland_r9.yaml`.
  Each is a copy of the primary's re-run, `configs/odisha_v120_3ha_squares_<district>_keptland_s1desc_r9.yaml`,
  changing only the feature description to AlphaEarth, as `configs/sanjay_van_alphaearth_keptland.yaml`
  does against `configs/sanjay_van_baseline_keptland.yaml`. SNIC draws the superpixels on the 64
  AlphaEarth dimensions (`segmentation.input_bands`), and k-means types the stands on them
  (`clustering.feature_source: embedding`). The annual images (`GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL`)
  are averaged over 2017 to 2022. `tests/test_r9_configs.py` checks that nothing else differs.
- **The same boxes and the same mask.** Everything else is the copied config: the 20 boxes, the
  kept-land mask before SNIC, SNIC's spacing 6 and compactness 0.5, stands of 1 to 3 ha with the
  soft ceiling, k = 5 stand types per district, seed 42, the stands under 1 ha left out of the fit.
  The merge keeps its three criteria (canopy height, its spread, the NDVI amplitude), which still
  come from the hand-crafted features, so that what makes two pieces one stand is the same rule in
  both arms, as in Sanjay Van. The arm computes the optical, structure and embedding features; the
  radar and static features are read by nothing in it (`fmu.pipeline.feature_stage_names`, and
  the clustering and export stages read the embedding alone), so the radar orbit plays no part.
- **Scored as the primary, on the same plots.** The field types (`odisha_phase3_0_field_types.csv`),
  the 267 plots inside the boxes, the join (the covering stand, the lowest stand id where several
  cover; the nearest stand whose edge lies within 30 m; left out past 30 m, reported per district),
  the five scores and the checks (S1, S2, how the plots join with every score again on the covered
  plots only, the box runs beside it) are all exactly the primary's. The masks of the two arms are
  the same, so they should leave out the same plots. If the plots the arm scores differ from those
  the primary's re-run scores, the difference is reported as counts per district and the plots are
  named, and no further analysis is made of it.
- **Reported beside the primary, descriptive only.** The arm's five scores are written next to the
  primary re-run's (`keptland_s1desc_r9`), on the same plots. No test of the difference between
  the arms, and, as for the primary, no pass or fail and no claim about chance until the chance
  test runs.
- **The chance test is not part of this change.** Claude (chat)'s amendment says its check C1
  applies to every arm scored under this file, this one included. Running the chance test, C1
  with it, and deciding how it treats two arms are for the chance test and its author, not for
  this change.
- **Files.** `odisha_script/odisha_keptland_score.py --runs 'odisha_alphaearth_3ha_squares_{district}_keptland_r9' --stem keptland_alphaearth_r9`,
  with the stand layers in `docs/reproducibility/r9_runs/`, writes
  `odisha_script/keptland_scores/keptland_alphaearth_r9_*`; no older file is written over.
- **The kept-land scores that existed when this was written.** The primary's on the round 7 runs
  (`keptland_s1desc_scores.json`, commit `f56ad57`); the chance test's rehearsal on the same stands
  (`keptland_s1desc_chance_rehearsal.txt`, `f041170`, Claude (chat)); the primary's on the round 9
  re-runs (`keptland_s1desc_r9_scores.json`, `99480b7`); and the comparison of the two
  (`keptland_s1desc_r9_vs_s1desc.md`, `e926a31`). **No AlphaEarth stand or score on the boxes or
  on kept land existed**: no such config existed before this change.
- **AlphaEarth scores in Odisha on other stands did exist:** the demo set's AlphaEarth runs on the
  village hulls (10 ha, k = 6, no kept-land mask), scored in round 2 under
  `PHASE3_ALPHAEARTH_PREDECLARED.md`. Their logs are in `odisha_script/phase3_demo/` on the Mac;
  their result files are not on the branch. While writing this, Claude Code read the last lines of
  the primary score's log there. Nothing in this arm is Claude Code's choice, and nothing in it was
  chosen from a score: the copy, the one change and k = 5 are the brief's, and the AlphaEarth
  settings (the 64 bands, the mean over 2017 to 2022) are Sanjay Van's.

## Note of 19 Oct 2026 (round 11): which scores are the record

Since 18 Oct 2026 (Jaskaran's answer to question 1 of `docs/handoff/2026-10-18-round10.md`; register
entry `field-keptland-scores-of-record-are-the-r9-re-runs`) the scores of record are those on the
`_r9` stands: the primary's re-runs (`keptland_scores/keptland_s1desc_r9_scores.*`) and the
AlphaEarth arm (`keptland_scores/keptland_alphaearth_r9_scores.*`). The scores on the runs of 15 Oct
(`keptland_scores/keptland_s1desc_scores.*`) stay as history. Kept-land scores existed when this
note was written: those of round 7, of the `_r9` re-runs and of the AlphaEarth arm, the chance test's
rehearsal and its declared results on both arms. Nothing declared above is changed.

## Change of 19 Oct 2026 (round 12): the 10 ha box runs, both arms

Made by Claude Code on Jaskaran's instruction (the round 12 brief, Task 4, roadmap 3.3;
`docs/handoff/2026-10-19-round12.md`), before any 10 ha run on the boxes. First committed as
`071fbee`; this shorter form, also before any such run, drops what that one added beyond the brief
(the last point). Nothing above is changed and nothing new is added.

- **The runs.** Eight copies of the eight 3 ha `_r9` box runs above, named with `10ha` in place of
  `3ha` (`configs/odisha_v120_10ha_squares_<district>_keptland_s1desc_r9.yaml` and
  `configs/odisha_alphaearth_10ha_squares_<district>_keptland_r9.yaml`), each changing only
  `segmentation.size` from 6 to 10 and `merge.max_area_ha` from 3 to 10, the Sanjay Van 10 ha
  configs' values; k stays 5 (`tests/test_r9_configs.py`).
- **Scored as declared above, unchanged, arm by arm.** Everything above, and Claude (chat)'s
  `PHASE_KEPTLAND_AMENDMENT_chance_checks.md`, applies to each arm's 10 ha runs as to its 3 ha
  runs: the five scores, the plots, the join with the 30 m rule, the checks S1 and S2, how the
  plots join, the 13 Oct box runs beside (the runs on the boxes without the kept-land mask,
  `configs/odisha_v120_3ha_squares_<district>.yaml`; there is no 10 ha one), and the chance test
  as declared, 1,999 realisations per null with Holm, and C1.
- **The chance test's placements.** Given the 10 ha run names, the chance script names the two
  sets `v120_10ha_squares_keptland_s1desc` and `alphaearth_10ha_squares_keptland` and seeds each by
  its name, so each draws placements of its own. Whether they should instead draw their arm's
  3 ha placements is question 5 of the round 12 brief. The 10 ha chance test runs as the answer
  says; with no answer by then, with the script's names, and its results file says so.
- **3 ha and 10 ha side by side**, arm by arm, descriptive only, with no test of the difference.
- **Files.** New files only, in `odisha_script/keptland_scores/` (`keptland_s1desc_10ha_r9_*`,
  `keptland_alphaearth_10ha_r9_*` and the side-by-side tables); nothing older is written over.
- **What existed when this was written.** On the boxes: round 7's kept-land scores (history), the
  `_r9` record of both arms with their declared chance tests and comparisons, and the rehearsal.
  **No 10 ha stand or score on the Odisha boxes or on kept land in Odisha.** At Sanjay Van, 10 ha
  stands on kept land (its kept-land runs, k = 6), which has no field plots to score. In Odisha, 10
  ha scores on other stands, all on the village hulls without the kept-land mask (k = 6): Phase 2
  and Phase 3 (`PHASE2_STATUS.md`, `PHASE3_STATUS.md`; in Phase 3 no test survived Holm at either
  size), and the demo set's runs of 13 Oct, scored then (`docs/reproducibility/odisha_repro/`) and
  tested against chance in round 2, where the hand-crafted 10 ha arm's two drawing tests passed
  after Holm (Holm p 0.010 and 0.027; the log is on the Mac, in `odisha_script/phase3_demo/`); the
  demo set's AlphaEarth runs there were scored in round 2 (`PHASE3_ALPHAEARTH_PREDECLARED.md`).
- **Corrected before any run.** `071fbee` also set the AlphaEarth arm at 10 ha beside the
  hand-crafted at 10 ha, added a rule naming the plots a 10 ha run scores unlike its 3 ha run, and
  fixed the chance test's seed names: none is in the brief. It also said that no 10 ha stand
  existed on kept land, which Sanjay Van's runs contradict, and left the demo set's chance test
  out of what existed.

## Note of 20 Oct 2026 (round 13): the scores of record are from before the round 13 fixes

The scores of record named in the note of 19 Oct 2026 above, and the 10 ha files of the round 12
change, rest on runs from before the round 13 fixes (review `docs/reviews/2026-10-19-review.md`, A1,
A4, A5, A6, B13, B14, B16, B17 and B18; `docs/handoff/2026-10-20-round13.md`). They stay in the repo
as first written, the record from before the fixes, each with a dated note
(`keptland_scores/README.md`). The hand-crafted arm's runs are to be re-run (roadmap R3). A1 and A5
do not reach the AlphaEarth arm, and A4 reaches it in Koraput only (question 1 of the round 13
brief); whether R3 re-runs that arm is put to Jaskaran there. Nothing declared above is changed.

## Change of 26 Oct 2026 (round 14): R3, the four method changes, and k chosen from the elbow report

Made by Claude Code on Jaskaran's instruction (the round 14 brief, Task 2, "the declarations,
committed before any R3 run"; `docs/handoff/2026-10-26-round14.md`), before any R3 config, run,
stand or score exists. Jaskaran decided to run R3 before his meeting with Prof. Seth, so that
October's unused Earth Engine hours are not lost; every method choice below was made before any
R3 result exists. Nothing above is changed except where this section says so.

- **The runs (roadmap R3).** Nineteen copies of the `_r9` configs under the suffix `_r14`: Sanjay
  Van both arms, the eight 3 ha box configs and the eight 10 ha box configs of both arms, and the
  10 km tile in Angul (`configs/<the _r9 name with _r14 in place of _r9>.yaml`), each changing only
  the name and the four settings below, and k as set below. Two more copies of the Angul
  hand-crafted 3 ha config, `..._r14_check_a` and `..._r14_check_b`, identical but for their names,
  are the live check of the round's code (Task 4), not R3 results, and are not scored. (Added 27
  Oct 2026, before it runs: the live check stopped in the merge, so after the merge's fix it runs
  again from scratch as `..._r14_check_c` and `..._r14_check_d`, copies of those two with only
  their names changed, by the same pass rules: Jaskaran's answer to question 11 of the round 14
  record. They are not R3 results either, and are not scored. Added 27 Oct 2026, before it runs:
  that one stopped in the k elbow's table export, so after the fix it runs again from scratch as
  `..._r14_check_e` and `..._r14_check_f`, copies of `..._r14_check_c` and `..._r14_check_d` with
  only their names changed, by the same pass rules, after a smoke test that finishes
  `..._r14_check_c` and `..._r14_check_d` from what they cached and does not count as the live
  check: Jaskaran's answer to question 13. None of these is an R3 result or is scored.) Both arms are
  re-run, Koraput's AlphaEarth runs included (Jaskaran's answers (a) to questions 22 and 1 of the
  round 13 brief).
- **The four method changes**, the same in both arms (each off by default, so no earlier run
  changes; each a register entry in `docs/decisions.yaml`):
  1. `clustering.fit_outside_earth_engine: true`: k-means fitted off Earth Engine with
     scikit-learn on the table of stands, one row per stand, the stands under 1 ha left out of the
     fit and given the nearest centre (as D3 above); median/IQR scaling with exact quartiles;
     k-means++ with 25 starts from seed 42, the start with the lowest within-cluster sum of squares
     kept; each stand's type written back by its label; the best start's sum of squares and the
     starts' median and lowest pairwise adjusted Rand index recorded, a diagnostic of the
     clustering, not a field score (`spec-clustering-kmeans-outside-earth-engine`).
  2. `clustering.log_rule: right_skew`: only right-skewed bands (skew above 1.0, the moment
     coefficient that Earth Engine's skew computes) logged, as log1p((x - min) / IQR), with min over
     every stand, fitted or not; a band whose IQR is 0 dropped first; left-skewed bands not
     transformed; the sine and cosine of an angle (the NDVI phase, aspect) never skew-tested or
     logged, and each such pair scaled with one shared spread, the root mean square of its two IQRs;
     each band's skew recorded before and after (`spec-clustering-log-rule-right-skewed-bands`).
  3. `features_optical.mean_over_window: true`: `ndvi_mean` the fitted curve's mean over the dates
     window (2017-01-01 to 2022-12-31), computed analytically, whatever `time_reference` is (Jaskaran's
     answer (c) to question 31 of the round 13 brief; `spec-optical-mean-over-the-window`). The
     AlphaEarth arm computes it but does not cluster on it.
  4. `k_elbow.in_fit_space: true`: the k elbow on the fit's own rows, in its own space, with its own
     starts, k 2 to 12, and the starts' agreement at each k; no plot read
     (`spec-k-elbow-in-the-fits-space`).
- **The code R3 runs** also carries the fixes of round 13 (review A1, A4, A5, A6, B13, B14, B16,
  B17, B18) and the code changes of round 14's Task 1 (round 13's questions 21, 24, 30, 33, 35, 37,
  40, 41 and 42; register entries named in the round 14 record). They are fixes to how the stands and
  features are made and recorded, not changes to the declared analysis. Added 27 Oct 2026, before
  any R3 result exists: it also carries the merge's two changes of round 14 (merge revision 4): every
  count the merge takes on Earth Engine on the SNIC label image's own projection, with a label image
  more than 1% from the analysis scale refused (Jaskaran's answer to the round 14 record's question
  11; `spec-merge-pixel-counts-on-one-inclusion-rule`), and every tie of the merge broken by
  centroid, pass 1's partner tie too (his answer to question 2; `spec-merge-every-tie-by-centroid`).
  These too are fixes, not changes to the declared analysis. Added 27 Oct 2026, before any R3 result exists: it also
  carries the k elbow's table fix, each row of the elbow's cached table with the same fixed point
  as its geometry, so that Earth Engine exports it (his answer to question 13;
  `spec-k-elbow-table-rows-carry-a-fixed-point`). It changes no number, no file and no key; it too
  is a fix, not a change to the declared analysis.
- **Nothing else in the declared analysis changes**: the plots, the field types (the Phase 3
  primary typology, not refitted), the five scores, the join with the 30 m rule, the checks S1 and
  S2, how the plots join, the 13 Oct box runs beside, the chance test as declared (1,999
  realisations per null, Holm), C1 (`PHASE_KEPTLAND_AMENDMENT_chance_checks.md`), and the 10 ha change
  of 19 Oct 2026 above, each applied arm by arm and size by size as declared.
- **k.** Declared above as 5 for the boxes (6 at Sanjay Van, in its configs). For R3, k for each
  area is chosen by Jaskaran from the elbow report alone (round 14, Task 6:
  `odisha_script/keptland_scores/r14_elbow_report.md`), before any R3 field score exists, and
  committed with his reason before the clustering pass (Task 7). Unless he says otherwise, both
  arms of an area take the same k. The areas are each district at 3 ha and at 10 ha, Sanjay Van and
  the tile. The report reads no plot and computes no field score. For each area and arm it gives the
  within-cluster sum of squares for k 2 to 12 with the knee (the k farthest from the chord between
  the first and last points, the rule of every elbow so far, `fmu.stages.k_elbow.knee`), and the
  starts' median and lowest pairwise adjusted Rand index at each k; and the pooled elbow of the four
  districts for each arm and size (their tables of stands pooled, then preprocessed together by the
  same rule). Until then the `_r14` configs carry the `_r9` k.
- **The chance test's placements.** Each R3 set draws the same placements as its `_r9` set: the seed
  takes no run suffix (review B22; `odisha_keptland_chance.py` strips `_r14` as it strips `_r9`), so
  the four sets keep the names, and the seeds, `v120_3ha_squares_keptland_s1desc`,
  `alphaearth_3ha_squares_keptland`, `v120_10ha_squares_keptland_s1desc` and
  `alphaearth_10ha_squares_keptland`.
- **Side by side**, descriptive only, with no test of any difference: R3 beside `_r9`, arm by arm and
  size by size; 3 ha beside 10 ha for each arm (as the 10 ha change declares); and the two arms
  beside each other at each size. The last was not declared at 10 ha (the 10 ha change above
  dropped it before any run); it is declared here, before any R3 score. Sanjay Van, which has no
  plots: stand counts, sizes, k and the types' shares only.
- **Files.** New files only, beside the old ones (`odisha_script/keptland_scores/`, names with
  `_r14`); nothing older is written over.
- **What existed when this was written.** No `_r14` config, run, stand or score (no config name
  holds `_r14` at the commit of this section). The `_r9` record of both arms at 3 ha and 10 ha, with
  their declared chance tests and comparisons, from before the round 13 fixes (the note of 20 Oct
  above); round 13's elbows in the clustering stage's space, rebuilt from the stand files of
  record and the stage's rows of the demo set (`odisha_phase3_2_k_elbow_comparison.md`), which do
  not use the R3 code; Sanjay Van's kept-land stands. Which scores are the record once R3 exists
  (the note of 19 Oct above names the `_r9` ones) is not decided here: it is put to Jaskaran
  (round 14 brief, Questions).
- **Note of 27 Oct 2026: the pooled elbows also with the rows in reverse order.** k-means++
  depends on the order of the rows, and round 13 found that the order alone can move an elbow by 1
  or 2 (`odisha_phase3_2_k_elbow_comparison.md`). So the elbow report also gives each pooled elbow
  (the four districts of one arm and stand size, pooled in the stated order: Angul, Dhenkanal,
  Kendujhar, Koraput, each by stand label) with the same rows in reverse order, the same
  preprocessing and the same sweep, beside it: both knees and both tables. Each run's own elbow is
  given as before, in one order, the run's. Decided by Jaskaran on 27 Oct 2026 (his answer (b) to
  question 9 of the round 14 record, `docs/handoff/2026-10-26-round14.md`), before any R3 result
  exists: no R3 config has been run, and no R3 elbow, stand or score exists (the live check's two
  runs, which are not R3 results, stopped in the merge before their elbow). Nothing else in this
  section is changed.
