"""
Phase 1, step 9 — fix the GEDI shot count, re-sample, and re-report Test 4's GEDI row.

THE SYMPTOM
-----------
In odisha_plots_sampled_v2.csv, gedi_n_50m is 0.0 in exactly the 10 rows where it is non-null
and NaN in the other 264, while those same 10 rows carry real-looking gedi_rh98_50m values
(6.42 to 21.30 m). odisha_phase1_tests456_results.txt therefore prints, from one run:

    GEDI L2A rh98 (<=50m):
      all plots      n= 10  r=+0.635  R2=0.404  slope=+0.63  RMSE=4.59  bias=+3.19
    ...
    GEDI coverage: plots with >=1 shot within 50 m = 0 / 274

n=10 and coverage=0 cannot both be right. R2=0.404 is the best-looking number in the whole
study and currently rests on 10 means with no established provenance.

THE CODE
--------
odisha_phase1_3_sample_gee_v2.py:57-62

    gedi_mean  = gedi.mean().rename("gedi_rh98")
    gedi_count = gedi.count().rename("gedi_n")
    gedi_50 = (gedi_mean.reduceNeighborhood(ee.Reducer.mean(),
                                            ee.Kernel.circle(50, "meters")).rename("gedi_rh98_50m")
               .addBands(gedi_count.reduceNeighborhood(ee.Reducer.sum(),
                                            ee.Kernel.circle(50, "meters")).rename("gedi_n_50m")))

and odisha_phase1_4_analyse_v2.py:56-57 prints the coverage line as `(df.gedi_n_50m > 0).sum()`.

WHAT IS WRONG, AND WHAT IS VERIFIED VS NOT
------------------------------------------
Two defects. The first is verifiable from the installed client; the second needs one GEE call.

1. THE COUNT PATH DEPENDS ON AN EE SERVER DEFAULT IT NEVER STATES.  [VERIFIED offline]

   `ee.Kernel.circle(radius, units, normalize, magnitude)` -- the Python client passes
   `normalize=None`, so whatever the server's default is applies. The client docstring says
   "normalize: Normalize the kernel values to sum to 1". `Image.reduceNeighborhood(reducer,
   kernel, inputWeight, skipMasked, optimization)` likewise passes `inputWeight=None`; its
   docstring says "Reducers with weighted inputs can have the input weight based on the input
   mask, the kernel value, or the smaller of those two."

   So with a NORMALIZED kernel and kernel weighting, `Reducer.sum()` computes a weighted MEAN
   (weights summing to 1), not a count -- a fraction far below 1, which is what a column of
   0.0 looks like. With an UN-normalized boolean kernel and no weighting it computes a true
   count. The code is correct under one default and silently wrong under the other, and it
   states neither. That alone disqualifies the column, whichever way the default falls.

   Confirmed by reading `inspect.signature` on the installed ee 1.7.41: both parameters exist
   and both are passed as None. NOT confirmed offline: which value the server actually uses.
   That is a live-call question and this script does not guess it.

2. THE TWO PATHS DO NOT SHARE A MASK.  [VERIFIED offline, from the code]

   `gedi.mean()` is masked wherever no quality-passing shot exists. `gedi.count()` is a count,
   which is 0 rather than masked where a collection has no valid value. So `gedi_rh98_50m` and
   `gedi_n_50m` are derived from images with different masks, and comparing "rows with an rh98"
   against "rows with n>0" compares two different things. Whatever the kernel does, these two
   columns were never going to agree.

THE FIX
-------
Stop relying on any unstated default. Drop the kernel entirely and sample with an explicit
buffered reduction -- the pattern odisha_phase1_5_meta_rerun.py already uses for Meta:

    buf = pts.map(lambda f: f.buffer(50))
    gedi_mean.reduceRegions(buf, ee.Reducer.mean().combine(ee.Reducer.count(), True), scale=25)
    gedi_count.reduceRegions(buf, ee.Reducer.sum(), scale=25)

`Reducer.count()` over the masked mean image counts unmasked 25 m cells in the buffer, which is
the honest reading of "how many GEDI observations back this mean". `Reducer.sum()` over the
per-pixel count image gives total shot-observations. Both are reported; neither depends on a
kernel default. scale=25 is stated explicitly because GEDI L2A rasterises to ~25 m footprints
and letting the scale default would reintroduce exactly the kind of unstated dependence
defect 1 is about.

ACCEPTANCE
----------
  gedi_n_50m > 0 holds for EXACTLY the rows carrying a gedi_rh98_50m value, and
  the printed coverage line equals the regression's n.
This script asserts both and says so. If true coverage is 0, the GEDI result is WITHDRAWN.

Run:  python odisha_phase1_9_gedi_recount.py
Out:  odisha_phase1_9_results.txt, and (with GEE) the four gedi_* columns rewritten in
      odisha_plots_sampled_v2.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

CSV = "odisha_plots_sampled_v2.csv"
OUT = "odisha_phase1_9_results.txt"
GEDI_L2A_IC = "LARSE/GEDI/GEDI02_A_002_MONTHLY"
BUFFER_M = 50
GEDI_SCALE = 25

_out: list[str] = []


def say(s: str = "") -> None:
    _out.append(s)
    print(s)


def rule(t: str) -> None:
    say("")
    say("=" * 92)
    say(t)
    say("=" * 92)


def fit(x: pd.Series, y: pd.Series, label: str) -> None:
    m = x.notna() & y.notna()
    xs, ys = x[m].to_numpy(float), y[m].to_numpy(float)
    if len(xs) < 3:
        say(f"  {label:40} n={len(xs):>3}  (too few)")
        return
    r = float(stats.pearsonr(xs, ys)[0])
    lr = stats.linregress(xs, ys)
    say(f"  {label:40} n={len(xs):>3}  r={r:+.3f}  R2={r * r:.3f}  "
        f"slope={lr.slope:+.2f}  RMSE={float(np.sqrt(np.mean((ys - xs) ** 2))):.2f}  "
        f"bias={float(np.mean(ys - xs)):+.2f}")


def report_current(df: pd.DataFrame) -> None:
    rule("The column as it stands")
    n_rh = int(df.gedi_rh98_50m.notna().sum())
    n_ct = int(df.gedi_n_50m.notna().sum())
    say(f"  gedi_rh98_50m non-null : {n_rh} / {len(df)}")
    say(f"  gedi_n_50m    non-null : {n_ct} / {len(df)}")
    vals = df.gedi_n_50m.dropna().unique()
    say(f"  gedi_n_50m distinct non-null values: {sorted(vals)}")
    say(f"  gedi_n_50m > 0         : {int((df.gedi_n_50m.fillna(0) > 0).sum())}")
    say("")
    say("  So the coverage line and the regression n disagree by construction: the regression")
    say(f"  uses the {n_rh} rows with an rh98 value, the coverage line counts rows with n>0, and")
    say("  there are none. Both come from the same run.")
    say("")
    say("  The 10 rows currently carrying a value:")
    g = df[df.gedi_rh98_50m.notna()][
        ["plot_key", "district", "loreys_h_m", "gedi_rh98_50m", "gedi_n_50m"]]
    say(g.to_string(index=False))
    say("")
    fit(df.loreys_h_m, df.gedi_rh98_50m, "PUBLISHED gedi_rh98_50m vs Lorey's")
    say("")
    say("  WITHDRAWN pending re-sample. Not because the correlation is implausible, but because")
    say("  the number of observations behind each of those 10 means is unknown, and the column")
    say("  that was supposed to record it is provably not a count (see the module docstring).")


def resample(df: pd.DataFrame) -> pd.DataFrame | None:
    rule("Re-sample with an explicit buffered reduction (Earth Engine)")
    try:
        import ee
        ee.Initialize()
    except Exception as e:  # noqa: BLE001 - import or auth failure is one outcome here
        say("  BLOCKED — Earth Engine is not available in this environment.")
        say(f"  {type(e).__name__}: {str(e).splitlines()[0]}")
        say("")
        say("  The two code defects above are established from the script source and the")
        say("  installed ee client, and stand without a live call. What needs GEE is the")
        say("  corrected column and the honest n. Nothing is estimated in its place.")
        say("")
        say("  Run this where `earthengine authenticate` has been done. It will rewrite")
        say("  gedi_rh98_50m, gedi_n_50m, gedi_npix_50m and gedi_nshots_50m in")
        say(f"  {CSV} and fill in the section below.")
        return None

    pts = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([float(r.lon), float(r.lat)]),
                   {"plot_key": str(r.plot_key)})
        for r in df.itertuples()])
    region = pts.geometry().bounds().buffer(2000)

    gedi = (ee.ImageCollection(GEDI_L2A_IC)
            .filterBounds(region).filterDate("2019-04-01", "2023-01-01")
            .map(lambda im: im.updateMask(im.select("quality_flag").eq(1))
                              .updateMask(im.select("degrade_flag").eq(0)))
            .select("rh98"))
    n_img = int(gedi.size().getInfo())
    say(f"  collection: {GEDI_L2A_IC}")
    say(f"  quality_flag==1 and degrade_flag==0, 2019-04-01..2023-01-01: {n_img} images over the ROI")

    gedi_mean = gedi.mean().rename("h")
    gedi_count = gedi.count().rename("n")
    buf = pts.map(lambda f: f.buffer(BUFFER_M))

    # Reducer.count() over the MASKED mean: unmasked 25 m cells backing each mean.
    got = gedi_mean.reduceRegions(
        collection=buf,
        reducer=ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True),
        scale=GEDI_SCALE, tileScale=4).getInfo()["features"]
    a = pd.DataFrame([{"plot_key": f["properties"]["plot_key"],
                       "gedi_rh98_50m": f["properties"].get("mean"),
                       "gedi_npix_50m": f["properties"].get("count")} for f in got])

    # Reducer.sum() over the per-pixel observation count: total shot-observations.
    got2 = gedi_count.reduceRegions(
        collection=buf, reducer=ee.Reducer.sum(),
        scale=GEDI_SCALE, tileScale=4).getInfo()["features"]
    b = pd.DataFrame([{"plot_key": f["properties"]["plot_key"],
                       "gedi_nshots_50m": f["properties"].get("sum")} for f in got2])

    out = df.drop(columns=[c for c in ("gedi_rh98_50m", "gedi_n_50m", "gedi_npix_50m",
                                       "gedi_nshots_50m") if c in df])
    out = out.merge(a, on="plot_key", how="left").merge(b, on="plot_key", how="left")
    # gedi_n_50m keeps its name for downstream compatibility, now meaning unmasked cells.
    out["gedi_n_50m"] = out["gedi_npix_50m"]
    return out


def report_fixed(out: pd.DataFrame) -> None:
    rule("Corrected GEDI row")
    n_rh = int(out.gedi_rh98_50m.notna().sum())
    n_pos = int((out.gedi_n_50m.fillna(0) > 0).sum())
    say(f"  gedi_rh98_50m non-null            : {n_rh} / {len(out)}")
    say(f"  gedi_n_50m > 0 (unmasked 25 m cells): {n_pos} / {len(out)}")
    say(f"  gedi_nshots_50m > 0                : "
        f"{int((out.gedi_nshots_50m.fillna(0) > 0).sum())} / {len(out)}")
    say("")

    have = out.gedi_rh98_50m.notna()
    pos = out.gedi_n_50m.fillna(0) > 0
    exact = bool((have == pos).all())
    say(f"  ACCEPTANCE 1 — n>0 exactly where an rh98 exists : {'PASS' if exact else 'FAIL'}")
    if not exact:
        say(f"    rh98 but n==0 : {int((have & ~pos).sum())}    n>0 but no rh98 : "
            f"{int((~have & pos).sum())}")
    say(f"  ACCEPTANCE 2 — coverage line equals regression n : "
        f"{'PASS' if n_pos == n_rh else 'FAIL'}  ({n_pos} vs {n_rh})")
    say("")

    if n_rh == 0:
        say("  TRUE COVERAGE IS ZERO. The GEDI result is WITHDRAWN: no plot has a")
        say("  quality-passing GEDI observation within 50 m, so Test 4's GEDI row carries no")
        say("  information and must not be quoted. That is a real finding about GEDI's")
        say("  sampling density over this AOI, not a failure of the test.")
        return

    say(f"  GEDI coverage: plots with >=1 unmasked GEDI cell within {BUFFER_M} m = {n_pos} / {len(out)}")
    say("")
    fit(out.loreys_h_m, out.gedi_rh98_50m, "CORRECTED gedi_rh98_50m vs Lorey's")
    say("")
    say("  Observations behind each mean:")
    g = out[out.gedi_rh98_50m.notna()][
        ["plot_key", "district", "loreys_h_m", "gedi_rh98_50m", "gedi_n_50m", "gedi_nshots_50m"]]
    say(g.to_string(index=False))
    say("")
    if n_rh < 30:
        say(f"  CAVEAT, to travel with the number wherever it goes: n={n_rh}. Too sparse to carry")
        say("  a conclusion on its own. It can say whether GEDI tracks height where GEDI exists;")
        say("  it cannot say GEDI is a usable height source for this AOI, and it cannot")
        say("  adjudicate between ETH and Meta, which are measured on all 274 plots.")


def main() -> None:
    df = pd.read_csv(CSV)
    say("=" * 92)
    say("PHASE 1 STEP 9 — GEDI shot count")
    say("=" * 92)
    say(f"  input: {CSV}  ({len(df)} plots)")
    report_current(df)
    out = resample(df)
    if out is not None:
        report_fixed(out)
        out.to_csv(CSV, index=False)
        say("")
        say(f"  rewrote {CSV}")
    with open(OUT, "w") as f:
        f.write("\n".join(_out) + "\n")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
