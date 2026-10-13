"""Phase 3, step 4c: how big are the small patches and the stands?

Two figures for the summary deck, drawn from the exported vector layers (real data,
all four districts):

  patch_sizes  -- why the forest had to be cut more finely for a 3 hectare ceiling.
                  Stands are built by joining small patches (superpixels) and a patch
                  is never split, so no stand can be smaller than its biggest patch.
                  At the original spacing (patch centres ~100 m apart, SNIC size 10)
                  some single patches are already bigger than 3 hectares; at the finer
                  spacing (~60 m, SNIC size 6) none are.
  stand_sizes  -- the stands themselves, for the 10 hectare and the 3 hectare ceiling:
                  pooled histograms (left) and one box per district (right).

WHAT IS COUNTED
  * A stand or a patch can be exported as several polygons (a piece cut off by the
    habitat mask). Areas are summed over pieces first, so every count here is of
    PATCHES (grouped by `snic_label`) and STANDS (grouped by `stand_lbl`), not of
    polygons. `stand_lbl` is the stand key: its unique count matches n_stands in the
    run.json export manifests (`stand_id` is a per-polygon row number). Polygon counts
    are printed alongside for reference.
  * `area_ha` is the polygon's own area (checked against n_pixels x 0.01 and against
    an equal-area reprojection when this script was written).
  * Every stand in each district's study areas is counted, not only stands holding
    a field plot.

Run from the repo root:
    .venv/bin/python odisha_script/odisha_phase3_4c_sizes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).parent))
import phase3_figstyle as st  # noqa: E402

VEC = Path(__file__).parent / "phase2_vectors"
DISTRICTS = ["angul", "dhenkanal", "kendujhar", "koraput"]
ARMS = {"v120": "odisha_v120_handcrafted", "v120_3ha": "odisha_v120_3ha"}
ARM_ORDER = ["v120", "v120_3ha"]
SPACING = {"v120": "Original cutting: patch centres about 100 metres apart",
           "v120_3ha": "Finer cutting: patch centres about 60 metres apart"}
CEILING = {"v120": 10.0, "v120_3ha": 3.0}


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (patches, stands, polygon_counts), areas summed over pieces."""
    patches, stands, polys = [], [], []
    for arm, prefix in ARMS.items():
        for d in DISTRICTS:
            s = gpd.read_file(VEC / f"{prefix}_{d}_stands_snic.geojson")
            m = gpd.read_file(VEC / f"{prefix}_{d}_stands_merged.geojson")
            p = s.groupby("snic_label").area_ha.sum().rename("area_ha").reset_index()
            t = m.groupby("stand_lbl").area_ha.sum().rename("area_ha").reset_index()
            patches.append(p.assign(arm=arm, district=d))
            stands.append(t.assign(arm=arm, district=d))
            polys.append(dict(arm=arm, district=d,
                              patch_polygons=len(s), patch_polygons_over_3=int((s.area_ha > 3).sum()),
                              stand_polygons=len(m), stand_polygons_over_3=int((m.area_ha > 3).sum())))
    return pd.concat(patches), pd.concat(stands), pd.DataFrame(polys)


def report(patches: pd.DataFrame, stands: pd.DataFrame, polys: pd.DataFrame) -> None:
    def rows(df, what):
        out = []
        for arm in ARM_ORDER:
            for d in DISTRICTS + ["all four"]:
                a = df[(df.arm == arm) & ((df.district == d) | (d == "all four"))].area_ha
                over3 = int((a > 3).sum())
                r = dict(arm=st.ARM_NAME[arm] if what == "stands" else SPACING[arm].split(":")[0],
                         district=st.DISTRICT_NAME.get(d, d), n=len(a),
                         median_ha=round(a.median(), 2), largest_ha=round(a.max(), 2),
                         over_3ha=over3, over_3ha_pct=round(100 * over3 / len(a), 1))
                if what == "stands":
                    r["over_10ha"] = int((a > 10).sum())
                    r["under_1ha"] = int((a < 1).sum())
                out.append(r)
        return pd.DataFrame(out)

    pd.set_option("display.width", 200)
    print("\nSMALL PATCHES (counted as patches: pieces with the same snic_label summed)")
    print(rows(patches, "patches").to_string(index=False))
    print("\nSTANDS (counted as stands: pieces with the same stand_lbl summed)")
    print(rows(stands, "stands").to_string(index=False))
    print("\nPOLYGON COUNTS (features in the exported files, for reference)")
    tot = polys.groupby("arm")[polys.columns[2:]].sum().reset_index().assign(district="all four")
    print(pd.concat([polys, tot]).to_string(index=False))
    for arm in ARM_ORDER:
        a = stands[stands.arm == arm].area_ha
        cap = CEILING[arm]
        over = a[a > cap]
        print(f"\n{st.ARM_NAME[arm]}: {len(over)} of {len(a)} stands exceed the {cap:g} hectare "
              f"ceiling, by at most {over.max() - cap:.3f} hectares" if len(over) else "")


def _row_label(ax, text, n_text):
    ax.text(0.995, 0.93, text, transform=ax.transAxes, ha="right", va="top",
            fontsize=13, color=st.INK, fontweight="bold")
    ax.text(0.995, 0.93 - 0.17, n_text, transform=ax.transAxes, ha="right", va="top",
            fontsize=12, color=st.MUTE)


def fig_patch_sizes(patches: pd.DataFrame) -> Path:
    bins = np.arange(0, 7.01, 0.1)
    fig, axes = plt.subplots(2, 1, figsize=(st.FULL[0], 5.4), sharex=True,
                             gridspec_kw=dict(hspace=0.28))
    for ax, arm in zip(axes, ARM_ORDER):
        a = patches[patches.arm == arm].area_ha.to_numpy()
        colour = st.ARM_COLOUR[arm]
        counts, edges = np.histogram(a, bins=bins)
        centres = edges[:-1]
        over = centres >= 3.0 - 1e-9
        ax.bar(centres[~over], counts[~over], width=0.1, align="edge", color=colour,
               edgecolor="white", linewidth=0.6)
        ax.bar(centres[over], counts[over], width=0.1, align="edge", color=st.AMBER,
               edgecolor="white", linewidth=0.6)
        big = a[a > 3]
        # every patch over 3 hectares also gets its own tick under the axis, so a
        # count of 1 or 2 in a bar is still visible at slide size
        ymax = counts.max() * 1.12
        if len(big):
            ax.vlines(big, -0.07 * ymax, -0.015 * ymax, color=st.AMBER, linewidth=1.3)
        ax.set_ylim(-0.08 * ymax, ymax)
        ax.axvline(3, color=st.INK, linestyle=(0, (4, 3)), linewidth=1.3)
        ax.set_ylabel("Number of patches")
        ax.spines["bottom"].set_position(("data", 0))
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
        head, tail = SPACING[arm].split(": ")
        _row_label(ax, head, f"{tail}\n{len(a):,} patches; the typical (middle) patch is "
                             f"{np.median(a):.2f} hectares")
        if len(big):
            # the amber bars and ticks directly below the text are the patches meant
            ax.text(3.25, counts.max() * 0.12,
                    f"{len(big)} single patches (amber) are already larger than\n"
                    f"3 hectares (the largest is {big.max():.2f} hectares),\n"
                    f"so no 3 hectare stand can be drawn around them",
                    fontsize=12, color=st.INK, va="bottom")
        else:
            ax.text(3.25, counts.max() * 0.12,
                    f"No patch is larger than 3 hectares\n(the largest is {a.max():.2f} hectares)",
                    fontsize=12, color=st.INK, va="bottom")
    axes[0].text(3.06, axes[0].get_ylim()[1] * 0.97, "3 hectare ceiling", fontsize=12,
                 color=st.INK, va="top")
    axes[-1].set_xlabel("Size of each small patch (hectares)")
    axes[-1].set_xlim(0, 7)
    axes[-1].set_xticks(range(0, 8))
    for ax in axes:
        ax.tick_params(axis="x", labelbottom=True)
    return st.save(fig, "patch_sizes")


def fig_stand_sizes(stands: pd.DataFrame) -> Path:
    fig = plt.figure(figsize=(st.FULL[0], 5.6))
    gs = GridSpec(2, 2, figure=fig, width_ratios=[1.25, 1], wspace=0.24, hspace=0.32)
    hist_axes = [fig.add_subplot(gs[0, 0])]
    hist_axes.append(fig.add_subplot(gs[1, 0], sharex=hist_axes[0]))
    box_ax = fig.add_subplot(gs[:, 1])

    bins = np.arange(0, 10.5 + 1e-9, 0.25)
    for ax, arm in zip(hist_axes, ARM_ORDER):
        a = stands[stands.arm == arm].area_ha.to_numpy()
        counts, _ = np.histogram(a, bins=bins)
        ax.bar(bins[:-1], counts, width=0.25, align="edge", color=st.ARM_COLOUR[arm],
               edgecolor="white", linewidth=0.6)
        ymax = counts.max() * 1.18
        ax.set_ylim(0, ymax)
        for x in (3, 10):
            ax.axvline(x, color=st.INK, linestyle=(0, (4, 3)), linewidth=1.2)
        ax.set_ylabel("Number of stands")
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
        over3 = int((a > 3).sum())
        pct = 100 * over3 / len(a)
        ax.text(0.93, 0.95, st.ARM_NAME[arm], transform=ax.transAxes, ha="right",
                va="top", fontsize=13, fontweight="bold", color=st.INK)
        if arm == "v120":
            msg = (f"{len(a):,} stands. {over3:,} of them ({pct:.0f}%)\n"
                   f"are larger than 3 hectares")
        else:
            msg = (f"{len(a):,} stands. Only {over3} ({pct:.0f}%)\n"
                   f"go past 3 hectares, and by\nat most {a.max() - 3:.2f} hectares")
        ax.text(0.93, 0.78, msg, transform=ax.transAxes, ha="right", va="top",
                fontsize=12, color=st.INK)
    hist_axes[0].tick_params(axis="x", labelbottom=True)
    hist_axes[1].set_xlabel("Size of each stand (hectares)")
    hist_axes[1].set_xlim(0, 10.5)
    hist_axes[1].set_xticks(range(0, 11, 1))

    # right: one pair of boxes per district. Whiskers run to the smallest and largest
    # stand (no separate "outlier" dots to explain on a slide).
    rng = np.random.default_rng(0)
    pos_off = {"v120": -0.19, "v120_3ha": 0.19}
    for i, d in enumerate(DISTRICTS):
        for arm in ARM_ORDER:
            a = stands[(stands.arm == arm) & (stands.district == d)].area_ha.to_numpy()
            x = i + pos_off[arm]
            box_ax.scatter(x + rng.uniform(-0.12, 0.12, len(a)), a, s=5,
                           color=st.ARM_COLOUR[arm], alpha=0.22, linewidths=0, zorder=1)
            box_ax.boxplot(a, positions=[x], widths=0.3, whis=(0, 100), patch_artist=True,
                           showfliers=False, zorder=2,
                           boxprops=dict(facecolor="none", edgecolor=st.ARM_COLOUR[arm], linewidth=1.8),
                           medianprops=dict(color=st.ARM_COLOUR[arm], linewidth=2.6),
                           whiskerprops=dict(color=st.ARM_COLOUR[arm], linewidth=1.4),
                           capprops=dict(color=st.ARM_COLOUR[arm], linewidth=1.4))
    for y in (3, 10):
        box_ax.axhline(y, color=st.INK, linestyle=(0, (4, 3)), linewidth=1.2, zorder=0)
    box_ax.set_xticks(range(len(DISTRICTS)))
    labels = []
    for d in DISTRICTS:
        n10 = int(((stands.arm == "v120") & (stands.district == d)).sum())
        n3 = int(((stands.arm == "v120_3ha") & (stands.district == d)).sum())
        labels.append(f"{st.DISTRICT_NAME[d]}\n{n10:,} | {n3:,}")
    box_ax.set_xticklabels(labels)
    box_ax.set_xlim(-0.55, len(DISTRICTS) - 0.45)
    box_ax.set_ylim(0, 11.8)
    box_ax.set_yticks(range(0, 11, 1))
    box_ax.set_ylabel("Size of each stand (hectares)")
    handles = [Patch(facecolor="none", edgecolor=st.ARM_COLOUR[a], linewidth=1.8,
                     label=st.ARM_NAME[a]) for a in ARM_ORDER]
    box_ax.legend(handles=handles, loc="upper center", ncol=2, fontsize=11.5,
                  bbox_to_anchor=(0.5, 1.02), handlelength=1.2, columnspacing=1.0)
    box_ax.text(0.0, -0.17, "Numbers under each district: stands up to 10 | up to 3 hectares.\n"
                "Box: the middle half of stands. Thick line: the middle stand.\n"
                "Thin lines reach the smallest and the largest stand. Dots: every stand.",
                transform=box_ax.transAxes, fontsize=11, color=st.MUTE, va="top")
    return st.save(fig, "stand_sizes")


def main() -> None:
    st.use()
    patches, stands, polys = load()
    report(patches, stands, polys)
    for p in (fig_patch_sizes(patches), fig_stand_sizes(stands)):
        print("wrote", p)


if __name__ == "__main__":
    main()
