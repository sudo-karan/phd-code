"""Reproduce the field forest-type grouping, standalone.

Answers: "where can I see that 259 of 274 plots are one type?"

Reads   : phase2_plots_joined_districts.csv  (the field table, 274 plots)
Prints  : the species matrix it builds, the group sizes, and every plot
          that is NOT in the dominant group, with why it differs.

Run:  python odisha_script/explain_field_types.py
No Earth Engine, no network. Mirrors odisha_phase2_5_stats.py lines 1801-1806.
"""
import json
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

N_TYPES = 6  # the k used for the field typology

p = pd.read_csv("phase2_plots_joined_districts.csv")
print(f"plots in the field table: {len(p)}\n")

# ---- 1. species x plot matrix of RELATIVE basal area -------------------
# sp_ba_json holds {species: basal_area_m2} per plot. Relative = share of
# that plot's total basal area, so a big plot and a small plot compare on
# composition rather than on size.
rows = {k: json.loads(s) if isinstance(s, str) else {}
        for k, s in zip(p.plot_key, p.sp_ba_json)}
mat = pd.DataFrame(rows).T.fillna(0.0)
mat = mat.div(mat.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
print(f"species matrix: {mat.shape[0]} plots x {mat.shape[1]} species")
print("most common species by mean share:")
for sp, v in mat.mean().sort_values(ascending=False).head(5).items():
    print(f"   {sp:<28} {v:6.1%}")

# ---- 2. Bray-Curtis dissimilarity between every pair of plots ----------
# 0 = identical composition, 1 = no species in common.
a = mat.to_numpy()
num = np.abs(a[:, None, :] - a[None, :, :]).sum(-1)
den = (a[:, None, :] + a[None, :, :]).sum(-1)
bc = num / den

# ---- 3. UPGMA (average-linkage) clustering, cut into N_TYPES groups ----
Z = linkage(squareform(bc, checks=False), method="average")
t = pd.Series(fcluster(Z, N_TYPES, criterion="maxclust"), index=mat.index)

sizes = t.value_counts().sort_index()
print(f"\nfield types (UPGMA on Bray-Curtis, k={N_TYPES}): {sizes.to_dict()}")
big = sizes.idxmax()
print(f"  -> type {big} holds {sizes.max()} of {len(t)} plots "
      f"({sizes.max()/len(t):.1%}). The other {len(t)-sizes.max()} sit in "
      f"{len(sizes)-1} groups.\n")

# ---- 4. which plots differ, and why ------------------------------------
odd = t[t != big].index
info = p.set_index("plot_key").loc[odd]
print("the plots that are NOT in the dominant type:")
print(f"{'plot_key':<26}{'type':>5}{'dist':>11}{'Sal share':>11}{'spp':>5}"
      f"{'height m':>10}  top species")
for k in odd:
    r = info.loc[k]
    top = max(rows[k].items(), key=lambda kv: kv[1])[0] if rows[k] else "-"
    print(f"{k:<26}{t[k]:>5}{str(r.district)[:10]:>11}{r.sal_ba_frac:>11.2f}"
          f"{int(r.n_species):>5}{r.loreys_h_m:>10.1f}  {top}")

# ---- 5. the alternative grouping actually used as a second typology ----
sal = (p.sal_ba_frac > 0.5).astype(int)
print(f"\nby comparison, the Sal-dominance rule (>50% of basal area is Sal) "
      f"splits them {sal.value_counts().sort_index().to_dict()}"
      f"  (0 = not Sal-dominated, 1 = Sal-dominated)")
