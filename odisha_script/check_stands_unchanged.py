"""Did a re-run leave the stands where they were?

    python odisha_script/check_stands_unchanged.py [--arm odisha_v120_3ha] [--ref HEAD] [--expect-new-run]

Changing the number of stand types (clustering.k) must not move a single stand: k is read
when stands are given their type, after the stands exist. When the 3 hectare arm went from
6 types to 5 the earlier stages were not recomputed but copied (copy_upstream_cache.py), so
"the stands are the same" is true by construction only if nothing else changed. This script
checks it instead of assuming it.

For every district it compares the stand files on disk with the same files at a git ref:

  stands_snic    the building blocks (superpixels): same outlines?
  stands_merged  the stands: same outlines, and for each outline the same stand label and
                 the same area? How many changed stand TYPE (cluster_id), and how many
                 distinct types before and after?

Outlines are matched by their geometry, not by position in the file, so a different feature
order is not reported as a change.

It also reads the run record (<config>_run.json) and prints the cache fingerprint it was
written under, at the ref and on disk, next to the fingerprint of the config as it is now.
If the two run records carry the same fingerprint, the files on disk are still the old run's
and comparing them proves nothing. --expect-new-run turns that into a failure, which is how
this script is meant to be used after a re-run: without it, the check passes trivially on
files that were never replaced.

Exit status 0: every stand and building block is unchanged (and, with --expect-new-run,
every district's files come from a new run under the current config). 1 otherwise.
A git diff cannot do this job: each geojson is a single line, so any change shows as one
changed line.

Offline; reads only. Run from the repo root.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import shapely
from shapely.geometry import shape

HERE = Path(__file__).parent
REPO = HERE.parent
DISTRICTS = ["angul", "dhenkanal", "kendujhar", "koraput"]
GRID = 1e-7          # degrees, about 1 cm: outlines are compared after snapping to this grid
AREA_TOL = 1e-6      # hectares


def at_ref(ref: str, path: Path) -> str:
    rel = path.resolve().relative_to(REPO.resolve())
    return subprocess.run(["git", "-C", str(REPO), "show", f"{ref}:{rel}"],
                          capture_output=True, text=True, check=True).stdout


def outline(geom: dict) -> bytes:
    g = shapely.normalize(shapely.set_precision(shape(geom), GRID))
    return shapely.to_wkb(g)


def stand_type(props: dict) -> int | None:
    """The stand's type as the join reads it: Earth Engine's mode reducer stores 2.9999999999999973 for
    class 3, so it is rounded; None for a stand that was given no type."""
    cid = props.get("cluster_id")
    return None if cid is None else int(round(float(cid)))


def by_outline(text: str) -> tuple[dict, int]:
    """{outline: properties} for one geojson, and how many outlines occurred twice."""
    out, dup = {}, 0
    for f in json.loads(text)["features"]:
        k = outline(f["geometry"])
        dup += k in out
        out[k] = f["properties"]
    return out, dup


def config_fingerprint_now(config: str) -> str | None:
    try:
        from fmu.config import load_config
        from fmu.utils.caching import config_fingerprint
        return config_fingerprint(load_config(REPO / "configs" / f"{config}.yaml"))
    except Exception as e:          # the comparison below does not need it; say so and go on
        print(f"    (could not compute the config fingerprint: {type(e).__name__}: {e})")
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--arm", default="odisha_v120_3ha", help="config name without the district")
    ap.add_argument("--ref", default="HEAD", help="git ref holding the stand files to compare against")
    ap.add_argument("--vectors-dir", type=Path, default=HERE / "phase2_vectors",
                    help="where the files to check are (default odisha_script/phase2_vectors)")
    ap.add_argument("--expect-new-run", action="store_true",
                    help="fail unless every district's run record differs from the one at --ref and "
                         "matches the config as it is now")
    args = ap.parse_args()

    ok = True
    print(f"stands of {args.arm}: {args.vectors_dir} against git ref {args.ref}")
    for d in DISTRICTS:
        cfg = f"{args.arm}_{d}"
        ref_dir = HERE / "phase2_vectors"
        print(f"\n  {d}")

        fp_old = json.loads(at_ref(args.ref, ref_dir / f"{cfg}_run.json")).get("fingerprint")
        fp_new = json.loads((args.vectors_dir / f"{cfg}_run.json").read_text()).get("fingerprint")
        fp_cfg = config_fingerprint_now(cfg)
        new_run = fp_new != fp_old
        print(f"    run record fingerprint: {fp_old} at {args.ref}, {fp_new} on disk; the config as it is now gives {fp_cfg}")
        if not new_run:
            print("    -> the files on disk are from the SAME run as the ref: nothing below tests a re-run")
        elif fp_cfg is not None and fp_new != fp_cfg:
            print("    -> the files on disk are from a new run, but NOT under the config as it is now")
        if args.expect_new_run and (not new_run or (fp_cfg is not None and fp_new != fp_cfg)):
            ok = False

        for layer in ("stands_snic", "stands_merged"):
            name = f"{cfg}_{layer}.geojson"
            old, dup_o = by_outline(at_ref(args.ref, ref_dir / name))
            new, dup_n = by_outline((args.vectors_dir / name).read_text())
            gone, added = len(old.keys() - new.keys()), len(new.keys() - old.keys())
            same = old.keys() & new.keys()
            line = f"    {layer:13} {len(old):5d} outlines at the ref, {len(new):5d} on disk; {gone} gone, {added} new"
            if dup_o or dup_n:
                line += f"; repeated outlines {dup_o} / {dup_n}"
            if gone or added:
                ok = False
            if layer == "stands_merged":
                lbl = sum(old[k]["stand_lbl"] != new[k]["stand_lbl"] for k in same)
                area = sum(abs(old[k]["area_ha"] - new[k]["area_ha"]) > AREA_TOL for k in same)
                typ = sum(stand_type(old[k]) != stand_type(new[k]) for k in same)
                n_old = len({stand_type(p) for p in old.values()} - {None})
                n_new = len({stand_type(p) for p in new.values()} - {None})
                stands_o = len({p["stand_lbl"] for p in old.values()})
                stands_n = len({p["stand_lbl"] for p in new.values()})
                line += (f"\n    {'':13} stands {stands_o} -> {stands_n}; of the {len(same)} shared outlines: "
                         f"{lbl} with another stand label, {area} with another area, {typ} with another stand type"
                         f"\n    {'':13} distinct stand types {n_old} -> {n_new}")
                if lbl or area or stands_o != stands_n:
                    ok = False
            print(line)

    print()
    if ok:
        print("RESULT: every building block and every stand is unchanged"
              + (", and every district's files come from a new run under the current config."
                 if args.expect_new_run else
                 ". (Run with --expect-new-run after a re-run: without it this passes on files that were never replaced.)"))
    else:
        print("RESULT: NOT confirmed. See the lines above. If outlines, labels or areas changed, the stands moved and "
              "scores computed on the old files do not carry over.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
