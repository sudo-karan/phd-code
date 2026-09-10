"""
Phase 1, step 10 — the two confirmations that close out the Task 1 verdict.

WHY
---
Step 7 part B established, at 12 zero plots and 5 non-zero controls, that the Meta/WRI
30 m box is fully UNMASKED (masked=0 of ~780 native pixels, mask()==1 at the plot point,
exactly 1 intersecting collection image) and nonetheless reads 0 at 10 of 12, with the
other two topping out at 2 m. That rules out NO DATA by direct measurement.

Two loose ends remain before RECOVERABLE can be ruled out and the verdict recorded:

  A. GEOREFERENCING OFFSET. RECOVERABLE's own test is "box has values, sample point does
     not". The box has values and they are zero -- but a systematic shift of the Meta
     raster larger than the 15 m box half-width would produce exactly that signature. If
     the product is displaced by d, the true location falls outside a 30 m box once
     d > ~14 m, so the box reads whatever is at the displaced position.

     The test: take concentric discs of 15, 50, 100, 200 and 500 m at the same plots and
     watch max / mean / non-zero fraction as the radius grows. An offset of magnitude d is
     only a viable explanation if real canopy appears once the disc is large enough to
     re-contain the true location. If the wider neighbourhood is also predominantly zero,
     no offset of any magnitude explains the reading, and RECOVERABLE is closed.

     The five non-zero controls are carried through the same ladder as a positive control:
     they must show canopy at every radius. If they went to zero at large radii, the
     ladder itself would be measuring something other than what it claims.

  B. BAND IDENTITY. The asset carries exactly ONE band, named `cover_code`, UINT8 0..255.
     The name is not "height", and the whole of Test 4a rests on reading it as metres. It
     behaves like height (controls at 23.86 m of field Lorey's sit in a 10-17 box; r=+0.49
     against Lorey's across 274 plots; values vary smoothly within a box) -- but that is
     inference from correlation, not from the encoding.

     The test: a frequency histogram of the band over the 274 sampled neighbourhoods. A
     height field in metres gives a broad, ordered, roughly unimodal distribution running
     from 0 to a few tens. A categorical cover code gives a handful of spikes on
     arbitrary integers with empty space between them. These are not subtle to tell apart.

WHAT THIS DOES NOT DO
---------------------
It does not re-sample anything, write any CSV, or change any published number. It reads
the same plots step 7 chose -- via `pick_plots`, imported rather than reimplemented, so the
two steps cannot drift apart -- and reports. Everything here is a read.

COST
----
Four getInfo calls: one reduceRegions over all 85 (plot x radius) discs at once, one
frequency histogram, and two small metadata reads. No exports, no tasks.

Run:  python odisha_phase1_10_meta_offset_check.py
Out:  odisha_phase1_10_results.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from odisha_phase1_7_meta_zero_diagnosis import META_CHM_IC, pick_plots

CSV = "odisha_plots_sampled_v2.csv"
OUT = "odisha_phase1_10_results.txt"
RADII_M = [15, 50, 100, 200, 500]
RING_SCALE = 10      # stated, not defaulted: 1 m native, read at 10 m for the wide discs
HIST_SCALE = 10
HIST_BUFFER_M = 500

_out: list[str] = []


def say(s: str = "") -> None:
    _out.append(s)
    print(s)


def rule(t: str) -> None:
    say("")
    say("=" * 96)
    say(t)
    say("=" * 96)


def main() -> None:
    if not Path(CSV).exists():
        sys.exit(f"MISSING INPUT: {CSV} — run from the odisha_script directory.")

    import ee
    ee.Initialize()

    df = pd.read_csv(CSV)
    zero = df["meta_chm"] == 0
    picked, ctrl = pick_plots(df, zero)

    say("=" * 96)
    say("PHASE 1 STEP 10 — closing out the Task 1 verdict: offset ladder and band identity")
    say("=" * 96)
    say(f"  input: {CSV}  ({len(df)} plots)")
    say(f"  collection: {META_CHM_IC}")
    say(f"  plots: {len(picked)} zero + {len(ctrl)} control, selected by step 7's pick_plots()")

    ic = ee.ImageCollection(META_CHM_IC)

    # ---------------------------------------------------------------- A. offset ladder
    rule("A — offset ladder: does canopy appear as the disc grows?")
    say(f"  radii (m): {RADII_M}   read at scale={RING_SCALE} m")
    say("  nz% is the percentage of unmasked pixels in the disc that are greater than zero.")

    rows = []
    for kind, frame in (("ZERO", picked), ("CTRL", ctrl)):
        for r in frame.itertuples():
            for rad in RADII_M:
                rows.append(ee.Feature(
                    ee.Geometry.Point([float(r.lon), float(r.lat)]).buffer(rad),
                    {"plot_key": str(r.plot_key), "kind": kind, "radius": rad}))
    fc = ee.FeatureCollection(rows)
    say(f"  discs in one reduceRegions call: {len(rows)}")

    region = fc.geometry().bounds()
    raw = (ic.filterBounds(region).mosaic()
           .setDefaultProjection(ee.Image(ic.filterBounds(region).first()).projection())
           .toFloat().rename("h"))
    stack = raw.addBands(raw.gt(0).rename("nz"))

    red = (ee.Reducer.mean()
           .combine(ee.Reducer.max(), sharedInputs=True)
           .combine(ee.Reducer.count(), sharedInputs=True))
    got = stack.reduceRegions(collection=fc, reducer=red,
                              scale=RING_SCALE, tileScale=4).getInfo()["features"]

    res = pd.DataFrame([f["properties"] for f in got])
    fld = df.set_index("plot_key")[["loreys_h_m", "crown_cover_pct", "district"]]

    for kind in ("ZERO", "CTRL"):
        sub = res[res.kind == kind]
        say("")
        say(f"  --- {kind} plots ---")
        for pk, g in sub.groupby("plot_key"):
            f = fld.loc[pk]
            say(f"  {pk}  {f.district}  loreys={f.loreys_h_m:.2f}m  "
                f"crown={f.crown_cover_pct:.0f}%")
            g = g.sort_values("radius")
            head = "      " + "".join(f"{int(x):>9}m" for x in g.radius)
            say(head)
            say("      max   " + "".join(f"{v:>9.1f}" for v in g.h_max))
            say("      mean  " + "".join(f"{v:>9.2f}" for v in g.h_mean))
            say("      nz%   " + "".join(f"{100 * v:>9.1f}" for v in g.nz_mean))
            say("      npix  " + "".join(f"{int(v):>9}" for v in g.h_count))

    say("")
    z = res[res.kind == "ZERO"]
    c = res[res.kind == "CTRL"]
    say("  Summary across the ladder:")
    say(f"  {'radius':>8} {'ZERO max':>10} {'ZERO mean':>10} {'ZERO nz%':>9}   "
        f"{'CTRL max':>10} {'CTRL mean':>10} {'CTRL nz%':>9}")
    for rad in RADII_M:
        zr, cr = z[z.radius == rad], c[c.radius == rad]
        say(f"  {rad:>7}m {zr.h_max.max():>10.1f} {zr.h_mean.mean():>10.2f} "
            f"{100 * zr.nz_mean.mean():>9.1f}   "
            f"{cr.h_max.max():>10.1f} {cr.h_mean.mean():>10.2f} "
            f"{100 * cr.nz_mean.mean():>9.1f}")
    say("")
    say("  How to read it. The controls are the positive control: they must carry canopy at")
    say("  every radius, and if they do the ladder is measuring what it claims. For the zero")
    say("  plots, an offset of magnitude d predicts near-zero readings while the disc is")
    say("  smaller than d and real canopy appearing once it exceeds d. A ladder that stays")
    say("  flat and near zero out to 500 m is not consistent with an offset of ANY magnitude,")
    say("  and closes RECOVERABLE.")

    # ---------------------------------------------------------------- B. band identity
    rule("B — band identity: is `cover_code` a height field or a class code?")
    pts = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([float(r.lon), float(r.lat)]), {})
        for r in df.itertuples()])
    hist_region = pts.geometry().buffer(HIST_BUFFER_M)
    say(f"  region: the union of {len(df)} discs of {HIST_BUFFER_M} m, read at "
        f"scale={HIST_SCALE} m")

    hraw = (ic.filterBounds(hist_region).mosaic()
            .setDefaultProjection(
                ee.Image(ic.filterBounds(hist_region).first()).projection())
            .toFloat().rename("h"))
    h = hraw.reduceRegion(
        reducer=ee.Reducer.frequencyHistogram(), geometry=hist_region,
        scale=HIST_SCALE, maxPixels=1_000_000_000, bestEffort=False,
        tileScale=4).getInfo()["h"]

    hist = sorted((float(k), float(v)) for k, v in h.items())
    total = sum(v for _, v in hist)
    say(f"  distinct values present: {len(hist)}")
    say(f"  value range: {hist[0][0]:.0f} .. {hist[-1][0]:.0f}")
    say(f"  total pixels: {total:,.0f}")
    say("")
    say(f"  {'value':>6} {'pixels':>14} {'share':>8}  {'cumulative':>10}")
    cum = 0.0
    for val, cnt in hist:
        cum += cnt
        bar = "#" * int(60 * cnt / max(c for _, c in hist))
        say(f"  {val:>6.0f} {cnt:>14,.0f} {100 * cnt / total:>7.2f}% "
            f"{100 * cum / total:>9.2f}%  {bar}")
    say("")
    nonzero = [(v, c) for v, c in hist if v > 0]
    gaps = [int(a[0]) for a, b in zip(hist, hist[1:], strict=False) if b[0] - a[0] > 1]
    say(f"  zero pixels: {100 * dict(hist).get(0.0, 0) / total:.1f}% of the region")
    say(f"  contiguous integer support (no interior gaps): {not gaps}"
        + (f"   gaps after: {gaps}" if gaps else ""))
    if nonzero:
        nz_total = sum(c for _, c in nonzero)
        wmean = sum(v * c for v, c in nonzero) / nz_total
        say(f"  non-zero mean: {wmean:.2f}   non-zero max: {nonzero[-1][0]:.0f}")
    say("")
    say("  A height field in metres gives contiguous integer support with a broad, ordered,")
    say("  roughly unimodal shape. A categorical cover code gives a few spikes on arbitrary")
    say("  integers with empty space between them.")

    rule("What this settles")
    say("  NO DATA was already closed by step 7 part B: 1 intersecting image, masked=0,")
    say("  mask()==1 at every zero plot. Section A above is what closes RECOVERABLE, and")
    say("  section B is what licenses reading the band as metres in the first place.")
    say("")
    say("  The verdict itself is NOT recorded here or in PHASE1_STATUS.md. It is a")
    say("  supervisory call, and it is made from the evidence above.")

    with open(OUT, "w") as f:
        f.write("\n".join(_out) + "\n")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
