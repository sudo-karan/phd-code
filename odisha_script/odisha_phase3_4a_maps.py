"""Phase 3 summary deck, map figures: where the plots are, what a stand looks like, how the method works.

Three figures from the real data, for the Phase 3 summary slides:

  study_area.png          Odisha, the four districts' field plots coloured by district, plus one
                          satellite close-up per district with its village forests (study areas)
                          outlined. Message: 274 plots in 20 village forests across 4 districts.
  stand_view_10_vs_3.png  One village forest (Jogi Bandha, Angul) on satellite imagery, twice: the
                          stands drawn with the 10 hectare ceiling (left) and the 3 hectare ceiling
                          (right), field plots as dots coloured by their structural forest type.
  method_steps.png        A ~650 m crop of the same village forest in four steps using the 3 hectare
                          arm: satellite image, small patches (SNIC superpixels), patches joined into
                          stands, stands filled by their automatic (k-means) type.

Why Jogi Bandha (Angul): 10 field plots of three structural types, mostly continuous forest canopy
visible in the imagery, and the two ceilings differ as much as anywhere in the data -- the 10 plots
fall in 2 stands at 10 hectares and in 6 stands at 3 hectares. The 650 m method crop is centred on
the mean of its plots, where the 3 hectare stands cover 99% of the crop and 4 automatic types occur.

Everything is reprojected to Web Mercator (EPSG:3857) to sit on the Esri tiles. Scale bars are drawn in
true ground metres (Web Mercator units shrunk by cos(latitude)). As a check that plots and stands are
in the same frame, each plot's containing stand polygon (point-in-polygon, in EPSG:3857) is compared
with the stand label (stand_lbl) the join wrote to the plots table; any mismatch stops the script.

State outlines (study_area only) come from Natural Earth 1:50m admin-1, downloaded once into a temp
cache. Satellite tiles are fetched by contextily (network needed on first run).

Usage:  python odisha_script/odisha_phase3_4a_maps.py
Output: odisha_script/phase3_figures/{study_area,stand_view_10_vs_3,method_steps}.png
"""
from __future__ import annotations

import sys
import tempfile
import urllib.request
from pathlib import Path

import contextily as cx
import geopandas as gpd
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from shapely.geometry import box

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import phase3_figstyle as st  # noqa: E402

VEC = HERE / "phase2_vectors"
AOI = ROOT / "aois"
DISTRICTS = ["angul", "dhenkanal", "kendujhar", "koraput"]
MERC = 3857
ESRI = cx.providers.Esri.WorldImagery

# District colours: blue, orange, violet, aqua from the dataviz reference palette. Checked with the
# dataviz validator (--pairs all, light): CVD worst 9.2, normal-vision worst 16.3, all hard checks pass.
# Every district is also named in text next to its dots, so colour is never the only cue.
DISTRICT_COLOUR = {"angul": "#2a78d6", "dhenkanal": "#eb6834", "kendujhar": "#4a3aa7", "koraput": "#1baf7a"}

# Automatic stand types: a neutral categorical set kept away from the field-type greens. Only the
# types present in the method crop get a colour, in cluster-id order. blue, yellow, magenta, violet
# pass the validator all-pairs (CVD worst 13.0, normal-vision worst 16.3); stand outlines separate
# neighbouring fills as a second cue.
AUTO_TYPE_COLOURS = ["#2a78d6", "#eda100", "#e87ba4", "#4a3aa7"]

FEATURE_VILLAGE = ("ANGUL", "JOGI BANDHA")
METHOD_CROP_M = 650.0

NE_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
          "ne_50m_admin_1_states_provinces.geojson")
NE_CACHE = Path(tempfile.gettempdir()) / "phase3_maps_cache" / "ne_50m_admin_1_states_provinces.geojson"

HALO = [pe.withStroke(linewidth=3, foreground="white")]
DARK_HALO = [pe.withStroke(linewidth=2.6, foreground="#111111")]


# ---------------------------------------------------------------------- data
def load_plots() -> gpd.GeoDataFrame:
    p10 = pd.read_csv(HERE / "phase2_plots_joined_districts.csv")
    p3 = pd.read_csv(HERE / "phase3_3ha" / "phase2_plots_joined_districts.csv",
                     usecols=["plot_key", "v120_3ha_merged_id", "v120_3ha_snic_id"])
    ft = pd.read_csv(HERE / "odisha_phase3_0_field_types.csv", usecols=["plot_key", "field_type"])
    p = p10.merge(p3, on="plot_key", how="left", validate="1:1").merge(ft, on="plot_key", how="left",
                                                                         validate="1:1")
    assert len(p) == 274, len(p)
    p["dist"] = p["district"].str.lower()
    return gpd.GeoDataFrame(p, geometry=gpd.points_from_xy(p.lon6, p.lat6), crs=4326).to_crs(MERC)


def load_stands(arm: str, district: str, kind: str) -> gpd.GeoDataFrame:
    tag = {"v120": "handcrafted", "v120_3ha": "3ha"}[arm]
    g = gpd.read_file(VEC / f"odisha_v120_{tag}_{district}_stands_{kind}.geojson").to_crs(MERC)
    g["type_id"] = g["cluster_id"].round().astype("Int64")      # stored as floats like 2.9999999
    return g


def load_village_forests(plots: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """One row per study-area part, named after the habitation with most plots inside it."""
    rows = []
    for d in DISTRICTS:
        geom = gpd.read_file(AOI / f"odisha_habitations_{d}.geojson").to_crs(MERC).geometry.iloc[0]
        parts = list(getattr(geom, "geoms", [geom]))
        for poly in parts:
            inside = plots[(plots.dist == d) & plots.within(poly)]
            name = inside.habitation.mode().iloc[0] if len(inside) else None
            rows.append({"dist": d, "habitation": name, "n_plots": len(inside), "geometry": poly})
    vf = gpd.GeoDataFrame(rows, crs=MERC)
    return vf


def check_alignment(plots: gpd.GeoDataFrame) -> None:
    """Each plot's containing stand polygon must be the stand the join recorded for it."""
    for arm, col in [("v120", "v120_merged_id"), ("v120_3ha", "v120_3ha_merged_id")]:
        bad = n = 0
        for d in DISTRICTS:
            s = load_stands(arm, d, "merged")
            pts = plots[(plots.dist == d) & plots[col].notna()]
            j = gpd.sjoin(pts[[col, "geometry"]], s[["stand_lbl", "geometry"]], predicate="within",
                          how="left")
            j = j[~j.index.duplicated()]
            n += len(j)
            bad += int((j["stand_lbl"].astype("float") != j[col].astype("float")).sum())
        print(f"alignment {arm}: {n} plots in stands, {bad} whose containing polygon disagrees with the join")
        if bad:
            raise SystemExit("plots and stand polygons are not in the same frame")


# ---------------------------------------------------------------------- helpers
def ground_to_merc(metres: float, lat_deg: float) -> float:
    """Web Mercator units for a ground distance at this latitude."""
    return metres / np.cos(np.radians(lat_deg))


def centre_lat(ax) -> float:
    y = np.mean(ax.get_ylim())
    return float(gpd.GeoSeries(gpd.points_from_xy([0], [y]), crs=MERC).to_crs(4326).y.iloc[0])


def scale_bar(ax, metres: float, label: str, on_image: bool = True, loc: str = "lower left") -> None:
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    L = ground_to_merc(metres, centre_lat(ax))
    w, h = x1 - x0, y1 - y0
    if loc == "lower left":
        bx, by = x0 + 0.05 * w, y0 + 0.07 * h
    else:  # lower right
        bx, by = x1 - 0.05 * w - L, y0 + 0.07 * h
    fg, halo = ("white", DARK_HALO) if on_image else (st.INK, HALO)
    ax.plot([bx, bx + L], [by, by], color=fg, lw=3, solid_capstyle="butt", zorder=20,
            path_effects=[pe.Stroke(linewidth=5, foreground="#111111" if on_image else "white"), pe.Normal()])
    tx, ha = (bx, "left") if loc == "lower left" else (bx + L, "right")
    ax.text(tx, by + 0.025 * h, label, ha=ha, va="bottom", fontsize=12, color=fg,
            zorder=20, path_effects=halo)


def fit_extent(ax, bounds, pad_frac: float = 0.08, min_half: float = 0.0) -> None:
    """Centre bounds in the axes at the axes' own aspect (equal scale)."""
    x0, y0, x1, y1 = bounds
    cxm, cym = (x0 + x1) / 2, (y0 + y1) / 2
    hw, hh = max((x1 - x0) / 2, min_half), max((y1 - y0) / 2, min_half)
    hw, hh = hw * (1 + pad_frac), hh * (1 + pad_frac)
    bb = ax.get_position()
    fw, fh = ax.figure.get_size_inches()
    aspect = (bb.height * fh) / (bb.width * fw)          # height / width of the axes box
    if hh / hw > aspect:
        hw = hh / aspect
    else:
        hh = hw * aspect
    ax.set_xlim(cxm - hw, cxm + hw)
    ax.set_ylim(cym - hh, cym + hh)
    ax.set_aspect("equal", adjustable="box")


def bare(ax) -> None:
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def imagery(ax, zoom) -> None:
    cx.add_basemap(ax, source=ESRI, zoom=zoom, attribution=False, reset_extent=True)


def panel_label(ax, text: str, sub: str | None = None, on_image: bool = True) -> None:
    fg, halo = ("white", DARK_HALO) if on_image else (st.INK, HALO)
    ax.text(0.03, 0.97, text, transform=ax.transAxes, ha="left", va="top", fontsize=14,
            fontweight="bold", color=fg, path_effects=halo, zorder=25)
    if sub:
        ax.text(0.03, 0.885, sub, transform=ax.transAxes, ha="left", va="top", fontsize=12.5,
                color=fg, path_effects=halo, zorder=25)


# ---------------------------------------------------------------------- figure 1
def ne_states() -> gpd.GeoDataFrame:
    if not NE_CACHE.exists():
        NE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(NE_URL, NE_CACHE)
    g = gpd.read_file(NE_CACHE)
    return g[g["admin"] == "India"].to_crs(MERC)


def fig_study_area(plots: gpd.GeoDataFrame, vf: gpd.GeoDataFrame) -> Path:
    states = ne_states()
    odisha = states[states["name"] == "Odisha"]
    fig = plt.figure(figsize=(st.FULL[0], 5.6))
    gs = fig.add_gridspec(2, 3, width_ratios=[1.28, 1, 1], wspace=0.06, hspace=0.20,
                          left=0.0, right=1.0, top=0.93, bottom=0.07)

    # ---- left: Odisha overview (vector only, no tiles)
    ax = fig.add_subplot(gs[:, 0])
    ax.set_facecolor("#E4ECF1")                                     # sea
    fit_extent(ax, odisha.total_bounds, pad_frac=0.10)
    states.plot(ax=ax, color="#EEEEEA", edgecolor="#B9BDB7", lw=0.6, zorder=1)
    odisha.plot(ax=ax, color="white", edgecolor=st.INK, lw=1.1, zorder=2)
    for name, (lon, lat) in {"Chhattisgarh": (82.0, 22.3), "Jharkhand": (85.3, 22.85),
                             "West Bengal": (87.35, 22.75), "Andhra Pradesh": (82.4, 17.75)}.items():
        x, y = gpd.GeoSeries(gpd.points_from_xy([lon], [lat]), crs=4326).to_crs(MERC).iloc[0].coords[0]
        ax.text(x, y, name, fontsize=11, color=st.MUTE, style="italic", ha="center", va="center", zorder=3)
    bx, by = gpd.GeoSeries(gpd.points_from_xy([86.9], [19.4]), crs=4326).to_crs(MERC).iloc[0].coords[0]
    ax.text(bx, by, "Bay of\nBengal", fontsize=11, color="#6C8595", style="italic", ha="center", zorder=3)
    ox, oy = gpd.GeoSeries(gpd.points_from_xy([84.0], [19.95]), crs=4326).to_crs(MERC).iloc[0].coords[0]
    ax.text(ox, oy, "ODISHA", fontsize=13, color=st.MUTE, ha="center", fontweight="bold", zorder=3,
            alpha=0.8)
    for d in DISTRICTS:
        q = plots[plots.dist == d]
        ax.scatter(q.geometry.x, q.geometry.y, s=26, color=DISTRICT_COLOUR[d], edgecolor="white", lw=0.5,
                   zorder=5)
    # district names beside their dots (offsets in degrees, chosen by eye so labels do not collide)
    lab = {"angul": (-0.75, -0.05, "right"), "dhenkanal": (0.40, -0.35, "left"),
           "kendujhar": (0.35, 0.25, "left"), "koraput": (0.28, -0.05, "left")}
    for d, (dx, dy, ha) in lab.items():
        q = plots[plots.dist == d]
        lon, lat = q.lon6.mean(), q.lat6.mean()
        x0, y0 = gpd.GeoSeries(gpd.points_from_xy([lon], [lat]), crs=4326).to_crs(MERC).iloc[0].coords[0]
        x1, y1 = gpd.GeoSeries(gpd.points_from_xy([lon + dx], [lat + dy]), crs=4326).to_crs(MERC).iloc[0].coords[0]
        ax.annotate(st.DISTRICT_NAME[d], (x0, y0), (x1, y1), ha=ha, va="center", fontsize=13,
                    fontweight="bold", color=st.INK, zorder=6, path_effects=HALO,
                    arrowprops=dict(arrowstyle="-", color=st.MUTE, lw=0.8, shrinkA=2, shrinkB=4))
    scale_bar(ax, 100_000, "100 kilometres", on_image=False, loc="lower right")
    bare(ax)
    for s in ax.spines.values():
        s.set_visible(True)
        s.set_color(st.RULE)

    # ---- right: one satellite close-up per district
    pos = {"kendujhar": gs[0, 1], "dhenkanal": gs[0, 2], "angul": gs[1, 1], "koraput": gs[1, 2]}
    bar = {"kendujhar": (500, "500 metres"), "dhenkanal": (10_000, "10 kilometres"),
           "angul": (2_000, "2 kilometres"), "koraput": (2_000, "2 kilometres")}
    for d, g in pos.items():
        a = fig.add_subplot(g)
        q = plots[plots.dist == d]
        v = vf[vf.dist == d]
        inside = q[q.within(v.union_all())]
        outside = q.drop(inside.index)
        b = np.array([min(q.total_bounds[0], v.total_bounds[0]), min(q.total_bounds[1], v.total_bounds[1]),
                      max(q.total_bounds[2], v.total_bounds[2]), max(q.total_bounds[3], v.total_bounds[3])])
        fit_extent(a, b, pad_frac=0.18, min_half=900)
        imagery(a, "auto")
        v.boundary.plot(ax=a, color="white", lw=1.4, zorder=4)
        a.scatter(inside.geometry.x, inside.geometry.y, s=16, color=DISTRICT_COLOUR[d], edgecolor="white",
                  lw=0.5, zorder=5)
        if len(outside):
            a.scatter(outside.geometry.x, outside.geometry.y, s=16, facecolor="none",
                      edgecolor="white", lw=1.0, zorder=5)
        nv = len(v)
        a.text(0.0, 1.03, st.DISTRICT_NAME[d], transform=a.transAxes, ha="left", va="bottom",
               fontsize=14, fontweight="bold", color=st.INK)
        a.text(1.0, 1.03, f"{len(q)} plots, {nv} village forest{'s' if nv > 1 else ''}",
               transform=a.transAxes, ha="right", va="bottom", fontsize=12.5, color=st.INK)
        scale_bar(a, *bar[d], loc="lower right")
        bare(a)
        a.patch.set_edgecolor(DISTRICT_COLOUR[d])
        for s in a.spines.values():
            s.set_visible(True)
            s.set_color(DISTRICT_COLOUR[d])
            s.set_linewidth(3)

    handles = [Line2D([], [], ls="none", marker="o", ms=7, mfc="#888888", mec="white", label="field plot"),
               Line2D([], [], ls="none", marker="o", ms=7, mfc="none", mec="#555555",
                      label="field plot outside the village forests (7 plots)"),
               Line2D([], [], color="#555555", lw=1.4, label="village forest (study area) outline")]
    fig.legend(handles=handles, loc="lower right", bbox_to_anchor=(1.0, -0.005), ncol=3, fontsize=11.5,
               handletextpad=0.4, columnspacing=1.2)
    fig.text(0.0, 0.035, "State outlines: Natural Earth.", fontsize=9, color=st.MUTE, ha="left", va="top")
    fig.text(0.0, 0.005, st.ESRI_CREDIT, fontsize=9, color=st.MUTE, ha="left", va="top")
    return st.save(fig, "study_area")


# ---------------------------------------------------------------------- figure 2
def fig_stand_view(plots: gpd.GeoDataFrame, vf: gpd.GeoDataFrame) -> Path:
    dname, hab = FEATURE_VILLAGE
    d = dname.lower()
    part = vf[(vf.dist == d) & (vf.habitation == hab)]
    assert len(part) == 1
    poly = part.geometry.iloc[0]
    q = plots[(plots.district == dname) & (plots.habitation == hab)]
    n10 = q["v120_merged_id"].nunique()
    n3 = q["v120_3ha_merged_id"].nunique()
    print(f"stand view: {hab}: {len(q)} plots; {n10} stands at 10 hectares, {n3} at 3 hectares")

    fig = plt.figure(figsize=(st.FULL[0], 5.3))
    axes = [fig.add_axes([0.0, 0.0, 0.395, 1.0]), fig.add_axes([0.405, 0.0, 0.395, 1.0])]
    for ax, arm, n in zip(axes, ["v120", "v120_3ha"], [n10, n3]):
        s = load_stands(arm, d, "merged")
        s = s[s.intersects(poly)]
        fit_extent(ax, poly.bounds, pad_frac=0.06)
        imagery(ax, 17)
        s.boundary.plot(ax=ax, color="white", lw=1.0, alpha=0.9, zorder=4)
        for t in st.TYPE_ORDER:
            qq = q[q.field_type == t]
            ax.scatter(qq.geometry.x, qq.geometry.y, s=130, color=st.TYPE_COLOUR[t], edgecolor="white",
                       lw=1.6, zorder=6)
        panel_label(ax, st.ARM_NAME[arm], f"the {len(q)} plots fall in {n} stands")
        scale_bar(ax, 200, "200 metres", loc="lower left")
        bare(ax)

    present = [t for t in st.TYPE_ORDER if (q.field_type == t).any()]
    handles = [Line2D([], [], ls="none", marker="o", ms=11, mfc=st.TYPE_COLOUR[t], mec="#777777",
                      label=st.TYPE_NAME[t]) for t in st.TYPE_ORDER]
    handles += [Line2D([], [], color="#9A9A9A", lw=1.2, label="stand boundary")]
    leg = fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.81, 0.97), fontsize=12,
                     title="Field plot, forest type\nmeasured on the ground", title_fontsize=12.5,
                     alignment="left", labelspacing=0.8, handletextpad=0.5)
    leg.get_title().set_fontweight("bold")
    fig.text(0.81, 0.30, f"{hab.title()} village forest,\n{st.DISTRICT_NAME[d]} district.\n"
             f"Its plots cover {len(present)} of\nthe 5 forest types.", fontsize=11.5, color=st.MUTE, va="top")
    fig.text(0.81, 0.02, st.ESRI_CREDIT.replace(": ", ":\n", 1), fontsize=9, color=st.MUTE, va="bottom")
    return st.save(fig, "stand_view_10_vs_3")


# ---------------------------------------------------------------------- figure 3
def fig_method_steps(plots: gpd.GeoDataFrame) -> Path:
    dname, hab = FEATURE_VILLAGE
    d = dname.lower()
    q = plots[(plots.district == dname) & (plots.habitation == hab)]
    lat = q.lat6.mean()
    cxm, cym = q.geometry.x.mean(), q.geometry.y.mean()
    half = ground_to_merc(METHOD_CROP_M / 2, lat)
    crop = box(cxm - half, cym - half, cxm + half, cym + half)
    snic = load_stands("v120_3ha", d, "snic")
    snic = snic[snic.intersects(crop)]
    merged = load_stands("v120_3ha", d, "merged")
    merged = merged[merged.intersects(crop)]
    cover = merged.intersection(crop).area.sum() / crop.area
    types = sorted(merged["type_id"].dropna().unique().tolist())
    assert len(types) <= len(AUTO_TYPE_COLOURS), types
    colour = {t: AUTO_TYPE_COLOURS[i] for i, t in enumerate(types)}
    print(f"method crop: {METHOD_CROP_M:.0f} m, {len(snic)} small patches, {len(merged)} stands, "
          f"cover {cover:.2f}, types {types}, untyped stands {int(merged.type_id.isna().sum())}")

    fig = plt.figure(figsize=(st.FULL[0], 3.95))
    w, gap = 0.2375, 0.0167
    axes = [fig.add_axes([i * (w + gap), 0.20, w, 0.80]) for i in range(4)]
    labels = ["1  Satellite image", "2  Small patches", "3  Joined into stands", "4  Stands given a type"]
    for i, ax in enumerate(axes):
        ax.set_xlim(crop.bounds[0], crop.bounds[2])
        ax.set_ylim(crop.bounds[1], crop.bounds[3])
        ax.set_aspect("equal")
        imagery(ax, 17)
        ax.set_xlim(crop.bounds[0], crop.bounds[2])
        ax.set_ylim(crop.bounds[1], crop.bounds[3])
        if i == 1:
            snic.boundary.plot(ax=ax, color="white", lw=0.7, alpha=0.95, zorder=4)
        if i == 2:
            snic.boundary.plot(ax=ax, color="white", lw=0.4, alpha=0.35, zorder=3)
            merged.boundary.plot(ax=ax, color="white", lw=1.5, zorder=4)
        if i == 3:
            for t in types:
                merged[merged.type_id == t].plot(ax=ax, color=colour[t], alpha=0.5, lw=0, zorder=3)
            merged.boundary.plot(ax=ax, color="white", lw=1.0, zorder=4)
        ax.set_xlim(crop.bounds[0], crop.bounds[2])
        ax.set_ylim(crop.bounds[1], crop.bounds[3])
        bare(ax)
        ax.text(0.0, -0.04, labels[i], transform=ax.transAxes, ha="left", va="top", fontsize=14,
                fontweight="bold", color=st.INK)
    scale_bar(axes[0], 200, "200 metres", loc="lower left")

    handles = [Patch(facecolor=colour[t], alpha=0.75, edgecolor="none", label=f"Type {int(t) + 1}")
               for t in types]
    if merged["type_id"].isna().any():
        handles.append(Patch(facecolor="white", edgecolor=st.MUTE, lw=0.8, label="no type given"))
    # Legend spans the width under panels 3 and 4, its title explaining what the colours mean.
    leg = axes[2].legend(handles=handles, loc="upper left", bbox_to_anchor=(0.0, -0.13), ncol=len(handles),
                         fontsize=12, handlelength=1.3, handletextpad=0.45, columnspacing=1.3,
                         borderaxespad=0, alignment="left", title_fontsize=12,
                         title=f"Colour in picture 4 = the type the computer gave each stand "
                               f"({len(types)} of its 6 types occur here)")
    leg.get_title().set_color(st.MUTE)
    axes[0].text(0.0, -0.15, f"The same {METHOD_CROP_M:.0f} × {METHOD_CROP_M:.0f} metre square of forest "
                 f"in all four pictures,\n{st.DISTRICT_NAME[d]} district. {st.ESRI_CREDIT}",
                 transform=axes[0].transAxes, ha="left", va="top", fontsize=9, color=st.MUTE)
    return st.save(fig, "method_steps")


def main() -> None:
    st.use()
    plots = load_plots()
    check_alignment(plots)
    vf = load_village_forests(plots)
    per = vf.groupby("dist").agg(village_forests=("geometry", "size"), plots_inside=("n_plots", "sum"))
    per["plots"] = plots.groupby("dist").size()
    print(per.to_string())
    print(f"total: {per.plots.sum()} plots, {per.village_forests.sum()} village forests, "
          f"{per.plots_inside.sum()} plots inside")
    assert per.plots.sum() == 274 and per.village_forests.sum() == 20 and per.plots_inside.sum() == 267
    for f in (fig_study_area(plots, vf), fig_stand_view(plots, vf), fig_method_steps(plots)):
        print("wrote", f.relative_to(ROOT))


if __name__ == "__main__":
    main()
