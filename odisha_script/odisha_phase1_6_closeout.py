"""
Phase 1, step 6 — close-out analysis. Fully offline.

Input : odisha_plots_sampled_v2.csv  (after step 5)
Output: odisha_phase1_closeout.txt

A. Meta/WRI re-test with correct sampling (mean and p95, 15 m and 30 m).
B. Spearman rank correlation for every structural candidate — for delineation, ordering
   neighbours correctly matters more than absolute calibration.
C. Site-level aggregation: mean field height vs mean product across the ~10 plots in each of
   the six Dhenkanal polygons. Six points is directional only — but it shows whether
   aggregation lifts the plot-level R2, which is the case for stand-scale use.

Run:  python odisha_phase1_6_closeout.py
"""
import numpy as np
import pandas as pd
from scipy import stats

df = pd.read_csv("odisha_plots_sampled_v2.csv")
out = []
def say(s=""): out.append(s); print(s)

def both(x, y, label):
    m = x.notna() & y.notna()
    x, y = x[m].to_numpy(float), y[m].to_numpy(float)
    if len(x) < 5 or np.ptp(x) == 0 or np.ptp(y) == 0:
        say(f"  {label:26} n={len(x):>3}  (skipped)"); return
    pr = stats.pearsonr(x, y)[0]; sr = stats.spearmanr(x, y)[0]
    slope = stats.linregress(x, y).slope
    say(f"  {label:26} n={len(x):>3}  pearson r={pr:+.3f} (R2={pr**2:.3f})   spearman={sr:+.3f}   slope={slope:+.2f}   bias={np.mean(y-x):+5.2f}")

HEIGHT = [c for c in ["eth_chm_3x3", "meta_chm_3x3", "meta_mean_15m", "meta_p95_15m",
                      "meta_mean_30m", "meta_p95_30m", "glad_chm", "gedi_rh98_50m",
                      "vh_iqr", "vv_iqr"] if c in df]

# ---------------------------------------------------------------- A + B
say("=" * 96)
say("A/B — every structural candidate vs field Lorey's height: Pearson, Spearman, slope, bias")
say("=" * 96)
say("(meta_chm_3x3 is the WRONGLY sampled version from step 3, kept for comparison)")
for c in HEIGHT: both(df.loreys_h_m, df[c], c)
say("\nRead: Spearman well above Pearson => the product ranks plots correctly but is badly calibrated.")
say("      That is usable for delineation (which compares neighbours) even if useless as a height map.")
say("      meta_p95 is the fair Meta number. If it is still < 0.5, Meta is out.")

# ---------------------------------------------------------------- C
say("\n" + "=" * 96)
say("C — site-level aggregation, six Dhenkanal polygons (~10 plots each)")
say("=" * 96)
sites = df[df.site_polygon.notna()]
say(f"plots inside polygons: {len(sites)}  across {sites.site_polygon.nunique()} sites")
agg = sites.groupby("site_polygon").agg(n=("plot_key", "size"), field=("loreys_h_m", "mean"),
                                        **{c: (c, "mean") for c in HEIGHT if c != "gedi_rh98_50m"}).round(2)
say(agg.to_string())
say("")
for c in HEIGHT:
    if c == "gedi_rh98_50m" or c not in agg: continue
    x, y = agg["field"], agg[c]
    if x.notna().sum() < 5 or np.ptp(y.dropna()) == 0: continue
    pr = stats.pearsonr(x, y)[0]; sr = stats.spearmanr(x, y)[0]
    say(f"  site-level  {c:22} n={len(agg)}  pearson r={pr:+.3f} (R2={pr**2:.3f})   spearman={sr:+.3f}")
say("\nRead: compare each site-level R2 against the plot-level R2 above. A jump means aggregation")
say("      recovers signal that plot noise was hiding — the argument for stand-scale use.")
say("      Six points: treat as direction, not proof.")

open("odisha_phase1_closeout.txt", "w").write("\n".join(out))
say("\nwrote odisha_phase1_closeout.txt")