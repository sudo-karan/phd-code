"""The field check of the Odisha kept-land runs, as odisha_script/PHASE_KEPTLAND_PREDECLARED.md fixes it.

    python odisha_script/odisha_keptland_score.py [--out-dir odisha_script/keptland_scores]
        [--stands-dir docs/reproducibility/keptland_runs] [--box-stands-dir outputs/squares_runs/phase2_vectors]
        [--runs odisha_v120_3ha_squares_{district}_keptland_s1desc] [--stem keptland_s1desc]

Offline; no Earth Engine. Numbers only: no chance test is run (the declaration defers it), so
nothing here says that a score is more, or less, than chance would give, and nothing passes or
fails.

THE RUNS SCORED: by default the four descending-orbit kept-land runs,
configs/odisha_v120_3ha_squares_<district>_keptland_s1desc.yaml (the declaration's change of 15 Oct
2026, round 7), their merged stands (<run>_stands_merged.geojson). --runs names other runs by a
pattern with {district} (round 10: their _r9 re-runs, and the AlphaEarth arm of the amendment of
18 Oct 2026), and --stem names the result files, so the files of one set of runs never overwrite
another's. A stand layer kept off git for
its size (docs/decisions.yaml, spec-files-over-5-mb-off-git) is read from where its record
(<run>_files_off_git.json) says, after its SHA-256 is checked.

THE PLOTS: the 267 inside the boxes (aois/odisha_squares_<district>.geojson), each joined only to
its own district's run.

THE JOIN, as declared. A plot takes the stand that covers it; where several do, the lowest stand id
(the Phase 2 rule of odisha_phase2_3_join.py: stand id `stand_lbl`, `cluster_id` rounded, distances
in the local UTM zone of the box holding the plot). A plot that no stand covers takes the nearest
stand whose edge lies within 30 m of it, ties broken by the lowest stand id. A plot with no stand
within 30 m is left out of every score, and the number left out is given per district.

THE SCORES: the five Phase 3 statistics, computed as odisha_phase3_1_pairwise_score.py computes them
(`five_scores`, the arithmetic of odisha_phase3_3_significance.scorer_observed, which
tests/test_keptland_score.py checks it against on the committed Phase 3 table): stands keyed by
district, labelling within district, far-apart pairs over 2 km.
  1. drawing: ARI, all plots              2. drawing: ARI, stands holding two or more plots
  3. drawing: same-stand pair precision   4. labelling: ARI, plot-weighted mean of the districts'
  5. labelling: far-apart same-label rate, alike minus differ

THE CHECKS, as declared: S1, every score again with field type 0 left out; S2, four field types
(odisha_phase3_0_field_types_k4.csv); how the plots join (per district: on a stand, by the 30 m
rule, left out) and every score again with only the plots a stand covers; beside the box runs,
descriptive only, the five scores of the 13 Oct box runs (their merged stands, by the Phase 2 rule)
on the same plots as the primary analysis, with no test of the difference.

WRITES, in --out-dir, results only (no dates): <stem>_joined.csv (per plot: its stand by each
rule, how it joined, its distance), <stem>_scores.json and <stem>_scores.txt (stem by default
keptland_s1desc). The inputs' SHA-256 are in the JSON, so a re-run on other files cannot pass for
this one. Beside them, <stem>_scores_run.json, the run's record: the command, the date, the git
commit and whether the tree was dirty.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pyproj import Geod, Transformer
from shapely import STRtree
from shapely.geometry import Point
from sklearn.metrics import adjusted_rand_score as ari

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

import odisha_phase2_3_join as J  # noqa: E402, N812
from odisha_phase2_0_aois import load_plot_points, utm_transformers  # noqa: E402

GEOD = Geod(ellps="WGS84")
DISTRICTS = ("angul", "dhenkanal", "kendujhar", "koraput")
REACH_M = 30.0          # the declared reach for a plot no stand covers
DISTANT_M = 2000.0      # far-apart pairs, as Phase 3
FIELD_TYPES = HERE / "odisha_phase3_0_field_types.csv"
FIELD_TYPES_K4 = HERE / "odisha_phase3_0_field_types_k4.csv"
STANDS_DIR = REPO / "docs" / "reproducibility" / "keptland_runs"
BOX_STANDS_DIR = REPO / "outputs" / "squares_runs" / "phase2_vectors"
OUT_DIR = HERE / "keptland_scores"
STATS = (("delin_all", "drawing: ARI, all plots"),
         ("delin_multi", "drawing: ARI, stands holding two or more plots"),
         ("prec", "drawing: same-stand pair precision"),
         ("lab_wmean", "labelling: ARI, plot-weighted mean of the districts'"),
         ("far_gap", "labelling: far-apart same-label rate, alike minus differ"))


RUNS = "odisha_v120_3ha_squares_{district}_keptland_s1desc"   # the declaration's scored runs
STEM = "keptland_s1desc"


def run_id(district: str, runs: str = RUNS) -> str:
    return runs.format(district=district)


def runs_label(runs: str) -> str:
    """How the analyses name the runs: as before for the declared runs."""
    return "the _s1desc runs" if runs == RUNS else f"the runs {runs.format(district='<district>')}"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def stand_layer(run: str, stands_dir: Path) -> Path:
    """The run's merged stand layer: in stands_dir, or where its off-git record says, checked."""
    path = stands_dir / f"{run}_stands_merged.geojson"
    if path.exists():
        return path
    record = stands_dir / f"{run}_files_off_git.json"
    if not record.exists():
        raise SystemExit(f"{run}: no stand layer in {stands_dir} and no off-git record")
    entry = {f["file"]: f for f in json.loads(record.read_text())["files"]}[path.name]
    where = Path(entry["where"])
    if not where.exists():
        raise SystemExit(f"{run}: {path.name} is off git at {where}, which is not here")
    if sha256(where) != entry["sha256"]:
        raise SystemExit(f"{run}: {where} is not the file its record names (SHA-256 differs)")
    return where


# ---------------------------------------------------------------------- the join
def plots_in_boxes(aoi_dir: Path = REPO / "aois") -> pd.DataFrame:
    """The plots inside the boxes, each with the district of its box and that box's UTM zone."""
    pts = load_plot_points()
    ftype = pd.read_csv(FIELD_TYPES)[["plot_key", "field_type"]]
    pts = pts.merge(ftype, on="plot_key", how="left", validate="1:1")
    rows = []
    ll = [Point(lo, la) for lo, la in zip(pts.lon6, pts.lat6, strict=True)]
    for district in DISTRICTS:
        for part in J.aoi_parts(aoi_dir / f"odisha_squares_{district}.geojson"):
            c = part.centroid
            epsg = utm_transformers(c.x, c.y)[0]
            for i, q in enumerate(ll):
                if part.covers(q):
                    rows.append({"plot_key": pts.plot_key.iat[i], "box_district": district, "epsg": epsg})
    inside = pd.DataFrame(rows).drop_duplicates("plot_key")
    out = pts.merge(inside, on="plot_key", how="inner", validate="1:1")
    return out[["plot_key", "lat6", "lon6", "district", "habitation", "field_type", "box_district",
                "epsg"]].reset_index(drop=True)


def join(plots: pd.DataFrame, layer_path: Path, reach_m: float | None) -> pd.DataFrame:
    """Each plot's stand by the declared rule: covered (lowest stand id), else, with reach_m, the
    nearest stand within reach_m (ties: lowest stand id), else none. Returns plot_key, sid,
    cluster, how ('covered', 'within', 'none') and dist_m (0 where covered; to the nearest stand
    within 1,000 m otherwise, else inf)."""
    out = []
    for epsg in sorted(plots.epsg.unique()):
        sel = plots[plots.epsg == epsg]
        fwd = Transformer.from_crs(4326, int(epsg), always_xy=True).transform
        layer = J.load_layer(layer_path, "stand_lbl", fwd)
        geoms = list(layer.geom)
        tree = STRtree(geoms)
        for _, r in sel.iterrows():
            pt = Point(fwd(r.lon6, r.lat6))
            hits = list(tree.query(pt, predicate="covered_by"))
            if hits:
                i = min(hits, key=lambda h: layer.sid.iat[h])
                how, dist = "covered", 0.0
            else:
                # Per stand, its nearest polygon and that polygon's distance: a stand in pieces
                # is as near as its nearest piece, and the plot takes that piece's type, as a
                # covered plot takes the type of the polygon that covers it.
                near: dict[int, tuple[float, int]] = {}
                for j in tree.query(pt, predicate="dwithin", distance=1000.0):
                    s, dj = int(layer.sid.iat[j]), geoms[j].distance(pt)
                    if s not in near or dj < near[s][0]:
                        near[s] = (dj, j)
                dist = min(d for d, _ in near.values()) if near else np.inf
                best = min(near, key=lambda s: (near[s][0], s)) if near else None
                if reach_m is not None and best is not None and near[best][0] <= reach_m:
                    how = "within"
                    i = near[best][1]
                else:
                    out.append({"plot_key": r.plot_key, "sid": np.nan, "cluster": np.nan,
                                "how": "none", "dist_m": dist})
                    continue
            cid = layer.cluster_id.iat[i]
            out.append({"plot_key": r.plot_key, "sid": int(layer.sid.iat[i]),
                        "cluster": np.nan if cid is None else float(cid), "how": how, "dist_m": dist})
    return pd.DataFrame(out)


# ---------------------------------------------------------------------- the five statistics
def five_scores(d: pd.DataFrame) -> dict[str, Any]:
    """The five Phase 3 statistics on a table with district, lat6, lon6, field_type, sid and
    cluster, plots without a stand dropped: the arithmetic of
    odisha_phase3_3_significance.scorer_observed, line for line."""
    d = d[d.sid.notna()].reset_index(drop=True)
    d = d.assign(skey=d.district.astype(str) + ":" + d.sid.round().astype(int).astype(str))
    out: dict[str, Any] = {"delin_all": float(ari(d.skey, d.field_type))}
    multi = d.groupby("skey").skey.transform("size").to_numpy() > 1
    sub = d[multi]
    out["delin_multi"] = float(ari(sub.skey, sub.field_type))
    sizes = d.groupby("skey").size()
    alike = d.groupby(["skey", "field_type"]).size()
    out["prec"] = float((alike * (alike - 1) / 2).sum() / (sizes * (sizes - 1) / 2).sum())
    lab = np.rint(pd.to_numeric(d.cluster, errors="coerce").to_numpy())
    ok = ~np.isnan(lab)
    per, wts, by_district = [], [], {}
    for name, g in d[ok].groupby("district"):
        if len(g) >= 2 and g.field_type.nunique() >= 2:
            a = float(ari(g.field_type, np.rint(g.cluster.astype(float))))
            per.append(a)
            wts.append(len(g))
            by_district[str(name)] = {"n": int(len(g)), "ari": a}
        else:
            by_district[str(name)] = {"n": int(len(g)), "ari": None}
    out["lab_wmean"] = float(np.average(per, weights=wts)) if per else float("nan")
    i, j = np.triu_indices(len(d), 1)
    _, _, dm = GEOD.inv(d.lon6.to_numpy()[i], d.lat6.to_numpy()[i], d.lon6.to_numpy()[j],
                        d.lat6.to_numpy()[j])
    far = ok[i] & ok[j] & (d.district.to_numpy()[i] == d.district.to_numpy()[j]) & (dm > DISTANT_M)
    st = d.field_type.to_numpy()[i] == d.field_type.to_numpy()[j]
    sl = lab[i] == lab[j]
    a, b = far & st, far & ~st
    out["far_gap"] = float(sl[a].mean() - sl[b].mean()) if a.any() and b.any() else float("nan")
    out["counts"] = {"plots": int(len(d)), "stands_holding_them": int(sizes.size),
                     "multi_plot_stands": int((sizes > 1).sum()),
                     "plots_in_multi_plot_stands": int(sizes[sizes > 1].sum()),
                     "plots_without_a_type": int((~ok).sum()),
                     "far_apart_pairs_alike": int(a.sum()), "far_apart_pairs_differ": int(b.sum())}
    out["labelling_by_district"] = by_district
    return out


# ---------------------------------------------------------------------- the analyses
def analyses(plots: pd.DataFrame, joined: pd.DataFrame, box: pd.DataFrame,
             runs: str = RUNS) -> list[dict[str, Any]]:
    """The primary analysis and the declared checks, each a row of numbers."""
    k4 = pd.read_csv(FIELD_TYPES_K4)[["plot_key", "field_type"]].rename(columns={"field_type": "ft_k4"})
    base = plots.merge(joined, on="plot_key", validate="1:1").merge(k4, on="plot_key", validate="1:1")
    scored = base[base.sid.notna()]
    rows = []

    def row(name: str, what: str, d: pd.DataFrame) -> None:
        rows.append({"analysis": name, "what": what, **five_scores(d)})

    row("primary", f"{runs_label(runs)}; the primary field types; the 30 m rule", base)
    row("S1", "as the primary, field type 0 (no trees) left out", base[base.field_type != 0])
    row("S2", "as the primary, four field types (odisha_phase3_0_field_types_k4.csv)",
        base.assign(field_type=base.ft_k4))
    row("covered_only", "as the primary, only the plots a stand covers (no 30 m rule)",
        base[base.how == "covered"])
    boxed = scored[["plot_key", "district", "lat6", "lon6", "field_type"]].merge(
        box[["plot_key", "sid", "cluster"]], on="plot_key", validate="1:1")
    row("box_runs", "beside it, descriptive only: the 13 Oct box runs' merged stands (the Phase 2 "
        "rule) on the plots the primary scores", boxed)
    return rows


def join_counts(plots: pd.DataFrame, joined: pd.DataFrame) -> dict[str, dict[str, int]]:
    t = plots.merge(joined, on="plot_key", validate="1:1")
    out = {}
    for name, g in t.groupby("box_district"):
        out[str(name)] = {"inside_the_boxes": int(len(g)), "on_a_stand": int((g.how == "covered").sum()),
                          "by_the_30_m_rule": int((g.how == "within").sum()),
                          "left_out": int((g.how == "none").sum())}
    out["all"] = {k: sum(v[k] for v in out.values()) for k in next(iter(out.values()))}
    return out


def text(result: dict[str, Any], runs: str = RUNS) -> str:
    lines = ["The field check of the Odisha kept-land runs (odisha_script/PHASE_KEPTLAND_PREDECLARED.md)",
             f"Runs: configs/{runs.format(district='<district>')}.yaml. Numbers only: the",
             "chance test is not run, so no score here is said to be more, or less, than chance gives.",
             "", "How the plots join (per district)",
             f"  {'district':<11}{'inside':>8}{'on a stand':>12}{'by 30 m':>9}{'left out':>10}"]
    for name, c in result["join"].items():
        lines.append(f"  {name:<11}{c['inside_the_boxes']:>8}{c['on_a_stand']:>12}"
                     f"{c['by_the_30_m_rule']:>9}{c['left_out']:>10}")
    lines += ["", "The five scores"]
    head = f"  {'analysis':<14}" + "".join(f"{k:>13}" for k, _ in STATS) + f"{'plots':>8}"
    lines.append(head)
    for r in result["analyses"]:
        lines.append(f"  {r['analysis']:<14}" + "".join(
            f"{r[k]:>+13.4f}" if r[k] == r[k] else f"{'n/a':>13}" for k, _ in STATS)
            + f"{r['counts']['plots']:>8}")
    lines += ["", "  " + "; ".join(f"{k} = {label}" for k, label in STATS), ""]
    for r in result["analyses"]:
        lines.append(f"  {r['analysis']}: {r['what']}.")
        c = r["counts"]
        lines.append(f"    {c['plots']} plots in {c['stands_holding_them']} stands; {c['multi_plot_stands']} "
                     f"stands hold two or more ({c['plots_in_multi_plot_stands']} plots); far-apart pairs "
                     f"alike {c['far_apart_pairs_alike']}, differ {c['far_apart_pairs_differ']}")
        per = ", ".join(f"{k} {v['ari']:+.4f} (n={v['n']})" if v["ari"] is not None else f"{k} not scored (n={v['n']})"
                        for k, v in r["labelling_by_district"].items())
        lines.append(f"    labelling ARI by district: {per}")
    return "\n".join(lines) + "\n"


def write_run_record(out_dir: Path, argv: list[str], stem: str = STEM) -> None:
    import datetime
    import shlex

    sys.path.insert(0, str(REPO / "src"))
    from fmu.utils.provenance import git_state

    run = {"result_files": [f"{stem}_joined.csv", f"{stem}_scores.json", f"{stem}_scores.txt"],
           "command_line": "python " + " ".join(shlex.quote(a) for a in
                                                ["odisha_script/odisha_keptland_score.py", *argv]),
           "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
           "git": {k: v for k, v in git_state(HERE).items() if k != "root"}}
    (out_dir / f"{stem}_scores_run.json").write_text(json.dumps(run, indent=1) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stands-dir", type=Path, default=STANDS_DIR)
    ap.add_argument("--box-stands-dir", type=Path, default=BOX_STANDS_DIR)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--runs", default=RUNS,
                    help="the runs scored, a pattern with {district} (default: the declaration's)")
    ap.add_argument("--stem", default=STEM, help="the result files' names begin with this")
    args = ap.parse_args(argv)
    if "{district}" not in args.runs:
        ap.error("--runs must hold {district}")
    plots = plots_in_boxes()
    inputs: dict[str, str] = {}
    joined, box = [], []
    for district in DISTRICTS:
        sub = plots[plots.box_district == district]
        layer = stand_layer(run_id(district, args.runs), args.stands_dir)
        box_layer = args.box_stands_dir / f"odisha_v120_3ha_squares_{district}_stands_merged.geojson"
        inputs[run_id(district, args.runs)] = sha256(layer)
        inputs[box_layer.stem.removesuffix("_stands_merged")] = sha256(box_layer)
        j = join(sub, layer, REACH_M)
        j = j.merge(join(sub, layer, None)[["plot_key", "sid"]].rename(columns={"sid": "sid_covered"}),
                    on="plot_key", validate="1:1")
        joined.append(j)
        box.append(join(sub, box_layer, None))
    joined_df = pd.concat(joined, ignore_index=True)
    box_df = pd.concat(box, ignore_index=True)
    result = {"what": "The field check of the Odisha kept-land runs, as "
                      "odisha_script/PHASE_KEPTLAND_PREDECLARED.md fixes it; numbers only, no chance test.",
              "inputs_sha256": inputs, "join": join_counts(plots, joined_df),
              "analyses": analyses(plots, joined_df, box_df, args.runs)}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    table = plots.merge(joined_df, on="plot_key", validate="1:1").merge(
        box_df[["plot_key", "sid", "cluster"]].rename(columns={"sid": "box_sid", "cluster": "box_cluster"}),
        on="plot_key", validate="1:1")
    table.drop(columns=["epsg"]).to_csv(args.out_dir / f"{args.stem}_joined.csv", index=False)
    (args.out_dir / f"{args.stem}_scores.json").write_text(json.dumps(result, indent=1) + "\n")
    (args.out_dir / f"{args.stem}_scores.txt").write_text(text(result, args.runs))
    write_run_record(args.out_dir, list(sys.argv[1:] if argv is None else argv), args.stem)
    print(text(result, args.runs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
