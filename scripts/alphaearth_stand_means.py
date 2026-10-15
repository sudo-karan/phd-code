"""The named feature means of the AlphaEarth Sanjay Van kept-land stands, by one read-only reduction.

    python scripts/alphaearth_stand_means.py --plan     # offline: what it would reduce, over what
    python scripts/alphaearth_stand_means.py            # Earth Engine, read-only: reduce and write

Why. The export stage averages only the embedding over an AlphaEarth run's stands, so the stand
layer of sanjay_van_alphaearth_keptland holds A00 to A63 and no named measurement (canopy height,
greenness and so on; docs/handoff/2026-10-15-round6.md, step 5 a). Jaskaran, 15 Oct 2026, round 7,
his answer (b) to its question 5: add them with one read-only reduction, the file saying that the
radar and static means are the baseline run's (docs/decisions.yaml,
spec-ui-alphaearth-stands-named-means-by-reduction).

What. Four cached feature images are put together: the AlphaEarth run's own optical and structure
images, which the arm computes for the merge, and the baseline kept-land run's radar and static
images of the same rectangle, since the AlphaEarth arm computes neither. They are taken by path
from round 5's copy record, docs/reproducibility/keptland_reuse.json. The image is reduced with the
mean, at export.analysis_scale_m (10 m), over each polygon of the committed stand layer, as the
export stage reduces a hand-crafted run's images over its stands (the same bands; the observation
counts left out). One request reads the means back (559 polygons, under Earth Engine's 5,000).

Read-only: `ee_read_only.forbid_writes()` runs before any other Earth Engine call, so no task is
submitted and no asset is written.

The result, docs/reproducibility/keptland_runs/sanjay_van_alphaearth_keptland_stand_means.json,
holds results only: per polygon of the stand layer (stand_id, stand_lbl) the mean of each band,
and per band the run and image it came from, with the note that the radar and static means are
the baseline run's. Beside it, `..._stand_means_run.json` holds the command, the date, the git
commit and whether the tree was dirty.
"""

from __future__ import annotations

import argparse
import datetime
import json
import shlex
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))  # this checkout's fmu
sys.path.insert(0, str(REPO / "scripts"))  # ee_read_only

RUN = "sanjay_van_alphaearth_keptland"
BASELINE = "sanjay_van_baseline_keptland"
KEPTLAND = REPO / "docs" / "reproducibility" / "keptland_runs"
COPIES = REPO / "docs" / "reproducibility" / "keptland_reuse.json"
OUT = KEPTLAND / f"{RUN}_stand_means.json"
# (whose run, stage): the AlphaEarth run's own optical and structure, the baseline's radar, static.
SOURCES = ((RUN, "features_optical"), (RUN, "features_structure"),
           (BASELINE, "features_radar"), (BASELINE, "features_static"))
# Left out of the means, as the export stage leaves them out of a stand's feature means.
EXCLUDED = ("ndvi_obs_count", "nirv_obs_count")
NOTE = (f"The radar and static means are the baseline kept-land run's ({BASELINE}): the AlphaEarth "
        f"arm computes no radar or static features. The optical and structure means are the "
        f"AlphaEarth run's own ({RUN}). All are means over the AlphaEarth run's stand polygons.")


def plan(copies_path: Path = COPIES, keptland: Path = KEPTLAND) -> dict[str, Any]:
    """The four images (by path, from the copy record) and the stand layer. Offline."""
    copies = json.loads(copies_path.read_text())["copies"]
    images = []
    for run, stage in SOURCES:
        found = [c["destination"] for c in copies if c["config"] == run and c["stage"] == stage]
        if len(found) != 1:
            raise SystemExit(f"{copies_path}: {len(found)} copies of {run} {stage}, not one")
        images.append({"run": run, "stage": stage, "asset": found[0]})
    layer = keptland / f"{RUN}_stands_merged.geojson"
    n = len(json.loads(layer.read_text())["features"])
    from fmu.config import load_config

    scale = load_config(REPO / "configs" / f"{RUN}.yaml").export.analysis_scale_m
    return {"images": images, "stand_layer": str(layer.relative_to(REPO)), "n_polygons": n,
            "scale_m": scale}


def reduce_in_earth_engine(p: dict[str, Any]) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    """Reduce the images over the stand polygons; return each image's bands and the read-back
    features (properties stand_id, stand_lbl and one mean per band). Read-only."""
    import ee

    from fmu.utils.gee import init_gee

    init_gee()
    import ee_read_only

    ee_read_only.forbid_writes()
    bands = {}
    parts = []
    for img in p["images"]:
        image = ee.Image(img["asset"])
        names = [b for b in image.bandNames().getInfo() if b not in EXCLUDED]
        bands[img["asset"]] = names
        parts.append(image.select(names))
    layer = json.loads((REPO / p["stand_layer"]).read_text())
    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry(f["geometry"]), {"stand_id": f["properties"]["stand_id"],
                                                "stand_lbl": f["properties"]["stand_lbl"]})
        for f in layer["features"]])
    out = ee.Image.cat(parts).reduceRegions(collection=fc, reducer=ee.Reducer.mean(),
                                            scale=p["scale_m"])
    return bands, out.getInfo()["features"]


def result(p: dict[str, Any], bands: dict[str, list[str]],
           features: list[dict[str, Any]]) -> dict[str, Any]:
    """The result file's content: the means per polygon, in the stand layer's order."""
    by_band = {}
    for img in p["images"]:
        for b in bands[img["asset"]]:
            if b in by_band:
                raise SystemExit(f"band {b} in two images")
            by_band[b] = {"run": img["run"], "stage": img["stage"], "asset": img["asset"]}
    layer = json.loads((REPO / p["stand_layer"]).read_text())["features"]
    got = {f["properties"]["stand_id"]: f["properties"] for f in features}
    if set(got) != {f["properties"]["stand_id"] for f in layer}:
        raise SystemExit("the polygons read back are not the stand layer's")
    stands = []
    for f in layer:
        sid = f["properties"]["stand_id"]
        stands.append({"stand_id": sid, "stand_lbl": f["properties"]["stand_lbl"],
                       **{b: got[sid].get(b) for b in by_band}})
    return {"what": f"The mean of each named feature over each stand polygon of {RUN} "
                    f"({p['stand_layer']}), by one read-only reduceRegions (mean, "
                    f"{p['scale_m']} m) over cached feature images; "
                    "spec-ui-alphaearth-stands-named-means-by-reduction.",
            "note": NOTE, "bands": by_band, "n_polygons": len(stands), "stands": stands}


def write_run_record(out: Path, argv: list[str], *, completed: bool) -> None:
    from fmu.utils.provenance import git_state

    run = {"result_file": out.name,
           "command_line": "python " + " ".join(shlex.quote(a) for a in
                                                ["scripts/alphaearth_stand_means.py", *argv]),
           "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
           "git": {k: v for k, v in git_state().items() if k != "root"},
           "completed": completed}
    out.with_name(out.stem + "_run.json").write_text(json.dumps(run, indent=1) + "\n")


def main(argv: list[str] | None = None,
         reducer: Callable[[dict[str, Any]], tuple[dict, list]] = reduce_in_earth_engine) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--plan", action="store_true", help="offline: print what would be reduced")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    argv = list(sys.argv[1:] if argv is None else argv)
    p = plan()
    for img in p["images"]:
        print(f"  {img['stage']} of {img['run']}: {img['asset']}")
    print(f"  over the {p['n_polygons']} polygons of {p['stand_layer']}, mean at {p['scale_m']} m")
    if args.plan:
        print("plan only: no Earth Engine call")
        return 0
    write_run_record(args.out, argv, completed=False)
    bands, features = reducer(p)
    res = result(p, bands, features)
    args.out.write_text(json.dumps(res, indent=1) + "\n")
    write_run_record(args.out, argv, completed=True)
    print(f"wrote {args.out}: {res['n_polygons']} polygons, {len(res['bands'])} bands; "
          f"export tasks submitted: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
