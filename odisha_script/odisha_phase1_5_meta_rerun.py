"""
Phase 1, step 5 — re-sample Meta/WRI canopy height properly.

Why: step 3 reprojected the 1 m product to 10 m with nearest-neighbour, so each 10 m cell got
one random 1 m pixel — mostly gaps in open forest. That is why the scatter floored at zero.

This samples at native 1 m inside a circular buffer around each plot, with two reducers:
  meta_mean_15m / meta_mean_30m   mean canopy height in a 15 m / 30 m radius
  meta_p95_15m  / meta_p95_30m    95th percentile — closest to what Lorey's height measures

Reads  odisha_plots_sampled_v2.csv,  adds the four columns, writes back to the same file.
Run:   python odisha_phase1_5_meta_rerun.py
"""
import ee
import pandas as pd

ee.Initialize()
META_CHM_IC = "projects/meta-forest-monitoring-okw37/assets/CanopyHeight"
F = "odisha_plots_sampled_v2.csv"

plots = pd.read_csv(F)
for c in ["meta_mean_15m", "meta_mean_30m", "meta_p95_15m", "meta_p95_30m"]:
    if c in plots: plots = plots.drop(columns=c)

pts = ee.FeatureCollection([
    ee.Feature(ee.Geometry.Point([float(r.lon), float(r.lat)]), {"plot_key": str(r.plot_key)})
    for r in plots.itertuples()
])
region = pts.geometry().bounds().buffer(1000)
meta = ee.ImageCollection(META_CHM_IC).filterBounds(region).mosaic().select([0]).rename("h").toFloat()

def sample_buffer(radius_m):
    buf = pts.map(lambda f: f.buffer(radius_m))
    red = ee.Reducer.mean().combine(ee.Reducer.percentile([95]), sharedInputs=True)
    out = meta.reduceRegions(collection=buf, reducer=red, scale=1, tileScale=4)
    rows = out.getInfo()["features"]
    d = pd.DataFrame([{"plot_key": f["properties"]["plot_key"],
                       f"meta_mean_{radius_m}m": f["properties"].get("mean"),
                       f"meta_p95_{radius_m}m":  f["properties"].get("p95")} for f in rows])
    print(f"   {radius_m} m buffer: {d[f'meta_mean_{radius_m}m'].notna().sum()} plots")
    return d

print("sampling Meta at native 1 m:")
out = plots
for r in (15, 30):
    out = out.merge(sample_buffer(r), on="plot_key", how="left")
out.to_csv(F, index=False)
print(f"updated {F}")