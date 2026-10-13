"""Phase 3 summary deck: the field-data figures.

Draws four figures for the summary slides, every number recomputed here from the
committed data rather than typed in:

  species_groups      grouping the plots by tree SPECIES collapses: 259 of 274
                      plots land in one group (same method as explain_field_types.py)
  structure_boxplots  the 5 forest types built from STRUCTURE (height, crown cover,
                      number of trees, trunk area), one box per type, every plot a dot
  elbow_field         how the number of field types (5) was chosen: the elbow method
  elbow_stands        the same method on the satellite features of the stands, for
                      both stand-size ceilings (10 and 3 hectares)

Before drawing, the recomputed numbers are checked against the committed results
files (odisha_phase3_0_results.txt, odisha_phase3_0_field_types.csv,
odisha_phase3_2_k_elbow_odisha_v120_handcrafted.txt); the script stops if they differ.

Run from the repo root:  python odisha_script/odisha_phase3_4b_field.py
Offline; no Earth Engine. Writes odisha_script/phase3_figures/<name>.png.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from sklearn.cluster import KMeans

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

import phase3_figstyle as st  # noqa: E402
import odisha_phase3_0_field_structure_types as fst  # noqa: E402
import odisha_phase3_2_stand_k_elbow as sel  # noqa: E402

st.use()

ARMS = [("odisha_v120_handcrafted", "v120"), ("odisha_v120_3ha", "v120_3ha")]
K_USED_FIELD = 5
K_USED_STANDS = 6


def plots() -> pd.DataFrame:
    return pd.read_csv(HERE / "phase2_plots_joined_districts.csv")


def trunk_area(p: pd.DataFrame) -> pd.Series:
    """Total trunk area (basal area, square centimetres) of all stems in the plot."""
    return p.sp_ba_json.map(lambda s: sum(json.loads(s).values()) if isinstance(s, str) else 0.0)


# ---------------------------------------------------------------------------
# 1. species groups -- exactly as explain_field_types.py
# ---------------------------------------------------------------------------
def species_groups(p: pd.DataFrame) -> pd.Series:
    rows = {k: json.loads(s) if isinstance(s, str) else {}
            for k, s in zip(p.plot_key, p.sp_ba_json)}
    mat = pd.DataFrame(rows).T.fillna(0.0)
    mat = mat.div(mat.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    a = mat.to_numpy()
    num = np.abs(a[:, None, :] - a[None, :, :]).sum(-1)
    den = (a[:, None, :] + a[None, :, :]).sum(-1)
    bc = num / den
    Z = linkage(squareform(bc, checks=False), method="average")
    return pd.Series(fcluster(Z, 6, criterion="maxclust"), index=mat.index)


def fig_species(p: pd.DataFrame, ftypes: pd.DataFrame) -> dict:
    t = species_groups(p)
    sizes = t.value_counts().sort_values(ascending=False)
    assert sizes.iloc[0] == 259 and len(t) == 274, sizes.to_dict()
    assert sizes.tolist() == [259, 11, 1, 1, 1, 1], sizes.tolist()

    # who are the 15 that broke away?
    odd = t[t != sizes.index[0]].index
    info = p.set_index("plot_key").loc[odd]
    ft = ftypes.set_index("plot_key").field_type.loc[odd]
    facts = {
        "n_odd": len(odd),
        "odd_scrub_type": int((ft == 2).sum()),
        "odd_no_trees": int((info.n_trees == 0).sum()),
        "odd_height_max": float(info.loreys_h_m.max()),
        "odd_height_median": float(info.loreys_h_m.median()),
        "odd_koraput": int((info.district == "KORAPUT").sum()),
    }

    fig, ax = plt.subplots(figsize=st.HALF)
    x = np.arange(len(sizes))
    cols = [st.AMBER] + [st.SLATE] * (len(sizes) - 1)
    ax.bar(x, sizes.values, width=0.62, color=cols, linewidth=0)
    ax.set_xticks(x, [f"Group {i + 1}" for i in x])
    ax.set_ylabel("Number of plots")
    ax.set_ylim(0, 300)
    ax.set_xlim(-0.6, len(sizes) - 0.4)
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    ax.text(-0.31, sizes.iloc[0] + 6, "259 of 274 plots", ha="left", va="bottom",
            fontsize=14, fontweight="bold", color=st.INK)
    for xi, v in zip(x[1:], sizes.values[1:]):
        ax.text(xi, v + 4, f"{v}", ha="center", va="bottom", fontsize=12, color=st.INK)
    ax.text(3.3, 150,
            "The other 15 plots are\nmostly scrub and bushes:\n"
            f"{facts['odd_scrub_type']} of the 15 fall in the scrub type,\n"
            f"and half are under {facts['odd_height_median']:.1f} metres tall",
            ha="center", va="center", fontsize=12, color=st.MUTE)
    st.save(fig, "species_groups")
    return {"sizes": sizes.tolist(), **facts}


# ---------------------------------------------------------------------------
# 2. structure box plots
# ---------------------------------------------------------------------------
def fig_boxplots(p: pd.DataFrame, ftypes: pd.DataFrame) -> dict:
    d = ftypes[["plot_key", "field_type"]].merge(
        p[["plot_key", "loreys_h_m", "crown_cover_pct", "n_trees", "sp_ba_json"]],
        on="plot_key", how="inner", validate="one_to_one")
    assert len(d) == 274
    d["trunk_area"] = trunk_area(d)

    panels = [
        ("loreys_h_m", "Average tree height (metres)", False),
        ("crown_cover_pct", "Crown cover (percent)", False),
        ("n_trees", "Number of trees in the plot", False),
        ("trunk_area", "Total trunk area in the plot\n(square centimetres, log scale)", True),
    ]
    counts = d.field_type.value_counts()
    rng = np.random.default_rng(7)
    # horizontal boxes so the type names read left to right, once, on the shared axis;
    # most forest at the top
    order = st.TYPE_ORDER
    ylabels = [f"{st.TYPE_SHORT[t]}\n({counts[t]} plots)" for t in order]

    fig, axes = plt.subplots(1, 4, figsize=(st.FULL[0], 5.0), sharey=True)
    for ax, (col, label, logx) in zip(axes, panels):
        data = [d.loc[d.field_type == t, col].to_numpy(float) for t in order]
        bp = ax.boxplot(data, positions=range(5), widths=0.62, patch_artist=True,
                        orientation="horizontal", showfliers=False, whis=1.5,
                        medianprops=dict(color=st.INK, linewidth=2.2),
                        whiskerprops=dict(color=st.MUTE, linewidth=1.2),
                        capprops=dict(color=st.MUTE, linewidth=1.2))
        for patch, t in zip(bp["boxes"], order):
            patch.set_facecolor(st.TYPE_COLOUR[t])
            patch.set_alpha(0.55)
            patch.set_edgecolor(st.TYPE_COLOUR[t])
            patch.set_linewidth(1.6)
        for i, v in enumerate(data):
            ax.scatter(v, i + rng.uniform(-0.2, 0.2, len(v)), s=9, color=st.INK,
                       alpha=0.4, linewidths=0, zorder=3)
        if logx:
            ax.set_xscale("log")
            ax.set_xticks([1, 100, 10000], ["1", "100", "10,000"])
        ax.set_xlabel(label)
        ax.xaxis.grid(True)
        ax.set_axisbelow(True)
        ax.set_ylim(-0.6, 4.6)
    axes[0].set_yticks(range(5), ylabels, fontsize=12)
    for ax in axes[1:]:
        ax.tick_params(axis="y", length=0)
    fig.tight_layout(w_pad=1.4)
    fig.text(0.5, -0.02, f"All {len(d)} field plots. Each dot is one plot; "
             "the box holds the middle half of the plots and the black line is the middle value.",
             ha="center", va="top", fontsize=11.5, color=st.MUTE)
    st.save(fig, "structure_boxplots")
    med = d.groupby("field_type")[["loreys_h_m", "crown_cover_pct", "n_trees", "trunk_area"]].median()
    return {"counts": {st.TYPE_SHORT[t]: int(counts[t]) for t in st.TYPE_ORDER},
            "medians": {st.TYPE_SHORT[t]: med.loc[t].round(1).to_dict() for t in st.TYPE_ORDER}}


# ---------------------------------------------------------------------------
# 3a. field elbow -- exactly as odisha_phase3_0_field_structure_types.py
# ---------------------------------------------------------------------------
def field_elbow(p: pd.DataFrame) -> tuple[pd.DataFrame, int, np.ndarray]:
    total_ba = trunk_area(p)
    feat = pd.DataFrame({
        "loreys_h_m": p.loreys_h_m.astype(float),
        "crown_cover_pct": p.crown_cover_pct.astype(float),
        "log_basal_area": np.log1p(total_ba.astype(float)),
        "n_trees": p.n_trees.astype(float),
    })
    X = fst.robust_scale(feat)
    rows = []
    for k in fst.K_RANGE:
        km = KMeans(n_clusters=k, random_state=fst.SEED, n_init=25).fit(X)
        rows.append({"k": k, "inertia": km.inertia_})
    res = pd.DataFrame(rows)
    ke = fst.knee(res.k.tolist(), res.inertia.tolist())
    labels = KMeans(n_clusters=ke, random_state=fst.SEED, n_init=25).fit(X).labels_
    return res, ke, labels


def check_field(res: pd.DataFrame, ke: int, labels: np.ndarray, p: pd.DataFrame,
                ftypes: pd.DataFrame) -> None:
    txt = (HERE / "odisha_phase3_0_results.txt").read_text()
    committed = {int(m[0]): float(m[1]) for m in
                 re.findall(r"^\s+(\d+)\s+([\d.]+)\s+[\d.]+\s+[\d.]+\s+[\d.]+\s*$", txt, re.M)}
    mine = {int(r.k): round(r.inertia, 1) for r in res.itertuples()}
    assert mine == committed, (mine, committed)
    assert f"elbow (knee of inertia)      k = {ke}" in txt
    assert ke == K_USED_FIELD
    ref = ftypes.set_index("plot_key").field_type.loc[p.plot_key].to_numpy()
    assert (ref == labels).all(), "field types differ from the committed CSV"


def elbow_index(inertia: np.ndarray) -> np.ndarray:
    """Spread relative to two groups (2 groups = 100). An affine rescale, so the
    knee -- the point farthest from the chord -- is unchanged."""
    return 100 * inertia / inertia[0]


def fig_field_elbow(res: pd.DataFrame, ke: int) -> dict:
    k = res.k.to_numpy()
    y = elbow_index(res.inertia.to_numpy())
    fig, ax = plt.subplots(figsize=st.HALF)
    ax.plot([k[0], k[-1]], [y[0], y[-1]], ls=(0, (4, 3)), color=st.CHANCE_EDGE, lw=1.4, zorder=1)
    ax.plot(k, y, color=st.FOREST, lw=2, marker="o", ms=7, zorder=2)
    i = int(np.where(k == ke)[0][0])
    # the gap to the chord at the chosen point
    ychord = y[0] + (y[-1] - y[0]) * (k[i] - k[0]) / (k[-1] - k[0])
    ax.plot([k[i], k[i]], [y[i], ychord], color=st.AMBER, lw=1.4, ls=":", zorder=1)
    ax.plot(k[i], y[i], "o", ms=15, mfc="none", mec=st.AMBER, mew=2.6, zorder=3)
    ax.annotate(f"The bend: {ke} groups\n(the number I used)", xy=(k[i], y[i]),
                xytext=(2.1, 30), fontsize=13, color=st.AMBER,
                fontweight="bold", va="center", ha="left",
                arrowprops=dict(arrowstyle="-", color=st.AMBER, lw=1.2))
    ax.text(9.2, 62, "Dashed line joins the two ends.\nThe bend is the point\nfarthest below it.",
            fontsize=11.5, color=st.MUTE, ha="center", va="bottom")
    ax.set_xticks(k)
    ax.set_xlabel("Number of groups")
    ax.set_ylabel("How spread out the groups still are\n(lower is tighter; 2 groups = 100)")
    ax.set_ylim(15, 108)
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    st.save(fig, "elbow_field")
    return {"index": dict(zip(k.tolist(), np.round(y, 1).tolist()))}


# ---------------------------------------------------------------------------
# 3b. stand elbow -- exactly as odisha_phase3_2_stand_k_elbow.py, both arms
# ---------------------------------------------------------------------------
def stand_elbows() -> dict:
    out = {}
    for arm, key in ARMS:
        sel._lines.clear()
        per = sel.load(arm)
        assert set(per) == set(st.DISTRICT_NAME), (arm, list(per))
        feats = sorted(set.intersection(*[set(v.columns) for v in per.values()]) - sel.DROP)
        dist = {}
        for d, df in per.items():
            X, _ = sel.prep(df[feats])
            dist[d] = sel.sweep(X, d)
        Xall, _ = sel.prep(pd.concat([v[feats] for v in per.values()], ignore_index=True))
        pooled = sel.sweep(Xall, "pooled")
        elbows = [r["elbow"] for r in dist.values()]
        out[key] = {"arm": arm, "n_feats": len(feats), "districts": dist, "pooled": pooled,
                    "median_rule": int(round(float(np.median(elbows + [pooled["elbow"]]))))}
    return out


def check_stands(se: dict) -> None:
    txt = (HERE / "odisha_phase3_2_k_elbow_odisha_v120_handcrafted.txt").read_text()
    r = se["v120"]
    for d, res in r["districts"].items():
        m = re.search(rf"^\s+{d}\s+n=\s*(\d+)\s+elbow k=(\d+)", txt, re.M)
        assert m and int(m[1]) == res["n"] and int(m[2]) == res["elbow"], (d, res["elbow"])
    m = re.search(r"^\s+pooled\s+n=\s*(\d+)\s+elbow k=(\d+)", txt, re.M)
    assert int(m[1]) == r["pooled"]["n"] and int(m[2]) == r["pooled"]["elbow"]
    committed = {int(a): float(b) for a, b in
                 re.findall(r"^\s+(\d+)\s+([\d.]+)\s+[\d.]+\s+[\d.]+\s+[\d.]+\s*$", txt, re.M)}
    mine = {int(x.k): round(x.inertia, 1) for x in r["pooled"]["table"].itertuples()}
    assert mine == committed, (mine, committed)
    assert f"median across district and pooled elbows: k = {r['median_rule']}" in txt


def fig_stand_elbow(se: dict) -> None:
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(st.FULL[0], 5.1),
                                 gridspec_kw=dict(width_ratios=[1.0, 1.05]))
    marker = {"v120": "s", "v120_3ha": "o"}

    # left: the pooled curves, both arms, indexed to 2 groups = 100
    for key in ("v120", "v120_3ha"):
        tab = se[key]["pooled"]["table"]
        k = tab.k.to_numpy()
        y = elbow_index(tab.inertia.to_numpy())
        a1.plot(k, y, color=st.ARM_COLOUR[key], lw=2, marker=marker[key], ms=6.5,
                label=st.ARM_NAME[key])
        ke = se[key]["pooled"]["elbow"]
        i = int(np.where(k == ke)[0][0])
        a1.plot(k[i], y[i], marker[key], ms=15, mfc="none", mec=st.ARM_COLOUR[key], mew=2.2)
    a1.axvline(K_USED_STANDS, color=st.AMBER, lw=1.8, ls=(0, (5, 3)), zorder=0)
    a1.text(K_USED_STANDS + 0.15, 99, f"{K_USED_STANDS} types used\nin the stand maps",
            color=st.AMBER, fontsize=12, fontweight="bold", va="top")
    a1.annotate("Both curves bend\nat 5 (circled)", xy=(4.9, 65.5), xytext=(2.2, 56),
                fontsize=12, color=st.INK,
                arrowprops=dict(arrowstyle="-", color=st.MUTE, lw=1.1))
    a1.set_xticks(range(2, 13))
    a1.set_xlabel("Number of groups")
    a1.set_ylabel("How spread out the groups still are\n(lower is tighter; 2 groups = 100)")
    a1.set_ylim(40, 104)
    a1.yaxis.grid(True)
    a1.set_axisbelow(True)
    a1.legend(loc="upper right", bbox_to_anchor=(1.0, 0.84), fontsize=12, handlelength=2.2)

    # right: where each curve bends, per district and pooled
    rows = [(d, st.DISTRICT_NAME[d]) for d in st.DISTRICT_NAME] + [("pooled", "All four\ndistricts together")]
    off = {"v120": -0.15, "v120_3ha": 0.15}
    for j, (d, name) in enumerate(rows):
        a2.axhline(j, color=st.RULE, lw=0.8, zorder=0)
        for key in ("v120", "v120_3ha"):
            r = se[key]["pooled"] if d == "pooled" else se[key]["districts"][d]
            a2.plot(r["elbow"], j + off[key], marker[key], ms=11, color=st.ARM_COLOUR[key],
                    mec="white", mew=1.5, zorder=3)
    a2.axvline(K_USED_STANDS, color=st.AMBER, lw=1.8, ls=(0, (5, 3)), zorder=1)
    a2.set_yticks(range(len(rows)), [n for _, n in rows])
    a2.set_ylim(len(rows) - 0.4, -0.6)
    a2.set_xlim(3.5, 10.6)
    a2.set_xticks(range(4, 11))
    a2.set_xlabel("Number of groups where the curve bends")
    a2.axhline(len(rows) - 1.5, color=st.MUTE, lw=1.0)
    handles = [Line2D([], [], ls="none", marker=marker[k], ms=10, color=st.ARM_COLOUR[k],
                      label=st.ARM_NAME[k]) for k in ("v120", "v120_3ha")]
    handles.append(Line2D([], [], color=st.AMBER, lw=1.8, ls=(0, (5, 3)),
                          label=f"{K_USED_STANDS} types used"))
    a2.legend(handles=handles, loc="upper right", fontsize=12, borderaxespad=0.3)
    a2.spines["left"].set_visible(False)
    a2.tick_params(axis="y", length=0, labelsize=12.5)
    fig.tight_layout(w_pad=3.0)
    st.save(fig, "elbow_stands")


def main() -> int:
    p = plots()
    ftypes = pd.read_csv(HERE / "odisha_phase3_0_field_types.csv")
    report: dict = {}

    report["species"] = fig_species(p, ftypes)
    report["boxplots"] = fig_boxplots(p, ftypes)

    res, ke, labels = field_elbow(p)
    check_field(res, ke, labels, p, ftypes)
    report["field_elbow"] = {"k": ke, **fig_field_elbow(res, ke)}
    print("field elbow: matches odisha_phase3_0_results.txt and the field-types CSV")

    se = stand_elbows()
    check_stands(se)
    print("stand elbow (10 hectare arm): matches odisha_phase3_2_k_elbow_odisha_v120_handcrafted.txt")
    fig_stand_elbow(se)
    report["stand_elbow"] = {
        key: {"districts": {d: r["elbow"] for d, r in v["districts"].items()},
              "stands": {d: r["n"] for d, r in v["districts"].items()},
              "pooled": v["pooled"]["elbow"], "pooled_n": v["pooled"]["n"],
              "median_rule": v["median_rule"],
              "pooled_index": dict(zip(v["pooled"]["table"].k.tolist(),
                                       np.round(elbow_index(v["pooled"]["table"].inertia.to_numpy()), 1).tolist()))}
        for key, v in se.items()}

    print(json.dumps(report, indent=1, default=str))
    three = report["stand_elbow"]["v120_3ha"]
    if three["pooled"] != K_USED_STANDS or any(v != K_USED_STANDS for v in three["districts"].values()):
        print(f"\n*** NOTE: the 3 hectare stands' own elbow does NOT land on {K_USED_STANDS}: "
              f"districts {three['districts']}, pooled {three['pooled']}, "
              f"median rule {three['median_rule']}. ***")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
