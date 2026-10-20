# The kept-land field check: score files

**Note of 19 Oct 2026 (round 11):** since 18 Oct 2026 the record is the scores on the `_r9` stands,
`keptland_s1desc_r9_scores.*` for the hand-crafted re-runs and `keptland_alphaearth_r9_scores.*`
for the AlphaEarth arm (register entry `field-keptland-scores-of-record-are-the-r9-re-runs`).
Round 7's `keptland_s1desc_{joined.csv,scores.json,scores.txt,scores_run.json}` stay as history;
the first three hold results only and the fourth is their run record, so the note is here and not
in them.

**Note of 20 Oct 2026 (round 13, review C8):** five chance files here,
`keptland_{s1desc,alphaearth}_r9_chance.txt`, `keptland_{s1desc,alphaearth}_10ha_r9_chance.txt` and
`keptland_s1desc_chance_rehearsal.txt`, hold a dated note after their table "How far the null moves
the plots", which `odisha_keptland_chance.py` does not write: a re-run writes each file without it.
The note says why three boxes (BHANRADI SAHI, KHASUGUDA, BARAKANTI) have the largest moves: each is
stretched by one plot that lies 3.9 to 9.3 km from the rest of its habitation (measured in the docstring
of `odisha_script/odisha_squares_0_aois.py`). No number in the five files changed.

**Note of 20 Oct 2026 (round 13, review C27): the rehearsal's files.**
`keptland_s1desc_chance_rehearsal.{txt,json}` (the chance test on round 7's pre-fix stands,
committed in `647a133`) are kept as committed; the brief of round 13 forbids overwriting a
committed result. Two facts about them:
- **The `.json` differs from a regeneration in 23 descriptive values.** Regenerated on 20 Oct 2026
  (`python odisha_script/odisha_keptland_chance.py --out-dir <scratch folder>`, 1,999 rotations,
  offline), the `.txt` is byte-identical to the committed one (before its round 13 note), and in the
  `.json` 23 values differ, all of them `median_m` or `p90_m` under `null_moves_plots/by_box`, by at
  most 8.5e-13 relative (`dhenkanal:Balikurma`'s median, 453.0367430899039 committed against
  453.0367430895191). Every score, null, percentile, p, Holm p and check C1 is identical. The
  regenerated `null_moves_plots` equal those of the declared `keptland_s1desc_r9_chance.json`
  exactly, as the script's Q6 says they should (the same placements); the committed rehearsal's do
  not, by these last-digit differences. The review of 19 Oct 2026 found the same at `5caae3f`.
- **Its run record's `"dirty": true` does not show an edited source tree.** The record
  (`keptland_s1desc_chance_rehearsal_run.json`, commit `42896a8`) lists as modified only the run's
  own two output files: the script reads the git state after writing its results (review C32), so
  rewriting a tracked result marks the tree dirty. The commit that holds them (`647a133`) says the
  run was made at `42896a8` on a clean tree.

**Note of 20 Oct 2026 (round 13; review A1, A4, A5, A6, B13, B14, B16, B17 and B18): the `_r9` and
10 ha results are from before the round 13 fixes.** The results of the hand-crafted 3 ha `_r9` runs
(`keptland_s1desc_r9_*`), of round 12's 10 ha runs of both arms (`keptland_s1desc_10ha_r9_*`,
`keptland_alphaearth_10ha_r9_*`) and of the AlphaEarth 3 ha `_r9` runs (`keptland_alphaearth_r9_*`),
with their `_run.json` records, and the seven side-by-side tables
(`keptland_alphaearth_r9_beside_s1desc_r9.md`, `keptland_chance_r9_both_arms.md`,
`keptland_s1desc_10ha_r9_beside_3ha_r9.md`, `keptland_s1desc_10ha_r9_chance_beside_3ha_r9.md`,
`keptland_alphaearth_10ha_r9_beside_3ha_r9.md`,
`keptland_alphaearth_10ha_r9_chance_beside_3ha_r9.md`, `keptland_s1desc_r9_vs_s1desc.md`) are kept
as first written, the record from before the fixes. No number is changed. The round 13 brief
(`docs/handoff/2026-10-20-round13.md`, Done) says what each fix changes.
- **Where the notes are.** The eight `.txt` files and the seven tables each hold a dated note at
  their end, which the scripts do not write: a re-run writes each file without it (the four chance
  files among them also hold the C8 note above). The `.json` and `.csv` files and the run records
  cannot hold a note, so this one is theirs.
- **The hand-crafted arm.** Its inputs were affected by A1 (distance to water saw no water outside
  the ROI; in Angul every stand read the 10 km cap, at 3 ha and at 10 ha, and the band was dropped
  as constant), A4 (the Sentinel-1 and Sentinel-2 date windows stopped on 30 Dec 2022, which left
  out one Sentinel-1 scene of 31 Dec 2022 over the Angul, Dhenkanal and Kendujhar boxes and two
  Sentinel-2 scenes over the Koraput boxes; read-only call 4 of the brief) and A5 (slope and aspect
  in whole degrees, a flat cell read as facing north). B13 reaches it too: the NDVI phase's cosine
  was log-transformed in every run, its sine too in Angul. Its runs are to be re-run (roadmap R3).
- **The AlphaEarth arm.** A1, A5 and B13 do not reach it: it reads no distance to water, slope,
  aspect or NDVI phase. A4 reaches its two Koraput runs (3 ha and 10 ha) only, through the NDVI
  amplitude, one of the merge's three criteria. Question 1 of the brief asks whether they join the
  hand-crafted ones in R3; until it is answered they are noted as affected, by an amount not
  measured. Over the other boxes A4 left out a Sentinel-1 scene only, which this arm does not read.
  Whether R3 re-runs the arm is put to Jaskaran in the brief.
- **Both arms.** The merge and clustering fixes reach every run: B14 (a stand in several pieces got
  one mean per piece, not one per stand), B16 (the constant-band test and the scaling used histogram
  quartiles, not exact ones; where it was checked, no drop decision of these runs changes), B17 (the
  merge counted a superpixel's pixels and its valid pixels by different rules at the ROI's edge) and
  B18 (the merge tested its area limits on a sum of floats). Of what these files read, A4 (in the
  AlphaEarth arm, in Koraput only), B17 and B18 can move the stand outlines, and so every score, the
  joined tables' stands and the chance tests' nulls; A1, A5 and B13 (the hand-crafted arm only), B14
  and B16 reach only the stand types, and so the two labelling scores, their nulls and the joined
  tables' `cluster` column. A6 changes the layers' `area_ha` and `n_pixels`, which none of these
  files reads. Round 13's Task 1 changes no type of these runs.
- **Not measured:** how far any fix moves a stand, a type, a score or a p; it needs Earth Engine.
  The counts per run are in `docs/reproducibility/r9_runs/README.md` and
  `docs/reproducibility/round12_runs/README.md`. The review's method questions (A2, A3, B12, B15)
  are not fixes of this round and are not covered here.
- **From before the fixes too:** the 13 Oct box runs that the `box_runs` analysis of every scores
  file reads (hand-crafted; A1 and A5 reach them), and round 7's files and the rehearsal, which stay
  as history (the notes above).
