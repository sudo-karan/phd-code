"""How many stands of a run's exported layer would change type if each took its row's type? Offline.

    python scripts/stand_types_from_fit_rows.py --runs-dir docs/reproducibility/r9_runs \
        --out docs/reproducibility/r9_runs/stand_types_from_fit_rows.json RUN [RUN ...]

Round 12, Task 2 (roadmap 3.2, issue #44 item 12; register entry
spec-export-stand-type-from-its-fit-row). Until round 12 the export typed each stand polygon by a
vote over the typed pixels it touches; since then a stand with a row in the k-means fit takes
the type most of its own typed pixels carry, which is its row's type (src/fmu/stages/export.py,
_stand_row_types, says when it is not quite). So the change alters a polygon's type exactly where
the stand's own pixels say something other than the polygon's vote.

The run's own pixels are not in its committed files, but its superpixels are: the export pass
writes every superpixel with a typed pixel to `stands_snic`, typed by the same vote over its own
polygon, and every superpixel lies inside one stand. So, per run:

  1. Both layers, and `stands_dissolved`, which the export vectorises from the type image in that
     image's own grid, are projected to the run's analysis grid (the UTM zone of its ROI's
     midpoint, fmu.utils.grid.utm_epsg_code) and every vertex is checked to lie on the grid's
     10 m pixel edges. Where all do, the polygons and the type image share one pixel grid: a
     polygon covers whole pixels of its own unit only, so each vote is over the unit's own pixels,
     and a superpixel's type is the type of its pixels.
  2. Each superpixel is placed in the stand its polygon overlaps most, by area.
  3. A stand's own type is the commonest type over the area of its superpixels: the commonest
     type over its typed pixels. A polygon (a piece of a stand) WOULD CHANGE when its exported
     type is not its stand's own type (an untyped polygon, when its stand has a typed
     superpixel), unless the stand was left out of the fit (below merge.min_area_ha with
     clustering.fit_excludes_stands_below_min_area on): the export leaves those on the vote
     (question 2 of docs/handoff/2026-10-19-round12.md), and they are counted apart. A stand none
     of whose superpixels is in the layer is UNCHECKED.

(Note of 20 Oct 2026, round 13: this counts round 12's export. Since round 13 a stand left out
of the fit takes its own row's type too, and a stand with no typed pixel of its own gets a null
type (register entry spec-export-stand-type-from-its-own-row-or-null); so under round 13's export
the stands left out whose type is not their own, counted apart here, would change as well.)

Layers over 5 MB are read where the run's <run>_files_off_git.json says, after checking their
SHA-256. Results only, no dates; nothing is written over. Earth Engine is not used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform
from shapely.strtree import STRtree

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from fmu.utils.grid import utm_epsg_code  # noqa: E402

SCALE_M = 10.0
GRID_TOLERANCE_M = 1e-3


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def layer_path(run: str, layer: str, runs_dir: Path) -> tuple[Path, str]:
    """The run's layer file and where it was found: in runs_dir, or off git, checked."""
    name = f"{run}_stands_{layer}.geojson"
    if (runs_dir / name).exists():
        return runs_dir / name, "committed"
    record = runs_dir / f"{run}_files_off_git.json"
    if not record.exists():
        raise SystemExit(f"{run}: no {name} in {runs_dir} and no off-git record")
    entry = {f["file"]: f for f in json.loads(record.read_text())["files"]}.get(name)
    if entry is None:
        raise SystemExit(f"{run}: {name} is neither in {runs_dir} nor in its off-git record")
    where = Path(entry["where"])
    if not where.exists():
        raise SystemExit(f"{run}: {name} is off git at {where}, which is not here")
    if sha256(where) != entry["sha256"]:
        raise SystemExit(f"{run}: {where} is not the file its record names (SHA-256 differs)")
    return where, "off git, SHA-256 checked"


def grid_epsg(run: str) -> int:
    """The UTM zone of the run's analysis grid: from its config's ROI file, as fmu.utils.grid picks it."""
    cfg = yaml.safe_load((REPO / "configs" / f"{run}.yaml").read_text())
    roi = json.loads((REPO / cfg["roi"]["roi_file"]).read_text())
    xs, ys = [], []
    for f in roi["features"]:
        b = shape(f["geometry"]).bounds
        xs += [b[0], b[2]]
        ys += [b[1], b[3]]
    return utm_epsg_code((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def fit_excludes(run: str) -> bool:
    """Whether the run's config left the stands below merge.min_area_ha out of the k-means fit."""
    cfg = yaml.safe_load((REPO / "configs" / f"{run}.yaml").read_text())
    return bool((cfg.get("clustering") or {}).get("fit_excludes_stands_below_min_area", False))


def read_layer(path: Path, epsg: int, id_field: str) -> list[dict[str, Any]]:
    to_utm = Transformer.from_crs(4326, epsg, always_xy=True).transform
    out = []
    for f in json.loads(path.read_text())["features"]:
        if not f.get("geometry"):
            continue
        out.append({"id": f["properties"].get(id_field), "type": f["properties"].get("cluster_id"),
                    "geom": transform(to_utm, shape(f["geometry"]))})
    return out


def grid_offsets(polygons: list[dict[str, Any]]) -> tuple[int, int, float]:
    """(vertices, vertices off the 10 m grid, largest offset in metres)."""
    n, off, worst = 0, 0, 0.0
    for p in polygons:
        geoms = getattr(p["geom"], "geoms", [p["geom"]])
        for g in geoms:
            for ring in [g.exterior, *g.interiors]:
                for x, y in ring.coords:
                    d = max(abs(x - SCALE_M * round(x / SCALE_M)), abs(y - SCALE_M * round(y / SCALE_M)))
                    n += 1
                    worst = max(worst, d)
                    off += d > GRID_TOLERANCE_M
    return n, off, worst


def count(run: str, runs_dir: Path) -> dict[str, Any]:
    epsg = grid_epsg(run)
    merged_path, merged_where = layer_path(run, "merged", runs_dir)
    snic_path, snic_where = layer_path(run, "snic", runs_dir)
    dissolved_path, dissolved_where = layer_path(run, "dissolved", runs_dir)
    stands = read_layer(merged_path, epsg, "stand_lbl")
    superpixels = read_layer(snic_path, epsg, "snic_label")
    type_regions = read_layer(dissolved_path, epsg, "unit_id")
    record = json.loads((runs_dir / f"{run}_run.json").read_text())
    left_out = ({int(s) for s, p in record["stand_provenance"].items() if p["below_min"]}
                if fit_excludes(run) else set())

    pieces: dict[int, list[Any]] = {}
    for s in stands:
        pieces.setdefault(int(s["id"]), []).append(s["type"])
    tree = STRtree([s["geom"] for s in stands])
    area_by_type: dict[int, dict[Any, float]] = {}
    unplaced = 0
    for sp in superpixels:
        overlaps = [(stands[i]["geom"].intersection(sp["geom"]).area, int(stands[i]["id"]))
                    for i in tree.query(sp["geom"], predicate="intersects")]
        overlaps = [o for o in overlaps if o[0] > 0]
        if not overlaps:
            unplaced += 1
            continue
        sid = max(overlaps)[1]
        if sp["type"] is not None:
            per = area_by_type.setdefault(sid, {})
            per[sp["type"]] = per.get(sp["type"], 0.0) + sp["geom"].area

    changed, changed_pieces, left_out_differing, unchecked, untyped_with_type = [], 0, [], [], []
    for sid, types in sorted(pieces.items()):
        own = area_by_type.get(sid, {})
        if not own:
            if any(t is not None for t in types):
                unchecked.append(sid)
            continue
        top = max(own.values())
        own_type = min(t for t, a in own.items() if a == top)
        n = sum(1 for t in types if t != own_type)
        if not n:
            continue
        if sid in left_out:
            left_out_differing.append(sid)
            continue
        changed.append(sid)
        changed_pieces += n
        if all(t is None for t in types):
            untyped_with_type.append(sid)
    n_v, n_off, worst = grid_offsets(stands + superpixels)
    t_v, t_off, t_worst = grid_offsets(type_regions)
    return {
        "analysis_grid": f"EPSG:{epsg}, {SCALE_M:g} m",
        "layers": {"stands_merged": merged_where, "stands_snic": snic_where,
                   "stands_dissolved": dissolved_where},
        "stand_polygons": len(stands),
        "stands": len(pieces),
        "stands_typed": sum(1 for t in pieces.values() if any(x is not None for x in t)),
        "stands_in_several_pieces": sum(1 for t in pieces.values() if len(t) > 1),
        "stands_in_several_pieces_of_different_types": sum(1 for t in pieces.values() if len(set(t)) > 1),
        "superpixel_polygons": len(superpixels),
        "superpixels_in_no_stand": unplaced,
        "vertices": n_v,
        "vertices_off_the_grid": n_off,
        "largest_vertex_offset_m": round(worst, 6),
        "type_image_vertices": t_v,
        "type_image_vertices_off_the_grid": t_off,
        "type_image_largest_vertex_offset_m": round(t_worst, 6),
        "typed_stands_checked": sum(1 for sid, t in pieces.items()
                                    if any(x is not None for x in t) and sid not in unchecked),
        "typed_stands_unchecked": len(unchecked),
        "stands_that_would_change_type": len(changed),
        "polygons_that_would_change_type": changed_pieces,
        "untyped_stands_with_a_typed_superpixel": len(untyped_with_type),
        "stands_left_out_of_the_fit": len(left_out & set(pieces)),
        "left_out_stands_whose_type_is_not_their_own": len(left_out_differing),
        "changed_stand_labels": changed,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--runs-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.out.exists():
        raise SystemExit(f"{args.out} exists; this script does not write over a result file")
    result = {
        "what": "Per run, how many stands of the exported stands_merged layer would change type under round 12's "
                "export, read offline from the run's stands_merged, stands_snic and stands_dissolved layers on its "
                "analysis grid (scripts/stand_types_from_fit_rows.py). A stand's own type is the commonest type over "
                "the area of the superpixels it holds; a polygon would change where its exported type is not its "
                "stand's own type, except for the stands left out of the fit, which the export leaves on the vote "
                "and which are counted apart.",
        "runs": {run: count(run, args.runs_dir) for run in args.runs},
    }
    args.out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({r: {k: v for k, v in c.items() if k != "changed_stand_labels"}
                      for r, c in result["runs"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
