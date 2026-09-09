"""
Phase 1, step 7 — diagnose the Meta/WRI canopy-height zeros, and re-run Test 4 without them.

WHY THIS BLOCKS merge.criteria
------------------------------
Meta/WRI is the leading replacement candidate for ETH as the structural merge criterion
(plot-level R2 0.241 vs ETH's 0.207). But meta_chm is exactly 0 at 122 of 274 plots — 45% of
the column — and the zero plots are shorter than average in the field, so at plot level they
anchor the low end and inflate the correlation. Whether that 0 is "no data", "recoverable",
or "the product genuinely says no canopy under 88% crown cover" decides whether Meta can carry
a criterion at all. Nothing downstream can be re-specified until this is answered.

TWO PARTS
---------
  A. OFFLINE  — zero census, quantisation check, and Test 4 / site-level aggregation recomputed
                with zeros excluded. Runs from odisha_plots_sampled_v2.csv alone, no credentials.
  B. EARTH ENGINE — the raw 1 m neighbourhood around 12 zero plots and 5 non-zero controls,
                the mask state, and the band encoding. This is what actually returns the verdict.
                Requires GEE credentials; if absent, part B reports BLOCKED and part A still runs.

Run:  python odisha_phase1_7_meta_zero_diagnosis.py
Out:  odisha_phase1_7_results.txt

HOW THE STEP-3 COLUMN WAS SAMPLED, for the record
-------------------------------------------------
odisha_phase1_3_sample_gee_v2.py builds it as:

    meta = (ee.ImageCollection(META_CHM_IC).filterBounds(region)
              .mosaic().select([0]).rename("meta_chm").toFloat())
    meta_3x3 = (meta.reproject(crs="EPSG:4326", scale=10)
                    .reduceNeighborhood(ee.Reducer.mean(), k3).rename("meta_chm_3x3"))

`.mosaic()` over a collection with a coverage gap yields MASKED pixels, and sampling a masked
pixel returns null, not 0. So an exact 0 means either the product genuinely encodes 0, or
something in this chain is unmasking. Part B separates those.

Separately, and on the record even though it is not the cause: reproject(crs="EPSG:4326",
scale=10) on a 1 m source resamples by nearest neighbour onto a geographic grid (~9.3 x 10 m at
21 deg N), so meta_chm_3x3 is a 3x3 mean of point samples, not of the underlying 1 m pixels.
odisha_phase1_5_meta_rerun.py re-sampled with native-1 m circular buffers and got the same
zero pattern, so the reprojection is not what produces the zeros.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

CSV = "odisha_plots_sampled_v2.csv"
OUT = "odisha_phase1_7_results.txt"
META_CHM_IC = "projects/meta-forest-monitoring-okw37/assets/CanopyHeight"

# The bands the side-by-side table covers, per the task brief.
BANDS = [
    "eth_chm_3x3", "meta_chm_3x3", "meta_mean_15m", "meta_p95_15m",
    "meta_mean_30m", "meta_p95_30m", "glad_chm", "vh_iqr", "vv_iqr",
]

_out: list[str] = []


def say(s: str = "") -> None:
    _out.append(s)
    print(s)


def rule(title: str) -> None:
    say("")
    say("=" * 96)
    say(title)
    say("=" * 96)


def corr(x: pd.Series, y: pd.Series) -> tuple[int, float, float] | None:
    """Pearson over the pairwise-complete rows. None if too few or degenerate."""
    m = x.notna() & y.notna()
    xs, ys = x[m].to_numpy(float), y[m].to_numpy(float)
    if len(xs) < 5 or np.ptp(xs) == 0 or np.ptp(ys) == 0:
        return None
    r = float(stats.pearsonr(xs, ys)[0])
    return len(xs), r, r * r


# =====================================================================
# PART A — offline
# =====================================================================

def part_a(df: pd.DataFrame) -> pd.Series:
    """Returns the boolean zero mask used for every exclusion below."""
    # The exclusion is defined on meta_chm, the SINGLE-PIXEL column, not on the 3x3 mean.
    # This matters and is easy to get wrong: meta_chm is 0 at 122 plots, meta_chm_3x3 at 93,
    # because a 3x3 mean is non-zero as soon as any one of its nine cells is. Excluding on the
    # 3x3 column keeps 181 plots and gives R2=0.182; excluding on meta_chm keeps 152 and gives
    # 0.142. The single-pixel column is the honest one: it is where the product either has a
    # value or does not.
    zero = df["meta_chm"] == 0

    rule("A1 — the zero census")
    say(f"  rows: {len(df)}   meta_chm nulls: {int(df.meta_chm.isna().sum())}   "
        f"meta_chm_3x3 nulls: {int(df.meta_chm_3x3.isna().sum())}")
    say("")
    say(f"  {'district':12} {'meta_chm==0':>14} {'meta_chm_3x3==0':>18}")
    for d, g in df.groupby("district"):
        say(f"  {d:12} {int((g.meta_chm == 0).sum()):>7}/{len(g):<6} "
            f"{int((g.meta_chm_3x3 == 0).sum()):>11}/{len(g):<6}")
    say(f"  {'TOTAL':12} {int(zero.sum()):>7}/{len(df):<6} "
        f"{int((df.meta_chm_3x3 == 0).sum()):>11}/{len(df):<6}")
    say(f"  zero rate (meta_chm): {100 * zero.mean():.1f}%")
    say("")
    say("  Not nulls. Zero. A masked pixel sampled through .mosaic() returns null, and there")
    say("  are none — so whatever produced these, it produced a value, and the value was 0.")

    rule("A2 — Meta is quantised to integer metres")
    v = df.meta_chm.dropna()
    nz = v[v > 0]
    say(f"  meta_chm  all values integral: {bool((v % 1 == 0).all())}")
    say(f"  meta_chm  range 0..{int(v.max())}   non-zero: n={len(nz)} min={int(nz.min())} "
        f"max={int(nz.max())} median={int(nz.median())}")
    say(f"  distinct non-zero values: {sorted(int(x) for x in nz.unique())}")
    nz3 = df.loc[df.meta_chm_3x3 > 0, "meta_chm_3x3"]
    resid = float(np.abs(nz3 * 9 - (nz3 * 9).round()).max())
    say(f"  meta_chm_3x3 values are exact multiples of 1/9: {resid < 1e-4}  "
        f"(max deviation {resid:.1e})")
    say("")
    say("  A 3x3 mean lands on exact ninths only if all nine inputs are integers. So the")
    say("  product is delivered as integer metres, and the entire observed range here is 16")
    say("  levels, 0 to 15 m, against field Lorey's heights running to 37.75 m.")
    say("")
    say("  Consequences, both load-bearing for merge.criteria:")
    say("    - a Meta '0' means 'the model predicted under half a metre', which is NOT the")
    say("      same statement as 'no data' and NOT the same as 'no canopy'.")
    say("    - a 2.0 m tolerance on an integer-metre product gates on 2 of 16 available")
    say("      levels. There is no sub-metre structure for a threshold to resolve.")

    rule("A3 — what the zero plots look like in the field")
    zl, nzl = df.loc[zero, "loreys_h_m"], df.loc[~zero, "loreys_h_m"]
    say(f"  Lorey's at meta_chm==0 : n={len(zl)} median={zl.median():.2f} mean={zl.mean():.2f} "
        f"min={zl.min():.2f} max={zl.max():.2f}")
    say(f"  Lorey's at meta_chm >0 : n={len(nzl)} median={nzl.median():.2f} mean={nzl.mean():.2f}")
    p = float(stats.mannwhitneyu(zl.dropna(), nzl.dropna())[1])
    say(f"  Mann-Whitney zero vs non-zero: p={p:.2e}")
    say("")
    say("  The zero plots are genuinely shorter — so at plot level they sit at the low end of")
    say("  both axes and pull the correlation up. That is the inflation. But the maximum is")
    say(f"  {zl.max():.2f} m: the product returns 0 at a plot carrying {zl.max():.1f} m of canopy,")
    say("  which no amount of 'they are just short plots' explains.")

    if "crown_cover_pct" in df:
        say("")
        cz = df.loc[zero, "crown_cover_pct"].dropna()
        say(f"  crown cover at meta_chm==0: n={len(cz)} median={cz.median():.0f}% "
            f"min={cz.min():.0f}% max={cz.max():.0f}%   "
            f">50%: {int((cz > 50).sum())}  >75%: {int((cz > 75).sum())}")

    rule("A4 — Pangatira, all ten plots")
    pg = df[df.site_polygon == "Pangatira"]
    cols = [c for c in ["plot_key", "loreys_h_m", "crown_cover_pct", "meta_chm",
                        "meta_chm_3x3", "meta_mean_15m", "eth_chm_3x3"] if c in df]
    say(pg[cols].to_string(index=False))
    if "crown_cover_pct" in pg:
        cc = pg.crown_cover_pct
        say("")
        say(f"  crown cover {cc.min():.0f}-{cc.max():.0f}%  "
            f"(nine of ten are {sorted(cc)[1]:.0f}-{cc.max():.0f}%; one plot reads {cc.min():.0f}%)")
    say(f"  Lorey's {pg.loreys_h_m.min():.2f}-{pg.loreys_h_m.max():.2f} m, site mean "
        f"{pg.loreys_h_m.mean():.2f} m; Meta 0 at all {len(pg)}.")

    # ---------------------------------------------------------------- side-by-side
    rule("A5 — plot level, as-published vs zeros excluded")
    say("  Exclusion is meta_chm==0 (122 rows). Applied to EVERY band, not just the Meta ones,")
    say("  so the two columns are computed over the same plots and are comparable to each other.")
    say("")
    say(f"  {'band':16} {'n':>4} {'r':>8} {'R2':>7}    {'n':>4} {'r':>8} {'R2':>7}   {'dR2':>7}")
    say(f"  {'':16} {'--- as published ---':^21}    {'--- zeros excluded ---':^21}   {'':>7}")
    kept = df[~zero]
    for b in BANDS:
        if b not in df:
            continue
        a = corr(df.loreys_h_m, df[b])
        k = corr(kept.loreys_h_m, kept[b])
        if a is None or k is None:
            say(f"  {b:16} (skipped)")
            continue
        say(f"  {b:16} {a[0]:>4} {a[1]:>+8.3f} {a[2]:>7.3f}    "
            f"{k[0]:>4} {k[1]:>+8.3f} {k[2]:>7.3f}   {k[2] - a[2]:>+7.3f}")
    say("")
    say("  Every height PRODUCT falls, and by almost the same amount (-0.097 to -0.103 for ETH")
    say("  and all five Meta variants). The 122 zero plots were doing the same work for all of")
    say("  them: they sit at the short end of the field range, and removing them shrinks the")
    say("  spread each product is being asked to track.")
    say("")
    say("  The two radar bands do not fall. vh_iqr and vv_iqr both rise slightly, and vh_iqr")
    say("  overtakes every height product once the zeros are gone (0.227 vs Meta's best 0.142).")
    say("  Radar is the only structural signal here whose relationship to field height does not")
    say("  depend on the short-plot anchor.")
    say("")
    say("  glad_chm does not merely weaken, it FLIPS: r=+0.202 becomes r=-0.121. Its entire")
    say("  positive correlation was the zero plots. GLAD is not a weak predictor of height in")
    say("  this forest; on the plots where Meta has data it is a slightly negative one.")

    # ---------------------------------------------------------------- site level
    rule("A6 — site level, as-published vs zeros excluded")
    say("  Six Dhenkanal polygons. n=6 is directional, not evidential — and dropping zero plots")
    say("  removes Pangatira entirely, so the excluded column is n=5. Read accordingly.")
    for label, d in (("as published (n=6)", df), ("zeros excluded", kept)):
        sites = d[d.site_polygon.notna()]
        present = [b for b in BANDS if b in sites]
        agg = sites.groupby("site_polygon").agg(
            n=("plot_key", "size"), field=("loreys_h_m", "mean"),
            **{b: (b, "mean") for b in present}).round(3)
        say("")
        say(f"  --- {label}: {len(agg)} sites, {len(sites)} plots ---")
        say(agg.to_string())
        say("")
        for b in present:
            c = corr(agg["field"], agg[b])
            if c:
                say(f"    site-level {b:16} n={c[0]}  r={c[1]:+.3f}  R2={c[2]:.3f}")

    # ---------------------------------------------------------------- aggregation claim
    rule("A7 — does aggregation still 'recover signal', with zeros excluded?")
    say("  The claim on the record: aggregating to sites lifts Meta (0.241 -> 0.452) and GLAD")
    say("  (0.041 -> 0.310) while destroying ETH (0.207 -> 0.100). If the Meta lift is an")
    say("  artefact of averaging over sites that contain zeros, the claim does not survive.")
    say("")
    say(f"  {'band':16} {'plot R2':>9} {'site R2':>9} {'lift':>8}   |  "
        f"{'plot R2':>9} {'site R2':>9} {'lift':>8}")
    say(f"  {'':16} {'---- as published ----':^28}   |  {'--- zeros excluded ---':^28}")
    for b in BANDS:
        if b not in df:
            continue
        row = [f"  {b:16}"]
        for d in (df, kept):
            s = d[d.site_polygon.notna()]
            pl = corr(d.loreys_h_m, d[b])
            agg = s.groupby("site_polygon").agg(field=("loreys_h_m", "mean"), v=(b, "mean"))
            si = corr(agg["field"], agg["v"])
            if pl is None or si is None:
                row.append(f" {'--':>9} {'--':>9} {'--':>8}")
            else:
                row.append(f" {pl[2]:>9.3f} {si[2]:>9.3f} {si[2] - pl[2]:>+8.3f}")
        say(row[0] + row[1] + "   |  " + row[2])
    say("")
    say("  Read the two 'lift' columns against each other. A lift that survives the exclusion")
    say("  is a real aggregation effect; one that collapses was the zero plots averaging in.")
    say("")
    say("  RESULT: the Meta lift survives, and strengthens. meta_chm_3x3 goes +0.206 -> +0.361")
    say("  and meta_mean_15m +0.220 -> +0.391 once the zero plots are dropped. So it is NOT an")
    say("  artefact of averaging over sites containing zeros -- the opposite: the zeros were")
    say("  suppressing it, via Pangatira, whose ten zeros dragged one of six site means to 0.")
    say("  GLAD's lift survives too (+0.269 -> +0.220), and ETH's collapse persists")
    say("  (-0.107 -> -0.090). The 'aggregation recovers what plot noise hides' claim holds for")
    say("  Meta and GLAD and still fails for ETH.")
    say("")
    say("  Two cautions that have to travel with that sentence. The excluded column is n=5")
    say("  sites: one point governs a great deal. And aggregation makes RADAR worse, not")
    say("  better (vh_iqr -0.111 -> -0.157), so 'aggregation recovers signal' is a statement")
    say("  about these height products, not a general property of stand-scale averaging.")

    return zero


# =====================================================================
# PART B — Earth Engine
# =====================================================================

def pick_plots(df: pd.DataFrame, zero: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """12 zero plots (>=3 Pangatira, >=4 Koraput, rest ANGUL/DHENKANAL) and 5 non-zero controls.

    Chosen by sorted plot_key rather than at random, so the same plots come back on a re-run
    and the diagnostic is quotable.
    """
    z = df[zero].sort_values("plot_key")
    pang = z[z.site_polygon == "Pangatira"].head(3)
    kora = z[z.district == "KORAPUT"].head(4)
    rest = z[z.district.isin(["ANGUL", "DHENKANAL"])]
    rest = rest[~rest.plot_key.isin(pang.plot_key)].head(5)
    picked = pd.concat([pang, kora, rest]).drop_duplicates("plot_key").head(12)

    ctrl = df[~zero].sort_values("meta_chm", ascending=False)
    ctrl = ctrl[ctrl.loreys_h_m.notna()].head(5)
    return picked, ctrl


def part_b(df: pd.DataFrame, zero: pd.Series) -> None:
    rule("B — raw 1 m Meta neighbourhood at the zero plots (Earth Engine)")

    try:
        import ee
        ee.Initialize()
    except Exception as e:  # noqa: BLE001 - any auth/import failure is the same outcome here
        say("  BLOCKED — Earth Engine is not available in this environment.")
        say(f"  {type(e).__name__}: {str(e).splitlines()[0]}")
        say("")
        say("  Part B is the half that returns the verdict; part A cannot substitute for it.")
        say("  Run this script where `earthengine authenticate` has been done, and the section")
        say("  below will fill in. NOTHING here is estimated in its absence.")
        say("")
        say("  The three outcomes it decides between, and what each one means:")
        say("    NO DATA      30 m box entirely masked / no intersecting tile.")
        say("                 -> exclude; Test 4 is n=152, R2=0.142. Meta is out.")
        say("    RECOVERABLE  box has values, the sample point does not.")
        say("                 -> geolocation or mosaic gap; re-sample with a buffered reducer")
        say("                    that ignores masked pixels, re-run Test 4, report both.")
        say("    DISQUALIFIED box is genuinely and validly 0 under 88% field crown cover.")
        say("                 -> no aggregation fixes this. Meta is out, and the fact that a")
        say("                    published 1 m product reads 0 over closed canopy is itself")
        say("                    a reportable finding.")
        return

    picked, ctrl = pick_plots(df, zero)
    say(f"  diagnosing {len(picked)} zero plots and {len(ctrl)} non-zero controls")
    say(f"  collection: {META_CHM_IC}")

    ic = ee.ImageCollection(META_CHM_IC)

    def diagnose(row, kind: str) -> None:
        pt = ee.Geometry.Point([float(row.lon), float(row.lat)])
        box = pt.buffer(15).bounds()          # 30 m box
        hits = ic.filterBounds(box)
        n_tiles = int(hits.size().getInfo())

        say("")
        say(f"  [{kind}] {row.plot_key}  {row.district}  "
            f"loreys={row.loreys_h_m:.2f}m  "
            f"crown={getattr(row, 'crown_cover_pct', float('nan'))}%  "
            f"gps_acc={getattr(row, 'gps_acc_m', float('nan'))}m")
        say(f"          sampled meta_chm={row.meta_chm}  meta_chm_3x3={row.meta_chm_3x3:.4f}")
        say(f"          collection images intersecting the 30 m box: {n_tiles}")

        if n_tiles == 0:
            say("          -> NO TILE. The product does not cover this location.")
            return

        first = ee.Image(hits.first())
        info = first.getInfo()
        bands = [b["id"] for b in info["bands"]]
        dtype = info["bands"][0].get("data_type", {})
        say(f"          band names: {bands}   dtype: {dtype}")

        # Un-mosaicked, un-reprojected: the raw pixels as delivered.
        raw = hits.mosaic().select([0])
        rect = raw.sampleRectangle(region=box, defaultValue=-9999, properties=[])
        arr = np.array(rect.get(bands[0]).getInfo(), dtype=float)
        nodata = arr == -9999
        valid = arr[~nodata]
        say(f"          30 m pixel grid: shape={arr.shape} total={arr.size} "
            f"masked={int(nodata.sum())} valid={len(valid)}")
        if len(valid):
            nzv = valid[valid > 0]
            say(f"          valid pixels: zeros={int((valid == 0).sum())} "
                f"non-zero={len(nzv)}")
            if len(nzv):
                say(f"          non-zero pixels: min={nzv.min():.2f} max={nzv.max():.2f} "
                    f"median={float(np.median(nzv)):.2f}")
            else:
                say("          non-zero pixels: NONE — every valid pixel in the box is 0")

        # Mask state exactly at the plot point.
        mv = raw.mask().reduceRegion(
            reducer=ee.Reducer.first(), geometry=pt, scale=1).getInfo()
        say(f"          mask() at the plot point: {mv}")

    for r in picked.itertuples():
        diagnose(r, "ZERO ")
    for r in ctrl.itertuples():
        diagnose(r, "CTRL ")

    say("")
    say("  VERDICT — fill in exactly one, from the grids above:")
    say("    [ ] NO DATA       [ ] RECOVERABLE       [ ] DISQUALIFIED")


def main() -> None:
    df = pd.read_csv(CSV)
    say("=" * 96)
    say("PHASE 1 STEP 7 — Meta/WRI canopy-height zeros")
    say("=" * 96)
    say(f"  input: {CSV}  ({len(df)} plots)")
    zero = part_a(df)
    part_b(df, zero)
    with open(OUT, "w") as f:
        f.write("\n".join(_out) + "\n")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
