"""Phase 3 summary deck, result figures: our scores against the random-shift (rotation) chance test.

Two figures, drawn from the real draws, for the Phase 3 summary slides:

  chance_test.png     2 x 2 panels. Rows: the 10 hectare and the 3 hectare stands. Columns: the two
                      questions, "are alike plots in the same stand?" (delineation, multi-plot stands)
                      and "do alike plots get the same stand type?" (labelling, per-district weighted
                      mean). Each panel: the 1,999 random-shift scores as a grey histogram, our score as
                      an amber line, and how many random maps our score beats.
  summary_scores.png  one compact chart: for each arm and question, our score as a dot, the middle 90%
                      of the random-shift scores as a grey band, and a reference line for "knowing only
                      which village a plot is in" (agreement between field type and village).

The random-shift draws are NOT reimplemented here. The data loading, the observed statistics and the
two rotation nulls (unconditional for delineation, conditional on typed polygons for labelling) all come
from odisha_phase3_3_significance.analyse_arm, with its seeds, so the draws are the ones behind
odisha_phase3_3_results.txt. Before drawing, the observed values and their percentiles are checked
against that results file; any mismatch stops the script.

"Beats N of 1,999" counts random maps scoring strictly below ours; the file's percentile is the mid-rank
(strictly below + half the ties), so N / 1,999 matches it up to ties, which are reported.

Usage:  python odisha_script/odisha_phase3_4d_results.py [--rotations 1999] [--cache path.npz]
        --cache stores the draws after the first run (about 8 minutes) and reuses them; the cache is
        only reused if its rotation count matches, and is checked against the results file like fresh draws.
Output: odisha_script/phase3_figures/chance_test.png, summary_scores.png
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import adjusted_rand_score

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import odisha_phase2_5_stats as S  # noqa: E402
import odisha_phase3_3_significance as G  # noqa: E402
import phase3_figstyle as st  # noqa: E402

ARMS = ["v120", "v120_3ha"]                         # row order: 10 hectares, then 3 hectares
QUESTIONS = [("delin_multi", "Are alike plots in the same stand?", "delineation ARI, multi-plot stands"),
             ("lab_wmean", "Do alike plots get the same stand type?", "labelling ARI, per-district wmean")]
RESULTS_TXT = HERE / G.OUT_NAME
FILE_SECTION = {"v120": "10 HA ARM", "v120_3ha": "3 HA ARM"}


# ---------------------------------------------------------------------- draws
def compute(n_rot: int) -> tuple[dict, float, float]:
    """Observed and null values for the two headline statistics of both arms, via the significance script."""
    spec, plots, parts = G.load_all()
    X = G.Plots(plots)
    out = {}
    for arm in ARMS:
        r = G.analyse_arm(arm, spec, plots, parts, X, n_rot)
        for k, _, _ in QUESTIONS:
            out[f"{arm}/{k}/obs"] = np.array(r["obs"][k])
            out[f"{arm}/{k}/null"] = r["null"][k]
    # "knowing only the village": the village of a plot is its study-area polygon part, assigned by the
    # point-in-polygon rule of odisha_phase2_5_stats.load (used by load_all above)
    village = adjusted_rand_score(plots.field_type, plots.aoi_part)
    per, w = [], []
    for _, g in plots.groupby("district_set"):
        if len(g) >= 2 and g.field_type.nunique() >= 2:
            per.append(adjusted_rand_score(g.field_type, g.aoi_part))
            w.append(len(g))
    village_district = float(np.average(per, weights=w))
    out["village"], out["village_district"], out["n_plots"] = village, village_district, len(plots)
    out["n_villages"] = plots.aoi_part.nunique()
    return out, village, village_district


def load_or_compute(n_rot: int, cache: Path | None) -> dict:
    if cache is not None and cache.exists():
        d = dict(np.load(cache))
        if all(len(d[f"{a}/{k}/null"]) == n_rot for a in ARMS for k, _, _ in QUESTIONS):
            print(f"  using cached draws {cache}")
            return d
        print(f"  cache {cache} has another rotation count; recomputing")
    d, _, _ = compute(n_rot)
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache, **d)
        print(f"  cached draws to {cache}")
    return d


# ---------------------------------------------------------------------- check against the results file
def file_values() -> dict:
    """(observed, percentile) for each arm and headline statistic, read from odisha_phase3_3_results.txt."""
    txt = RESULTS_TXT.read_text()
    vals = {}
    for arm in ARMS:
        sec = txt.split(f"{FILE_SECTION[arm]} (")[1]
        for k, _, label in QUESTIONS:
            m = re.search(re.escape(label) + r"\s+([+-]\d\.\d+) \|.*?\]\s+(\d+\.\d)\s", sec)
            vals[(arm, k)] = (float(m.group(1)), float(m.group(2)))
    return vals


def verify(d: dict) -> None:
    ref = file_values()
    for (arm, k), (obs_f, pc_f) in ref.items():
        obs, null = float(d[f"{arm}/{k}/obs"]), d[f"{arm}/{k}/null"]
        pc, n = S.percentile(obs, null)
        ok = round(obs, 4) == obs_f and round(pc, 1) == pc_f and n == len(null)
        print(f"  check {arm:9} {k:12} observed {obs:+.4f} (file {obs_f:+.4f})  percentile {pc:5.1f} "
              f"(file {pc_f:5.1f})  usable draws {n}  {'OK' if ok else 'MISMATCH'}")
        if not ok:
            raise SystemExit(f"draws do not reproduce {RESULTS_TXT.name} for {arm} {k}; not drawing")


# ---------------------------------------------------------------------- figures
def beats(obs: float, null: np.ndarray) -> tuple[int, int, int]:
    v = null[~np.isnan(null)]
    return int((v < obs).sum()), int((v == obs).sum()), len(v)


def fig_chance_test(d: dict) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(12.0, 6.0), sharex="col", sharey=True)
    for c, (k, question, _) in enumerate(QUESTIONS):
        allv = np.concatenate([d[f"{a}/{k}/null"] for a in ARMS] + [np.atleast_1d(d[f"{a}/{k}/obs"]) for a in ARMS])
        lo, hi = np.nanmin(allv), np.nanmax(allv)
        pad = 0.04 * (hi - lo)
        bins = np.linspace(lo - pad, hi + pad, 46)
        for r, arm in enumerate(ARMS):
            ax = axes[r, c]
            null, obs = d[f"{arm}/{k}/null"], float(d[f"{arm}/{k}/obs"])
            ax.hist(null[~np.isnan(null)], bins=bins, color=st.CHANCE, edgecolor="white", linewidth=0.6)
            b, ties, n = beats(obs, null)
            # our score: a line that stops short of the top, labelled directly above it
            ax.axvline(obs, ymax=0.70, color=st.AMBER, linewidth=3.2, solid_capstyle="butt", zorder=3)
            frac = (obs - bins[0]) / (bins[-1] - bins[0])
            ha, dx = ("left", -0.012) if frac < 0.35 else ("right", 0.012) if frac > 0.65 else ("center", 0)
            ax.text(frac + dx, 0.73, f"Our score {obs:.3f}\nbeats {b:,} of {n:,} random maps",
                    transform=ax.transAxes, ha=ha, va="bottom", fontsize=13, color=st.INK, linespacing=1.3)
            ax.tick_params(axis="both", labelsize=12)
            if r == 0:
                ax.set_title(question, fontsize=15, color=st.INK, pad=10, fontweight="bold")
            if r == 1:
                ax.set_xlabel("Agreement score", fontsize=13)
            if c == 0:
                ax.set_ylabel("Number of\nrandom maps", fontsize=13)
            ax.margins(x=0)
    ax0 = axes[0, 0]
    top = max(p.get_height() for ax in axes.flat for p in ax.patches)
    ax0.set_ylim(0, top / 0.66)                        # bars stay under the line's label
    fig.tight_layout(rect=(0.13, 0, 1, 1), h_pad=1.6, w_pad=2.5)
    for r, arm in enumerate(ARMS):
        bb = axes[r, 0].get_position()
        name = st.ARM_NAME[arm].replace("Stands up to ", "Stands up to\n")
        fig.text(0.005, (bb.y0 + bb.y1) / 2, name, ha="left", va="center", fontsize=14,
                 fontweight="bold", color=st.INK, linespacing=1.3)
    # one key for the grey bars, in the first panel
    axes[0, 1].text(0.98, 0.45, "Grey bars: 1,999 random\nshifts of our stand map",
                    transform=axes[0, 1].transAxes, ha="right", va="top", fontsize=12, color=st.MUTE)
    return st.save(fig, "chance_test")


def fig_summary_scores(d: dict, village: float) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(12.0, 3.9), sharex=True)
    allv = [village] + [float(d[f"{a}/{k}/obs"]) for a in ARMS for k, _, _ in QUESTIONS]
    for a in ARMS:
        for k, _, _ in QUESTIONS:
            allv += list(np.nanpercentile(d[f"{a}/{k}/null"], [5, 95]))
    xmax = max(allv) * 1.12
    ys = {"v120": 1.0, "v120_3ha": 0.0}
    for c, (k, question, _) in enumerate(QUESTIONS):
        ax = axes[c]
        for arm in ARMS:
            null, obs = d[f"{arm}/{k}/null"], float(d[f"{arm}/{k}/obs"])
            p5, p95 = np.nanpercentile(null, [5, 95])
            y = ys[arm]
            ax.plot([p5, p95], [y, y], color=st.CHANCE, linewidth=16, solid_capstyle="round", zorder=1)
            ax.plot(obs, y, "o", ms=13, color=st.AMBER, mec="white", mew=2, zorder=3)
        ax.axvline(village, color=st.INK, linewidth=1.6, linestyle=(0, (4, 3)), zorder=2)
        ax.text(village + 0.0015, 1.62, f"Knowing only the village: {village:.3f}", ha="left", va="center",
                fontsize=12, color=st.INK)
        ax.set_ylim(-0.6, 1.85)
        ax.set_yticks([ys[a] for a in ARMS])
        ax.set_yticklabels([st.ARM_NAME[a] for a in ARMS] if c == 0 else [], fontsize=13, color=st.INK)
        ax.tick_params(axis="y", length=0)
        ax.spines["left"].set_visible(False)
        ax.set_xlim(0, xmax)
        ax.set_xlabel("Agreement score", fontsize=13)
        ax.set_title(question, fontsize=15, color=st.INK, pad=8, fontweight="bold")
    # key, under the chart
    h_dot = plt.Line2D([], [], marker="o", ms=11, color=st.AMBER, mec="white", mew=2, linestyle="none")
    h_band = plt.Line2D([], [], color=st.CHANCE, linewidth=10, solid_capstyle="round")
    fig.legend([h_dot, h_band],
               ["Our score", "Middle 90% of 1,999 random shifts of our stand map (what chance gives)"],
               loc="lower center", ncol=2, fontsize=12, bbox_to_anchor=(0.55, -0.02), handlelength=2.2)
    fig.tight_layout(rect=(0, 0.1, 1, 1), w_pad=3)
    return st.save(fig, "summary_scores")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rotations", type=int, default=1999)
    ap.add_argument("--cache", type=Path, default=None, help="npz to store / reuse the random-shift draws")
    args = ap.parse_args()
    st.use()

    d = load_or_compute(args.rotations, args.cache)
    verify(d)
    village = float(d["village"])
    print(f"  plots {int(d['n_plots'])}, villages {int(d['n_villages'])}")
    print(f"  knowing only the village: agreement(field type, village) = {village:.4f} over all plots; "
          f"per-district plot-weighted mean {float(d['village_district']):.4f}")
    for arm in ARMS:
        for k, _, _ in QUESTIONS:
            null, obs = d[f"{arm}/{k}/null"], float(d[f"{arm}/{k}/obs"])
            b, ties, n = beats(obs, null)
            med = np.nanmedian(null)
            p5, p95 = np.nanpercentile(null, [5, 95])
            print(f"  {arm:9} {k:12} ours {obs:.4f}  beats {b} of {n} (ties {ties})  random median {med:.4f}  "
                  f"middle 90% [{p5:.4f}, {p95:.4f}]")
    print(f"  wrote {fig_chance_test(d)}")
    print(f"  wrote {fig_summary_scores(d, village)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
