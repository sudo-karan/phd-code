# Odisha on boxes: what is fixed before the runs

Written 13 Oct 2026 by Claude (chat), from Jaskaran's decision of the same day, and committed
**before any of the four box runs was started**, so before any stand or score on the boxes
exists. It fixes the one primary analysis and the checks that will be reported whatever they
show, on the pattern of `PHASE3_PREDECLARED.md`. Nothing may be added to the primary line
afterwards.

## What changes, and what does not

The 3 ha hand-crafted arm of Phase 3 is run again on new areas. Two things change:

1. **The area.** Per habitation with at least 5 plots, a north-up box around its plots, widened
   by 300 m on every side (`odisha_squares_0_aois.py`), in place of the convex hull of the plots
   plus 300 m (`odisha_phase2_0_aois.py`). Boxes that meet are merged into the box around both;
   only Bilaput and Hatimunda meet, as their hulls did. 8,248 ha in 20 boxes, against 4,299 ha in
   20 hull parts. The same 267 plots fall inside, and the same 7 fall outside.
2. **The merge rule.** `merge.pass2_skip_at_min_area: true` (`docs/decisions.yaml`,
   `spec-merge-pass2-skip-at-minimum`), the rule that configs of new runs set.

Everything else is the 3 ha arm as Phase 3 ran it: the v120 features, SNIC seed spacing 6, stands
of 1 to 3 ha, k = 5 stand types fitted per district, seed 42, and the field types. The configs are
`configs/odisha_v120_3ha_squares_<district>.yaml`; `tests/test_squares_configs.py` checks that
they differ from the `_repro` 3 ha configs in the area, the merge rule, the name and the Drive
folder only.

Why: Jaskaran's decision (PR #43, option (b)), so that the pipeline is shown on a whole rectangle
of landscape around each village instead of on outlines drawn from the plots themselves. It was
not taken to improve a score: no score on the boxes exists. AlphaEarth and the 10 ha arm stay on
the hull runs of the demo set for now.

## Primary analysis (one, fixed)

- **Field types:** the Phase 3 primary typology, `odisha_phase3_0_field_types.csv` (trees only,
  5 types). Not refitted.
- **Plots:** the 267 inside the boxes.
- **Stands:** the merged stands of the four box configs, joined to the plots by the Phase 2 join
  rule (`odisha_phase2_3_join.py`: a plot takes the stand that covers it; where several do, the
  lowest stand id).
- **Scores:** the five Phase 3 statistics, computed as `odisha_phase3_1_pairwise_score.py` and
  `odisha_phase3_3_significance.py` compute them (stands keyed by district, labelling within
  district, far-apart pairs over 2 km):
  1. drawing: adjusted Rand index (ARI), all plots;
  2. drawing: ARI, stands holding two or more plots;
  3. drawing: same-stand pair precision;
  4. labelling: ARI, the plot-weighted mean of the per-district ARIs;
  5. labelling: far-apart same-label rate, alike minus differ.
- **Chance:** the rotation null of `odisha_phase3_3_significance.py` as it stands, 1,999
  realisations, with each AOI part now a box: the part's plot cloud is rotated and moved rigidly to
  a random position with every plot inside the box, and each plot takes the stand under it. The
  unconditional null for 1 to 3 and the conditional (typed-stand) null for 4 and 5, as in Phase 3.
  The seed strings are the script's, with the arm's own name.
- **Correction:** Holm over these five tests. A test passes when its Holm-corrected p is at most
  0.05. With one arm, the script's arm comparison, village bootstrap and jackknife do not apply.

## Checks, declared now

- **S1. Without the no-tree type.** Every score again with field type 0 left out, as in Phase 3.
- **S2. Four field types**, as in Phase 3. (Phase 3's S3 was a regression check that holds only
  for unchanged stands, so it does not apply here.)
- **Beside the hull run, descriptive only.** The five scores of the box run next to those of the
  hull run at 3 ha, re-merged under the same rule (brief task A2), on the same 267 plots. No test
  of the difference: the two runs differ in area, and their nulls move the plots over different
  areas.
- **How far the null moves the plots.** For each part, the median distance a plot moves under the
  null, on the boxes and on the hulls. A box can let the plot cloud travel further than a hull
  does, and a null that moves plots further from where they were measured is easier to beat,
  because land close by is alike. This says how much further; it is reported whatever it shows.

## What Claude (chat) expects, stated so it can be wrong

On the hulls at 3 ha no test passed (Phase 3: drawing on all plots at the 92nd percentile of
chance, p = 0.080, Holm p = 0.716; labelling at the 83rd). The boxes add land around the plots but
change nothing about the plots themselves, and most plots still sit alone in a 3 ha stand. I expect
the scores to stay small (every ARI under 0.1) and no test to pass after the correction. If the
null moves plots clearly further on the boxes, the percentiles may rise for that reason alone,
which is why the check above exists. A pass would be a change of conclusion and is reported as
one.

## Note of 19 Oct 2026 (round 11): not run

The analysis declared here was never run on the box runs (`docs/handoff/2026-10-16-round8.md`,
Task 3), and on 18 Oct 2026 Jaskaran decided that it will not be: the box runs stay a descriptive
comparison beside the kept-land runs, not a declared score (register entry
`field-box-runs-a-descriptive-comparison-only`). Their stands are scored only as the kept-land
check's descriptive analysis beside the box runs (`PHASE_KEPTLAND_PREDECLARED.md`, "Beside the box
runs, descriptive only"), with no chance test and no test of any difference. Nothing declared above
is changed.
