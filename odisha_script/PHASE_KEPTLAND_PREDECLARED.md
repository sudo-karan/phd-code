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
`docs/handoff/2026-10-19-round12.md`). It applies everything above, and Claude (chat)'s amendment
`PHASE_KEPTLAND_AMENDMENT_chance_checks.md`, unchanged to eight more runs: the 10 ha box runs of
both arms. Nothing new is added and nothing above is changed. It is committed before any of the
eight configs exists, so before any 10 ha stand or score on the boxes exists.

- **The runs.** Eight configs, each a copy of one of the eight 3 ha `_r9` box runs above, named
  with `10ha` in place of `3ha`: `configs/odisha_v120_10ha_squares_<district>_keptland_s1desc_r9.yaml`,
  copies of the primary's re-runs, and `configs/odisha_alphaearth_10ha_squares_<district>_keptland_r9.yaml`,
  copies of the AlphaEarth arm's runs. Each changes only `segmentation.size`, from 6 to 10, and
  `merge.max_area_ha`, from 3 to 10, the values of the Sanjay Van 10 ha configs, besides its name
  and description; `tests/test_r9_configs.py` checks that nothing else differs. So SNIC's seeds are
  10 pixels apart and the stands are of 1 to 10 ha, with the soft ceiling (a piece still under 1 ha
  may join a neighbour up to 11 ha). Everything else is the copied run: the 20 boxes, the kept-land
  mask before SNIC, each arm's features and the merge's three criteria, k = 5 stand types per
  district (the brief's; Phase 3's 10 ha arm and Sanjay Van have 6), seed 42, the stands under
  1 ha left out of the fit.
- **Scored as the 3 ha runs, arm by arm, on the same plots.** The field types
  (`odisha_phase3_0_field_types.csv`), the 267 plots inside the boxes, the join (the covering
  stand, the lowest stand id where several cover; the nearest stand whose edge lies within 30 m;
  left out past 30 m, reported per district), the five scores and the checks (S1, S2, how the
  plots join, with every score again on the covered plots only) are all as declared above. "Beside
  the box runs" is unchanged too: each district's 13 Oct box run, the only box runs there are,
  whose stands are of 3 ha. If a 10 ha run scores other plots than its 3 ha run, the difference is
  reported as counts per district and the plots are named, and no further analysis is made of it.
- **The chance test, as declared above and as run on the 3 ha `_r9` stands:** 1,999 realisations
  per null; the unconditional null for scores 1 to 3 and the conditional one for 4 and 5; Holm over
  the five tests within each analysis, a pass at a Holm-corrected p of at most 0.05; each placed
  plot joined by the same rule, 30 m included, and a placed plot with no stand within 30 m left out
  of that realisation; S1 and S2 on the same realisations; and C1 (the chance-check amendment)
  beside score 4, outside Holm. Each set of runs draws its own placements, seeded by its name by
  the chance script's rule (register entry `field-keptland-chance-each-arm-draws-its-own-placements`;
  Phase 3 seeded its 3 ha and 10 ha arms on the village hulls each by its own name):
  `v120_10ha_squares_keptland_s1desc` and `alphaearth_10ha_squares_keptland`.
- **3 ha and 10 ha side by side, descriptive only.** In each arm the five scores and the chance
  test's results at 10 ha are written next to those at 3 ha (the record: `keptland_s1desc_r9` and
  `keptland_alphaearth_r9`), on the same plots; and, as the change of 18 Oct reports its arm beside
  the primary, the AlphaEarth arm at 10 ha beside the hand-crafted arm at 10 ha. No test of any
  difference, between the sizes or between the arms, and no pass or fail beyond each set's own
  chance test.
- **What the 10 ha scores are.** A size check beside the record, not a change of which scores are
  the record (the note of 19 Oct 2026 above).
- **One difference the brief did not choose.** The 10 ha runs are exported after round 12's change
  to how a stand gets its type (register entry `spec-export-stand-type-from-its-fit-row`), the 3 ha
  runs before it. On the analysis grid, where all of them lie, the change alters no stand of the
  eight 3 ha box runs (`docs/reproducibility/r9_runs/stand_types_from_fit_rows.json`).
- **Files.** New files only, beside the 3 ha ones in `odisha_script/keptland_scores/`:
  `keptland_s1desc_10ha_r9_*` and `keptland_alphaearth_10ha_r9_*` (the joined tables, the scores,
  the chance test's results) and the side-by-side tables; no older file is written over. The
  commands are round 10's with the new run names and stems.
- **The kept-land scores that existed when this was written:** round 7's (history); the `_r9`
  record of both arms, with their declared chance tests and comparisons; the chance test's
  rehearsal on round 7's stands. **No 10 ha stand or score on the boxes or on kept land existed.**
  10 ha scores in Odisha on other stands did: Phase 2 and Phase 3 on the village hulls (k = 6, no
  kept-land mask; `PHASE2_STATUS.md`, `PHASE3_STATUS.md`) and the demo set's AlphaEarth runs there
  (round 2).
- **What Claude (chat) expects**, above, was written for the 3 ha runs; nothing is added for 10 ha.
