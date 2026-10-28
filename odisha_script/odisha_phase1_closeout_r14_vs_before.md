# Phase 1 close-out: the file of round 14 (`_r14`) against the file from before it

The review of 19 Oct 2026 (`docs/reviews/2026-10-19-review.md`, finding C21) found that
`odisha_phase1_6_closeout.py` printed a bias between quantities in different units: for vh_iqr and
vv_iqr, radar spreads in dB, it subtracted field Lorey's height in metres. Round 13 put it to
Jaskaran as question 18 (`docs/handoff/2026-10-20-round13.md`); the round 14 brief (26 Oct 2026)
answers it by its recommendation, (a): the rule round 10 applied to step 12. Since the commit
"Round 14, Task 1, Q18: Phase 1 steps 2 and 6 print RMSE and bias only where both sides are heights
in metres", the close-out prints a bias in section A/B only for its eight height products, all in
metres; it prints no RMSE. Nothing else it prints changed, and it still writes
`odisha_phase1_closeout.txt`. The register entry is `field-phase1-rmse-and-bias-only-between-heights`
(`docs/decisions.yaml`).

**This file is not the only change since the committed file.** The committed
`odisha_phase1_closeout.txt` was written before round 13 changed the script for review C22
(commit `ef62da6`: the site means are correlated unrounded and rounded only when printed), and it
holds two dated notes that no script writes (round 11, 19 Oct 2026, and round 13, 20 Oct 2026).
So the `_r14` file is the first committed output of the script with the C22 fix as well, and it
differs from the committed file in three ways, each listed below: the two lines of this change,
the four site-level lines of C22, and the two notes.

## How the new file was made

The script and its input as committed in that commit were copied into an empty scratch folder and
run there with the documented command, so that no committed file was overwritten. The file it
wrote is committed here, byte for byte, as `odisha_phase1_closeout_r14.txt`:

```bash
cd <an empty folder holding only odisha_phase1_6_closeout.py and odisha_plots_sampled_v2.csv>
python odisha_phase1_6_closeout.py
```

| File | SHA-256 |
|---|---|
| `odisha_phase1_6_closeout.py`, the script run | `f560eacf7ac4eebdd3bf18fc37d1c5126e81bdc7ded480a16c4efdbf6a56121b` |
| `odisha_plots_sampled_v2.csv`, its input (unchanged since `5271ea5`) | `f387e391b6cb1a12667805c92c7e1ea87fc69f96e5de63dcab0675c95173010a` |
| `odisha_phase1_closeout.txt` as written, committed as `odisha_phase1_closeout_r14.txt` | `2f16d1d22f361d92917aa09a1c8822d547c9d1f55052a0251412a29bc780610e` |
| `odisha_phase1_closeout.txt` as the script before the change wrote it (at `284b73d`, with the C22 fix) | `83a8ccea7ae84ac0fdf9006e57e3c04a49ebd061b7245b3a39609054d685f17e` |

Machine: macOS 26.7.1, Python 3.13.14, NumPy 2.5.1, pandas 3.0.3, SciPy 1.18.0.
`tests/test_phase1_rmse_bias_units.py` runs the script on the committed input and checks its
output against both files.

## Which change each difference comes from

| Lines before | Lines in `_r14` | What | Why |
|---|---|---|---|
| 13, 14 | 13, 14 | vh_iqr and vv_iqr lose their bias | this change (round 13 question 18 (a), review C21) |
| 39, 45, 46, 47 | 33, 39, 40, 41 | eth_chm_3x3, glad_chm, vh_iqr and vv_iqr site-level r or R2, each in the third decimal | round 13's C22 fix (`ef62da6`); the committed file's own note of 20 Oct 2026 gives these values |
| 20 to 25 | none | the note of 19 Oct 2026 (round 11) and the blank line after it | a dated note, not output |
| 52 to 59 | none | the blank line before the note of 20 Oct 2026 (round 13, C22) and its seven lines | a dated note, not output |

Taken apart: the script as it was before this change (at `284b73d`, run the same way) writes a file
that differs from the `_r14` file in lines 13 and 14 only, and from the committed file in the four
site-level lines and the two notes, as `docs/reproducibility.md` has recorded since 20 Oct 2026.

## Every line that differs

`-` is the committed file from before the change, its 59 lines (the dated note of 26 Oct 2026 that
points here follows them, lines 60 to 68), `+` the `_r14` file. With the two notes taken out, the
committed file has 45 lines, as the `_r14` file has, and the other 39 are identical.

This change (each `+` line is its `-` line cut where `   bias=` began; nothing else in it changed):

```diff
@@ line 13 before, line 13 in _r14 @@
-  vh_iqr                     n=274  pearson r=+0.458 (R2=0.210)   spearman=+0.484   slope=+0.16   bias=-8.17
+  vh_iqr                     n=274  pearson r=+0.458 (R2=0.210)   spearman=+0.484   slope=+0.16
@@ line 14 before, line 14 in _r14 @@
-  vv_iqr                     n=274  pearson r=+0.415 (R2=0.172)   spearman=+0.461   slope=+0.15   bias=-8.06
+  vv_iqr                     n=274  pearson r=+0.415 (R2=0.172)   spearman=+0.461   slope=+0.15
```

Round 13's C22 fix (the values the committed note of 20 Oct 2026 gives at 3 dp):

```diff
@@ line 39 before, line 33 in _r14 @@
-  site-level  eth_chm_3x3            n=6  pearson r=+0.315 (R2=0.099)   spearman=+0.429
+  site-level  eth_chm_3x3            n=6  pearson r=+0.316 (R2=0.100)   spearman=+0.429
@@ line 45 before, line 39 in _r14 @@
-  site-level  glad_chm               n=6  pearson r=+0.556 (R2=0.309)   spearman=+0.429
+  site-level  glad_chm               n=6  pearson r=+0.556 (R2=0.310)   spearman=+0.429
@@ line 46 before, line 40 in _r14 @@
-  site-level  vh_iqr                 n=6  pearson r=+0.314 (R2=0.098)   spearman=+0.429
+  site-level  vh_iqr                 n=6  pearson r=+0.313 (R2=0.098)   spearman=+0.429
@@ line 47 before, line 41 in _r14 @@
-  site-level  vv_iqr                 n=6  pearson r=+0.270 (R2=0.073)   spearman=+0.429
+  site-level  vv_iqr                 n=6  pearson r=+0.271 (R2=0.073)   spearman=+0.429
```

The two notes, which the `_r14` file does not have:

```diff
@@ lines 20 to 25 before, none in _r14 @@
-  NOTE ADDED 19 Oct 2026 (round 11; the numbers above are as first written): vh_iqr's R2=0.210 and
-  vv_iqr's R2=0.172 rested on the 146 Koraput plots whose ascending spread is exactly zero (one
-  image each): without them they are 0.028 and 0.005 (128 plots), and on the descending orbit,
-  where no plot has zero spread, 0.018 and 0.002 (274 plots). Their Spearman values here were not
-  recomputed. See odisha_phase1_12_radar_descending_results.txt (round 9, task E, 17 Oct 2026).
-
@@ lines 52 to 59 before, none in _r14 @@
-
-  NOTE ADDED 20 Oct 2026 (round 13, review C22; the numbers above are as first written): the
-  site-level lines above correlate the site means as rounded to 2 dp in the table. Correlated
-  unrounded, as the script now does, four lines change in the third decimal: eth_chm_3x3
-  r=+0.316 (R2=0.100), glad_chm R2=0.310, vh_iqr r=+0.313, vv_iqr r=+0.271. To 4 dp,
-  unrounded: eth_chm_3x3 r=+0.3157 R2=0.0997, glad_chm r=+0.5564 R2=0.3096, vh_iqr r=+0.3135
-  R2=0.0983, vv_iqr r=+0.2709 R2=0.0734. The other five site-level lines, every Spearman value
-  and the table are unchanged. Step 7 (odisha_phase1_7_results.txt, A6) gives 0.100 and 0.310.
```

These two bias lines are the lines the review named (`odisha_phase1_closeout.txt:13-14`). The
eight height products keep their bias (lines 5 to 12), and the table of site means, every Spearman
value, and every n, r, R2 and slope of section A/B are unchanged. No write-up quoted the dropped
values (review C21; the repository was searched for them again on 26 Oct 2026).
