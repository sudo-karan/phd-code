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
