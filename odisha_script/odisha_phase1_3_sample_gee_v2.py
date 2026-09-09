"""
Phase 1, step 3 — sample the inputs for Tests 4, 5 and 6 at the 274 Odisha plots.

Reads  odisha_plots_sampled.csv   (from step 1; already has ETH + NDVI harmonic columns)
Writes odisha_plots_sampled_v2.csv (same rows, new columns appended)

Test 4  alternative canopy height products
          meta_chm_3x3    Meta/WRI 1 m canopy height (Tolan et al. 2024), 3x3 mean at 10 m
          glad_chm        GLAD/Potapov 2019 global forest height, 30 m
          gedi_rh98_50m   mean GEDI L2A rh98 within 50 m, quality-filtered  (sparse — NaN where no shot)
          gedi_n_50m      number of GEDI shots within 50 m
Test 5  Sentinel-1 structural signal, same recipe as FMU features_radar
          vv_p10 vv_p50 vv_p90 vh_p10 vh_p50 vh_p90 vv_iqr vh_iqr vv_minus_vh_median   (dB)
Test 6  leaf-off vs leaf-on Sentinel-2, 2017-2022 medians
          off_B4 off_B5 off_B6 off_B7 off_B8 off_B8A off_B11 off_B12   (Feb-Apr)
          on_B4  on_B8  on_B11                                          (Aug-Oct)
          off_ndvi off_nbr off_ndmi off_ndre  on_ndvi  ndvi_seasonal_diff (= on - off)

ASSET IDS: verify the three in the block below in the GEE catalog before running — they move.
Run:  python odisha_phase1_3_sample_gee_v2.py
"""
import ee
import pandas as pd

ee.Initialize()

# ---------------------------------------------------------------- VERIFY THESE THREE
META_CHM_IC = "projects/meta-forest-monitoring-okw37/assets/CanopyHeight"   # ImageCollection, 1 m tiles
GLAD_CHM    = "users/potapovpeter/GEDI_V27"                                  # Image, 30 m, 2019
GEDI_L2A_IC = "LARSE/GEDI/GEDI02_A_002_MONTHLY"                              # ImageCollection, rasterised footprints
# ----------------------------------------------------------------

IN, OUT = "odisha_plots_sampled.csv", "odisha_plots_sampled_v2.csv"
FEAT_START, FEAT_END = "2017-01-01", "2023-01-01"
CLOUD_MAX = 20

plots = pd.read_csv(IN)
fc = ee.FeatureCollection([
    ee.Feature(ee.Geometry.Point([float(r.lon), float(r.lat)]), {"plot_key": str(r.plot_key)})
    for r in plots.itertuples()
])
region = fc.geometry().bounds().buffer(1000)
k3 = ee.Kernel.square(1)

# ================================================================ TEST 4 — alternative CHMs
meta = (ee.ImageCollection(META_CHM_IC).filterBounds(region).mosaic()
        .select([0]).rename("meta_chm").toFloat())
meta_3x3 = (meta.reproject(crs="EPSG:4326", scale=10)   # 1 m -> 10 m so "3x3" matches ETH's footprint
                .reduceNeighborhood(ee.Reducer.mean(), k3).rename("meta_chm_3x3"))

glad = (ee.ImageCollection(GLAD_CHM).filterBounds(region).mosaic()
        .select([0]).rename("glad_chm").toFloat())

gedi = (ee.ImageCollection(GEDI_L2A_IC).filterBounds(region).filterDate("2019-04-01", "2023-01-01")
        .map(lambda im: im.updateMask(im.select("quality_flag").eq(1))
                          .updateMask(im.select("degrade_flag").eq(0)))
        .select("rh98"))
gedi_mean  = gedi.mean().rename("gedi_rh98")
gedi_count = gedi.count().rename("gedi_n")
# 50 m neighbourhood so a plot picks up any nearby 25 m footprint
gedi_50 = (gedi_mean.reduceNeighborhood(ee.Reducer.mean(), ee.Kernel.circle(50, "meters")).rename("gedi_rh98_50m")
           .addBands(gedi_count.reduceNeighborhood(ee.Reducer.sum(), ee.Kernel.circle(50, "meters")).rename("gedi_n_50m")))

# ================================================================ TEST 5 — Sentinel-1 (FMU recipe)
s1 = (ee.ImageCollection("COPERNICUS/S1_GRD")
      .filterBounds(region).filterDate(FEAT_START, FEAT_END)
      .filter(ee.Filter.eq("instrumentMode", "IW"))
      .filter(ee.Filter.eq("orbitProperties_pass", "ASCENDING"))
      .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
      .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
      .select(["VV", "VH"]))
pct = s1.reduce(ee.Reducer.percentile([10, 50, 90]))
# reducer names bands VV_p10, VV_p50 ... ; rename to FMU's lowercase convention
radar = pct.rename(["vv_p10", "vv_p50", "vv_p90", "vh_p10", "vh_p50", "vh_p90"])
radar = (radar
         .addBands(radar.select("vv_p90").subtract(radar.select("vv_p10")).rename("vv_iqr"))
         .addBands(radar.select("vh_p90").subtract(radar.select("vh_p10")).rename("vh_iqr"))
         .addBands(radar.select("vv_p50").subtract(radar.select("vh_p50")).rename("vv_minus_vh_median")))

# ================================================================ TEST 6 — leaf-off / leaf-on S2
def mask_scl(img):
    scl = img.select("SCL")
    bad = scl.eq(3).Or(scl.eq(8)).Or(scl.eq(9)).Or(scl.eq(10))
    return img.updateMask(bad.Not())

s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
      .filterBounds(region).filterDate(FEAT_START, FEAT_END)
      .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", CLOUD_MAX))
      .map(mask_scl))

OFF_BANDS = ["B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"]
off = s2.filter(ee.Filter.calendarRange(2, 4, "month")).select(OFF_BANDS).median().divide(10000)
on  = s2.filter(ee.Filter.calendarRange(8, 10, "month")).select(["B4", "B8", "B11"]).median().divide(10000)

def nd(img, a, b, name):
    return img.normalizedDifference([a, b]).rename(name)

off_idx = ee.Image.cat([
    nd(off, "B8", "B4",  "off_ndvi"),
    nd(off, "B8", "B12", "off_nbr"),
    nd(off, "B8", "B11", "off_ndmi"),
    nd(off, "B8", "B5",  "off_ndre"),
])
on_ndvi = nd(on, "B8", "B4", "on_ndvi")
seasonal_diff = on_ndvi.subtract(off_idx.select("off_ndvi")).rename("ndvi_seasonal_diff")

off_named = off.rename([f"off_{b}" for b in OFF_BANDS])
on_named  = on.rename(["on_B4", "on_B8", "on_B11"])

# ================================================================ sample — one call per group
# GEE evaluates lazily, so one bad asset id would otherwise kill everything. Each group is
# sampled on its own; a failure prints a warning and leaves that group's columns as NaN.
def sample(img, label):
    try:
        feats = img.toFloat().sampleRegions(collection=fc, scale=10, geometries=False, tileScale=4)
        rows = feats.getInfo()["features"]
        d = pd.DataFrame([f["properties"] for f in rows])
        print(f"   {label:12} ok  ({len(d.columns)-1} columns)")
        return d
    except Exception as e:
        msg = str(e).split("\n")[0][:160]
        print(f"   {label:12} FAILED -> skipped.  {msg}")
        return pd.DataFrame({"plot_key": plots.plot_key})

print("sampling:")
out = plots
for img, label in [(ee.Image.cat([meta, meta_3x3]), "meta"),
                   (glad,                           "glad"),
                   (gedi_50,                        "gedi"),
                   (radar,                          "radar"),
                   (ee.Image.cat([off_named, on_named, off_idx, on_ndvi, seasonal_diff]), "sentinel2")]:
    d = sample(img, label)
    out = out.merge(d, on="plot_key", how="left")
out.to_csv(OUT, index=False)

print(f"\nwrote {OUT}: {len(out)} plots")
for c in ["meta_chm_3x3", "glad_chm", "gedi_rh98_50m", "vv_p50", "off_ndvi", "ndvi_seasonal_diff"]:
    if c in out: print(f"   {c:20} non-null: {out[c].notna().sum()}")
if "gedi_n_50m" in out:
    print(f"   plots with >=1 GEDI shot within 50 m: {(out['gedi_n_50m'] > 0).sum()}")