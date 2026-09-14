"""
Phase 2, step 3 — the field-side plot table, and the plot <-> stand join.

FULLY OFFLINE. Reads Odisha_samples.csv through odisha_phase1_0_clean.load_trees, and the vector
layers odisha_phase2_2_run_pipeline.py pulled into phase2_vectors/.

THIS SCRIPT COMPUTES NO STATISTIC RELATING FIELD DATA TO STANDS. It builds the table and reports
how plots distribute over stands (a property of the geometry), because
PHASE2_PREDICTIONS.md has to be committed before any such statistic exists.

FIELD TABLE
-----------
Reuses odisha_phase1_0_clean.load_trees (crown-cover Excel repair, GPS <= 20 m filter, plot_key)
rather than re-deriving it. Per plot:

  n_records        every record, as Phase 1's `n_trees` was: ("Height", "size") counts saplings,
                   shrubs, climbers and stumps too. Renamed, because it is not a tree count.
  n_trees          records with Habit == "Tree".
  no_tree_record   True where a plot has no Tree record at all (15 plots). Lorey's height there
                   is computed entirely from shrubs and saplings.
  loreys_h_m       basal-area-weighted height over ALL records -- Phase 1's definition, for
                   continuity. Asserted equal to odisha_plots_clean.csv.
  loreys_h_tree_m  the same over Tree records only; NaN where no_tree_record.
  h_top5_m         mean height of the 5 tallest records (all habits, Phase 1's definition).
  crown_cover_pct  plot median of the crown-cover band midpoint (Phase 1's definition).
  sal_ba_frac      Shorea robusta basal area / plot basal area, all records.
  n_species        distinct species among Tree records (0 where no_tree_record).
  dbh_mean_cm      mean DBH of Tree records.
  sp_ba_json       per-species basal area (cm2), all records, as JSON -- the Bray-Curtis input.

Species identity: `Scientific Name` is inconsistent (e.g. "Sala Shorea robusta" and
"Sal_Shorea_robusta"). Names are normalised to their last two tokens after splitting on
underscores and spaces, lower-cased -- the binomial, since every multi-token name here is
"<local name> <Genus> <species>". One- and two-token names ("Other") are kept as they are.
Genus misspellings are NOT corrected (no authority list to correct against); the collapsed
mapping is printed so the choice is auditable.

NOT computed, deliberately: basal area per hectare and stem density. Plot radius is not in
either CSV, and `Area` is the forest patch area per site (1-200 ha), not plot area. `Steepness`
is not used (values 0-190, 39 plots above 90).

JOIN
----
By geometry, never by name. A plot belongs to the polygon that covers its point (coordinates
from plot_key, 6 dp). Stand identity per layer:

  stands_merged     `stand_lbl`  (a stand clipped into pieces is still one stand)
  stands_snic       `snic_label`
  stands_dissolved  `unit_id`    (a connected same-cluster region is the unit by definition)

`bdist_m` is the distance from the plot to the nearest polygon of a DIFFERENT stand in that
layer, in local UTM. The AOI's outer edge is not counted as a stand boundary: GPS error there
moves a plot out of the analysis, not into another stand.

The raster sample written by the pipeline script is used as a cross-check: the vector stand
identity must agree with `stand_clusters` / `snic_clusters` at the plot pixel.

Run:  python odisha_phase2_3_join.py            (from odisha_script/ or the repo root)
Writes: phase2_plots_joined.csv, odisha_phase2_3_results.txt
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely import STRtree
from shapely.geometry import Point, shape
from shapely.ops import transform

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from odisha_phase1_0_clean import load_trees, loreys_height, top5_height  # noqa: E402
from odisha_phase2_0_aois import load_plot_points, utm_transformers  # noqa: E402

VECTOR_DIR = HERE / "phase2_vectors"
OUT = HERE / "phase2_plots_joined.csv"
RESULTS = HERE / "odisha_phase2_3_results.txt"

# short name -> config name. Order is the reporting order: primary arm first.
ARMS = {"v120": "odisha_v120_handcrafted",
        "current": "odisha_current_handcrafted",
        "alphaearth": "odisha_alphaearth"}
LAYERS = {"merged": ("stands_merged", "stand_lbl"),
          "snic": ("stands_snic", "snic_label"),
          "dissolved": ("stands_dissolved", "unit_id")}
SAL = "shorea robusta"

_lines: list[str] = []


def say(s: str = "") -> None:
    print(s)
    _lines.append(s)


def rule(title: str) -> None:
    say("")
    say("=" * 90)
    say(title)
    say("=" * 90)


# ---------------------------------------------------------------------- field side
def species_key(name: str) -> str:
    toks = re.sub(r"[_\s]+", " ", str(name)).strip().split(" ")
    return " ".join(toks[-2:]).lower() if len(toks) >= 3 else " ".join(toks).lower()


def field_table() -> pd.DataFrame:
    s, n_raw = load_trees(HERE / "Odisha_samples.csv")
    s["species"] = s["Scientific Name"].map(species_key)
    s["is_tree"] = s["Habit"].astype(str).str.lower().eq("tree")

    rule("FIELD TABLE")
    say(f"  records: {n_raw} raw -> {len(s)} after GPS filter; plots: {s.plot_key.nunique()}")
    say(f"  Habit: {s.Habit.value_counts().to_dict()}")
    say(f"  species strings: {s['Scientific Name'].nunique()} raw -> {s.species.nunique()} normalised")
    collapsed = s.groupby("species")["Scientific Name"].unique()
    collapsed = collapsed[collapsed.map(len) > 1]
    say(f"  {len(collapsed)} normalised name(s) collapse more than one raw string:")
    for sp, raws in collapsed.items():
        say(f"    {sp:<28} <- {sorted(raws)}")

    grp = s.groupby("plot_key")
    trees = s[s.is_tree].groupby("plot_key")
    plots = pd.DataFrame({
        "n_records": grp.size(),
        "n_trees": s.groupby("plot_key").is_tree.sum().astype(int),
        "loreys_h_m": grp.apply(loreys_height, include_groups=False),
        "loreys_h_tree_m": trees.apply(loreys_height, include_groups=False),
        "h_top5_m": grp.apply(top5_height, include_groups=False),
        "crown_cover_pct": grp.crown_cover_pct.median(),
        "sal_ba_frac": grp.apply(lambda g: g.loc[g.species == SAL, "ba_cm2"].sum() / g.ba_cm2.sum(),
                                 include_groups=False),
        "n_species": trees.species.nunique(),
        "dbh_mean_cm": trees.DBH.mean(),
    })
    plots["no_tree_record"] = plots.n_trees.eq(0)
    plots["n_species"] = plots.n_species.fillna(0).astype(int)
    ba = s.groupby(["plot_key", "species"]).ba_cm2.sum()
    plots["sp_ba_json"] = pd.Series({k: json.dumps({sp: round(v, 3) for sp, v in g.droplevel(0).items()})
                                     for k, g in ba.groupby(level=0)})
    plots = plots.reset_index()

    clean = pd.read_csv(HERE / "odisha_plots_clean.csv")
    chk = plots.merge(clean[["plot_key", "loreys_h_m", "h_top5_m", "crown_cover_pct"]],
                      on="plot_key", suffixes=("", "_p1"), validate="1:1")
    for c in ["loreys_h_m", "h_top5_m", "crown_cover_pct"]:
        dev = (chk[c].round(4) - chk[f"{c}_p1"]).abs().max()
        say(f"  {c:<16} max |phase2 - phase1| = {dev:.2e}")
        assert dev < 1e-3, f"{c} does not reproduce odisha_plots_clean.csv"

    nt = plots[plots.no_tree_record]
    say(f"  plots with no Tree record: {len(nt)}")
    diff = (plots.loreys_h_m - plots.loreys_h_tree_m).abs()
    say(f"  |Lorey's all-habit - tree-only|: median {diff.median():.2f} m, p90 {diff.quantile(.9):.2f} m, "
        f"max {diff.max():.2f} m (n={int(diff.notna().sum())})")
    tree_ba = s.loc[s.is_tree, "ba_cm2"].sum() / s.ba_cm2.sum()
    say(f"  Tree records carry {tree_ba:.1%} of basal area")
    say(f"  plots with any Sal basal area: {int((plots.sal_ba_frac > 0).sum())}; "
        f"with sal_ba_frac > 0.5: {int((plots.sal_ba_frac > 0.5).sum())}")
    return plots


# ---------------------------------------------------------------------- join
def load_layer(path: Path, id_field: str, fwd) -> pd.DataFrame:
    gj = json.loads(path.read_text())
    rows = []
    for f in gj["features"]:
        p = f["properties"]
        rows.append({"sid": int(float(p[id_field])),
                     "cluster_id": p.get("cluster_id"),
                     "area_ha": p.get("area_ha"),
                     "geom": transform(fwd, shape(f["geometry"]))})
    return pd.DataFrame(rows)


def join_layer(pts: pd.DataFrame, layer: pd.DataFrame, fwd) -> pd.DataFrame:
    geoms = list(layer.geom)
    tree = STRtree(geoms)
    out = []
    n_ambiguous = 0
    for k, lo, la in zip(pts.plot_key, pts.lon6, pts.lat6):
        pt = Point(fwd(lo, la))
        hits = [i for i in tree.query(pt, predicate="covered_by")]
        if not hits:
            out.append((k, np.nan, np.nan, np.nan, np.nan))
            continue
        sids = sorted({int(layer.sid.iat[i]) for i in hits})
        n_ambiguous += len(sids) > 1
        i = min(hits, key=lambda h: (layer.sid.iat[h]))
        sid = int(layer.sid.iat[i])
        # stand area: all pieces of the stand
        area = float(layer.loc[layer.sid == sid, "area_ha"].astype(float).sum())
        near = tree.query(pt.buffer(1000))
        others = [geoms[j].distance(pt) for j in near if int(layer.sid.iat[j]) != sid]
        bdist = min(others) if others else np.inf
        cid = layer.cluster_id.iat[i]
        out.append((k, sid, np.nan if cid is None else float(cid), area, bdist))
    df = pd.DataFrame(out, columns=["plot_key", "id", "cluster", "area_ha", "bdist_m"])
    df.attrs["n_ambiguous"] = n_ambiguous
    return df


def distribution(col: pd.Series) -> dict:
    counts = col.dropna().value_counts()
    return {
        "stands_with_plots": int(len(counts)),
        "plots_assigned": int(counts.sum()),
        "multi_plot_stands": int((counts >= 2).sum()),
        "plots_in_multi": int(counts[counts >= 2].sum()),
        "hist": counts.value_counts().sort_index().to_dict(),
    }


def main() -> int:
    plots = field_table()
    pts = load_plot_points()
    table = pts[["plot_key", "lat6", "lon6", "district", "block", "habitation", "site_polygon"]].merge(
        plots, on="plot_key", validate="1:1")

    rule("JOIN — plots to stands by geometry")
    ran = {a: c for a, c in ARMS.items() if (VECTOR_DIR / f"{c}_stands_merged.geojson").exists()}
    missing = sorted(set(ARMS) - set(ran))
    if missing:
        say(f"  NOTE: no vectors yet for {missing}; their columns are omitted")
    lon0, lat0 = table.lon6.mean(), table.lat6.mean()
    for arm, cfg in ran.items():
        run = json.loads((VECTOR_DIR / f"{cfg}_run.json").read_text())
        raster = pd.read_csv(VECTOR_DIR / f"{cfg}_raster_at_plots.csv")
        say("")
        say(f"  --- {arm} ({cfg}), fingerprint {run['fingerprint']}")
        md = run["merge_diagnostics"]
        say(f"  merge: {md['n_superpixels']} superpixels -> {md['n_stands']} stands; "
            f"pass-2 fallback merges {md['pass2_fallback_merges']} of {md['pass2_merges']}; "
            f"stands below min area {md['stands_below_min_area']}")
        for short, (layer_name, id_field) in LAYERS.items():
            path = VECTOR_DIR / f"{cfg}_{layer_name}.geojson"
            gj_first = json.loads(path.read_text())["features"]
            c = shape(gj_first[0]["geometry"]).centroid
            _, fwd, _ = utm_transformers(c.x, c.y)
            layer = load_layer(path, id_field, fwd)
            j = join_layer(table, layer, fwd)
            for col in ["id", "cluster", "area_ha", "bdist_m"]:
                table[f"{arm}_{short}_{col}"] = j[col].values
            d = distribution(table[f"{arm}_{short}_id"])
            areas = layer.groupby("sid").area_ha.sum().astype(float)
            say(f"  {layer_name:<17} {layer.sid.nunique():>5} stands ({len(layer)} polygons), area ha "
                f"p10 {areas.quantile(.1):.2f} / median {areas.median():.2f} / p90 {areas.quantile(.9):.2f}")
            say(f"      plots assigned {d['plots_assigned']}, in {d['stands_with_plots']} stands; "
                f"multi-plot stands {d['multi_plot_stands']} holding {d['plots_in_multi']} plots; "
                f"plots-per-stand histogram {d['hist']}; boundary-ambiguous plots {j.attrs['n_ambiguous']}")
            nb = table[f"{arm}_{short}_bdist_m"]
            say(f"      distance to another stand: median {nb.median():.0f} m; "
                f"plots > 30 m from a boundary {int((nb > 30).sum())}")
            if short in ("merged", "snic"):
                rcol = "stand_clusters" if short == "merged" else "snic_clusters"
                if short == "merged":
                    # stand_lbl is the merge's own stand id, i.e. the value of stand_clusters
                    m = table[["plot_key", f"{arm}_{short}_id"]].merge(raster[["plot_key", rcol]], on="plot_key")
                    agree = (m[f"{arm}_{short}_id"] == m[rcol]).sum()
                else:
                    m = table[["plot_key", f"{arm}_{short}_id"]].merge(raster[["plot_key", rcol]], on="plot_key")
                    agree = (m[f"{arm}_{short}_id"] == m[rcol]).sum()
                say(f"      raster cross-check: vector id == {rcol} at plot pixel for {agree} of {len(m)}")
        typed = table[f"{arm}_merged_cluster"].notna().sum()
        say(f"  plots whose merged stand carries a cluster_id: {typed} of "
            f"{int(table[f'{arm}_merged_id'].notna().sum())}")

    table.to_csv(OUT, index=False)
    say("")
    say(f"  wrote {OUT.name}: {len(table)} rows, {len(table.columns)} columns")
    RESULTS.write_text("\n".join(_lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
