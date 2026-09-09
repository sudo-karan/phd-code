"""
Phase 1, step 2 — the three validation tests. Fully offline.

Input : odisha_plots_sampled.csv  (from odisha_phase1_1_sample_gee.py)
Output: odisha_phase1_results.txt, odisha_phase1_figs.png

Test 1  ETH canopy height vs field Lorey's height (and top-5 height)
        -> overall R2 / RMSE / bias, per-district, and BY HEIGHT BIN (the tails are the question)
Test 2  NDVI amplitude vs Sal (Shorea robusta) dominance
        -> is the deciduous/evergreen proxy real where Sal dominates?
Test 3  ETH 3x3 roughness vs field crown cover
        -> does canopy_height_std track canopy closure?

Run:  python odisha_phase1_2_analyse.py
"""
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

IN = "odisha_plots_sampled.csv"
df = pd.read_csv(IN)
out = []
def say(s=""): out.append(s); print(s)

def fit(x, y, label):
    m = x.notna() & y.notna()
    x, y = x[m].to_numpy(float), y[m].to_numpy(float)
    if len(x) < 5:
        say(f"  {label:38} n={len(x):>3}  (too few)"); return None
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        say(f"  {label:38} n={len(x):>3}  (no variance in x or y — skipped)"); return None
    r = stats.linregress(x, y)
    rmse = np.sqrt(np.mean((y - x) ** 2)); bias = np.mean(y - x)
    say(f"  {label:38} n={len(x):>3}  r={r.rvalue:+.3f}  R2={r.rvalue**2:.3f}  "
        f"slope={r.slope:.2f}  RMSE={rmse:5.2f}  bias(pred-field)={bias:+5.2f}")
    return r

# ================================================================ TEST 1
say("=" * 78)
say("TEST 1 — ETH canopy height (3x3 mean) vs field height")
say("=" * 78)
say("Against Lorey's height (basal-area weighted; ETH predicts canopy TOP so this or top-5 is the right target):")
fit(df.loreys_h_m, df.eth_chm_3x3, "all plots")
for d, g in df.groupby("district"):
    fit(g.loreys_h_m, g.eth_chm_3x3, f"  {d}")
say("\nAgainst top-5 mean height:")
fit(df.h_top5_m, df.eth_chm_3x3, "all plots")
say("\nAgainst simple mean height (for reference only — includes saplings, NOT the right target):")
fit(df.h_mean_m, df.eth_chm_3x3, "all plots")

say("\nBias by field-height bin  (this is where GEDI-trained models are known to fail):")
bins = [0, 5, 8, 12, 16, 20, 30, 60]
df["h_bin"] = pd.cut(df.loreys_h_m, bins)
tab = (df.dropna(subset=["eth_chm_3x3"])
         .groupby("h_bin", observed=True)
         .apply(lambda g: pd.Series({
             "n": len(g),
             "field_mean": g.loreys_h_m.mean(),
             "eth_mean": g.eth_chm_3x3.mean(),
             "bias": (g.eth_chm_3x3 - g.loreys_h_m).mean(),
             "eth_sd_mean": g.eth_sd_3x3.mean() if "eth_sd_3x3" in g else np.nan,
         }), include_groups=False).round(2))
say(tab.to_string())
say("\nRead: a large negative bias in the top bins = underestimation of tall canopy;")
say("      a large positive bias in the bottom bins = ETH can't see scrub as short.")
say("      eth_sd_mean is ETH's own claimed uncertainty — check whether it grows where bias grows.")

# ================================================================ TEST 2
say("\n" + "=" * 78)
say("TEST 2 — NDVI amplitude vs Sal dominance  (is the deciduous proxy real?)")
say("=" * 78)
df["sal_dom"] = np.where(df.dominant_sp.str.contains("Shorea robusta", na=False), df.sp_dominance, 0.0)
say(f"plots with Sal as dominant species: {(df.sal_dom > 0).sum()} / {len(df)}")
fit(df.sal_dom, df.ndvi_amplitude, "amplitude ~ Sal dominance (all)")
for d, g in df.groupby("district"):
    fit(g.sal_dom, g.ndvi_amplitude, f"  {d}")
sal = df[df.sal_dom > 0.5]; nosal = df[df.sal_dom == 0]
if len(sal) > 4 and len(nosal) > 4:
    t = stats.mannwhitneyu(sal.ndvi_amplitude.dropna(), nosal.ndvi_amplitude.dropna())
    say(f"\nSal-dominated (>50%) median amplitude {sal.ndvi_amplitude.median():.4f}  "
        f"vs  non-Sal {nosal.ndvi_amplitude.median():.4f}   Mann-Whitney p={t.pvalue:.3g}")
say("Read: if Sal plots do NOT show lower amplitude than mixed/deciduous plots, the")
say("      semi-evergreen concern is real and ndvi_amplitude is a weak composition proxy here.")

# ================================================================ TEST 3
say("\n" + "=" * 78)
say("TEST 3 — ETH 3x3 roughness vs field crown cover  (does canopy_height_std track closure?)")
say("=" * 78)
fit(df.crown_cover_pct, df.eth_chm_std_3x3, "roughness ~ crown cover (all)")
for d, g in df.groupby("district"):
    fit(g.crown_cover_pct, g.eth_chm_std_3x3, f"  {d}")
say("Read: expect NEGATIVE correlation — closed canopy is smoother. If flat, the")
say("      roughness proxy isn't measuring closure at this resolution.")

# ================================================================ figures
fig, ax = plt.subplots(2, 2, figsize=(11, 9))
a = ax[0, 0]
a.scatter(df.loreys_h_m, df.eth_chm_3x3, s=14, alpha=.6, c=df.district.astype("category").cat.codes, cmap="tab10")
lim = [0, max(df.loreys_h_m.max(), df.eth_chm_3x3.max()) * 1.05]
a.plot(lim, lim, "k--", lw=1); a.set_xlabel("field Lorey's height (m)"); a.set_ylabel("ETH CHM 3x3 (m)")
a.set_title("Test 1: ETH vs field height (1:1 dashed)")
a = ax[0, 1]
t2 = tab.reset_index()
a.bar(range(len(t2)), t2.bias, color=["#c0392b" if b < 0 else "#2980b9" for b in t2.bias])
a.set_xticks(range(len(t2))); a.set_xticklabels([str(b) for b in t2.h_bin], rotation=45, ha="right", fontsize=8)
a.axhline(0, color="k", lw=.8); a.set_ylabel("bias ETH − field (m)"); a.set_title("Test 1: bias by height bin")
a = ax[1, 0]
a.scatter(df.sal_dom, df.ndvi_amplitude, s=14, alpha=.6)
a.set_xlabel("Sal dominance fraction"); a.set_ylabel("NDVI amplitude"); a.set_title("Test 2: amplitude vs Sal")
a = ax[1, 1]
a.scatter(df.crown_cover_pct, df.eth_chm_std_3x3, s=14, alpha=.6)
a.set_xlabel("field crown cover (%)"); a.set_ylabel("ETH 3x3 std (m)"); a.set_title("Test 3: roughness vs crown cover")
plt.tight_layout(); plt.savefig("odisha_phase1_figs.png", dpi=150)

open("odisha_phase1_results.txt", "w").write("\n".join(out))
say("\nwrote odisha_phase1_results.txt and odisha_phase1_figs.png")