"""
Phase 2, step 3 — the field-side plot table, and the plot <-> stand join.

FULLY OFFLINE. Reads Odisha_samples.csv through odisha_phase1_0_clean.load_trees, and the vector
layers odisha_phase2_2_run_pipeline.py pulled into phase2_vectors/.

THIS SCRIPT COMPUTES NO STATISTIC RELATING FIELD DATA TO STANDS. It builds the table and reports
how plots distribute over stands (a property of the geometry), because
PHASE2_PREDICTIONS.md has to be committed before any such statistic exists.

SETS (--set)
------------
  pilot      configs odisha_{v120_handcrafted,current_handcrafted,alphaearth}, AOI
             aois/odisha_dhenkanal_sites.geojson -> phase2_plots_joined.csv
  districts  configs odisha_<arm>_<district> for district in angul, dhenkanal, kendujhar, koraput,
             AOIs aois/odisha_habitations_<district>.geojson -> phase2_plots_joined_districts.csv
             The pipeline ran per district (the whole set's bounding box exceeds Earth Engine's
             export cap), so each district has its own stand ids and its own k-means. Stand ids
             are written as the pipeline wrote them; the statistics make them unique by
             (district, id).
An arm whose vector files are missing is skipped with a printed note (AlphaEarth may be missing).

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
"Sal_Shorea_robusta"). Names are split on underscores and spaces, a trailing '.' is stripped
from every token ("Eucalyptus spp." and "Eucalyptus_spp" are one taxon), and the key is the last
two tokens, lower-cased -- the binomial, since every multi-token name here is
"<local name> <Genus> <species>". One- and two-token names ("Other") are kept as they are.

After that rule, SPECIES_ALIASES maps a key to another key. It holds ONLY misspellings where the
correct spelling of the same binomial is itself present in the data, so the two keys are
certainly one taxon and leaving them apart would make two plots with the same tree look
compositionally different in Bray-Curtis. A misspelling with no correctly spelt twin in the data
("termanalia chebula") is left alone: renaming it changes no distance. Token-order swaps
("anacardium semecarpus" vs "semecarpus anacardium") are not misspellings and are not aliased.
Every application is printed so the choice is auditable.

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

If more than one stand covers a plot (a shared edge), the minimum stand id wins; the rotation
null in odisha_phase2_5_stats.py uses the same rule so observed and null assignments agree.

`cluster_id` is rounded to the nearest integer at load time. The stand's cluster is a GEE mode
reducer output and arrives as e.g. 4.9999999999999885; compared as floats, that stand and a stand
with cluster 5 would carry different labels, which silently split one k-means class into many.

`bdist_m` is the distance from the plot to the nearest polygon of a DIFFERENT stand in that
layer, searched within 1000 m (inf if none), in the local UTM zone of the AOI part holding the
plot. The AOI's outer edge is not counted as a stand boundary: GPS error there moves a plot out
of the analysis, not into another stand.

The raster sample written by the pipeline script is used as a cross-check: the vector stand
identity must agree with `stand_clusters` / `snic_clusters` at the plot pixel.

Run:  python odisha_phase2_3_join.py [--set pilot|districts] [--vectors-dir D] [--aoi-dir D] [--out-dir D]
      (from odisha_script/ or the repo root; the path options default to the paths above)
Writes: phase2_plots_joined[_districts].csv, odisha_phase2_3_results[_districts].txt
"""
from __future__ import annotations

import argparse
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
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from odisha_phase1_0_clean import load_trees, loreys_height, top5_height  # noqa: E402
from odisha_phase2_0_aois import load_plot_points, utm_transformers  # noqa: E402

VECTOR_DIR = HERE / "phase2_vectors"

# short name -> config name. Order is the reporting order: primary arm first.
# ALL_ARMS is the registry; ARMS is the set this run actually joins, and it is
# mutated IN PLACE by --arms so that modules which did `from ... import ARMS`
# (the statistics script) see the same object. DEFAULT_ARMS is the three arms the
# committed results were produced from, so the default output is unchanged.
ALL_ARMS = {"v120": "odisha_v120_handcrafted",
            "current": "odisha_current_handcrafted",
            "alphaearth": "odisha_alphaearth",
            # 2026-09-24: stands capped at 3 ha, which also needed finer
            # segmentation (seed spacing 6, not 10) because merge joins
            # superpixels and cannot split one.
            "v120_3ha": "odisha_v120_3ha"}
DEFAULT_ARMS = ("v120", "current", "alphaearth")
ARMS = {k: ALL_ARMS[k] for k in DEFAULT_ARMS}
LAYERS = {"merged": ("stands_merged", "stand_lbl"),
          "snic": ("stands_snic", "snic_label"),
          "dissolved": ("stands_dissolved", "unit_id")}
SAL = "shorea robusta"
DISTRICTS = ["angul", "dhenkanal", "kendujhar", "koraput"]
BDIST_SEARCH_M = 1000.0

# Applied after the last-two-token rule. Only misspellings whose correct twin is in the data.
SPECIES_ALIASES = {
    "cassia fistul": "cassia fistula",
    "lagerstroemia parviflor": "lagerstroemia parviflora",
    "zizyphus oenoplia": "ziziphus oenoplia",
}


def set_spec(name: str, aoi_dir: Path | None = None, out_dir: Path | None = None) -> dict:
    """Everything that differs between the pilot and the district set, in one place, so the join
    and the statistics cannot disagree about which configs, AOIs and files belong to a set.
    aoi_dir / out_dir default to REPO/aois and this script's directory (the joined CSV lives there)."""
    aoi_dir = Path(aoi_dir) if aoi_dir is not None else REPO / "aois"
    out_dir = Path(out_dir) if out_dir is not None else HERE
    if name == "pilot":
        return {"name": "pilot",
                "districts": [("pilot", aoi_dir / "odisha_dhenkanal_sites.geojson")],
                "config": lambda cfg, district: cfg,
                "joined": out_dir / "phase2_plots_joined.csv",
                "out_dir": out_dir,
                "suffix": ""}
    if name == "districts":
        return {"name": "districts",
                "districts": [(d, aoi_dir / f"odisha_habitations_{d}.geojson") for d in DISTRICTS],
                "config": lambda cfg, district: f"{cfg}_{district}",
                "joined": out_dir / "phase2_plots_joined_districts.csv",
                "out_dir": out_dir,
                "suffix": "_districts"}
    raise ValueError(f"unknown set {name!r}")


def vector_path(cfg: str, layer_name: str) -> Path:
    return VECTOR_DIR / f"{cfg}_{layer_name}.geojson"


def arm_districts(spec: dict, cfg0: str) -> list[tuple[str, str]]:
    """(district, config) pairs where this arm has EVERY layer file. The single presence rule: the
    join assigns plots only there, and the statistics load layers only there, so a district with a
    partial set of layer files is absent in both scripts (never loaded by one and not the other)."""
    return [(d, spec["config"](cfg0, d)) for d, _ in spec["districts"]
            if all(vector_path(spec["config"](cfg0, d), ln).exists() for ln, _ in LAYERS.values())]


def add_path_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--vectors-dir", type=Path, default=None, help="default: odisha_script/phase2_vectors")
    ap.add_argument("--aoi-dir", type=Path, default=None, help="default: <repo>/aois")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="where the joined CSV and results are written (and read by the stats); default: odisha_script/")
    ap.add_argument("--arms", default=None,
                    help=f"comma-separated subset of {','.join(ALL_ARMS)}; "
                         f"default {','.join(DEFAULT_ARMS)}, the arms the committed results came from")


def apply_path_args(args) -> dict:
    global VECTOR_DIR
    if getattr(args, "arms", None):
        want = [a.strip() for a in str(args.arms).split(",") if a.strip()]
        unknown = [a for a in want if a not in ALL_ARMS]
        if unknown:
            raise SystemExit(f"--arms: unknown {unknown}; known: {sorted(ALL_ARMS)}")
        ARMS.clear()                      # in place: the stats script holds this object
        ARMS.update({k: ALL_ARMS[k] for k in want})
    if args.vectors_dir is not None:
        VECTOR_DIR = Path(args.vectors_dir).resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir is not None else None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
    return set_spec(args.set, aoi_dir=args.aoi_dir, out_dir=out_dir)


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
def _first_run_key(name: str) -> str:
    """The first run's rule (git 8d4c2ed), kept only to report which plots the correction touches."""
    toks = re.sub(r"[_\s]+", " ", str(name)).strip().split(" ")
    return " ".join(toks[-2:]).lower() if len(toks) >= 3 else " ".join(toks).lower()


def species_key_raw(name: str) -> str:
    """The last-two-token rule, with a trailing '.' stripped from each token. No aliases."""
    toks = [t.rstrip(".") for t in re.sub(r"[_\s]+", " ", str(name)).strip().split(" ")]
    toks = [t for t in toks if t]
    return " ".join(toks[-2:]).lower() if len(toks) >= 3 else " ".join(toks).lower()


def species_key(name: str) -> str:
    k = species_key_raw(name)
    return SPECIES_ALIASES.get(k, k)


def field_table() -> pd.DataFrame:
    s, n_raw = load_trees(HERE / "Odisha_samples.csv")
    s["species_raw_key"] = s["Scientific Name"].map(species_key_raw)
    s["species"] = s["species_raw_key"].map(lambda k: SPECIES_ALIASES.get(k, k))
    s["is_tree"] = s["Habit"].astype(str).str.lower().eq("tree")

    rule("FIELD TABLE")
    say(f"  records: {n_raw} raw -> {len(s)} after GPS filter; plots: {s.plot_key.nunique()}")
    say(f"  Habit: {s.Habit.value_counts().to_dict()}")
    say(f"  species strings: {s['Scientific Name'].nunique()} raw -> {s.species_raw_key.nunique()} by the token rule "
        f"-> {s.species.nunique()} after aliases")
    dotted = s.loc[s["Scientific Name"].astype(str).str.contains(r"\.\s*$|\.[_\s]", regex=True), "Scientific Name"].unique()
    say(f"  trailing '.' stripped from: {sorted(dotted)}")
    say("  alias applications (key by the token rule -> alias; records; plots; raw strings):")
    for src, dst in SPECIES_ALIASES.items():
        m = s.species_raw_key == src
        if not m.any():
            say(f"    {src:<26} -> {dst:<26} NOT FOUND in the data")
            continue
        assert (s.species_raw_key == dst).any(), f"alias target {dst!r} is not in the data; the alias is not justified"
        say(f"    {src:<26} -> {dst:<26} {int(m.sum()):>4} records, {s.loc[m, 'plot_key'].nunique():>3} plots; "
            f"{sorted(s.loc[m, 'Scientific Name'].unique())}")
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
    # plots whose species keys differ from the first run's rule (no '.'-strip, no aliases)
    changed = s.species != s["Scientific Name"].map(_first_run_key)
    plots.attrs["aliased_plots"] = sorted(s.loc[changed, "plot_key"].unique())

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
        cid = p.get("cluster_id")
        rows.append({"sid": int(float(p[id_field])),
                     # rounded: GEE's mode reducer returns 4.9999999999999885 for class 5
                     "cluster_id": None if cid is None else float(np.rint(float(cid))),
                     "area_ha": p.get("area_ha"),
                     "geom": transform(fwd, shape(f["geometry"]))})
    return pd.DataFrame(rows)


def aoi_parts(path: Path) -> list:
    feat = json.loads(path.read_text())["features"][0]
    return list(shape(feat["geometry"]).geoms)


def join_layer(pts: pd.DataFrame, path: Path, id_field: str, epsg_of_plot: np.ndarray) -> pd.DataFrame:
    """Join every plot to the layer at `path`, each plot in the UTM zone given for it."""
    out = [None] * len(pts)
    n_ambiguous = 0
    for epsg in np.unique(epsg_of_plot):
        sel = np.where(epsg_of_plot == epsg)[0]
        fwd = Transformer.from_crs(4326, int(epsg), always_xy=True).transform
        layer = load_layer(path, id_field, fwd)
        geoms = list(layer.geom)
        tree = STRtree(geoms)
        for r in sel:
            k, lo, la = pts.plot_key.iat[r], pts.lon6.iat[r], pts.lat6.iat[r]
            pt = Point(fwd(lo, la))
            hits = [i for i in tree.query(pt, predicate="covered_by")]
            if not hits:
                out[r] = (k, np.nan, np.nan, np.nan, np.nan)
                continue
            sids = sorted({int(layer.sid.iat[i]) for i in hits})
            n_ambiguous += len(sids) > 1
            i = min(hits, key=lambda h: (layer.sid.iat[h]))
            sid = int(layer.sid.iat[i])
            # stand area: all pieces of the stand
            area = float(layer.loc[layer.sid == sid, "area_ha"].astype(float).sum())
            near = tree.query(pt, predicate="dwithin", distance=BDIST_SEARCH_M)
            others = [geoms[j].distance(pt) for j in near if int(layer.sid.iat[j]) != sid]
            bdist = min(others) if others else np.inf
            cid = layer.cluster_id.iat[i]
            out[r] = (k, sid, np.nan if cid is None else float(cid), area, bdist)
    df = pd.DataFrame(out, columns=["plot_key", "id", "cluster", "area_ha", "bdist_m"])
    df.attrs["n_ambiguous"] = n_ambiguous
    df.attrs["layer_sids"] = None
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["pilot", "districts"], default="pilot")
    add_path_args(ap)
    args = ap.parse_args()
    spec = apply_path_args(args)
    out_csv = spec["joined"]
    results = spec["out_dir"] / f"odisha_phase2_3_results{spec['suffix']}.txt"

    plots = field_table()
    pts = load_plot_points()
    table = pts[["plot_key", "lat6", "lon6", "district", "block", "habitation", "site_polygon"]].merge(
        plots, on="plot_key", validate="1:1")

    rule(f"JOIN — plots to stands by geometry (set: {spec['name']})")
    P = len(table)
    ll = [Point(lo, la) for lo, la in zip(table.lon6, table.lat6)]
    plot_district = np.array([""] * P, dtype=object)
    plot_epsg = np.array([utm_transformers(lo, la)[0] for lo, la in zip(table.lon6, table.lat6)])
    for district, aoi_path in spec["districts"]:
        for part in aoi_parts(aoi_path):
            c = part.centroid
            epsg = utm_transformers(c.x, c.y)[0]
            inside = np.array([part.covers(q) for q in ll])
            plot_district[inside] = district
            plot_epsg[inside] = epsg  # per-part local UTM for boundary distances
    say(f"  plots inside the set's AOIs: {int((plot_district != '').sum())} of {P}; by district "
        f"{pd.Series(plot_district[plot_district != '']).value_counts().to_dict()}")
    if plots.attrs.get("aliased_plots"):
        inset = set(table.plot_key[plot_district != ""])
        hit = [k for k in plots.attrs["aliased_plots"] if k in inset]
        say(f"  plots in this set holding a record whose key an alias or '.'-strip changed: {len(hit)} {hit}")

    for arm, cfg0 in ARMS.items():
        for short in LAYERS:
            for col in ["id", "cluster", "area_ha", "bdist_m"]:
                table[f"{arm}_{short}_{col}"] = np.nan
        present = arm_districts(spec, cfg0)
        missing = [d for d, _ in spec["districts"] if d not in {p[0] for p in present}]
        if not present:
            say("")
            say(f"  NOTE: no vectors for {arm} ({cfg0}) in any district of this set; its columns are omitted")
            table = table.drop(columns=[f"{arm}_{s}_{c}" for s in LAYERS for c in ["id", "cluster", "area_ha", "bdist_m"]])
            continue
        if missing:
            say(f"  NOTE: {arm} has no vectors for {missing}; its plots there stay unassigned")
        for district, cfg in present:
            run_path = VECTOR_DIR / f"{cfg}_run.json"
            say("")
            if run_path.exists():
                run = json.loads(run_path.read_text())
                say(f"  --- {arm} ({cfg}), fingerprint {run['fingerprint']}")
                md = run["merge_diagnostics"]
                say(f"  merge: {md['n_superpixels']} superpixels -> {md['n_stands']} stands; "
                    f"pass-2 fallback merges {md['pass2_fallback_merges']} of {md['pass2_merges']}; "
                    f"stands below min area {md['stands_below_min_area']}")
            else:
                say(f"  --- {arm} ({cfg}): NOTE {run_path.name} missing; fingerprint and merge diagnostics not shown")
            raster_path = VECTOR_DIR / f"{cfg}_raster_at_plots.csv"
            raster = pd.read_csv(raster_path) if raster_path.exists() else None
            # pilot: every plot is joined (as the first run did); districts: plots of this district only,
            # so a neighbouring district's layer can never claim a plot
            rows = np.arange(P) if spec["name"] == "pilot" else np.where(plot_district == district)[0]
            sub = table.iloc[rows]
            for short, (layer_name, id_field) in LAYERS.items():
                path = vector_path(cfg, layer_name)
                j = join_layer(sub, path, id_field, plot_epsg[rows])
                for col in ["id", "cluster", "area_ha", "bdist_m"]:
                    table.loc[table.index[rows], f"{arm}_{short}_{col}"] = j[col].values
                d = distribution(table.iloc[rows][f"{arm}_{short}_id"])
                layer = load_layer(path, id_field, lambda x, y: (x, y))
                areas = layer.groupby("sid").area_ha.sum().astype(float)
                say(f"  {layer_name:<17} {layer.sid.nunique():>5} stands ({len(layer)} polygons), area ha "
                    f"p10 {areas.quantile(.1):.2f} / median {areas.median():.2f} / p90 {areas.quantile(.9):.2f}")
                say(f"      plots assigned {d['plots_assigned']}, in {d['stands_with_plots']} stands; "
                    f"multi-plot stands {d['multi_plot_stands']} holding {d['plots_in_multi']} plots; "
                    f"plots-per-stand histogram {d['hist']}; boundary-ambiguous plots {j.attrs['n_ambiguous']}")
                nb = table.iloc[rows][f"{arm}_{short}_bdist_m"]
                say(f"      distance to another stand: median {nb.median():.0f} m; "
                    f"plots > 30 m from a boundary {int((nb > 30).sum())}")
                if short in ("merged", "snic") and raster is not None:
                    # stand_lbl is the merge's own stand id, i.e. the value of stand_clusters
                    rcol = "stand_clusters" if short == "merged" else "snic_clusters"
                    m = table.iloc[rows][["plot_key", f"{arm}_{short}_id"]].merge(raster[["plot_key", rcol]], on="plot_key")
                    m = m[m[f"{arm}_{short}_id"].notna()] if spec["name"] != "pilot" else m
                    agree = (m[f"{arm}_{short}_id"] == m[rcol]).sum()
                    say(f"      raster cross-check: vector id == {rcol} at plot pixel for {agree} of {len(m)}")
            sub = table.iloc[rows]
            typed = sub[f"{arm}_merged_cluster"].notna().sum()
            nonint = (sub[f"{arm}_merged_cluster"].dropna() % 1 != 0).sum()
            say(f"  plots whose merged stand carries a cluster_id: {typed} of "
                f"{int(sub[f'{arm}_merged_id'].notna().sum())}; cluster values after rounding "
                f"{sorted(sub[f'{arm}_merged_cluster'].dropna().unique().tolist())} (non-integer: {nonint})")

    table.to_csv(out_csv, index=False)
    say("")
    say(f"  wrote {out_csv.name}: {len(table)} rows, {len(table.columns)} columns")
    results.write_text("\n".join(_lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
