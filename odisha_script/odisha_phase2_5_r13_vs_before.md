# Phase 2 statistics: the files with the A8 fix (`_r13`) against those from before it

The review of 19 Oct 2026 (`docs/reviews/2026-10-19-review.md`, finding A8) found that the rotation
null of 6.1 and of its null structure was scored on every plot a realisation put on a stand, while
the observed value leaves out a plot the observed stand map leaves unassigned. Since commit
`57235ca`, `odisha_phase2_5_stats.py` scores the null on the observed-assigned plots only, as Phase 3
does, and ends every name it writes with `_r13`. The files from before the fix keep their names.

This file lists every line and cell that differs between the files from before the fix, as
committed at `c368eb7` (before the dated note added to the results text in round 13), and the
`_r13` files the fixed script wrote with the documented commands, run from the repo root, at
`390c5fb`, the fix's first commit, on a local branch (the script and every file it reads are those
of `57235ca`, its commit on this branch; ids corrected 20 Oct 2026):

```bash
python odisha_script/odisha_phase2_5_stats.py --set pilot
python odisha_script/odisha_phase2_5_stats.py --set districts --jobs 4
```

## Every file

| Set | Before the fix | With the fix | What differs |
|---|---|---|---|
| pilot | `odisha_phase2_5_results.txt` | `odisha_phase2_5_results_r13.txt` | nothing: the same bytes |
| pilot | `odisha_phase2_5_summary.csv` | `odisha_phase2_5_summary_r13.csv` | nothing: the same bytes |
| pilot | `odisha_phase2_5_primary_r2_null.png` | `odisha_phase2_5_primary_r2_null_r13.png` | nothing: the same bytes |
| pilot | `odisha_phase2_5_arms_excess.png` | `odisha_phase2_5_arms_excess_r13.png` | nothing: the same bytes |
| pilot | `odisha_phase2_5_pairwise_bands.png` | `odisha_phase2_5_pairwise_bands_r13.png` | nothing: the same bytes |
| full set | `odisha_phase2_5_results_districts.txt` | `odisha_phase2_5_results_districts_r13.txt` | 15 lines, listed below |
| full set | `odisha_phase2_5_summary_districts.csv` | `odisha_phase2_5_summary_districts_r13.csv` | 26 cells, listed below |
| full set | `odisha_phase2_5_primary_r2_null_districts.png` | `odisha_phase2_5_primary_r2_null_districts_r13.png` | nothing: the same bytes |
| full set | `odisha_phase2_5_arms_excess_districts.png` | `odisha_phase2_5_arms_excess_districts_r13.png` | nothing: the same bytes |
| full set | `odisha_phase2_5_pairwise_bands_districts.png` | `odisha_phase2_5_pairwise_bands_districts_r13.png` | nothing: the same bytes |

The pilot assigns all 60 plots on every layer, so the fix changes nothing there. The figures draw
the merged layers only, which assign every plot in both sets.

## The full set's results text: every line that differs

Both files have the same number of lines, so a line has the same number in both. `-` is the file
from before the fix, `+` the `_r13` file.

`v120 / stands_snic`:

```diff
@@ line 263 @@
-  NOTE: observed assigned plots 265 < 267 plots in loaded districts; the rotation null may assign the other 2 (it forces only the observed-assigned plots to land on a stand)
+  NOTE: observed assigned plots 265 < 267 plots in loaded districts; every statistic, observed and null alike, leaves out the other 2: the rotation null forces only the observed-assigned plots onto a stand and is scored on them only
@@ line 270 @@
-    loreys_h_m         0.926  (210,265)     0.752   (38,93)     0.785   0.67   0.86  -0.033    30.3   1999
+    loreys_h_m         0.926  (210,265)     0.752   (38,93)     0.785   0.67   0.86  -0.033    30.4   1999
@@ line 271 @@
-    loreys_h_tree_m    0.933  (204,252)     0.758   (34,82)     0.785   0.66   0.87  -0.027    36.3   1999
+    loreys_h_tree_m    0.933  (204,252)     0.758   (34,82)     0.785   0.66   0.87  -0.026    36.6   1999
@@ line 274 @@
-    n_species          0.872  (210,265)     0.601   (38,93)     0.707   0.62   0.79  -0.106     2.8   1999
+    n_species          0.872  (210,265)     0.601   (38,93)     0.707   0.62   0.79  -0.106     2.9   1999
@@ line 276 @@
-    h_top5_m           0.866  (210,265)     0.639   (38,93)     0.709   0.60   0.82  -0.070    14.6   1999
+    h_top5_m           0.866  (210,265)     0.639   (38,93)     0.709   0.60   0.82  -0.070    14.7   1999
@@ line 281 @@
-    k (multi-plot stands)             38.000    35.000  30.000  41.000  77.7 (n_null 1999)
+    k (multi-plot stands)             38.000    35.000  30.000  41.000  78.6 (n_null 1999)
@@ line 282 @@
-    n (plots in them)                 93.000    83.000  72.000  95.000  91.2 (n_null 1999)
+    n (plots in them)                 93.000    83.000  72.000  95.000  91.8 (n_null 1999)
@@ line 283 @@
-    E = (k-1)/(n-1)                    0.402     0.419   0.388   0.446  15.6 (n_null 1999)
+    E = (k-1)/(n-1)                    0.402     0.420   0.388   0.446  15.6 (n_null 1999)
@@ line 284 @@
-    largest multi-plot group           4.000     5.000   4.000   6.000  24.9 (n_null 1999)
+    largest multi-plot group           4.000     5.000   4.000   6.000  25.1 (n_null 1999)
@@ line 285 @@
-    same-stand within-part pairs      76.000    64.000  51.000  80.000  89.6 (n_null 1999)
+    same-stand within-part pairs      76.000    64.000  51.000  80.000  90.2 (n_null 1999)
@@ line 287 @@
-    pushes the observed value below the null median by about that much, i.e. the percentile is biased low: loreys_h_m -0.002 (n 1999); loreys_h_tree_m -0.001 (n 1999); crown_cover_pct -0.001 (n 1999); sal_ba_frac +0.003 (n 1999); n_species -0.012 (n 1999); dbh_mean_cm -0.003 (n 1999); h_top5_m -0.009 (n 1999)
+    pushes the observed value below the null median by about that much, i.e. the percentile is biased low: loreys_h_m -0.002 (n 1999); loreys_h_tree_m -0.001 (n 1999); crown_cover_pct -0.001 (n 1999); sal_ba_frac +0.004 (n 1999); n_species -0.012 (n 1999); dbh_mean_cm -0.003 (n 1999); h_top5_m -0.009 (n 1999)
```

`v120 / stands_dissolved`:

```diff
@@ line 330 @@
-  NOTE: observed assigned plots 252 < 267 plots in loaded districts; the rotation null may assign the other 15 (it forces only the observed-assigned plots to land on a stand)
+  NOTE: observed assigned plots 252 < 267 plots in loaded districts; every statistic, observed and null alike, leaves out the other 15: the rotation null forces only the observed-assigned plots onto a stand and is scored on them only
```

`current / stands_dissolved`:

```diff
@@ line 692 @@
-  NOTE: observed assigned plots 253 < 267 plots in loaded districts; the rotation null may assign the other 14 (it forces only the observed-assigned plots to land on a stand)
+  NOTE: observed assigned plots 253 < 267 plots in loaded districts; every statistic, observed and null alike, leaves out the other 14: the rotation null forces only the observed-assigned plots onto a stand and is scored on them only
```

`alphaearth / stands_snic`:

```diff
@@ line 988 @@
-  NOTE: observed assigned plots 266 < 267 plots in loaded districts; the rotation null may assign the other 1 (it forces only the observed-assigned plots to land on a stand)
+  NOTE: observed assigned plots 266 < 267 plots in loaded districts; every statistic, observed and null alike, leaves out the other 1: the rotation null forces only the observed-assigned plots onto a stand and is scored on them only
```

`alphaearth / stands_dissolved`:

```diff
@@ line 1055 @@
-  NOTE: observed assigned plots 253 < 267 plots in loaded districts; the rotation null may assign the other 14 (it forces only the observed-assigned plots to land on a stand)
+  NOTE: observed assigned plots 253 < 267 plots in loaded districts; every statistic, observed and null alike, leaves out the other 14: the rotation null forces only the observed-assigned plots onto a stand and is scored on them only
```

## The full set's summary CSV: every cell that differs

Both files have the same rows and columns in the same order. The line is the line of the CSV file
(the header is line 1).

| Line | Section | Partition | Variable | Column | Before the fix | With the fix |
|---|---|---|---|---|---|---|
| 118 | 6.1 | v120 / stands_snic | `loreys_h_m` | `null_median` | 0.7852352029410246 | 0.7851950507475122 |
| 118 | 6.1 | v120 / stands_snic | `loreys_h_m` | `null_p5` | 0.668505196092573 | 0.6681563276583186 |
| 118 | 6.1 | v120 / stands_snic | `loreys_h_m` | `excess` | -0.033089394746385725 | -0.03304924255287334 |
| 118 | 6.1 | v120 / stands_snic | `loreys_h_m` | `percentile` | 30.265132566283143 | 30.4152076038019 |
| 119 | 6.1 | v120 / stands_snic | `loreys_h_tree_m` | `null_median` | 0.7850509478975907 | 0.7847718849952385 |
| 119 | 6.1 | v120 / stands_snic | `loreys_h_tree_m` | `null_p95` | 0.8658370307637648 | 0.8652886387304672 |
| 119 | 6.1 | v120 / stands_snic | `loreys_h_tree_m` | `excess` | -0.026586756022228597 | -0.026307693119876463 |
| 119 | 6.1 | v120 / stands_snic | `loreys_h_tree_m` | `percentile` | 36.31815907953977 | 36.568284142071036 |
| 120 | 6.1 | v120 / stands_snic | `crown_cover_pct` | `null_median` | 0.8064327060392837 | 0.8064888082919279 |
| 120 | 6.1 | v120 / stands_snic | `crown_cover_pct` | `null_p5` | 0.7196955302875251 | 0.7196094802099496 |
| 120 | 6.1 | v120 / stands_snic | `crown_cover_pct` | `excess` | -0.03919474717946303 | -0.039250849432107215 |
| 121 | 6.1 | v120 / stands_snic | `sal_ba_frac` | `null_median` | 0.8562502572053493 | 0.8562456419496358 |
| 121 | 6.1 | v120 / stands_snic | `sal_ba_frac` | `null_p5` | 0.7591641052935161 | 0.7589808531966756 |
| 121 | 6.1 | v120 / stands_snic | `sal_ba_frac` | `null_p95` | 0.927374041050063 | 0.9273505534659826 |
| 121 | 6.1 | v120 / stands_snic | `sal_ba_frac` | `excess` | 0.02460437016994821 | 0.0246089854256617 |
| 122 | 6.1 | v120 / stands_snic | `n_species` | `null_median` | 0.7073476129582268 | 0.7069803237292704 |
| 122 | 6.1 | v120 / stands_snic | `n_species` | `null_p95` | 0.7937953360908921 | 0.7939301198114701 |
| 122 | 6.1 | v120 / stands_snic | `n_species` | `excess` | -0.10633375770273235 | -0.105966468473776 |
| 122 | 6.1 | v120 / stands_snic | `n_species` | `percentile` | 2.751375687843922 | 2.9014507253626816 |
| 123 | 6.1 | v120 / stands_snic | `dbh_mean_cm` | `null_p5` | 0.5353843806302688 | 0.5352530384718771 |
| 123 | 6.1 | v120 / stands_snic | `dbh_mean_cm` | `percentile` | 23.561780890445224 | 23.611805902951474 |
| 124 | 6.1 | v120 / stands_snic | `h_top5_m` | `null_median` | 0.7094518082065504 | 0.7090074362776732 |
| 124 | 6.1 | v120 / stands_snic | `h_top5_m` | `null_p5` | 0.5974036187868729 | 0.5975640720595464 |
| 124 | 6.1 | v120 / stands_snic | `h_top5_m` | `null_p95` | 0.8247402652349043 | 0.8247370457862113 |
| 124 | 6.1 | v120 / stands_snic | `h_top5_m` | `excess` | -0.07047764964696746 | -0.0700332777180902 |
| 124 | 6.1 | v120 / stands_snic | `h_top5_m` | `percentile` | 14.607303651825912 | 14.70735367683842 |

The columns that change: `excess`, `null_median`, `null_p5`, `null_p95`, `percentile`. Every one is read
from the rotation null; no observed value changes.

## Does a conclusion move?

No.

- Only v120 `stands_snic` moves, the one layer of the full set that leaves plots unassigned (265 of
  267) and has a rotation null. Its 6.1 percentiles move by 0.25 at most, and none crosses 2.5, 5,
  95 or 97.5: `n_species` stays in the low tail (2.75 to 2.90). Its excesses move by less than
  0.0005; `n_species`'s is outside ±0.10 before and after (−0.1063, −0.1060). The null structure's
  percentiles move by 0.9 at most (k, 77.7 to 78.6), and none reaches 95.
- AlphaEarth `stands_snic` also leaves a plot unassigned (266 of 267), but none of its numbers
  moves. The three `stands_dissolved` layers have no rotation null (NOT BUILT), before and after.
- `PHASE2_STATUS.md` reads v120 `stands_snic` through 6.2 ("shows nothing in the primary arm"),
  which does not change. Neither do the primary result (v120 `stands_merged`), the other merged
  layers, the arms comparison, 6.3 or the figures.

## How to check

From the repo root. The two results texts are compared with their versions at `c368eb7`, because
each committed file now also holds dated notes of round 13 at its end (A8's and A6's in the full
set's, A6's in the pilot's). Corrected 20 Oct 2026: the pilot's was compared with the committed
file, which `cmp` then reported as well.

```bash
git show c368eb7:odisha_script/odisha_phase2_5_results_districts.txt |
  diff - odisha_script/odisha_phase2_5_results_districts_r13.txt
git show c368eb7:odisha_script/odisha_phase2_5_results.txt |
  cmp - odisha_script/odisha_phase2_5_results_r13.txt
for s in '' _districts; do
  for f in summary.csv primary_r2_null.png arms_excess.png pairwise_bands.png; do
    cmp "odisha_script/odisha_phase2_5_${f%.*}$s.${f##*.}" "odisha_script/odisha_phase2_5_${f%.*}${s}_r13.${f##*.}"
  done
done
```

`cmp` reports the full set's summary CSV only, whose cells are listed above.
