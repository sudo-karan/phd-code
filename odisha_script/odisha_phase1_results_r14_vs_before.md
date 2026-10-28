# Phase 1 step 2: the file of round 14 (`_r14`) against the file from before it

The review of 19 Oct 2026 (`docs/reviews/2026-10-19-review.md`, finding C21) found that
`odisha_phase1_2_analyse.py` printed RMSE and bias between quantities in different units: in
Test 2 the Sal dominance fraction subtracted from NDVI amplitude, in Test 3 crown cover in per cent
subtracted from ETH roughness in metres. Round 13 put it to Jaskaran as question 18
(`docs/handoff/2026-10-20-round13.md`); the round 14 brief (26 Oct 2026) answers it by its
recommendation, (a): the rule round 10 applied to step 12. Since the commit "Round 14, Task 1,
Q18: Phase 1 steps 2 and 6 print RMSE and bias only where both sides are heights in metres", the
script prints RMSE and bias for Test 1 only, where both sides are heights in metres. Nothing else
it prints changed, and it still writes `odisha_phase1_results.txt` and `odisha_phase1_figs.png`.
The register entry is `field-phase1-rmse-and-bias-only-between-heights` (`docs/decisions.yaml`).

## How the new file was made

The script and its input as committed in that commit were copied into an empty scratch folder and
run there with the documented command, so that no committed file was overwritten. The text file it
wrote is committed here, byte for byte, as `odisha_phase1_results_r14.txt`:

```bash
cd <an empty folder holding only odisha_phase1_2_analyse.py and odisha_plots_sampled.csv>
python odisha_phase1_2_analyse.py
```

| File | SHA-256 |
|---|---|
| `odisha_phase1_2_analyse.py`, the script run | `35f98a44168aa77b6517089e7235972e3beb06e50c4c8309f663c895ca3c19ad` |
| `odisha_plots_sampled.csv`, its input (unchanged since `5271ea5`) | `d65a7a69c58493ccdfa169ac9b91f2fa0d6f47c9dea2941e0838f147333af6c6` |
| `odisha_phase1_results.txt` as written, committed as `odisha_phase1_results_r14.txt` | `a728ad150bfc58c606b75a1a8648015da5d77ef8d50eeaa106c64a4af0ab2c99` |
| `odisha_phase1_figs.png` as written, the same bytes as the committed figure | `3670f647e6d737906d67e50e862e40dc50c567a82c187d2c3754e6ebced055fb` |

Machine: macOS 26.7.1, Python 3.13.14, NumPy 2.5.1, pandas 3.0.3, SciPy 1.18.0, Matplotlib
3.11.0. Run the same way at `284b73d`, before the change, the script wrote both committed files
byte for byte, as `docs/reproducibility.md` records. `tests/test_phase1_rmse_bias_units.py` runs
the script on the committed input and checks its output against both files.

## Every file

| Before the change | Round 14 | What differs |
|---|---|---|
| `odisha_phase1_results.txt`, lines 1 to 55 (its dated note of 26 Oct 2026, lines 56 to 63, follows them) | `odisha_phase1_results_r14.txt` | 8 lines, listed below |
| `odisha_phase1_figs.png` | the same file, not written under a new name | nothing: the same bytes |

Both texts have 55 lines, so a line has the same number in both.

## Every line that differs

`-` is the file from before the change, `+` the `_r14` file. Each `+` line is its `-` line cut
where `  RMSE=` began; nothing else in it changed.

```diff
@@ line 36 @@
-  amplitude ~ Sal dominance (all)        n=274  r=-0.171  R2=0.029  slope=-0.04  RMSE= 0.22  bias(pred-field)=+0.08
+  amplitude ~ Sal dominance (all)        n=274  r=-0.171  R2=0.029  slope=-0.04
@@ line 38 @@
-    DHENKANAL                            n= 76  r=-0.138  R2=0.019  slope=-0.01  RMSE= 0.31  bias(pred-field)=-0.14
+    DHENKANAL                            n= 76  r=-0.138  R2=0.019  slope=-0.01
@@ line 39 @@
-    KENDUJHAR                            n= 12  r=-0.029  R2=0.001  slope=-0.01  RMSE= 0.21  bias(pred-field)=+0.14
+    KENDUJHAR                            n= 12  r=-0.029  R2=0.001  slope=-0.01
@@ line 49 @@
-  roughness ~ crown cover (all)          n=274  r=-0.011  R2=0.000  slope=-0.00  RMSE=44.96  bias(pred-field)=-38.42
+  roughness ~ crown cover (all)          n=274  r=-0.011  R2=0.000  slope=-0.00
@@ line 50 @@
-    ANGUL                                n= 40  r=+0.069  R2=0.005  slope=0.00  RMSE=58.54  bias(pred-field)=-54.88
+    ANGUL                                n= 40  r=+0.069  R2=0.005  slope=0.00
@@ line 51 @@
-    DHENKANAL                            n= 76  r=-0.017  R2=0.000  slope=-0.00  RMSE=46.12  bias(pred-field)=-37.89
+    DHENKANAL                            n= 76  r=-0.017  R2=0.000  slope=-0.00
@@ line 52 @@
-    KENDUJHAR                            n= 12  r=+0.192  R2=0.037  slope=0.00  RMSE=46.53  bias(pred-field)=-36.07
+    KENDUJHAR                            n= 12  r=+0.192  R2=0.037  slope=0.00
@@ line 53 @@
-    KORAPUT                              n=146  r=-0.058  R2=0.003  slope=-0.00  RMSE=39.62  bias(pred-field)=-34.37
+    KORAPUT                              n=146  r=-0.058  R2=0.003  slope=-0.00
```

These are the lines the review named (`odisha_phase1_results.txt:36, 38-39, 49-53`). The other 47
lines are identical: Test 1 keeps its RMSE and bias (ETH against field heights, both in metres), as
does the bias table by height bin (ETH minus field, in metres); the skipped fits (lines 37 and 40),
the Mann-Whitney line, the headings and the Read lines are unchanged. No n, r, R2 or slope moved.
No write-up quoted the dropped values (review C21; the repository was searched for them again on
26 Oct 2026).
