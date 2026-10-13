"""
Task 2 deliverable for Odisha: the land-cover masked output of each district, with the
field plots marked kept or dropped.

A thin wrapper. Everything general is in scripts/transparency_masking.py; this file holds
only what is specific to Odisha:

  - which configs: configs/odisha_v120_3ha_<district>.yaml, one per district;
  - the points: the 274 field plots (odisha_phase2_0_aois.load_plot_points), each district's
    plots passed to its own config, so a plot outside the mapped village forests is reported
    as outside the ROI rather than left out;
  - the names of the ROI parts: the `habitations` lists in aois/odisha_habitations_<district>.geojson;
  - the check that one map per district stands for all three arms. Everything the masking
    stage reads is compared across odisha_v120_3ha_<d>, odisha_v120_handcrafted_<d> and
    odisha_alphaearth_<d>: the roi block, the masking block, and the three datasets entries
    masking uses (indiasat, worldcover, water). The datasets block as a whole is NOT identical:
    the AlphaEarth arm adds `datasets.embedding`, which masking never reads. On top of that the
    other two arms' cached habitat_mask is compared pixel by pixel with the 3 ha arm's
    (--compare-mask-asset). If anything masking reads differs the script stops: the arms would
    then need a map each. An arm with no cached mask is named in summary.md as not compared;
  - the plots outside the mapped village forests. Each district has a few; they are on no map.
    summary.md and the map caption say how many, and what the Phase 2 step 1 retention table
    (odisha_phase2_1_mask_retention.csv, which samples the mask at all 274 plots) has for them,
    so the district's retention there (for example 8 of 12) can be squared with the map's;
  - the words: a plain title naming the district, and "field plot" for a point.

NEEDS LIVE EARTH ENGINE, READ-ONLY: cached assets are read, nothing is exported or written
(see the header of scripts/transparency_masking.py). --redraw needs no Earth Engine.

Run from the repo root (fmu reads .env from the working directory):
      python odisha_script/odisha_transparency_masking.py
      python odisha_script/odisha_transparency_masking.py --district kendujhar
      python odisha_script/odisha_transparency_masking.py --redraw
Writes: docs/transparency/odisha_v120_3ha_<district>/ (maps, summary.md, run_record.json),
        outputs/transparency/odisha_v120_3ha_<district>/ (GeoTIFF, GeoJSON; ignored by git),
        outputs/transparency/_points/odisha_plots_<district>.csv (the points passed on)
"""
from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

import pandas as pd
import yaml
from shapely.geometry import Point

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "scripts"))
import transparency_masking  # noqa: E402
from odisha_phase2_0_aois import load_plot_points  # noqa: E402

DISTRICTS = ["angul", "dhenkanal", "kendujhar", "koraput"]
MAPPED_ARM = "odisha_v120_3ha"
OTHER_ARMS = ["odisha_v120_handcrafted", "odisha_alphaearth"]
SAME_BLOCKS = ["roi", "masking"]
# The datasets entries fmu.stages.masking reads (ds.indiasat, ds.worldcover, ds.water).
MASKING_DATASETS = ["indiasat", "worldcover", "water"]
POINTS_DIR = Path("outputs") / "transparency" / "_points"
DATA_DIR = Path("outputs") / "transparency"
RETENTION_CSV = HERE / "odisha_phase2_1_mask_retention.csv"
ARM_WORDS = "the three pipeline variants run on this district (the three arms: 3 ha, " \
            "handcrafted, AlphaEarth)"


def blocks_differing(district: str) -> dict[str, list[str]]:
    """For each other arm, the blocks of SAME_BLOCKS that differ from the mapped arm's."""
    def blocks(arm: str) -> dict:
        cfg = yaml.safe_load((REPO / "configs" / f"{arm}_{district}.yaml").read_text())
        out = {b: cfg.get(b) for b in SAME_BLOCKS}
        out.update({f"datasets.{k}": (cfg.get("datasets") or {}).get(k) for k in MASKING_DATASETS})
        return out

    mine = blocks(MAPPED_ARM)
    return {arm: [b for b in mine if blocks(arm)[b] != mine[b]] for arm in OTHER_ARMS}


def other_dataset_differences(district: str) -> list[str]:
    """Datasets entries that differ between the arms but that masking does not read."""
    def datasets(arm: str) -> dict:
        cfg = yaml.safe_load((REPO / "configs" / f"{arm}_{district}.yaml").read_text())
        return cfg.get("datasets") or {}

    mine = datasets(MAPPED_ARM)
    out = []
    for arm in OTHER_ARMS:
        theirs = datasets(arm)
        for key in sorted(set(mine) | set(theirs)):
            if key not in MASKING_DATASETS and mine.get(key) != theirs.get(key):
                out.append(f"`datasets.{key}` in `{arm}_{district}` "
                           f"({theirs.get(key)!r} against {mine.get(key)!r})")
    return out


def other_arm_mask_assets(district: str) -> list[str]:
    """The other arms' cached habitat_mask assets that exist, under their current fingerprints."""
    from fmu.config import load_config
    from fmu.utils.caching import asset_exists, cached_asset_path, config_fingerprint
    from fmu.utils.gee import init_gee

    init_gee()
    found = []
    for arm in OTHER_ARMS:
        cfg = load_config(REPO / "configs" / f"{arm}_{district}.yaml")
        path = cached_asset_path(cfg.name, "masking", "habitat_mask", config_fingerprint(cfg))
        if asset_exists(path):
            found.append(path)
        else:
            print(f"  {cfg.name}: no cached habitat_mask under its current fingerprint")
    return found


def compared_arms(district: str, assets: list[str] | None) -> tuple[list[str], list[str]]:
    """The other arms whose cached mask is compared, and those it could not be.

    `assets` are the asset ids found for this run; None for --redraw, which reads the
    comparisons saved by the run that made the rasters.
    """
    if assets is None:
        saved = DATA_DIR / f"{MAPPED_ARM}_{district}" / "masking_transparency.json"
        assets = [c["asset"] for c in json.loads(saved.read_text()).get("comparisons", [])]
    done = [arm for arm in OTHER_ARMS if any(f"/{arm}_{district}/" in a for a in assets)]
    return done, [arm for arm in OTHER_ARMS if arm not in done]


def outside_plots_sentences(district: str, here: pd.DataFrame) -> tuple[str | None, str | None]:
    """What to say about the district's plots outside the ROI: for summary.md, for the map.

    Counts the plots in no part of the ROI, and reads what the Phase 2 step 1 retention table
    has for them and for the district. (None, None) when every plot is inside.
    """
    roi = json.loads((REPO / "aois" / f"odisha_habitations_{district}.geojson").read_text())
    parts = transparency_masking.roi_parts(roi, "habitations")
    is_out = [not any(p.geometry.covers(Point(x, y)) for p in parts)
              for x, y in zip(here.lon6, here.lat6, strict=True)]
    outside = here[is_out]
    if outside.empty:
        return None, None
    n, m = len(outside), len(here)
    base = (f"{n} of the district's {m} field plots {'lies' if n == 1 else 'lie'} outside the "
            f"mapped village forests (the ROI) and {'is' if n == 1 else 'are'} on no map.")
    if not RETENTION_CSV.exists():
        print(f"  no {RETENTION_CSV.name}: the outside plots are counted but not looked up")
        return base, None
    table = pd.read_csv(RETENTION_CSV).set_index("plot_key")
    district_rows = table.loc[here.plot_key]
    out_rows = table.loc[outside.plot_key]
    kept, out_kept = int(district_rows.habitat.sum()), int(out_rows.habitat.sum())
    tail = (f"the Phase 2 step 1 retention table, which samples the same mask rule at every "
            f"plot, has {kept} of {m} plots of this district on a habitat pixel "
            f"({int(table.habitat.sum())} of {len(table)} over the four districts). That count "
            f"includes the {n} outside the ROI: {out_kept} kept and {n - out_kept} dropped there.")
    note = (base + " " + tail[0].upper() + tail[1:]
            + f" The map and the tables below cover only the {m - n} inside. Table: "
              f"`odisha_script/{RETENTION_CSV.name}`.")
    return note, tail[0].upper() + tail[1:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--district", action="append", choices=DISTRICTS,
                        help="District to run. Repeatable. Default: all four.")
    parser.add_argument("--redraw", action="store_true",
                        help="Redraw maps and summary.md from the saved rasters. No Earth Engine.")
    args = parser.parse_args()

    plots = load_plot_points()
    POINTS_DIR.mkdir(parents=True, exist_ok=True)
    for district in args.district or DISTRICTS:
        differing = blocks_differing(district)
        if any(differing.values()):
            print(f"STOP: {district}: blocks differ from {MAPPED_ARM}: {differing}. "
                  "The arms need a map each.")
            return 1
        extra = other_dataset_differences(district)
        here = plots[plots.district.str.lower() == district]
        points_csv = POINTS_DIR / f"odisha_plots_{district}.csv"
        here[["plot_key", "lon6", "lat6", "habitation"]].to_csv(points_csv, index=False)
        assets = None if args.redraw else other_arm_mask_assets(district)
        done, missing = compared_arms(district, assets)
        compared = ""
        if done:
            compared += (f" The cached mask of {' and of '.join(f'`{a}_{district}`' for a in done)} "
                         "is compared with this one, pixel by pixel, below.")
        if missing:
            compared += (f" No cached mask exists under the current fingerprint of "
                         f"{' or of '.join(f'`{a}_{district}`' for a in missing)}, so that "
                         "comparison could NOT be made.")
        outside_note, outside_map_note = outside_plots_sentences(district, here)

        argv = [
            "--config", f"configs/{MAPPED_ARM}_{district}.yaml",
            "--points", str(points_csv),
            "--id-col", "plot_key", "--lon-col", "lon6", "--lat-col", "lat6",
            "--point-noun", "field plot",
            "--part-name-key", "habitations",
            "--title", f"{district.capitalize()} district, Odisha: land-cover (habitat) mask of "
                       "the mapped village forests",
            "--note",
            f"This map stands for {ARM_WORDS}. Everything the masking stage "
            f"reads is identical in {', '.join(f'`{a}_{district}`' for a in OTHER_ARMS)} and "
            f"this config (`{MAPPED_ARM}_{district}`): the roi block, the masking block, and the "
            f"datasets entries {', '.join(MASKING_DATASETS)}. So all three use the same mask rule "
            f"on the same ROI.{compared} "
            + ("The datasets block as a whole is not identical; what differs is not read by "
               "masking: " + "; ".join(extra) + "." if extra else
               "The datasets block is identical too."),
            "--note",
            f"The field plots are the {len(here)} of the district "
            "(`odisha_script/odisha_plots_clean.csv`, coordinates from `plot_key`). Each part of "
            "the ROI is the forest around one or two habitations, named after them.",
            "--map-note",
            "One map for " + ARM_WORDS + ": they use the same mask rule on the same ROI"
            + (", and their cached masks were compared pixel by pixel (summary.md)." if not missing
               else "; not every arm's cached mask could be compared (summary.md)."),
        ]
        if outside_note:
            argv += ["--note", outside_note]
        if outside_map_note:
            argv += ["--map-note", outside_map_note]
        if args.redraw:
            argv.append("--redraw")
        else:
            for asset in assets or []:
                argv += ["--compare-mask-asset", asset]
        command = (
            "python " + " ".join(shlex.quote(a) for a in [
                f"odisha_script/{Path(__file__).name}", "--district", district,
                *(["--redraw"] if args.redraw else [])])
            + "   # which runs: python scripts/transparency_masking.py "
            + " ".join(shlex.quote(a) for a in argv)
        )
        code = transparency_masking.main(argv, command_line=command, code_files=[Path(__file__)])
        if code:
            return code
    return 0


if __name__ == "__main__":
    sys.exit(main())
