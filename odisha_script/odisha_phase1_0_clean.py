"""
Clean the raw Odisha field data to one row per plot.

Input : Odisha_samples.csv   (5910 tree records)
        Odisha_sites.csv     (6 village-forest polygons, Dhenkanal)
Output: odisha_plots_clean.csv  (274 plots)

What it does, and why:
  - Drops plots with GPS accuracy > 20 m (one record reads 3300 m).
  - Repairs the two crown-cover bands Excel turned into dates:
        "2023-11-15" was "11-15",  "2023-06-10" was "6-10"
    (they are exactly the two missing bands in the 0-5, 6-10, 11-15, 16-20 ... sequence).
  - Aggregates trees -> plots on rounded lat/lon, NOT on Plot No or Site Name:
    Plot No repeats across habitations, and Site Name has 183 spellings incl. Odia script as "¿¿¿".
  - Computes Lorey's height (basal-area weighted). ETH CHM predicts canopy TOP, so
    Lorey's or top-5 is the right comparison target — simple mean includes 0.2 m saplings.
  - Joins each plot to a site polygon BY GEOMETRY. Site names differ between the two files
    (e.g. the "Pangatira" polygon contains plots labelled "RAIJHARANA").

Run:  python odisha_phase1_0_clean.py
Needs: pandas, numpy, shapely
"""
import json
import numpy as np
import pandas as pd
from shapely.geometry import Point, Polygon

SAMPLES = "Odisha_samples.csv"
SITES   = "Odisha_sites.csv"
OUT     = "odisha_plots_clean.csv"
GPS_MAX_M = 20

s = pd.read_csv(SAMPLES)
n_trees_raw = len(s)

# ------------------------------------------------------------------ crown cover repair
CC_FIX = {"2023-11-15 00:00:00": "11-15", "2023-06-10 00:00:00": "6-10"}
s["crown_cover_band"] = s["Crown Cover"].astype(str).replace(CC_FIX)

def band_midpoint(v):
    if v == "0":   return 0.0
    if v == "nan": return np.nan
    try:
        lo, hi = v.split("-")
        return (float(lo) + float(hi)) / 2
    except Exception:
        return np.nan

s["crown_cover_pct"] = s["crown_cover_band"].map(band_midpoint)

# ------------------------------------------------------------------ numeric + GPS filter
for c in ["Height", "DBH", "Gbh Girth", "Plot Lat", "Plot Long", "Plot Acc", "Plot Alt"]:
    s[c] = pd.to_numeric(s[c], errors="coerce")
s = s[s["Plot Acc"] <= GPS_MAX_M].copy()

s["ba_cm2"]   = np.pi * (s["DBH"] / 2) ** 2
s["plot_key"] = s["Plot Lat"].round(6).astype(str) + "_" + s["Plot Long"].round(6).astype(str)

# ------------------------------------------------------------------ trees -> plots
def loreys_height(g):
    w = g["ba_cm2"].sum()
    return (g["Height"] * g["ba_cm2"]).sum() / w if w > 0 else np.nan

def top5_height(g):
    return g["Height"].nlargest(5).mean()

def dominant(g):
    return g["Scientific Name"].value_counts().index[0]

def dominance(g):
    vc = g["Scientific Name"].value_counts()
    return vc.iloc[0] / len(g)

grp = s.groupby("plot_key")
plots = grp.agg(
    lat=("Plot Lat", "first"), lon=("Plot Long", "first"),
    gps_acc_m=("Plot Acc", "first"), alt_m=("Plot Alt", "first"),
    district=("Habdistrict", "first"), block=("Habblock", "first"),
    habitation=("Habitation", "first"),
    n_trees=("Height", "size"),
    h_mean_m=("Height", "mean"), h_max_m=("Height", "max"),
    dbh_mean_cm=("DBH", "mean"), basal_area_cm2=("ba_cm2", "sum"),
    n_species=("Scientific Name", "nunique"),
    crown_cover_pct=("crown_cover_pct", "median"),
).reset_index()

plots["loreys_h_m"]   = grp.apply(loreys_height, include_groups=False).values
plots["h_top5_m"]     = grp.apply(top5_height,   include_groups=False).values
plots["dominant_sp"]  = grp.apply(dominant,      include_groups=False).values
plots["sp_dominance"] = grp.apply(dominance,     include_groups=False).values

# ------------------------------------------------------------------ site polygon join (geometry)
sites = pd.read_csv(SITES)
polys = {r["Name"]: Polygon(json.loads(r[".geo"])["coordinates"]) for _, r in sites.iterrows()}
plots["site_polygon"] = None
for name, poly in polys.items():
    inside = [poly.contains(Point(r.lon, r.lat)) for r in plots.itertuples()]
    plots.loc[inside, "site_polygon"] = name

# ------------------------------------------------------------------ write
cols = ["plot_key", "lat", "lon", "gps_acc_m", "alt_m", "district", "block", "habitation",
        "site_polygon", "n_trees", "loreys_h_m", "h_top5_m", "h_mean_m", "h_max_m",
        "dbh_mean_cm", "basal_area_cm2", "crown_cover_pct", "n_species",
        "dominant_sp", "sp_dominance"]
plots = plots[cols].round(4)
plots.to_csv(OUT, index=False)

print(f"trees : {n_trees_raw} -> {len(s)} after GPS filter (<= {GPS_MAX_M} m)")
print(f"plots : {len(plots)}   inside a site polygon: {plots.site_polygon.notna().sum()}")
print(f"crown cover recovered on {s['crown_cover_pct'].notna().sum()}/{len(s)} tree rows")
print("\nplots per district:")
print(plots.district.value_counts().to_string())
print(f"\nwrote {OUT}")