# Phase 3 re-analysis: what was fixed in advance

Written 2026-10-07 and committed **before any score was recomputed**. It records
the two changes being made, the one primary analysis, and the sensitivity checks
that will be reported whatever they show. Nothing here was chosen after seeing a
result, and nothing may be added to the "primary" line afterwards.

## The two changes

1. **Field truth, trees only.** The five structural forest types were built from
   four measurements that did not count the same rows of the field sheet: height
   and trunk area used every row (168 stumps, 290 climbers, 953 shrubs and 1,539
   saplings and seedlings included), while "number of trees" counted only rows
   marked Tree. Height and trunk area now use Tree rows only; a plot with no Tree
   row gets height 0 and trunk area 0. Crown cover and tree count are unchanged.
   `odisha_phase3_0_field_structure_types.py --rows trees` (the default);
   `--rows all` still reproduces the previous typology label for label.
2. **Stand types for the 3 hectare stands: 5, not 6.** The first 3 hectare run
   carried 6 over from the 10 hectare configs. The elbow on the 3 hectare stands
   themselves gives 5 in every district and pooled. Only labelling depends on it. (See the note of 20 Oct 2026 at the end.)

## Primary analysis (one, fixed)

- Field types: trees-only measurements, 274 plots, number of types chosen by the
  elbow rule (knee of the inertia curve, 2 to 12 groups, seed 42). It selects 5.
- Stands: 10 hectare arm with 6 stand types; 3 hectare arm with 5 stand types.
- Scores: `odisha_phase3_1_pairwise_score.py` as it stands (stands keyed by
  district; labelling within district).
- Chance test: `odisha_phase3_3_significance.py` as it stands (rotation null,
  1,999 realisations per arm; Holm over the headline tests).

## Sensitivity checks, declared now

The stress test of the new typology (run on field data alone, no stand or score
read) showed that 5 is a judgement under a pre-set rule rather than a fact of the
data: the knee is narrow (distance 0.263 at 5 against 0.250 at 6 and 0.249 at 4),
silhouette and Davies-Bouldin prefer 2 and Calinski-Harabasz prefers 4, and the
15 no-tree plots are what hold the elbow at 5 (without them it is 6). The plots
are a continuum with one real gap: no trees against everything else. So:

- **S1. Without the no-tree type.** Every score recomputed with field type 0
  (18 plots: the 15 with no Tree row and 3 with one or two very thin trees)
  left out. If agreement disappears, it rested on "trees against no trees".
- **S2. Four field types instead of five.** The stable neighbour of 5 (assignments
  agree across random starts at ARI 0.994; six types do not, mean 0.669).
- **S3. The previous all-rows typology.** For continuity with the numbers in
  PR #40. With unchanged stands, the 3 hectare delineation scores under S3 must
  reproduce the committed values exactly (0.0066 all plots, 0.0253 shared stands);
  that is a regression check on the redrawn stands, not a result.

## What I expect, stated so it can be wrong

The trees-only and all-rows typologies agree at ARI 0.914 and only 9 of 274 plots
change group, so I expect the primary scores to move in the third decimal and the
conclusion of PR #40 (neither stand size beats chance on drawing or labelling) to
stand. I have no expectation for S1 and S2. If any primary headline test survives
the Holm correction, that is a change of conclusion and will be reported as one.

---

**Note of 20 Oct 2026 (round 13, review A7).** Change 2 says the elbow on the
3 hectare stands gives 5 in every district and pooled. That holds in the elbow
script's own space (`odisha_phase3_2_k_elbow_odisha_v120_3ha.txt`), which departs
from the clustering stage's in five ways (review A7). It does not hold in the
stage's space. Rebuilt from the same stand files, the elbows by district (Angul,
Dhenkanal, Kendujhar, Koraput) are 6, 6, 6 and 5, pooled 5, with (x − median)/IQR,
and 5, 6, 6 and 6, pooled 5, with each band min-max normalised over the fit rows,
the geometry `wekaKMeans` fits in (review A2). On the stage's own rows of the
`_repro` stands they are 5, 6, 6 and 5 as the stage scaled them, and 5, 6, 6 and 5
min-max. The 5 declared here stays, and so does every score: it was fixed before
any labelling score was computed with it, and this note changes no declaration.
The comparison, with the limits of each route, is in
`odisha_phase3_2_k_elbow_comparison.md`. Apart from the pointer to this note on
line 20, the file is as first written.
