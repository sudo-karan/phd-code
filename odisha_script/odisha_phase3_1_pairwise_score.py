"""Phase 3, step 1: score delineation and labelling against the field data.

The supervisor's question, in his words: do trees that look alike in the field
end up in the same stand, and do they get the same stand type?

Both halves are pair questions, so both are scored the same way. For every pair
of plots we ask two things and cross-tabulate them:

                    | same stand (or same type) | different
  field says alike  |            hit            |   miss
  field differs     |        false alarm        |   hit

That table gives a plain accuracy, but accuracy is not readable on its own here:
most pairs are "different stand" simply because there are many stands, so a
partition that put every plot in its own stand would score highly while grouping
nothing. The Adjusted Rand Index is the same table corrected for that -- 0 means
no better than a random grouping of the same shape, 1 means perfect agreement.
It is the headline number; the raw table is printed beside it so the shape of
the agreement is visible rather than hidden behind one figure.

Truth = the structural field types from odisha_phase3_0 (k chosen by elbow from
the field data alone, before any stand label was read).

Delineation is scored on plots that share a stand at all -- the question "are
alike plots put together" is only answerable where the partition puts anything
together. Labelling is scored on pairs over 2 km apart, so "same type" cannot be
explained by the two plots simply being neighbours.

Usage:  python odisha_script/odisha_phase3_1_pairwise_score.py [--arm v120] [--set districts]
Offline; no Earth Engine.
"""
from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Geod
from sklearn.metrics import adjusted_rand_score

HERE = Path(__file__).parent
GEOD = Geod(ellps="WGS84")
DISTANT_M = 2000.0

_lines: list[str] = []


def say(s: str = "") -> None:
    print(s)
    _lines.append(s)


def pair_table(same_pred: np.ndarray, same_true: np.ndarray) -> dict:
    """The 2x2 and the scores that read off it."""
    tp = int(np.sum(same_pred & same_true))
    fp = int(np.sum(same_pred & ~same_true))
    fn = int(np.sum(~same_pred & same_true))
    tn = int(np.sum(~same_pred & ~same_true))
    n = tp + fp + fn + tn
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if prec == prec and rec == rec and prec + rec else float("nan")
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "n": n,
            "accuracy": (tp + tn) / n if n else float("nan"),
            "precision": prec, "recall": rec, "f1": f1,
            "base_rate_same_true": (tp + fn) / n if n else float("nan"),
            "base_rate_same_pred": (tp + fp) / n if n else float("nan")}


def show(name: str, t: dict, ari: float, note: str = "") -> None:
    say(f"  {name}{note}")
    say(f"      pairs {t['n']:,}   field-alike {t['base_rate_same_true']:.1%}   "
        f"grouped-together {t['base_rate_same_pred']:.1%}")
    say(f"      {'':14}{'same group':>12}{'different':>12}")
    say(f"      {'field alike':<14}{t['tp']:>12,}{t['fn']:>12,}")
    say(f"      {'field differs':<14}{t['fp']:>12,}{t['tn']:>12,}")
    say(f"      accuracy {t['accuracy']:.3f}   precision {t['precision']:.3f}   "
        f"recall {t['recall']:.3f}   F1 {t['f1']:.3f}")
    a = f"{ari:+.4f}   (0 = no better than chance, 1 = perfect)" if ari == ari else "n/a (see note)"
    say(f"      >>> ARI {a}")
    say("")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="v120")
    ap.add_argument("--set", dest="set_name", default="districts", choices=["pilot", "districts"])
    ap.add_argument("--layer", default="merged", choices=["merged", "snic", "dissolved"])
    ap.add_argument("--joined", type=Path, default=None,
                    help="joined CSV to score; default odisha_script/phase2_plots_joined<suffix>.csv. "
                         "Point this at a separate join so a new arm never overwrites the committed one.")
    ap.add_argument("--tag", default="", help="suffix for the output filename, to keep runs apart")
    args = ap.parse_args()
    suffix = "_districts" if args.set_name == "districts" else ""

    joined_path = args.joined if args.joined else HERE / f"phase2_plots_joined{suffix}.csv"
    joined = pd.read_csv(joined_path)
    ftypes = pd.read_csv(HERE / "odisha_phase3_0_field_types.csv")[["plot_key", "field_type"]]
    d = joined.merge(ftypes, on="plot_key", validate="1:1")

    id_col = f"{args.arm}_{args.layer}_id"
    cl_col = f"{args.arm}_{args.layer}_cluster"
    if id_col not in d.columns:
        say(f"arm '{args.arm}' layer '{args.layer}' not in the joined table "
            f"(have: {sorted({c.rsplit('_', 1)[0] for c in d.columns if c.endswith('_id')})})")
        return 2

    d = d[d[id_col].notna()].reset_index(drop=True)

    # Each district is its own pipeline run, so stand ids and k-means type numbers
    # both RESTART per district: stand 62 in angul is not stand 62 in koraput, and
    # type 3 in angul is unrelated to type 3 in koraput (k-means is fitted per
    # district). The first version of this script pooled raw ids across districts,
    # which merged 18 (10 ha) and 24 (3 ha) unrelated stands and compared unrelated
    # types. Stands are therefore keyed by (district, id), as odisha_phase2_5_stats
    # does, and labelling is scored within each district.
    d["skey"] = d.district.astype(str) + ":" + d[id_col].round().astype(int).astype(str)

    say("=" * 100)
    say(f"PHASE 3 STEP 1 -- pairwise score, arm={args.arm} layer={args.layer} set={args.set_name}")
    say("=" * 100)
    say(f"  joined table: {joined_path.name}")
    say(f"  plots with a stand: {len(d)}")
    sizes = d.groupby("skey").size()
    say(f"  stands holding them: {len(sizes)}   multi-plot stands: {int((sizes > 1).sum())} "
        f"holding {int(sizes[sizes > 1].sum())} plots   (stand key = district:id)")
    say(f"  field types: {d.field_type.value_counts().sort_index().to_dict()}")
    say("")
    say("  READ ARI AGAINST ITS CHANCE LEVEL, NOT AGAINST ZERO. In this design chance-level")
    say("  ARI is positive: villages cluster both the field types and the stands, so a")
    say("  rotated stand map scores ~0.005-0.022 on delineation and ~0.04-0.06 on labelling.")
    say("  Whether a value beats chance is tested with the spatial rotation null in")
    say("  odisha_phase3_3_significance.py, not read off this file.")
    say("")

    i, j = map(np.array, zip(*combinations(range(len(d)), 2)))
    same_type = d.field_type.to_numpy()[i] == d.field_type.to_numpy()[j]
    same_stand = d.skey.to_numpy()[i] == d.skey.to_numpy()[j]
    same_dist = d.district.to_numpy()[i] == d.district.to_numpy()[j]
    _, _, dist = GEOD.inv(d.lon6.to_numpy()[i], d.lat6.to_numpy()[i],
                          d.lon6.to_numpy()[j], d.lat6.to_numpy()[j])

    say("-" * 100)
    say("A. DELINEATION -- do alike plots end up in the same stand?")
    say("-" * 100)
    show("all pairs", pair_table(same_stand, same_type),
         adjusted_rand_score(d.skey, d.field_type))

    multi = d.groupby("skey").skey.transform("size").to_numpy() > 1
    keep = multi[i] & multi[j]
    if keep.sum():
        sub = d[multi]
        show("restricted to plots in multi-plot stands",
             pair_table(same_stand[keep], same_type[keep]),
             adjusted_rand_score(sub.skey, sub.field_type),
             f"  ({len(sub)} plots in {sub.skey.nunique()} stands)")
    else:
        say("  no multi-plot stands: the delineation question is not answerable here\n")

    if cl_col in d.columns and d[cl_col].notna().any():
        say("-" * 100)
        say("B. LABELLING -- do alike plots get the same stand TYPE, even far apart?")
        say("-" * 100)
        say("  k-means is fitted per district, so types are comparable only WITHIN a")
        say("  district. Pairs are restricted to same-district pairs, and the ARI is the")
        say("  plot-weighted mean of per-district ARIs.")
        lab = np.rint(pd.to_numeric(d[cl_col], errors="coerce").to_numpy())
        ok = ~np.isnan(lab)
        if (~ok).any():
            say(f"  {int((~ok).sum())} assigned plot(s) carry no type label and are left out")
        valid = ok[i] & ok[j] & same_dist
        same_lab = np.where(valid, lab[i] == lab[j], False)
        say("")
        per, wts = [], []
        for dist_name, g in d[ok].groupby("district"):
            if len(g) >= 2 and g.field_type.nunique() >= 2:
                a = adjusted_rand_score(g.field_type, np.rint(g[cl_col].astype(float)))
                per.append(a); wts.append(len(g))
                say(f"    {dist_name:<11} n={len(g):>4}   ARI {a:+.4f}")
            else:
                say(f"    {dist_name:<11} n={len(g):>4}   not scored (<2 plots or <2 field types)")
        wmean = float(np.average(per, weights=wts)) if per else float("nan")
        say("")
        show("same-district pairs", pair_table(same_lab[valid], same_type[valid]), wmean,
             "  (ARI = plot-weighted mean of the per-district values above)")
        far = valid & (dist > DISTANT_M)
        if far.sum() > 30:
            show(f"same-district pairs more than {DISTANT_M/1000:.0f} km apart",
                 pair_table(same_lab[far], same_type[far]), float("nan"),
                 "  (ARI is a whole-partition score, so it is not defined on a pair subset)")
        else:
            say(f"  only {int(far.sum())} same-district pairs beyond {DISTANT_M/1000:.0f} km: not reported\n")
    else:
        say("  no cluster labels on this layer; labelling not scored\n")

    out = HERE / f"odisha_phase3_1_score_{args.arm}_{args.layer}{suffix}{args.tag}.txt"
    out.write_text("\n".join(_lines) + "\n")
    say(f"  wrote {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
