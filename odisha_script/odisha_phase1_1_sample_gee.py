"""
Phase 1, step 1 — sample Earth Engine layers at the 274 Odisha field plots.

Pulls, at every plot:
  eth_chm          ETH Global Canopy Height 2020, single pixel (m)
  eth_chm_3x3      3x3 mean       — use this; GPS accuracy ~4.8 m, plot radius unknown
  eth_chm_std_3x3  3x3 std dev    — the FMU `canopy_height_std` proxy, for the crown-cover test
  eth_sd           ETH per-pixel predictive std dev (m) — nobody in the survey uses this
  eth_sd_3x3
  ndvi_mean        harmonic-fit constant term, 2017-2022   (same model as FMU features_optical)
  ndvi_amplitude   sqrt(b^2 + c^2) — the seasonal swing, for the Sal-dominance test

Writes odisha_plots_sampled.csv (one row per plot, joined on plot_key).

Untested against a live GEE session — written from the FMU pipeline's documented conventions.
Run:  python odisha_phase1_1_sample_gee.py
"""
import math
import ee
import pandas as pd

ee.Initialize()

PLOTS_IN  = "odisha_plots_clean.csv"
PLOTS_OUT = "odisha_plots_sampled.csv"
ANCHOR    = "2017-01-01"           # FMU's fixed harmonic anchor
FEAT_START, FEAT_END = "2017-01-01", "2023-01-01"
CLOUD_MAX = 20

# ---------------------------------------------------------------- plots -> FeatureCollection
plots = pd.read_csv(PLOTS_IN)
fc = ee.FeatureCollection([
    ee.Feature(ee.Geometry.Point([float(r.lon), float(r.lat)]), {"plot_key": str(r.plot_key)})
    for r in plots.itertuples()
])
region = fc.geometry().bounds().buffer(500)

# ---------------------------------------------------------------- ETH canopy height + SD
chm = ee.Image("users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1").select([0]).rename("eth_chm").toFloat()
sd  = ee.Image("users/nlang/ETH_GlobalCanopyHeightSD_2020_10m_v1").select([0]).rename("eth_sd").toFloat()
# ^ verify the SD asset id in the GEE catalog if this errors; it is the companion to the CHM asset.

k3 = ee.Kernel.square(1)  # 3x3 pixels at native 10 m
chm_3x3     = chm.reduceNeighborhood(ee.Reducer.mean(),   k3).rename("eth_chm_3x3")
chm_std_3x3 = chm.reduceNeighborhood(ee.Reducer.stdDev(), k3).rename("eth_chm_std_3x3")
sd_3x3      = sd.reduceNeighborhood(ee.Reducer.mean(),    k3).rename("eth_sd_3x3")

# ---------------------------------------------------------------- NDVI harmonic fit (FMU convention)
def mask_scl(img):
    scl = img.select("SCL")
    bad = scl.eq(3).Or(scl.eq(8)).Or(scl.eq(9)).Or(scl.eq(10))
    return img.updateMask(bad.Not())

def add_terms(img):
    t = img.date().difference(ee.Date(ANCHOR), "year")
    w = ee.Number(t).multiply(2 * math.pi)
    ndvi = img.normalizedDifference(["B8", "B4"]).rename("ndvi")
    return (ndvi
            .addBands(ee.Image.constant(1).rename("const"))
            .addBands(ee.Image.constant(w.cos()).rename("cos"))
            .addBands(ee.Image.constant(w.sin()).rename("sin"))
            .addBands(ee.Image.constant(t).rename("t"))
            .toFloat())

s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
      .filterBounds(region)
      .filterDate(FEAT_START, FEAT_END)
      .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", CLOUD_MAX))
      .map(mask_scl)
      .map(add_terms))

fit = (s2.select(["const", "cos", "sin", "t", "ndvi"])
         .reduce(ee.Reducer.linearRegression(numX=4, numY=1)))
coefs = fit.select("coefficients").arrayProject([0]).arrayFlatten([["a", "b", "c", "f"]])
ndvi_mean = coefs.select("a").rename("ndvi_mean")
ndvi_amp  = coefs.select("b").pow(2).add(coefs.select("c").pow(2)).sqrt().rename("ndvi_amplitude")

# ---------------------------------------------------------------- sample
stack = ee.Image.cat([chm, chm_3x3, chm_std_3x3, sd, sd_3x3, ndvi_mean, ndvi_amp])
sampled = stack.sampleRegions(collection=fc, scale=10, geometries=False, tileScale=4)

rows = sampled.getInfo()["features"]
df = pd.DataFrame([f["properties"] for f in rows])
out = plots.merge(df, on="plot_key", how="left")
out.to_csv(PLOTS_OUT, index=False)
print(f"wrote {PLOTS_OUT}: {len(out)} plots, {out['eth_chm_3x3'].notna().sum()} with ETH values")