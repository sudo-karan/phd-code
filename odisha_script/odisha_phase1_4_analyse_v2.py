"""
Phase 1, step 4 — Tests 4, 5 and 6. Fully offline.

Input : odisha_plots_sampled_v2.csv
Output: odisha_phase1_tests456_results.txt, odisha_phase1_tests456_figs.png

Test 4  Do Meta/WRI, GLAD, or raw GEDI track field height where ETH did not?
Test 5  Does Sentinel-1 backscatter track field height and crown cover?
Test 6  Do leaf-off bands / leaf-on minus leaf-off separate composition better than amplitude?

Run:  python odisha_phase1_4_analyse_v2.py
"""
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

df = pd.read_csv("odisha_plots_sampled_v2.csv")
out = []
def say(s=""): out.append(s); print(s)

def fit(x, y, label, bias=True):
    m = x.notna() & y.notna()
    x, y = x[m].to_numpy(float), y[m].to_numpy(float)
    if len(x) < 8:
        say(f"  {label:44} n={len(x):>3}  (too few)"); return None
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        say(f"  {label:44} n={len(x):>3}  (no variance — skipped)"); return None
    r = stats.linregress(x, y)
    line = f"  {label:44} n={len(x):>3}  r={r.rvalue:+.3f}  R2={r.rvalue**2:.3f}  slope={r.slope:+.2f}"
    if bias:
        line += f"  RMSE={np.sqrt(np.mean((y-x)**2)):5.2f}  bias={np.mean(y-x):+5.2f}"
    say(line); return r

def bin_table(pred, label):
    d = df.dropna(subset=[pred]).copy()
    d["h_bin"] = pd.cut(d.loreys_h_m, [0, 5, 8, 12, 16, 20, 30, 60])
    t = d.groupby("h_bin", observed=True).apply(lambda g: pd.Series({
        "n": len(g), "field": g.loreys_h_m.mean(), label: g[pred].mean(),
        "bias": (g[pred] - g.loreys_h_m).mean()}), include_groups=False).round(2)
    say(t.to_string())

# ================================================================ TEST 4
say("=" * 84); say("TEST 4 — alternative canopy height products vs field Lorey's height"); say("=" * 84)
say("(ETH from Test 1 for reference: r=+0.455  R2=0.207  slope=+0.30  bias=+7.18)\n")
for col, name in [("meta_chm_3x3", "Meta/WRI 1m (3x3 @10m)"),
                  ("glad_chm",     "GLAD/Potapov 2019 (30m)"),
                  ("gedi_rh98_50m","GEDI L2A rh98 (<=50m)")]:
    say(f"{name}:")
    fit(df.loreys_h_m, df[col], "all plots")
    for d, g in df.groupby("district"):
        fit(g.loreys_h_m, g[col], f"  {d}")
    say(""); bin_table(col, name.split()[0]); say("")
say("GEDI coverage: plots with >=1 shot within 50 m = "
    f"{(df.gedi_n_50m > 0).sum()} / {len(df)}   (sparse is expected)")
say("\nRead: a product 'works' if R2 > 0.5 AND slope near 1 AND bias does not flip sign across bins.")
say("      If GEDI itself tracks height but the models don't, the models are the problem.")
say("      If GEDI also fails, the vegetation defeats the lidar and no derived product will fix it.")

# ================================================================ TEST 5
say("\n" + "=" * 84); say("TEST 5 — Sentinel-1 backscatter as a structural signal"); say("=" * 84)
RADAR = ["vv_p10", "vv_p50", "vv_p90", "vh_p10", "vh_p50", "vh_p90", "vv_iqr", "vh_iqr", "vv_minus_vh_median"]
say("Against Lorey's height:")
for c in RADAR: fit(df.loreys_h_m, df[c], c, bias=False)
say("\nAgainst crown cover (%):")
for c in RADAR: fit(df.crown_cover_pct, df[c], c, bias=False)
say("\nAgainst basal area (cm2 per plot — per-hectare not possible without plot radius):")
for c in ["vv_p50", "vh_p50", "vv_minus_vh_median"]: fit(df.basal_area_cm2, df[c], c, bias=False)
# a simple multi-band linear model, leave-one-out
X = df[RADAR].to_numpy(float); y = df.loreys_h_m.to_numpy(float)
m = ~np.isnan(X).any(1) & ~np.isnan(y); X, y = X[m], y[m]
X1 = np.column_stack([np.ones(len(X)), X])
pred = np.empty(len(y))
for i in range(len(y)):
    keep = np.arange(len(y)) != i
    beta, *_ = np.linalg.lstsq(X1[keep], y[keep], rcond=None)
    pred[i] = X1[i] @ beta
r = stats.pearsonr(y, pred)[0]
say(f"\n  all 9 radar bands, linear, leave-one-out:      n={len(y)}  r={r:+.3f}  R2={r**2:.3f}  "
    f"RMSE={np.sqrt(np.mean((pred-y)**2)):.2f}")
say("Read: single-band r above ~0.4 with a consistent sign means radar carries height/closure info.")
say("      The LOO R2 is the honest ceiling for a locally calibrated radar height model.")

# ================================================================ TEST 6
say("\n" + "=" * 84); say("TEST 6 — leaf-off reflectance and seasonal difference vs composition"); say("=" * 84)
df["sal_dom"] = np.where(df.dominant_sp.str.contains("Shorea robusta", na=False), df.sp_dominance, 0.0)
say("(harmonic ndvi_amplitude from Test 2 for reference: r=-0.171  R2=0.029)\n")
OFF = ["off_ndvi", "off_nbr", "off_ndmi", "off_ndre", "off_B4", "off_B5", "off_B8", "off_B11", "off_B12",
       "on_ndvi", "ndvi_seasonal_diff"]
say("Against Sal dominance:")
for c in OFF: fit(df.sal_dom, df[c], c, bias=False)
say("\nAgainst species richness (n_species):")
for c in ["off_ndvi", "off_ndre", "off_nbr", "ndvi_seasonal_diff"]: fit(df.n_species, df[c], c, bias=False)
sal, nosal = df[df.sal_dom > 0.5], df[df.sal_dom == 0]
say("\nSal-dominated (>50%) vs non-Sal, Mann-Whitney:")
for c in ["off_ndvi", "off_ndre", "off_nbr", "ndvi_seasonal_diff", "ndvi_amplitude"]:
    a, b = sal[c].dropna(), nosal[c].dropna()
    if len(a) > 4 and len(b) > 4:
        p = stats.mannwhitneyu(a, b).pvalue
        say(f"  {c:22} Sal median {a.median():+.4f}   non-Sal median {b.median():+.4f}   p={p:.3g}")
say("\nRead: ndvi_seasonal_diff (leaf-on minus leaf-off) is the direct deciduousness measure —")
say("      if it beats harmonic amplitude, seasonal composites replace the harmonic fit for composition.")
say("      off_ndre (red-edge) is the chlorophyll/species signal; a p-value well below 0.014 beats Test 2.")

# ================================================================ figures
fig, ax = plt.subplots(2, 3, figsize=(15, 9))
lim = [0, 50]
for a, col, name in [(ax[0,0], "meta_chm_3x3", "Meta/WRI"), (ax[0,1], "glad_chm", "GLAD 2019"), (ax[0,2], "gedi_rh98_50m", "GEDI rh98")]:
    a.scatter(df.loreys_h_m, df[col], s=14, alpha=.6); a.plot(lim, lim, "k--", lw=1)
    a.set_xlabel("field Lorey's (m)"); a.set_ylabel(f"{name} (m)"); a.set_title(f"Test 4: {name}")
ax[1,0].scatter(df.loreys_h_m, df.vh_p50, s=14, alpha=.6); ax[1,0].set_xlabel("field Lorey's (m)"); ax[1,0].set_ylabel("VH p50 (dB)"); ax[1,0].set_title("Test 5: VH vs height")
ax[1,1].scatter(df.crown_cover_pct, df.vv_minus_vh_median, s=14, alpha=.6); ax[1,1].set_xlabel("crown cover (%)"); ax[1,1].set_ylabel("VV−VH (dB)"); ax[1,1].set_title("Test 5: cross-pol vs closure")
ax[1,2].scatter(df.sal_dom, df.ndvi_seasonal_diff, s=14, alpha=.6); ax[1,2].set_xlabel("Sal dominance"); ax[1,2].set_ylabel("NDVI on − off"); ax[1,2].set_title("Test 6: seasonal diff vs Sal")
plt.tight_layout(); plt.savefig("odisha_phase1_tests456_figs.png", dpi=150)
open("odisha_phase1_tests456_results.txt", "w").write("\n".join(out))
say("\nwrote odisha_phase1_tests456_results.txt and odisha_phase1_tests456_figs.png")