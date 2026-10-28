"""Build an early ui_data/ from the files the 13 Oct re-runs already saved, for the explorer.

    pip install rasterio pillow shapely numpy
    python scripts/build_ui_early_data.py [<outputs dir> [<repo root> [<out dir>]]]

Defaults: outputs/ and ui_data/ of this repo. It reads, for the 14 `_repro` runs of PR #42, the
mask GeoTIFFs and area outlines in outputs/transparency_repro/_mask_data/ and the stand files and
run records in outputs/repro_runs/phase2_vectors/, plus the committed plot tables. It writes the
ui_data/ contract of docs/handoff/2026-10-13-round2.md (task A3, with "Version 2 of the index"),
with three differences from the full export: stands are before the merge fix; feature layers are
stand means, not pixels, except for Sanjay Van; the satellite image comes in parts, one per part
of the area. Claude Code's A3 export replaces this folder entirely.

Every stand carries the mean of every feature its stand file holds (22 for the hand-crafted runs,
the 64 embedding numbers for AlphaEarth), not only the ones the map draws, with distance_to_water
of 10 km or more written as "over 10 km" in every run. For the two Sanjay Van
runs (`PIXEL_LAYER_RUNS`) the feature layers are drawn pixel by pixel, from the GeoTIFFs
scripts/fetch_ui_layers.py saved under outputs/ui_data_full/<run_id>/ (on the grid of the
satellite image, so the two line up): canopy height, the seasonal swing in greenness and radar VV
minus VH as colour ramps, and the AlphaEarth embedding as colour, the first three principal
components of its 64 numbers over the area's pixels. A run whose GeoTIFFs are missing keeps the
stand means, with a note.

The two kept-land runs of round 5 (`KEPTLAND_RUNS`: configs/sanjay_van_*_keptland.yaml, SNIC and
the merge on kept land only) are added when their committed files are in
docs/reproducibility/keptland_runs/ (stand layers, run record, export-pass manifest). Their
upstream assets are copies of the `_repro` runs' (docs/reproducibility/keptland_reuse.json), so
they share those runs' satellite image, land cover and per-pixel feature layers. Each also gets:
the kept-land mask layer (habitat_mask 1, from the masking output of its source run); a below-min
flag on each stand; its profiles, merge diagnostics and clustering metadata as files of their
own; and distance_to_water of 10 km or more written as "over 10 km", since where the distance
transform finds no water the band holds a fill value, not a distance.

The four box kept-land runs of round 6 (`KEPTLAND_BOX_RUNS`:
configs/odisha_v120_3ha_squares_<district>_keptland.yaml) are added the same way, each on the area
of its district's box run, so only when that run is added too. Their upstream assets are copies of
the box runs' (docs/reproducibility/keptland_reuse_odisha.json), except the static features: each
run computed its own, with distance_to_water capped at 10 km. They get what the round-5 runs get,
with their feature layers as stand means, as the box runs have. Their plots are shown without a stand:
their field check (odisha_script/PHASE_KEPTLAND_PREDECLARED.md) is not run yet, so no plot is
joined to a stand, the plots carry no stand_id or stand_type, and the runs are not fes_declared.
The four descending-orbit runs of round 7 (`KEPTLAND_S1DESC_RUNS`) are added the same way. Their
field check has been run (odisha_script/keptland_scores/keptland_s1desc_scores.json): they are
fes_declared and the site shows that check's scores (`keptland_rows`). Their plots are shown
without a stand too, because this script does not read that check's join
(keptland_s1desc_joined.csv), not because the check is not run (corrected 20 Oct 2026, review C24).

The box runs of A0 (configs/odisha_v120_3ha_squares_<district>.yaml) are added when their files
exist: the stand files and run record (searched in BOX_VEC_DIRS) and the output of
scripts/transparency_masking.py for the box config (searched in BOX_MASK_DIRS). Their plots are
joined to the stands here, by the Phase 2 join rule (the stand that covers a plot; the lowest
stand id where several do). A district whose box files are missing is skipped with a note.

Two encoders here are meant for reuse by that export: `polyline6` (Google's encoded polyline
format at 6 decimals, latitude first) and `superpixel_lines` (each edge between superpixels once,
as encoded lines, so the outlines stay sharp at any zoom). The land-cover mask is written the same
way, as encoded polygons per class (`class_shapes`).

R3, round 15 (docs/handoff/2026-10-28-round15.md). The eighteen R3 runs (`add_r3_runs`: those with
an export manifest in docs/reproducibility/r14_runs/second_half/) are the site's current results
(`"group": "current"`); every run above is kept as an earlier version (`"group": "earlier"`, with
a line saying what it is, `HISTORY`). Each R3 run is built from its own records: its stand layers
there or off git by its `_files_off_git.json`, its run record and export manifest (the land-cover
shares too, from the masking stage's numbers in it), its set's declared join, scores and chance
test (odisha_script/keptland_scores/keptland_<set>_r14_*), and k with Jaskaran's reason from the
register (`k_reason`). Its satellite image and land cover come from scripts/fetch_ui_r3_layers.py,
read-only from R3's own cached assets (`R3_LAYERS`); no raster of an earlier run is reused, since
none was made under a step key that could show the same computation. The kept land is the
masking stage's kept class from the same files. At Sanjay Van the feature layers are drawn pixel
by pixel, from the runs' own cached features, fetched by the same script; in Odisha they are
stand means, as for the box runs.
"""
from __future__ import annotations

import csv
import json
import math
import re
import shutil
import sys
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image

from fmu.config import load_config

_ROOT = Path(__file__).resolve().parent.parent
_ARGS = [Path(a) for a in sys.argv[1:4]]
STAGED = _ARGS[0] if len(_ARGS) > 0 else _ROOT / "outputs"
REPO = _ARGS[1] if len(_ARGS) > 1 else _ROOT
OUT = _ARGS[2] if len(_ARGS) > 2 else _ROOT / "ui_data"
MASK = STAGED / "transparency_repro" / "_mask_data"
VEC = STAGED / "repro_runs" / "phase2_vectors"
BOX_VEC_DIRS = [STAGED / "squares_runs" / "phase2_vectors",
                STAGED / "squares_runs" / "run_tree" / "odisha_script" / "phase2_vectors",
                REPO / "odisha_script" / "phase2_vectors"]
BOX_MASK_DIRS = [STAGED / "transparency_squares", STAGED / "transparency",
                 STAGED / "squares_runs" / "transparency"]
DISTRICTS = ("angul", "dhenkanal", "kendujhar", "koraput")
# Per-pixel feature layers (scripts/fetch_ui_layers.py): Sanjay Van only, as the brief of round 3
# (docs/handoff/2026-10-14-round3.md, step 3) asks; every other run draws the stand means.
PIXELS = STAGED / "ui_data_full"
PIXEL_LAYER_RUNS = ("sanjay_van_baseline_repro", "sanjay_van_alphaearth_repro",
                    "sanjay_van_baseline_keptland_r14", "sanjay_van_alphaearth_keptland_r14")
# R3 (round 15): the runs' records, their sets' scores, and their areas' display rasters, which
# scripts/fetch_ui_r3_layers.py writes under PIXELS / R3_LAYERS / <area>.
R3 = REPO / "docs" / "reproducibility" / "r14_runs" / "second_half"
R3_SCORES = REPO / "odisha_script" / "keptland_scores"
R3_LAYERS = "r14_areas"
REGISTER = REPO / "docs" / "decisions.yaml"
# Jaskaran's k for R3 with his reason, in the register (round 14, Task 7): for each kind of R3
# run, the entry and the lead of the item of its quoted rationale that names it.
K_REASONS = {"sanjay_van": ("field-r3-k-from-part-1-of-the-elbow-report", "Sanjay Van, both arms"),
             3.0: ("field-r3-k-from-part-1-of-the-elbow-report",
                   "The four Odisha districts at 3 ha, both arms"),
             10.0: ("field-r3-k-from-part-2-of-the-elbow-report", "10 ha k")}
# The record of the build, outside ui_data/ so that the site does not change with it (round 13's
# question 28, spec-ui-data-build-record-in-docs-in-a-later-round).
BUILD_RECORD = REPO / "docs" / "reproducibility" / "ui_data_build_run.json"
ROUND13 = "docs/handoff/2026-10-20-round13.md"
ROUND14 = "docs/handoff/2026-10-26-round14.md"
REVIEW = "docs/reviews/2026-10-19-review.md"
# The kept-land runs of round 5: run id -> (arm, the _repro run whose assets it reuses).
KEPTLAND = REPO / "docs" / "reproducibility" / "keptland_runs"
KEPTLAND_RUNS = {"sanjay_van_baseline_keptland": ("feature_vector", "sanjay_van_baseline_repro"),
                 "sanjay_van_alphaearth_keptland": ("alphaearth", "sanjay_van_alphaearth_repro")}
# The box kept-land runs of round 6: run id -> the district whose box run's assets it reuses.
KEPTLAND_BOX_RUNS = {f"odisha_v120_3ha_squares_{d}_keptland": d for d in DISTRICTS}
# The runs whose stands the "13 October 2026 re-runs" score rows scored (docs/reproducibility.md,
# section 3): the hull _repro runs, the 10 ha hand-crafted arm and the 3 ha arm.
RERUN_IDS = {10.0: [f"odisha_v120_handcrafted_{d}_repro" for d in DISTRICTS],
             3.0: [f"odisha_v120_3ha_{d}_repro" for d in DISTRICTS]}
# Their descending-orbit runs of round 7 (spec-odisha-keptland-s1-orbit-descending): run id ->
# the district. A stand layer of theirs over 5 MB is kept off git (spec-files-over-5-mb-off-git)
# and read from where its record says (`vec_file`).
KEPTLAND_S1DESC_RUNS = {f"odisha_v120_3ha_squares_{d}_keptland_s1desc": d for d in DISTRICTS}
# The stands of their field check's box_runs rows: the 13 Oct box runs, a comparison beside the
# check and not a declared score (Jaskaran, 18 Oct 2026; field-box-runs-a-descriptive-comparison-only).
BOX_RUNS_STANDS = ("13 Oct 2026 box runs, on the kept-land check's plots: a descriptive comparison, "
                   "not a declared score")
# Where fastDistanceTransform finds no water within features_static.max_water_distance_pixels
# (1,000 px = 10 km) it gives its fill value, sqrt(2^31 - 1) x 10 m, not a distance, or with
# features_static.cap_distance_to_water on the cap itself: 10 km or more is written as OVER_10_KM
# (`far`), in the stands of every run (spec-ui-distance-to-water-over-10-km; every run from round
# 7, Jaskaran's answer (b) to question 1 of docs/handoff/2026-10-15-round6.md).
FAR_WATER_M = 10_000.0
OVER_10_KM = "over 10 km"

AREAS = {
    "sanjay_van": {"title": "Sanjay Van", "site": "Sanjay Van", "roi": "rectangle",
                   "district": None, "mask_dir": MASK / "sanjay_van_baseline_repro"},
}
for _d in DISTRICTS:
    AREAS[_d] = {"title": _d.title(), "site": "Odisha", "roi": "hulls", "district": _d,
                 "mask_dir": MASK / f"odisha_v120_3ha_{_d}_repro"}
SANJAY_NOTE = ("Sanjay Van working area: a 1,300 ha rectangle (77.16 to 77.19 E, 28.51 to 28.55 N) "
               "around the park, not the park boundary.")
LABEL = ("Demo set, early build: the Earth Engine re-runs of 13 Oct 2026 (commit df45350), before "
         "the merge fix. Built from the files those runs saved, while Claude Code prepares the full "
         "export. Upstream of the merge it carries the open cache-grid issue (PR #42, question 1). "
         "The final re-run replaces it.")
SHORT_LABEL = ("Test runs from 13 October 2026, before the merge fix. The final runs will "
               "replace them.")
SHORT_LABEL_WITH_BOXES = ("Test runs from 13 and 14 October 2026: the village outlines before the "
                          "merge fix, the boxes with it. The final runs will replace them.")
SHORT_LABEL_WITH_KEPTLAND = ("Test runs from 13 to 15 October 2026: the village outlines before the "
                             "merge fix, the boxes with it, and two Sanjay Van runs on kept land "
                             "only. The final runs will replace them.")
KEPTLAND_LABEL = (" Two Sanjay Van runs of 15 Oct 2026 (commit {commit}) segment kept land only "
                  "(configs/sanjay_van_*_keptland.yaml).")
SHORT_LABEL_WITH_BOX_KEPTLAND = ("Test runs from 13 to 15 October 2026: the village outlines before "
                                 "the merge fix, the boxes with it, and kept land only at Sanjay "
                                 "Van and in the boxes. The final runs will replace them.")
KEPTLAND_BOX_LABEL = (" {n} Odisha box runs of 15 Oct 2026 (commit {commit}) segment kept land only "
                      "in the boxes (configs/odisha_v120_3ha_squares_*_keptland.yaml).")
KEPTLAND_S1DESC_LABEL = (" {n} more, of 15 Oct 2026 (commit {commit}), take their radar from the "
                         "descending Sentinel-1 orbit "
                         "(configs/odisha_v120_3ha_squares_*_keptland_s1desc.yaml).")
SHORT_LABEL_WITH_S1DESC = ("Test runs from 13 to 15 October 2026: the village outlines before the "
                           "merge fix, the boxes with it, and kept land only at Sanjay Van and in "
                           "the boxes, there on both radar orbits. The final runs will replace "
                           "them.")
NUMBER_WORDS = {1: "One", 2: "Two", 3: "Three", 4: "Four"}
MEANS_NOTE = (" Its stands' named measurements come from one read-only reduction "
              "(docs/reproducibility/keptland_runs/{run}_stand_means.json): the optical and "
              "structure ones from this run's own images, the radar and static ones from the "
              "baseline kept-land run's, since the AlphaEarth arm computes neither.")
# Round 15: the build as a whole, and each earlier run's one line (round 13's question 23,
# site-r3-notes-at-the-next-site-build).
R3_SHORT_LABEL = ("Current results: R3, the {n_current} runs of 28 Oct 2026, made after the "
                  "corrections of 19 to 28 Oct. The {n_earlier} runs of 13 to 15 Oct are kept as "
                  "earlier versions.")
R3_LABEL = ("R3 (round 14, docs/reproducibility/r14_runs/README.md): Sanjay Van and the Odisha "
            "boxes at 3 ha and 10 ha, both arms, on kept land only (configs/*_r14.yaml, commit "
            "{commit}), with the fixes of rounds 13 and 14 and round 14's four method changes "
            "(odisha_script/PHASE_KEPTLAND_PREDECLARED.md, the change of 26 Oct 2026). Earlier "
            "versions: ")
HISTORY = {
    "repro": "A test run of 13 Oct 2026 on {where}, before the merge fix.",
    "box": "A test run of 14 Oct 2026 on the boxes, over all land, after the merge fix.",
    "keptland": "A run of 15 Oct 2026 on kept land only (trees and scrub) in {where}.",
    "keptland_ascending": ("A run of 15 Oct 2026 on kept land only in the boxes, its radar from the "
                           "ascending Sentinel-1 orbit."),
    "s1desc": ("A run of 15 Oct 2026 on kept land only in the boxes, its radar from the descending "
               "Sentinel-1 orbit; its field-check scores are round 7's."),
}
HISTORY_BEFORE = " Its results are from before the corrections of 19 to 28 Oct 2026."
# The "What changed" panel (round 15, Task 2): the corrections that change what the pipeline
# computes, from the review of 19 Oct 2026 (fixed in round 13, or changed in the method before R3
# in round 14) and from round 14's two live checks; one plain sentence each, from those files.
WHAT_CHANGED = [
    {"title": "Fixed after the review of 19 Oct 2026 (round 13)", "record": ROUND13, "items": [
        ("A1", "Distance to water now sees water outside the mapped area too; before, it saw only "
               "the water inside it."),
        ("A4", "The Sentinel-1 and Sentinel-2 date windows now include their last day; before, "
               "they stopped a day early, and the images of that day were left out."),
        ("A5", "Slope and aspect now keep their decimals, and a flat cell has no direction; "
               "before, they were whole degrees, and a flat cell counted as facing north."),
        ("A6", "A stand's area is now its pixel count, and its position the mean of its pixel "
               "centres (round 14); before, Earth Engine's outlines counted some holes as area, "
               "which inflated those areas and moved those positions."),
        ("B13", "The sine and cosine of the time of peak greenness are no longer log-transformed "
                "before the stands are sorted into types."),
        ("B14", "A stand in several pieces now gets one average over all its pixels, and a stand "
                "with no data in a measurement is left out of the sorting, so it gets no type; "
                "before, each piece had its own average, and a stand could be sorted on a 0 it "
                "never measured."),
        ("B16", "Whether a measurement varies at all, and how it is scaled, now rest on exact "
                "quartiles; before, Earth Engine's approximate ones could drop a measurement that "
                "does vary."),
        ("B17", "The merge now counts a superpixel's pixels, and those with data, by one rule; "
                "before, pixels at the edge of the mapped area were counted in part, and some "
                "superpixels had more pixels with data than pixels."),
        ("B18", "The merge's size limits are now compared in whole pixels; before, a sum of two "
                "areas could be judged over a limit it exactly met."),
    ]},
    {"title": "Changed before R3, after the same review (round 14)", "record": ROUND14, "items": [
        ("A2, B15", "The stand types are now fitted off Earth Engine on the declared scaling, "
                    "with many starts, keeping the best; before, Earth Engine rescaled every "
                    "measurement by its range, which undid the declared scaling, and the types "
                    "rested on one start."),
        ("A3, B12", "Only measurements skewed to the right are now log-transformed, by a rule "
                    "that scales with each one's spread, and angles never; before, measurements "
                    "skewed either way were logged, which made the left-skewed ones more skewed."),
        ("C9", "Average greenness is now the fitted curve's mean over the whole window; before, it "
               "was the trend line's value on the window's first day."),
        ("A7", "The elbow behind the number of types is now drawn in the fit's own space, and "
               "Jaskaran chose k from it before any field score; before, it was drawn outside "
               "that space."),
        ("C10", "The stand layers now also give the averages of each angle's sine and cosine, "
                "from which this site reads which way a stand faces and when it is greenest; "
                "plain averages of angles mislead where they wrap round, at north or at the turn "
                "of the year."),
        ("C12", "Every tie in the merge is now broken by the regions' positions, not by the "
                "superpixels' numbers, which change from run to run."),
    ]},
    {"title": "Fixed after the two live checks (round 14)", "record": ROUND14, "items": [
        ("First live check", "The merge now takes every count on the superpixels' own grid; the "
                             "check stopped in the merge, which measured on another grid than "
                             "the one it counted pixels on."),
        ("Second live check", "The check stopped when Earth Engine refused to export the elbow's "
                              "saved table; each row of it now carries a fixed point, which "
                              "changes no number."),
    ]},
]

RUNS: list[dict] = []
for _arm_id, _arm in (("sanjay_van_baseline_repro", "feature_vector"),
                      ("sanjay_van_alphaearth_repro", "alphaearth")):
    RUNS.append({"run_id": _arm_id, "area": "sanjay_van", "arm": _arm, "vec": VEC})
for _d in DISTRICTS:
    RUNS += [{"run_id": f"odisha_v120_3ha_{_d}_repro", "area": _d, "arm": "feature_vector",
              "vec": VEC},
             {"run_id": f"odisha_v120_handcrafted_{_d}_repro", "area": _d,
              "arm": "feature_vector", "vec": VEC},
             {"run_id": f"odisha_alphaearth_{_d}_repro", "area": _d, "arm": "alphaearth",
              "vec": VEC}]


def vec_file(vec: Path, name: str) -> Path | None:
    """A run's file: in `vec`, or where a <run>_files_off_git.json there says, once its SHA-256
    is checked (spec-files-over-5-mb-off-git); None if it is in neither. A file the record names
    but that is not on this machine stops the build, so that a build elsewhere cannot drop the
    run without saying so."""
    import hashlib

    if (vec / name).is_file():
        return vec / name
    for record in sorted(vec.glob("*_files_off_git.json")):
        for f in json.loads(record.read_text())["files"]:
            if f["file"] == name:
                where = Path(f["where"])
                if not where.is_file():
                    raise SystemExit(f"{name} is kept off git at {where} ({record.name}), which is "
                                     "not on this machine: build ui_data where it is")
                if hashlib.sha256(where.read_bytes()).hexdigest() != f["sha256"]:
                    raise SystemExit(f"{where} is not the file {record.name} names (SHA-256)")
                return where
    return None


def first_dir_with(dirs: list[Path], names: list[str]) -> Path | None:
    for d in dirs:
        if all((d / n).is_file() for n in names):
            return d
    return None


def add_box_runs() -> list[str]:
    """Add each box run whose stand files and masking output exist; return notes on the rest."""
    notes = []
    for d in DISTRICTS:
        run_id = f"odisha_v120_3ha_squares_{d}"
        vec = first_dir_with(BOX_VEC_DIRS, [f"{run_id}_stands_merged.geojson",
                                            f"{run_id}_stands_snic.geojson", f"{run_id}_run.json"])
        mask = first_dir_with([b / run_id for b in BOX_MASK_DIRS],
                              ["masking_transparency.json", "roi_outline.geojson"])
        if vec is None or mask is None or not parts_of(mask, "true_colour"):
            notes.append(f"{run_id}: skipped ({'no stand files' if vec is None else 'no masking output'})")
            continue
        key = f"{d}_boxes"
        AREAS[key] = {"title": d.title(), "site": "Odisha", "roi": "boxes", "district": d,
                      "mask_dir": mask}
        RUNS.append({"run_id": run_id, "area": key, "arm": "feature_vector", "vec": vec,
                     "box": True})
    return notes

def add_r3_runs() -> list[str]:
    """Add the eighteen R3 runs, each on its R3 area, once their areas' display rasters exist
    (scripts/fetch_ui_r3_layers.py). An area without them stops the build: R3 is the site's
    current results, so it is never left out without a word. Returns no notes."""
    from fetch_ui_r3_layers import areas as r3_areas

    found = r3_areas(R3)
    n = sum(len(a["runs"]) for a in found.values())
    if n != 18:
        raise SystemExit(f"R3 is eighteen runs; {R3} holds the records of {n}")
    for name, a in found.items():
        mdir = PIXELS / R3_LAYERS / name
        if not parts_of(mdir, "true_colour") or not parts_of(mdir, "mask_provenance"):
            raise SystemExit(f"{mdir}: no display rasters for R3's {name} area; run "
                             "scripts/fetch_ui_r3_layers.py first")
        sanjay = name == "sanjay_van"
        key = f"{name}_r14"
        AREAS[key] = {"title": "Sanjay Van" if sanjay else name.title(),
                      "site": "Sanjay Van" if sanjay else "Odisha",
                      "roi": "rectangle" if sanjay else "boxes", "district": None if sanjay else name,
                      "mask_dir": mdir, "r3": True, "roi_file": REPO / a["roi_file"],
                      "numbers": r3_masking_numbers(a["runs"])}
        for run_id in a["runs"]:
            arm = ("alphaearth" if load_config(str(REPO / "configs" / f"{run_id}.yaml"))
                   .clustering.feature_source == "embedding" else "feature_vector")
            RUNS.append({"run_id": run_id, "area": key, "arm": arm, "vec": R3, "keptland": True,
                         "r3": True})
    return []


def r3_manifest(run_id: str) -> dict:
    return json.loads((R3 / f"{run_id}_manifest_export.json").read_text())


def r3_masking_numbers(runs: list[str]) -> dict:
    """The masking stage's summary numbers of an area's R3 runs, from their export manifests. The
    runs share the step's key, so the numbers must agree; the build stops if they do not."""
    seen = []
    for run_id in runs:
        masking = next(s for s in r3_manifest(run_id)["stages"] if s["name"] == "masking")
        seen.append({s["name"]: s["value"] for s in masking["transparency"]["summary_numbers"]})
    if any(s != seen[0] for s in seen):
        raise SystemExit(f"{runs}: the masking numbers differ between runs of one key")
    return seen[0]


_REGISTER: dict = {}


def register_entry(entry_id: str) -> dict:
    if not _REGISTER:
        import yaml

        _REGISTER.update({d["id"]: d for d in yaml.safe_load(REGISTER.read_text())["decisions"]})
    return _REGISTER[entry_id]


def k_reason(kind, k: int) -> dict:
    """k for an R3 run and Jaskaran's reason for it, from the register (`K_REASONS`): the
    sentences after "Reason:" in the item of the entry's quoted rationale that names the run's
    kind, up to the next item or the end of the quote. The item must give the run's k."""
    entry_id, lead = K_REASONS[kind]
    entry = register_entry(entry_id)
    quote = " ".join(entry["rationale"].split()).split('"')[1]
    item = quote[quote.index(lead):].split(" - ")[0]
    said = re.search(r"\bk\s*[=:]\s*(\d+)", item)
    if not said or int(said.group(1)) != k:
        raise SystemExit(f"{entry_id}: its item for {lead!r} does not give k = {k}")
    report = next(e["path"] for e in entry["evidence"] if e["path"].endswith("_report.md"))
    return {"k": k, "reason": item.split("Reason: ", 1)[1].strip(), "register": entry_id,
            "report": report}


def r3_set(arm: str, ceiling: float) -> str:
    """The stem of an R3 run's scored set in odisha_script/keptland_scores/."""
    return (f"keptland_{'alphaearth' if arm == 'alphaearth' else 's1desc'}"
            f"{'_10ha' if ceiling == 10.0 else ''}_r14")


def add_keptland_runs() -> list[str]:
    """Add each kept-land run whose committed files exist; return notes on the rest. A box
    kept-land run goes on the area of its district's box run, so add_box_runs comes first."""
    notes = []
    specs = [(run_id, arm, "sanjay_van", source)
             for run_id, (arm, source) in KEPTLAND_RUNS.items()]
    specs += [(run_id, "feature_vector", f"{d}_boxes", None)
              for run_id, d in {**KEPTLAND_BOX_RUNS, **KEPTLAND_S1DESC_RUNS}.items()]
    for run_id, arm, area, source in specs:
        need = [f"{run_id}_{n}" for n in ("stands_merged.geojson", "stands_snic.geojson",
                                          "run.json", "manifest_export.json")]
        if any(vec_file(KEPTLAND, n) is None for n in need):
            notes.append(f"{run_id}: skipped (no committed files under {KEPTLAND})")
            continue
        if area not in AREAS:
            notes.append(f"{run_id}: skipped (no area {area}: its box run was skipped)")
            continue
        RUNS.append({"run_id": run_id, "area": area, "arm": arm, "vec": KEPTLAND,
                     "keptland": True, "pixels_from": source})
    return notes


JOIN_PREFIX = {"odisha_v120_3ha": ("odisha_v120_3ha", "v120_3ha"),
               "odisha_v120_handcrafted": ("odisha_v120_handcrafted", "v120"),
               "odisha_alphaearth": ("odisha_alphaearth", "alphaearth")}

STEP_DECISIONS = {
    "masking": ["dn-masking-indiasat-primary-habitat", "spec-landcover-source-corestack-lulc-v4",
                "dn-masking-majority-vote-recent-year-tie-break",
                "dn-masking-single-phase-no-separate-subtraction", "dn-masking-worldcover-fallback",
                "dn-masking-jrc-water-mask-for-distance-only", "spec-masking-builtup-toggles-removed",
                "night-mask-provenance-layer"],
    "data_load": ["dn-date-windows-one-shared-window", "spec-analysis-grid-utm-from-roi"],
    "features_fv": ["dn-optical-harmonic-regression-derived-bands", "dn-nirv-units-reflectance-0-1",
                    "dn-radar-percentiles-no-harmonic", "dn-radar-vv-minus-vh-in-db",
                    "dn-radar-no-speckle-filter", "dn-structure-eth-canopy-height-input",
                    "sup-eth-canopy-height-stays", "dn-structure-neighbourhood-std-and-max",
                    "dn-static-terrain-bands-from-nasadem",
                    "dn-optical-features-over-whole-roi-mask-at-clustering"],
    "features_ae": ["dn-embedding-arm-controlled-swap", "dn-embedding-stage-source-agnostic",
                    "dn-optical-features-over-whole-roi-mask-at-clustering"],
    "segmentation": ["dn-snic-independent-per-arm", "dn-snic-zscore-per-band",
                     "dn-snic-distance-scale-normalisation", "dn-snic-default-adds-ndvi-amplitude",
                     "dn-snic-canopy-height-std-removed", "dn-snic-compactness-and-bands-not-swept",
                     "spec-snic-reduced-stack-kmeans-full-stack"],
    "merge": ["spec-merge-stage-makes-the-stand", "spec-merge-two-pass-hard-gate",
              "spec-merge-default-criteria", "spec-merge-tolerances-physical-units",
              "spec-merge-hard-area-bounds", "spec-merge-missing-data-rules",
              "dn-merge-criteria-identical-across-arms", "sup-stand-size-3ha",
              "spec-merge-pass2-skip-at-minimum", "field-structural-criterion-unresolved"],
    "clustering": ["spec-kmeans-one-row-per-unit", "dn-median-iqr-scaling-dec-003",
                   "dn-log-transform-skewed-dec-004", "dn-cyclic-sin-cos", "dn-drop-constant-bands",
                   "dn-kmeans-fixed-seed", "field-number-of-types-by-elbow",
                   "field-type-labels-within-district"],
    "fes_plots": ["field-analyses-declared-before-run", "field-all-267-plots",
                  "field-forest-types-from-structure", "field-truth-trees-only",
                  "field-rotation-null-only-null", "field-phase3-primary-analysis-and-checks",
                  "sup-established-methods-first", "sup-new-metrics-await-approval"],
}

# Plain names for the land-cover classes of the mask's "reason" band (masking_transparency.json).
LAND_COVER = {0: ("No land-cover data", "#000000"),
              1: ("Trees or scrub", "#1a9850"),
              2: ("Cropland", "#fdae61"),
              3: ("Built-up", "#d73027"),
              4: ("Water", "#4575b4"),
              5: ("Other land", "#9e9e9e")}
KEPT_LAND = ("Kept land: trees or scrub, all that SNIC and the merge see", "#1a9850")
TYPE_COLORS = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7",
               "#999999"]
# Field types of odisha_phase3_0_field_types.csv, described by their typical (median) plot,
# from odisha_script/odisha_phase3_0_results.txt.
FIELD_TYPES = [
    (0, "Type 0: no trees", 18),
    (1, "Type 1: trees ~7 m tall, ~6 per plot", 111),
    (2, "Type 2: trees ~8 m tall, ~14 per plot", 77),
    (3, "Type 3: trees ~15 m tall, ~29 per plot", 15),
    (4, "Type 4: trees ~18 m tall, ~8 per plot", 53),
]
FIELD_COLORS = ["#9e9e9e", "#ffe14d", "#ff9f40", "#e0457b", "#7b2cbf"]
OUTSIDE_REASON = ("Its village has fewer than 5 plots, so no area was mapped around it")
ID_FIELDS = {"area_ha", "centroid_lat", "centroid_lon", "cluster_id", "n_pixels", "perim_m",
             "stand_id", "stand_lbl"}
# What the merge says of how each stand was made (stand_provenance, in the box runs' stand files):
# not a feature.
PROVENANCE_FIELDS = {"n_superpx", "n_pass1", "n_relaxed", "n_fallback", "below_min", "below_why"}
# The decimals of the stand means the first build kept, unchanged; every other feature mean keeps
# four significant figures (`feature_value`).
DECIMALS = {"canopy_height": 1, "canopy_height_std": 2, "ndvi_amplitude_annual": 3,
            "vv_minus_vh_median": 2, "ndvi_mean": 3, "elevation": 0, "slope": 1}
# The three features the map draws for a hand-crafted run: (band, title, palette, units).
DRAWN_FEATURES = (
    ("canopy_height", "Canopy height",
     ["#f7fcf5", "#c7e9c0", "#74c476", "#238b45", "#00441b"], "m"),
    ("ndvi_amplitude_annual", "Seasonal swing in greenness",
     ["#fff7ec", "#fdd49e", "#fc8d59", "#d7301f", "#7f0000"], "NDVI"),
    ("vv_minus_vh_median", "Radar: VV minus VH",
     ["#f7fbff", "#c6dbef", "#6baed6", "#2171b5", "#08306b"], "dB"),
)
EMBEDDING_TITLE = "AlphaEarth, as colour"


def r6(x: float) -> float:
    return round(float(x), 6)


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))


def bounds_of(src) -> list[float]:
    b = src.bounds
    return [r6(b.left), r6(b.bottom), r6(b.right), r6(b.top)]


def png(path: Path, rgba: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(path, optimize=True)


def parts_of(mask_dir: Path, kind: str) -> list[Path]:
    return sorted(mask_dir.glob(f"part*_{kind}.tif"))


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------- encoders, for reuse by A3
def _enc(v: int) -> str:
    v = ~(v << 1) if v < 0 else (v << 1)
    out = []
    while v >= 0x20:
        out.append(chr((0x20 | (v & 0x1F)) + 63))
        v >>= 5
    out.append(chr(v + 63))
    return "".join(out)


def polyline6(coords) -> str:
    """Google's encoded polyline at 6 decimals. coords are (lon, lat); output is latitude first."""
    out, plat, plon = [], 0, 0
    for lon, lat in coords:
        ilat, ilon = int(round(lat * 1e6)), int(round(lon * 1e6))
        out.append(_enc(ilat - plat))
        out.append(_enc(ilon - plon))
        plat, plon = ilat, ilon
    return "".join(out)


def superpixel_lines(polygons: list) -> dict:
    """Every edge between superpixels once, merged into chains, as encoded lines."""
    import shapely
    from shapely.ops import linemerge, unary_union

    snapped = [shapely.set_precision(p, 1e-6) for p in polygons]
    net = linemerge(unary_union([p.boundary for p in snapped]))
    lines = list(net.geoms) if hasattr(net, "geoms") else [net]
    return {"encoding": "polyline6", "lines": [polyline6(line.coords) for line in lines]}


def class_shapes(band: np.ndarray, valid: np.ndarray, transform, classes: dict, crs=None) -> dict:
    """A categorical raster as encoded polygons, grouped by class (rings: outer first). A raster
    on a projected grid (`crs`, an R3 area's mask on its asset's UTM grid) has its rings turned to
    longitude and latitude, vertex by vertex, so its pixel edges stay where the stands' are."""
    from rasterio import features as rfeatures

    to_lonlat = None
    if crs is not None and crs.to_epsg() != 4326:
        from pyproj import Transformer

        to_lonlat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
    by_class: dict[int, list] = {}
    for geom, val in rfeatures.shapes(band, mask=valid, transform=transform, connectivity=4):
        v = int(val)
        if v not in classes:
            continue
        rings = geom["coordinates"]
        if to_lonlat is not None:
            rings = [list(zip(*to_lonlat(*zip(*ring, strict=True)), strict=True)) for ring in rings]
        by_class.setdefault(v, []).append([polyline6(ring) for ring in rings])
    return {"encoding": "polyline6",
            "classes": [{"value": v, "polygons": by_class[v]} for v in sorted(by_class)]}


def merge_class_shapes(items: list[dict]) -> dict:
    merged: dict[int, list] = {}
    for it in items:
        for c in it["classes"]:
            merged.setdefault(c["value"], []).extend(c["polygons"])
    return {"encoding": "polyline6",
            "classes": [{"value": v, "polygons": merged[v]} for v in sorted(merged)]}


# ---------------------------------------------------------------- per area (shared by its runs)
def r3_inside(info: dict, path: Path, transform, crs, shape_hw) -> np.ndarray:
    """For a raster of an R3 area (`<part>_<kind>.tif`, on its asset's grid): True for the pixels
    whose centre lies inside its part of the ROI, the pixels R3's merge counts. The download keeps
    every pixel the part's outline touches, about 1% more at the edges."""
    from pyproj import Transformer
    from shapely.ops import transform as reproject
    from transparency_masking import inside_mask, roi_parts

    slug = path.name.rsplit("_", 2)[0]
    part = next(p for p in roi_parts(json.loads(info["roi_file"].read_text())) if p.slug == slug)
    to_grid = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    return inside_mask(reproject(to_grid, part.geometry), transform, shape_hw)


def area_layers(area: str) -> dict:
    """Satellite image and land-cover layers for one area (shared by every run on it). For an R3
    area the land-cover numbers are its runs' masking stage's (`r3_masking_numbers`), the outline
    its ROI file's, and the land cover is drawn on the masks' own grid (`class_shapes`)."""
    info = AREAS[area]
    mdir = info["mask_dir"]
    out_dir = OUT / "areas" / area
    # One linear stretch for all three bands, percentiles 1 and 99 of the valid pixels.
    tc = parts_of(mdir, "true_colour")
    vals = []
    for f in tc:
        with rasterio.open(f) as s:
            a = s.read().astype("float32")
            valid = (a > 0).any(axis=0)
            vals.append(a[:, valid].ravel())
    lo, hi = (float(v) for v in np.percentile(np.concatenate(vals), [1, 99]))
    tc_parts = []
    for i, f in enumerate(tc, 1):
        with rasterio.open(f) as s:
            a = s.read().astype("float32")
            b = bounds_of(s)
            valid = (a > 0).any(axis=0)
            rgb = np.clip((a - lo) / (hi - lo) * 255.0, 0, 255).astype("uint8")
            rgba = np.dstack([rgb[0], rgb[1], rgb[2], np.where(valid, 255, 0).astype("uint8")])
            name = f"satellite_part{i:02d}.png"
            png(out_dir / name, rgba)
            tc_parts.append({"file": f"areas/{area}/{name}", "bounds": b})
    shapes = []
    for f in parts_of(mdir, "mask_provenance"):
        with rasterio.open(f) as s:
            reason = s.read(1)
            valid = s.read_masks(1) > 0
            if info.get("r3"):
                valid &= r3_inside(info, f, s.transform, s.crs, reason.shape)
            shapes.append(class_shapes(reason, valid, s.transform, LAND_COVER, s.crs))
    write_json(out_dir / "land_cover.json", merge_class_shapes(shapes))
    if info.get("r3"):
        from transparency_masking import roi_outline_geojson, roi_parts

        roi = roi_outline_geojson(roi_parts(json.loads(info["roi_file"].read_text())))
        sn = info["numbers"]
    else:
        roi = json.loads((mdir / "roi_outline.geojson").read_text())
        tj = json.loads((mdir / "masking_transparency.json").read_text())["transparency"]
        sn = {s["name"]: s["value"] for s in tj["summary_numbers"]}
    name_parts(roi, area)
    from shapely.geometry import shape
    from shapely.ops import unary_union

    area_geom = unary_union([shape(f["geometry"]) for f in roi["features"]])
    write_json(out_dir / "area_outline.geojson", roi)
    by_reason = sn["share_by_reason"]
    allb = [p["bounds"] for p in tc_parts]
    bbox = [min(b[0] for b in allb), min(b[1] for b in allb), max(b[2] for b in allb),
            max(b[3] for b in allb)]
    facts = {
        "area_ha": round(sn["area_ha"], 1),
        "n_parts": len(roi["features"]),
        "share_kept": round(sn["share_kept"], 4),
        "share_removed": {"cropland": round(by_reason["cropland"], 4),
                          "built_up": round(by_reason["built_up"], 4),
                          "water": round(by_reason["water"], 4),
                          "other": round(by_reason["other_non_habitat"], 4),
                          "no_data": round(by_reason["no_data"], 4)},
        "share_decided_by_worldcover": round(sn["share_decided_by_source"]["worldcover"], 4),
    }
    busiest = max(roi["features"], key=lambda f: f["properties"].get("n_plots", 0))
    return {"bbox": bbox, "tc": tc_parts, "tc_stretch": (lo, hi), "facts": facts,
            "land_cover": f"areas/{area}/land_cover.json", "geom": area_geom,
            "start_bounds": [r6(v) for v in shape(busiest["geometry"]).bounds],
            "roi": f"areas/{area}/area_outline.geojson"}


def name_parts(roi: dict, area: str) -> None:
    """Name each part of the area after the villages whose FES plots fall inside it."""
    from shapely.geometry import Point, shape

    if AREAS[area]["site"] != "Odisha":
        for f in roi["features"]:
            f["properties"]["name"] = AREAS[area]["title"]
            f["properties"]["n_plots"] = 0
        return
    plots = [r for r in read_csv(REPO / "odisha_script" / "odisha_plots_clean.csv")
             if r["district"].lower() == AREAS[area]["district"]]
    for f in roi["features"]:
        poly = shape(f["geometry"])
        counts: dict[str, int] = {}
        for r in plots:
            lat, lon = (float(v) for v in r["plot_key"].split("_"))
            if poly.contains(Point(lon, lat)):
                h = r["habitation"].title()
                counts[h] = counts.get(h, 0) + 1
        names = sorted(counts, key=lambda h: (-counts[h], h))
        n = sum(counts.values())
        label = " and ".join(names[:2]) + (f" and {len(names) - 2} more" if len(names) > 2 else "")
        f["properties"]["name"] = (f"{label} ({n} plots)" if names
                                   else f"Part {f['properties'].get('part_index', '')}".strip())
        f["properties"]["n_plots"] = n


def round_coords(c):
    if isinstance(c[0], (int, float)):
        return [r6(c[0]), r6(c[1])]
    out = [round_coords(x) for x in c]
    if out and isinstance(out[0][0], float):  # a ring: drop repeats left by rounding
        dedup = [out[0]]
        for p in out[1:]:
            if p != dedup[-1]:
                dedup.append(p)
        out = dedup
    return out


def pca_rgb(rows: list[list[float]]) -> list[str]:
    x = np.array(rows, dtype="float64")
    x = x - x.mean(axis=0)
    _, _, vt = np.linalg.svd(x, full_matrices=False)
    pcs = x @ vt[:3].T
    cols = []
    lo = np.percentile(pcs, 2, axis=0)
    hi = np.percentile(pcs, 98, axis=0)
    scaled = np.clip((pcs - lo) / np.where(hi > lo, hi - lo, 1), 0, 1)
    for r, g, b in (scaled * 255).astype(int):
        cols.append(f"#{r:02x}{g:02x}{b:02x}")
    return cols


def utm_area_ha(geom) -> float:
    import shapely
    from pyproj import Transformer

    from fmu.utils.grid import utm_epsg_code

    c = geom.centroid
    fwd = Transformer.from_crs(4326, utm_epsg_code(c.x, c.y), always_xy=True).transform
    projected = shapely.transform(geom, lambda xy: np.column_stack(fwd(xy[:, 0], xy[:, 1])))
    return projected.area / 10_000.0


def encode_stands(fc: dict) -> dict:
    """A stand FeatureCollection with its rings as encoded polylines (the page inflates it)."""
    feats = []
    for f in fc["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        feats.append({"properties": f["properties"],
                      "polygons": [[polyline6(ring) for ring in poly] for poly in polys]})
    return {"encoding": "polyline6", "features": feats}


def feature_names(properties: dict) -> list[str]:
    """The feature means of a stand: every property but the ids and the merge's provenance."""
    return [k for k in properties if k not in ID_FIELDS and k not in PROVENANCE_FIELDS]


def far(value) -> bool:
    """A distance_to_water of 10 km or more, at the four significant figures ui_data writes it
    with: Earth Engine reads the cap back as 9,999.98 m and the like (see FAR_WATER_M)."""
    return float(f"{float(value):.4g}") >= FAR_WATER_M


def feature_value(name: str, value, *, far_water: bool = False) -> float | str | None:
    """A stand mean as ui_data keeps it: None for no data, else rounded (`DECIMALS`). With
    `far_water`, a distance_to_water of 10 km or more is OVER_10_KM (`far`)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if far_water and name == "distance_to_water" and far(value):
        return OVER_10_KM
    if name in DECIMALS:
        return round(value, DECIMALS[name])
    return float(f"{float(value):.4g}")


def stand_means(run_id: str, vec: Path) -> dict:
    """{polygon stand_id: {band: mean}} from a run's <run>_stand_means.json, the named means of
    an AlphaEarth run's stands by one read-only reduction (scripts/alphaearth_stand_means.py,
    spec-ui-alphaearth-stands-named-means-by-reduction); empty if the run has none."""
    path = vec / f"{run_id}_stand_means.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {s["stand_id"]: {b: s.get(b) for b in data["bands"]} for s in data["stands"]}


def run_stands(run_id: str, arm: str, vec: Path, *, keptland: bool = False,
               r3: bool = False) -> tuple[dict, dict]:
    """The stands of a run, for stands.json. Distance to water of 10 km or more is OVER_10_KM
    (feature_value). A kept-land run's stands also say whether the merge left them below the
    minimum (`below_min`), and an R3 run's why (`below_why`: isolated, sharing no edge with
    another stand, or area_blocked, every neighbour too big to take it). Where the run has named
    means by reduction (`stand_means`), its stands carry them beside their own means. An R3 run's
    stand means of each angle's sine and cosine (aspect_sin and the like) are kept, and not counted
    as measurements of their own."""
    g = json.loads(vec_file(vec, f"{run_id}_stands_merged.geojson").read_text())
    feats = g["features"]
    extra = stand_means(run_id, vec)
    if extra:
        feats = [{**f, "properties": {**f["properties"], **extra[f["properties"]["stand_id"]]}}
                 for f in feats]
    names = feature_names(feats[0]["properties"])
    n_bands = len([n for n in names if not (n.endswith(("_sin", "_cos")) and n[:-4] in names)])
    emb_cols = None
    if arm == "alphaearth":
        keys = [f"A{i:02d}" for i in range(64)]
        rows = [[f["properties"].get(k) or 0.0 for k in keys] for f in feats]
        emb_cols = pca_rgb(rows)
    # The seven the first build kept first, in its order, then every other feature mean.
    keep = [*DECIMALS, *sorted(n for n in names if n not in DECIMALS)]
    out = []
    area_by_stand: dict = {}
    for i, f in enumerate(feats):
        p = f["properties"]
        ct = p.get("cluster_id")
        sid = p.get("stand_lbl")
        q = {"stand_id": sid,
             "stand_type": None if ct is None else int(round(float(ct))),
             "area_ha": round(p["area_ha"], 2) if p.get("area_ha") is not None else None}
        for k in keep:
            q[k] = feature_value(k, p.get(k), far_water=True)
        if keptland:
            q["below_min"] = bool(p.get("below_min"))
        if r3 and q["below_min"]:
            q["below_why"] = p.get("below_why") or None
        if emb_cols:
            q["emb_rgb"] = emb_cols[i]
        if q["area_ha"] is not None:
            area_by_stand[sid] = area_by_stand.get(sid, 0.0) + q["area_ha"]
        out.append({"type": "Feature", "properties": q,
                    "geometry": {"type": f["geometry"]["type"],
                                 "coordinates": round_coords(f["geometry"]["coordinates"])}})
    fc = {"type": "FeatureCollection", "features": out}
    types = sorted({f["properties"]["stand_type"] for f in out
                    if f["properties"]["stand_type"] is not None})
    areas = sorted(area_by_stand.values())
    untyped = sum(f["properties"]["area_ha"] or 0.0 for f in out
                  if f["properties"]["stand_type"] is None)
    total = sum(area_by_stand.values())
    return fc, {"types": types, "median_area": round(float(np.median(areas)), 2) if areas else None,
                "n_stands": len(area_by_stand), "n_bands": n_bands,
                "n_untyped": len({f["properties"]["stand_id"] for f in out
                                  if f["properties"]["stand_type"] is None}),
                "share_untyped": round(untyped / total, 4) if total else None}


def superpixel_layer(run_id: str, vec: Path) -> tuple[str, float | None]:
    from shapely.geometry import shape

    g = json.loads(vec_file(vec, f"{run_id}_stands_snic.geojson").read_text())
    polys = [shape(f["geometry"]) for f in g["features"]]
    name = f"by_run/{run_id}/superpixels.json"
    write_json(OUT / name, superpixel_lines(polys))
    areas = [utm_area_ha(p) for p in polys]
    return name, round(float(np.median(areas)), 2) if areas else None


def join_plots_to_stands(stands_fc: dict, plot_keys: list[str]) -> dict:
    """plot_key -> {"<col>_merged_id", "<col>_merged_cluster"} by the Phase 2 join rule: the stand
    whose polygon covers the plot, the lowest stand id where several do."""
    from shapely import STRtree
    from shapely.geometry import Point, shape

    geoms, ids, types = [], [], []
    for f in stands_fc["features"]:
        geoms.append(shape(f["geometry"]))
        ids.append(f["properties"]["stand_id"])
        types.append(f["properties"]["stand_type"])
    tree = STRtree(geoms)
    out = {}
    for key in plot_keys:
        lat, lon = (float(v) for v in key.split("_"))
        pt = Point(lon, lat)
        hits = [i for i in tree.query(pt) if geoms[i].covers(pt)]
        if hits:
            best = min(hits, key=lambda i: ids[i])
            out[key] = {"box_merged_id": str(ids[best]),
                        "box_merged_cluster": "" if types[best] is None else str(types[best])}
    return out


def plots_for(run_id: str, district: str, area_geom, stands_fc: dict | None = None, *,
              with_stands: bool = True, declared: Path | None = None) -> tuple[dict, dict]:
    """A district's FES plots, each with its field type and mask, and the stand it is on: a box
    run's by the Phase 2 join rule on `stands_fc`, an R3 run's from its set's declared join
    (`declared`, keptland_<set>_r14_joined.csv: the stand that covers the plot, else the nearest
    within 30 m, `join_m` metres off), any other run's from its committed join. Without
    `with_stands` no plot is joined: the plots carry no stand_id or stand_type, and the counts
    leave out the plots with a stand (for a kept-land run of rounds 5 to 7, whether or not its
    field check has run: this script does not read that check's join; review C24)."""
    plots = read_csv(REPO / "odisha_script" / "odisha_plots_clean.csv")
    ftype = {r["plot_key"]: r["field_type"]
             for r in read_csv(REPO / "odisha_script" / "odisha_phase3_0_field_types.csv")}
    ret = {r["plot_key"]: r["habitat"]
           for r in read_csv(REPO / "odisha_script" / "odisha_phase2_1_mask_retention.csv")}
    if declared is not None:
        col = "r3"
        join = {r["plot_key"]: {"r3_merged_id": r["sid"] if r["how"] != "none" else "",
                                "r3_merged_cluster": r["cluster"] if r["how"] != "none" else "",
                                "join_m": float(r["dist_m"]) if r["how"] == "within" else 0.0}
                for r in read_csv(declared) if r["box_district"] == district}
    elif not with_stands:
        col, join = "", {}
    elif stands_fc is not None:
        col = "box"
        join = join_plots_to_stands(stands_fc, [p["plot_key"] for p in plots
                                                if p["district"].lower() == district])
    else:
        arm_key = next(k for k in JOIN_PREFIX if run_id.startswith(k + "_"))
        folder, col = JOIN_PREFIX[arm_key]
        join = {r["plot_key"]: r for r in read_csv(
            REPO / "docs" / "reproducibility" / "odisha_repro" / folder
            / "phase2_plots_joined_districts.csv")}
    from shapely.geometry import Point

    feats = []
    n = {"in_district": 0, "inside": 0, "kept": 0, "with_stand": 0}
    for p in plots:
        if p["district"].lower() != district:
            continue
        lat, lon = (float(v) for v in p["plot_key"].split("_"))
        j = join.get(p["plot_key"], {})
        sid = j.get(f"{col}_merged_id") or None
        stype = j.get(f"{col}_merged_cluster") or None
        inside = bool(area_geom.covers(Point(lon, lat)))
        kept = ret.get(p["plot_key"]) == "1"
        n["in_district"] += 1
        n["inside"] += inside
        n["kept"] += kept
        n["with_stand"] += sid is not None
        props = {"plot_key": p["plot_key"], "district": p["district"].title(),
                 "habitation": p["habitation"].title(),
                 "field_type": int(ftype[p["plot_key"]]) if p["plot_key"] in ftype else None,
                 "mask": "kept" if kept else "dropped", "in_mapped_area": inside,
                 "outside_reason": None if inside else OUTSIDE_REASON}
        if with_stands:
            props["stand_id"] = int(float(sid)) if sid else None
            props["stand_type"] = int(float(stype)) if stype else None
        if declared is not None and sid:
            props["join_m"] = round(j["join_m"], 1)
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "Point", "coordinates": [r6(lon), r6(lat)]}})
    if not with_stands:
        del n["with_stand"]
    return {"type": "FeatureCollection", "features": feats}, n


def feature_layers(run_id: str, arm: str, stands_fc: dict, *, early: bool = True) -> list[dict]:
    """The feature layers as stand means, drawn on the stand polygons (`early`: an earlier run's,
    whose layer says "in this early version")."""
    if arm == "alphaearth":
        return [{
            "layer_id": "embedding_rgb", "title": EMBEDDING_TITLE,
            "kind": "vector", "file": f"by_run/{run_id}/stands.json",
            "color_by": "emb_rgb", "color_is_value": True,
            "popup_fields": ["stand_id", "area_ha"], "legend": None, "colormap": None,
            "default_on": False,
            "description": "Each stand is coloured by its average AlphaEarth embedding: the first "
                           "three principal components of the 64 numbers, as red, green and blue. "
                           "Similar colours mean the embedding sees the stands as alike."}]
    layers = []
    for prop, title, pal, units in DRAWN_FEATURES:
        vals = [f["properties"][prop] for f in stands_fc["features"]
                if f["properties"].get(prop) is not None]
        if not vals:
            continue
        vmin, vmax = (float(v) for v in np.percentile(vals, [2, 98]))
        layers.append({
            "layer_id": f"feature_{prop}", "title": title,
            "kind": "vector", "file": f"by_run/{run_id}/stands.json",
            "color_by": prop, "popup_fields": ["stand_id", prop, "area_ha"], "legend": None,
            "colormap": {"min": round(vmin, 3), "max": round(vmax, 3), "palette": pal,
                         "units": units},
            "default_on": False,
            "description": ("Averaged over each stand in this early version." if early
                            else "Averaged over each stand.")})
    return layers


def ramp_rgb(palette: list[str], t: np.ndarray) -> np.ndarray:
    """The explorer's colour ramp (`ramp` in ui/explorer.html) on an array of t: clamped to 0 to 1,
    linear between the palette's colours, evenly spaced. Returns uint8, shape t.shape + (3,)."""
    stops = np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in palette], dtype="float64")
    x = np.clip(t, 0.0, 1.0) * (len(palette) - 1)
    i = np.minimum(len(palette) - 2, np.floor(x)).astype(int)
    rgb = stops[i] + (stops[i + 1] - stops[i]) * (x - i)[..., None]
    return np.floor(rgb + 0.5).astype("uint8")  # JavaScript's Math.round


def pixel_parts(run_id: str, kind: str) -> list[Path]:
    """The GeoTIFFs scripts/fetch_ui_layers.py saved for a run, one per part, in part order."""
    return sorted((PIXELS / run_id).glob(f"{kind}_part[0-9][0-9].tif"))


def pixel_feature_layers(run_id: str, arm: str) -> list[dict] | None:
    """The feature layers pixel by pixel, from the run's GeoTIFFs; None if it has none."""
    files = pixel_parts(run_id, "embedding" if arm == "alphaearth" else "features")
    if not files:
        return None
    if arm == "alphaearth":
        return [embedding_pixel_layer(run_id, files)]
    layers = []
    for band, title, pal, units in DRAWN_FEATURES:
        data = []
        for path in files:
            with rasterio.open(path) as src:
                data.append((src.read(list(src.descriptions).index(band) + 1).astype("float64"),
                             bounds_of(src)))
        vals = np.concatenate([a[np.isfinite(a)] for a, _ in data])
        if not vals.size:
            continue
        # The same stretch as the stand means: percentiles 2 and 98, here of the pixels.
        vmin, vmax = (round(float(v), 3) for v in np.percentile(vals, [2, 98]))
        parts = []
        for i, (a, b) in enumerate(data, 1):
            valid = np.isfinite(a)
            t = np.where(valid, (np.where(valid, a, vmin) - vmin) / ((vmax - vmin) or 1.0), 0.0)
            rgba = np.dstack([ramp_rgb(pal, t), np.where(valid, 255, 0).astype("uint8")])
            name = f"feature_{band}_part{i:02d}.png"
            png(OUT / "by_run" / run_id / name, rgba)
            parts.append({"file": f"by_run/{run_id}/{name}", "bounds": b})
        layers.append({
            "layer_id": f"feature_{band}", "title": title, "kind": "raster", "parts": parts,
            "legend": None,
            "colormap": {"min": vmin, "max": vmax, "palette": pal, "units": units},
            "smooth": False, "default_on": False})
    return layers


def embedding_pixel_layer(run_id: str, files: list[Path]) -> dict:
    """The embedding as colour, pixel by pixel: the first three principal components of the 64
    numbers, over every pixel of the area with all 64, as red, green and blue."""
    stacks = []
    for path in files:
        with rasterio.open(path) as src:
            a = src.read().astype("float64")
            stacks.append((a.reshape(a.shape[0], -1).T, a.shape[1:], bounds_of(src)))
    valid = [np.isfinite(rows).all(axis=1) for rows, _, _ in stacks]
    x = np.concatenate([rows[m] for (rows, _, _), m in zip(stacks, valid, strict=True)])
    mean = x.mean(axis=0)
    _, _, vt = np.linalg.svd(x - mean, full_matrices=False)
    # A component's sign is arbitrary. Fixed so that its largest loading is positive, so the
    # colours do not depend on the linear-algebra library.
    comps = vt[:3] * np.sign(vt[np.arange(3), np.abs(vt[:3]).argmax(axis=1)])[:, None]
    lo, hi = np.percentile((x - mean) @ comps.T, [2, 98], axis=0)
    parts = []
    for i, ((rows, shape, b), m) in enumerate(zip(stacks, valid, strict=True), 1):
        rgb = np.zeros((rows.shape[0], 3), dtype="uint8")
        scaled = np.clip(((rows[m] - mean) @ comps.T - lo) / np.where(hi > lo, hi - lo, 1), 0, 1)
        rgb[m] = (scaled * 255).astype("uint8")  # as pca_rgb does for the stands
        rgba = np.dstack([rgb.reshape(*shape, 3), np.where(m, 255, 0).astype("uint8").reshape(shape)])
        name = f"embedding_rgb_part{i:02d}.png"
        png(OUT / "by_run" / run_id / name, rgba)
        parts.append({"file": f"by_run/{run_id}/{name}", "bounds": b})
    return {"layer_id": "embedding_rgb", "title": EMBEDDING_TITLE, "kind": "raster",
            "parts": parts, "color_is_value": True, "legend": None, "colormap": None,
            "smooth": False, "default_on": False,
            "description": "Each pixel is coloured by its AlphaEarth embedding: the first three "
                           "principal components of the 64 numbers, over the area's pixels, as "
                           "red, green and blue. Similar colours mean the embedding sees the "
                           "pixels as alike."}


def kept_land_layer(area: str) -> str:
    """The kept-land mask of an area (habitat_mask 1) as encoded polygons, written once."""
    name = f"areas/{area}/kept_land.json"
    info = AREAS[area]
    if not (OUT / name).exists():
        shapes = []
        for path in parts_of(info["mask_dir"], "habitat_mask"):
            with rasterio.open(path) as src:
                band = src.read(1)
                valid = (src.read_masks(1) > 0) & (band == 1)
                shapes.append(class_shapes(band, valid, src.transform, {1: KEPT_LAND}))
        if info.get("r3"):
            # R3: the masking stage's kept class (reason 1) in its mask provenance, which its
            # summary finds on no pixel apart from the habitat mask
            # (area_ha_reason_disagrees_with_habitat_mask), the pixels whose centre is inside.
            if info["numbers"]["area_ha_reason_disagrees_with_habitat_mask"] != 0:
                raise SystemExit(f"{area}: the mask's reasons and habitat mask disagree")
            for path in parts_of(info["mask_dir"], "mask_provenance"):
                with rasterio.open(path) as src:
                    band = src.read(1)
                    valid = ((src.read_masks(1) > 0) & (band == 1)
                             & r3_inside(info, path, src.transform, src.crs, band.shape))
                    shapes.append(class_shapes(band, valid, src.transform, {1: KEPT_LAND},
                                               src.crs))
        write_json(OUT / name, merge_class_shapes(shapes))
    return name


def profile_value(band: str, value):
    """A profile statistic as ui_data keeps it: four significant figures, far water marked."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if band == "distance_to_water" and far(value):
        return OVER_10_KM
    return float(f"{float(value):.4g}")


def type_area_excess(types_ha: float, kept_land_ha: float | None, lat: float) -> int:
    """How much larger, in %, the profiling stage's type areas come to than the kept land they
    cover (spec-profiling-export-type-areas-later); without the kept land's area, the grid's
    share alone, 1/cos(lat) - 1, at `lat`, the middle of the area."""
    if kept_land_ha:
        return round((types_ha / kept_land_ha - 1) * 100)
    return round((1 / math.cos(math.radians(lat)) - 1) * 100)


def area_note(where: str, pct: int) -> str:
    """profiles.json's note on its areas: `pct` from type_area_excess."""
    return ("pixel_count and area_ha are the profiling stage's: pixels counted on the clustering "
            "image's own grid, a geographic one, each taken as 0.01 ha. Away from the equator its "
            "pixels are narrower than 10 m, so area_ha is too large by about 1/cos(latitude), "
            f"some {pct}% {where}. The stands' areas (stands.json) are on the analysis grid.")


def keptland_files(run_id: str, vec: Path, run: dict, where: str, lat: float) -> tuple[dict, dict]:
    """Write a kept-land run's profiles (with a note on their areas: area_note, `where` naming
    the area, `lat` its middle), merge diagnostics and clustering metadata; return the index's
    references to them and the run's clustering metadata."""
    manifest = json.loads((vec / f"{run_id}_manifest_export.json").read_text())
    stages = {st["name"]: st for st in manifest["stages"]}
    prof = stages["profiling"]["metadata"]
    kept_ha = (run["merge_diagnostics"].get("kept_land") or {}).get("kept_land_ha")
    pct = type_area_excess(sum(p["area_ha"] for p in prof["profiles"]), kept_ha, lat)
    types = []
    for p in prof["profiles"]:
        bands: dict = {}
        for key, value in p.items():
            if key in ("cluster_id", "pixel_count", "area_ha"):
                continue
            band, _, stat = key.rpartition("_")
            bands.setdefault(band, {})[stat] = profile_value(band, value)
        types.append({"type": p["cluster_id"], "pixel_count": p["pixel_count"],
                      "area_ha": p["area_ha"], "bands": bands})
    profiles = {"k": prof["k"], "feature_bands": prof["feature_bands"],
                "what": "Per stand type, over the pixels of that type in the area: each "
                        "feature's mean and its 25th, 50th and 75th percentiles, in the "
                        "feature's own units (the profiling stage).",
                "area_note": area_note(where, pct),
                "types": types}
    clustering = stages["export"]["metadata"]["manifest"]["clustering"]
    names = {"profiles": f"by_run/{run_id}/profiles.json",
             "merge_diagnostics": f"by_run/{run_id}/merge_diagnostics.json",
             "clustering_metadata": f"by_run/{run_id}/clustering_metadata.json"}
    write_json(OUT / names["profiles"], profiles)
    write_json(OUT / names["merge_diagnostics"], run["merge_diagnostics"])
    write_json(OUT / names["clustering_metadata"], clustering)
    return names, clustering


def history_line(run_id: str, area: str) -> str:
    """An earlier run's one line: what it is, and that its results are from before the
    corrections of 19 to 28 Oct 2026 (round 13's question 23)."""
    if run_id.endswith("_repro"):
        where = ("the whole rectangle" if AREAS[area]["site"] == "Sanjay Van"
                 else "the village outlines")
        line = HISTORY["repro"].format(where=where)
    elif run_id.endswith("_keptland_s1desc"):
        line = HISTORY["s1desc"]
    elif run_id.endswith("_keptland"):
        line = (HISTORY["keptland"].format(where="Sanjay Van's rectangle")
                if AREAS[area]["site"] == "Sanjay Van" else HISTORY["keptland_ascending"])
    else:
        line = HISTORY["box"]
    return line + HISTORY_BEFORE


def versions(run_id: str, area: str, r3: bool, cfg, stands_fc: dict) -> dict:
    """Where a run stands among the site's versions, and how its angles and ndvi_mean are to be
    read: an R3 run is a current result; any other an earlier version, with its line
    (history_line). `angles` says how a stand's "faces" and "peak month" are given: from the
    stand means of each angle's sine and cosine (sin_cos), or as plain means of the angles
    (plain). `ndvi_mean` says what the band is, from the run's config: the fitted curve's mean
    over the dates window (features_optical.mean_over_window), or the trend line's value on the
    harmonic's reference date."""
    names = set(stands_fc["features"][0]["properties"]) if stands_fc["features"] else set()
    fo = cfg.features_optical
    out: dict = {"group": "current" if r3 else "earlier",
                 "ndvi_mean": ({"what": "window_mean", "from": str(cfg.dates.phenology.start),
                                "to": str(cfg.dates.phenology.end)} if fo.mean_over_window
                               else {"what": "trend_value", "on": str(fo.time_reference)})}
    if {"aspect_sin", "aspect_cos", "ndvi_phase_annual_sin", "ndvi_phase_annual_cos"} <= names:
        out["angles"] = "sin_cos"
    elif names & {"aspect", "ndvi_phase_annual"}:
        out["angles"] = "plain"
    if not r3:
        out["history"] = history_line(run_id, area)
    return out


def check_declared_join(run_id: str, plots: dict, stands_fc: dict) -> None:
    """Every plot an R3 set's declared join puts on a stand is on a stand of this run, of the type
    the join read; the build stops otherwise."""
    types = {f["properties"]["stand_id"]: f["properties"]["stand_type"]
             for f in stands_fc["features"]}
    for f in plots["features"]:
        p = f["properties"]
        if p.get("stand_id") is not None and types.get(p["stand_id"], "none") != p["stand_type"]:
            raise SystemExit(f"{run_id}: plot {p['plot_key']} joins stand {p['stand_id']}, whose "
                             f"type here is {types.get(p['stand_id'], 'no stand')}, not "
                             f"{p['stand_type']}")


def r3_entry(entry: dict, facts: dict, run: dict, clustering: dict, st: dict, cfg, arm: str,
             ceiling: float, sanjay: bool) -> None:
    """What an R3 run's index entry adds to a kept-land run's: its own source, rules and note,
    k with Jaskaran's reason (`k_reason`), and the counts behind its stands without a type."""
    if clustering["k"] != cfg.clustering.k:
        raise SystemExit(f"{entry['run_id']}: k {clustering['k']} in its export, "
                         f"{cfg.clustering.k} in its config")
    if st["n_untyped"] != clustering["n_units_dropped_null_band"] + clustering[
            "n_units_no_pixel_centre_in_roi"]:
        raise SystemExit(f"{entry['run_id']}: {st['n_untyped']} stands without a type, which its "
                         "clustering's counts do not account for")
    facts.update({"area_ha_below_min": run["merge_diagnostics"]["area_in_undersized_stands_ha"],
                  "stands_in_fit": clustering["n_training_units"],
                  "untyped_no_data": clustering["n_units_dropped_null_band"],
                  "untyped_no_pixel_centre": clustering["n_units_no_pixel_centre_in_roi"]})
    hand = arm == "feature_vector"
    entry.update({
        "fes_declared": not sanjay,
        "merge_rule": ("spec-merge-pass2-skip-at-minimum, spec-merge-pass2-soft-ceiling, "
                       "spec-merge-pixel-counts-on-one-inclusion-rule, "
                       "spec-merge-every-tie-by-centroid"),
        "note": (SANJAY_NOTE + " " if sanjay else "") + "SNIC and the merge saw kept land only "
                "(trees or scrub): the rest of the " + ("rectangle" if sanjay else "boxes")
                + " is in no stand."
                + (" Its radar comes from the descending Sentinel-1 orbit." if hand and not sanjay
                   else ""),
        "k_reason": k_reason("sanjay_van" if sanjay else ceiling, cfg.clustering.k),
    })
    if not sanjay:
        entry["scores"] = {"set": r3_set(arm, ceiling),
                           "files": [f"odisha_script/keptland_scores/{r3_set(arm, ceiling)}_{s}"
                                     for s in ("scores.txt", "chance.txt")]}


def build_record(git: dict, runs_out: list[dict]) -> dict:
    """What built ui_data/ and from what: the command, the date, the git state read before the
    build began, the environment, the runs by group, and the files off git it read for R3 (the
    display rasters scripts/fetch_ui_r3_layers.py saved: each one's size and SHA-256, and the
    assets each area's were downloaded from)."""
    import datetime as dt
    import hashlib

    from fmu.utils.provenance import environment_state

    off_git = sorted(p for p in (PIXELS / R3_LAYERS).rglob("*.tif")) + sorted(
        p for r in runs_out if r["group"] == "current" and r["run_id"] in PIXEL_LAYER_RUNS
        for p in (PIXELS / r["run_id"]).glob("*_part[0-9][0-9].tif"))
    fetched = {d.name: json.loads((d / "fetch_record.json").read_text())
               for d in sorted((PIXELS / R3_LAYERS).iterdir()) if (d / "fetch_record.json").is_file()}
    return {
        "what": "The last build of ui_data/ by scripts/build_ui_early_data.py: which code built it, "
                "from which inputs (round 13's question 28; register "
                "spec-ui-data-build-record-in-docs-in-a-later-round).",
        "command": " ".join(["python", *sys.argv]),
        "date": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "git": git, "environment": environment_state(),
        "runs": {g: sorted(r["run_id"] for r in runs_out if r["group"] == g)
                 for g in ("current", "earlier")},
        "r3_display_rasters": {
            "fetched_by": "scripts/fetch_ui_r3_layers.py",
            "areas": {a: {k: f[k] for k in ("runs_served", "keys", "assets_opened", "pixel_layers",
                                            "git") if k in f}
                      for a, f in fetched.items()},
            "files_off_git": [{"file": str(p.relative_to(PIXELS)), "bytes": p.stat().st_size,
                               "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                              for p in off_git]},
    }


def main() -> None:
    from fmu.utils.provenance import git_state

    git = {k: v for k, v in git_state().items() if k != "root"}
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    notes = add_box_runs() + add_keptland_runs() + add_r3_runs()
    pixel_layers: dict[str, list[dict]] = {}
    area_cache = {a: area_layers(a) for a in AREAS}
    runs_out = []
    for spec in RUNS:
        run_id, area, arm, vec = spec["run_id"], spec["area"], spec["arm"], spec["vec"]
        box = spec.get("box", False)
        keptland = spec.get("keptland", False)
        r3 = spec.get("r3", False)
        cfg = load_config(str(REPO / "configs" / f"{run_id}.yaml"))
        k = cfg.clustering.k
        ceiling = float(cfg.merge.max_area_ha)
        run = json.loads((vec / f"{run_id}_run.json").read_text())
        md = run["merge_diagnostics"]
        ai = area_cache[area]
        odisha = AREAS[area]["site"] == "Odisha"
        sanjay = AREAS[area]["site"] == "Sanjay Van"
        stands_fc, st = run_stands(run_id, arm, vec, keptland=keptland, r3=r3)
        write_json(OUT / "by_run" / run_id / "stands.json", encode_stands(stands_fc))
        sp_file, median_sp = superpixel_layer(run_id, vec)
        layers = pixel_feature_layers(run_id, arm) if run_id in PIXEL_LAYER_RUNS else None
        if layers is not None:
            pixel_layers[run_id] = layers
        if keptland and not r3:
            # The same features as its source run (copied assets): the same pixel layers.
            layers = pixel_layers.get(spec["pixels_from"])
        if run_id in PIXEL_LAYER_RUNS and layers is None:
            notes.append(f"{run_id}: no GeoTIFFs under {PIXELS / run_id}, so its feature layers "
                         "are stand means")
        if layers is None:
            layers = feature_layers(run_id, arm, stands_fc, early=not r3)
        seg_bands = [b.band for b in cfg.segmentation.input_bands]
        facts = dict(ai["facts"])
        facts.update({
            "n_feature_bands": 64 if arm == "alphaearth" else st["n_bands"],
            "n_segmentation_bands": 64 if seg_bands == ["*"] else len(seg_bands),
            "segmentation_bands": None if seg_bands == ["*"] else seg_bands,
            "seed_spacing_m": int(cfg.segmentation.size * cfg.export.analysis_scale_m),
            "n_superpixels": md["n_superpixels"], "median_superpixel_ha": median_sp,
            "n_stands": md["n_stands"], "median_stand_ha": st["median_area"],
            "min_stand_ha": float(cfg.merge.min_area_ha), "max_stand_ha": ceiling,
            "merge_criteria": [{"band": c.band, "tolerance": c.tolerance}
                               for c in cfg.merge.criteria],
            "relax_factor": float(cfg.merge.relax_factor),
            "merges_pass1": md.get("pass1_merges"),
            "merges_relaxed": md.get("pass2_merges", 0) - md.get("pass2_fallback_merges", 0),
            "merges_fallback": md.get("pass2_fallback_merges"),
            "stands_below_min": md.get("stands_below_min_area"),
            "below_min_isolated": md.get("orphans_isolated"),
            "below_min_blocked": md.get("orphans_area_blocked"),
            "k": k,
            "n_untyped_stands": st["n_untyped"],
            "share_stand_area_untyped": st["share_untyped"],
        })
        steps = [{
            "step": "masking", "title": "Land cover",
            "decisions": STEP_DECISIONS["masking"],
            "layers": [
                {"layer_id": "habitat_reason", "title": "Land cover", "kind": "shapes",
                 "file": ai["land_cover"],
                 "legend": [{"value": v, "label": lab, "color": col}
                            for v, (lab, col) in LAND_COVER.items()],
                 "colormap": None, "default_on": False},
                {"layer_id": "roi_outline", "title": "Area we mapped", "kind": "vector",
                 "file": ai["roi"], "color_by": None, "popup_fields": [], "style": "outline",
                 "default_on": True},
                *([{"layer_id": "kept_land", "title": "Kept land", "kind": "shapes",
                    "file": kept_land_layer(area),
                    "legend": [{"value": 1, "label": KEPT_LAND[0], "color": KEPT_LAND[1]}],
                    "colormap": None, "default_on": False}] if keptland else []),
            ]}, {
            "step": "data_load", "title": "Satellite image",
            "decisions": STEP_DECISIONS["data_load"],
            "layers": [{"layer_id": "true_colour", "title": "Satellite image (Sentinel-2)",
                        "kind": "raster", "parts": ai["tc"], "legend": None, "colormap": None,
                        "smooth": True, "default_on": True}]}, {
            "step": "features", "title": "What we measure",
            "decisions": STEP_DECISIONS["features_fv" if arm == "feature_vector"
                                        else "features_ae"],
            "layers": layers}, {
            "step": "segmentation", "title": "Superpixels",
            "decisions": STEP_DECISIONS["segmentation"],
            "layers": [{"layer_id": "superpixels", "title": "Superpixels", "kind": "lines",
                        "encoding": "polyline6", "file": sp_file,
                        "legend": [{"label": "Edge between superpixels", "color": "#ffd400"}],
                        "colormap": None, "default_on": False}]}, {
            "step": "merge", "title": "Stands",
            "decisions": STEP_DECISIONS["merge"],
            "layers": [{"layer_id": "stands", "title": "Stands", "kind": "vector",
                        "file": f"by_run/{run_id}/stands.json", "color_by": None,
                        "style": "outline",
                        "popup_fields": ["stand_id", "area_ha", "canopy_height",
                                         "ndvi_amplitude_annual", "stand_type"],
                        "default_on": True}]}, {
            "step": "clustering", "title": "Stand types",
            "decisions": STEP_DECISIONS["clustering"],
            "layers": [{"layer_id": "stand_types", "title": "Stand types", "kind": "vector",
                        "file": f"by_run/{run_id}/stands.json", "color_by": "stand_type",
                        "legend": [{"value": int(t), "label": f"Type {t}",
                                    "color": TYPE_COLORS[int(t) % 8]} for t in st["types"]],
                        "popup_fields": ["stand_id", "stand_type", "area_ha"],
                        "default_on": False},
                       {"layer_id": "removed_land", "title": "Land that isn't trees or scrub",
                        "kind": "shapes", "file": ai["land_cover"],
                        "only": [v for v in LAND_COVER if v != 1], "fill": "#3d4540",
                        "legend": None, "colormap": None, "default_on": False,
                        "description": "Cropland, built-up land, water, other land and pixels "
                                       "with no land-cover data, from the land-cover step."}]}]
        if odisha:
            # A kept-land run's plots are not joined to its stands here. The round-6 runs' field
            # check is not run; the _s1desc runs' is (round 7), but its join is not read here
            # (review C24). An R3 run's plots take its set's declared join.
            declared = R3_SCORES / f"{r3_set(arm, ceiling)}_joined.csv" if r3 else None
            pfc, pn = plots_for(run_id, AREAS[area]["district"], ai["geom"],
                                stands_fc if box else None, with_stands=not keptland or r3,
                                declared=declared)
            if r3:
                check_declared_join(run_id, pfc, stands_fc)
            write_json(OUT / "by_run" / run_id / "plots.geojson", pfc)
            facts.update({"plots_in_district": pn["in_district"], "plots_inside": pn["inside"],
                          "plots_on_kept_pixels": pn["kept"]})
            if "with_stand" in pn:
                facts["plots_with_stand"] = pn["with_stand"]
            plot_fields = ["plot_key", "habitation", "field_type", "mask", "in_mapped_area",
                           "outside_reason"] + ([] if keptland and not r3
                                                else ["stand_id", "stand_type"])
            steps.append({
                "step": "fes_plots", "title": "Field check",
                "decisions": STEP_DECISIONS["fes_plots"],
                "layers": [{"layer_id": "plots", "title": "FES plots", "kind": "vector",
                            "file": f"by_run/{run_id}/plots.geojson", "color_by": "field_type",
                            "legend": [{"value": v, "label": lab, "color": FIELD_COLORS[v]}
                                       for v, lab, _ in FIELD_TYPES],
                            "popup_fields": plot_fields,
                            "default_on": True}]})
        entry = {
            "run_id": run_id, "site": AREAS[area]["site"], "area": AREAS[area]["title"],
            "arm": arm, "stand_ceiling_ha": ceiling, "k": k, "roi": AREAS[area]["roi"],
            "config": f"configs/{run_id}.yaml",
            "source_commit": "4795358" if box else "df45350",
            "merge_rule": "spec-merge-pass2-skip-at-minimum" if box else "before the merge fix",
            "fes_declared": box,
            "bounds": ai["bbox"],
            "start_bounds": ai["start_bounds"] if odisha else ai["bbox"],
            "note": SANJAY_NOTE if sanjay else "", "facts": facts,
            "steps": steps}
        entry.update(versions(run_id, area, r3, cfg, stands_fc))
        if keptland:
            where = "at Sanjay Van" if sanjay else f"in the {AREAS[area]['title']} boxes"
            files, clustering = keptland_files(run_id, vec, run, where,
                                               (ai["bbox"][1] + ai["bbox"][3]) / 2)
            kl = md.get("kept_land") or {}
            facts.update({
                "kept_land_ha": kl.get("kept_land_ha"),
                "kept_land_ha_without_superpixel": kl.get("kept_land_ha_without_superpixel"),
                "superpixel_ha_off_kept_land": kl.get("superpixel_ha_off_kept_land"),
                "stands_over_max_stand_ha": md.get("stands_over_max_area"),
                "largest_excess_over_max_stand_ha": md.get("excess_over_max_area_largest_ha"),
                "stands_left_out_of_fit": clustering.get("n_stands_left_out_of_fit"),
                "area_ha_left_out_of_fit": clustering.get("area_ha_in_stands_left_out_of_fit"),
            })
            entry.update({
                "kept_land": True,
                # Round 8: the descending-orbit runs' declared field check has been run (numbers
                # only, odisha_script/keptland_scores/); the round-6 ascending runs' has not.
                "fes_declared": run_id.endswith("_s1desc"),
                "source_commit": str(run["git"]["commit"])[:7],
                "merge_rule": "spec-merge-pass2-skip-at-minimum, spec-merge-pass2-soft-ceiling",
                "note": (SANJAY_NOTE + " " if sanjay else "") + "SNIC and the merge saw kept "
                        "land only (trees or scrub): the rest of the "
                        + ("rectangle" if sanjay else "boxes") + " is in no stand."
                        + (" Its radar comes from the descending Sentinel-1 orbit. Its field-check "
                           "scores here are round 7's, kept as history: the record is the scores on "
                           "its _r9 re-run, which this site does not show."
                           if run_id.endswith("_s1desc") else "")
                        + (MEANS_NOTE.format(run=run_id) if stand_means(run_id, vec) else ""),
                "files": files})
        if r3:
            r3_entry(entry, facts, run, clustering, st, cfg, arm, ceiling, sanjay)
        runs_out.append(entry)
        print("built", run_id, st["n_stands"], "stands")
    for note in notes:
        print("note:", note)
    has_boxes = any(spec.get("box") for spec in RUNS)
    earlier = [r for r in runs_out if r["group"] == "earlier"]
    current = [r for r in runs_out if r["group"] == "current"]
    kept = [r for r in earlier if r.get("kept_land") and r["roi"] != "boxes"]
    kept_boxes = [r for r in earlier if r.get("kept_land") and r["roi"] == "boxes"
                  and not r["run_id"].endswith("_s1desc")]
    kept_s1desc = [r for r in earlier if r.get("kept_land") and r["run_id"].endswith("_s1desc")]
    short = SHORT_LABEL_WITH_BOXES if has_boxes else SHORT_LABEL
    label = LABEL
    if kept:
        short = SHORT_LABEL_WITH_KEPTLAND
        label += KEPTLAND_LABEL.format(commit=", ".join(sorted({r["source_commit"] for r in kept})))
    if kept_boxes:
        short = SHORT_LABEL_WITH_BOX_KEPTLAND
        label += KEPTLAND_BOX_LABEL.format(
            n=NUMBER_WORDS.get(len(kept_boxes), str(len(kept_boxes))),
            commit=", ".join(sorted({r["source_commit"] for r in kept_boxes})))
    if kept_s1desc:
        short = SHORT_LABEL_WITH_S1DESC
        label += KEPTLAND_S1DESC_LABEL.format(
            n=NUMBER_WORDS.get(len(kept_s1desc), str(len(kept_s1desc))),
            commit=", ".join(sorted({r["source_commit"] for r in kept_s1desc})))
    index = {"label": R3_LABEL.format(commit=", ".join(sorted({r["source_commit"] for r in current})))
                      + label,
             "short_label": R3_SHORT_LABEL.format(n_current=len(current), n_earlier=len(earlier)),
             "earlier_short_label": short,
             "commit": "early build", "fes_comparison": "fes_comparison.json",
             "history_links": [{"label": "the round 13 record", "path": ROUND13},
                               {"label": "the round 14 record", "path": ROUND14}],
             "what_changed": {"review": REVIEW,
                              "groups": [{"title": g["title"], "record": g["record"],
                                          "items": [{"ref": ref, "text": text}
                                                    for ref, text in g["items"]]}
                                         for g in WHAT_CHANGED]},
             "runs": runs_out}
    write_json(OUT / "index.json", index)
    write_json(OUT / "fes_comparison.json", fes_rows())
    if OUT.resolve() == (REPO / "ui_data").resolve():
        BUILD_RECORD.write_text(json.dumps(build_record(git, runs_out), indent=1) + "\n")


def fes_rows() -> dict:
    tests = [
        ("drawing_all_plots", "Plots of the same field type share a stand"),
        ("drawing_multi_plot", "The same, counting only stands that hold two or more plots"),
        ("pair_precision", "Plots that share a stand are the same field type"),
        ("labelling_district", "Plots of the same field type get the same stand type"),
        ("far_apart", "Far-apart plots of the same field type get the same stand type"),
    ]
    committed = {
        10.0: [(0.0121, 93.7, 0.063, 0.630), (0.0257, 77.0, 0.230, 1.0),
               (0.5385, 55.2, 0.451, 1.0), (0.0389, 66.8, 0.332, 1.0),
               (-0.0118, 46.6, 0.534, 1.0)],
        3.0: [(0.0060, 92.1, 0.080, 0.716), (0.0244, 65.7, 0.344, 1.0),
              (0.5575, 71.7, 0.284, 1.0), (0.0793, 83.1, 0.169, 1.0),
              (0.0143, 64.0, 0.360, 1.0)],
    }
    rerun = {10.0: {"drawing_all_plots": 0.0157, "drawing_multi_plot": 0.0364,
                    "labelling_district": 0.0619},
             3.0: {"drawing_all_plots": 0.0057, "drawing_multi_plot": 0.0233,
                   "labelling_district": 0.0478}}
    rows = []
    for ceil, vals in committed.items():
        for (tid, title), (score, pct, p, ph) in zip(tests, vals, strict=True):
            rows.append({"arm": "feature_vector", "stand_ceiling_ha": ceil, "roi": "hulls",
                         "analysis": "primary", "stands": "September 2026 runs (Phase 3)",
                         "test": tid, "title": title, "score": score, "chance_percentile": pct,
                         "p": p, "p_holm": ph, "n_plots": 267,
                         # No run in ui_data holds the September stands.
                         "run_ids": []})
        for tid, title in tests:
            if tid in rerun[ceil]:
                rows.append({"arm": "feature_vector", "stand_ceiling_ha": ceil, "roi": "hulls",
                             "analysis": "primary", "stands": "13 October 2026 re-runs",
                             "test": tid, "title": title, "score": rerun[ceil][tid],
                             "chance_percentile": None, "p": None, "p_holm": None,
                             "n_plots": 267, "run_ids": RERUN_IDS[ceil]})
    reading = (
        "At neither stand size can the stands be told apart from a randomly placed copy of the "
        "same stand map, on drawing or on labelling. None of the ten planned tests passes once "
        "corrected for running ten. That does not make the stands wrong: with 267 plots in 20 "
        "villages, a real but modest agreement could go undetected.")
    rows += keptland_rows(tests)
    rows += r3_rows(tests)
    return {"label": "Phase 3 numbers (September 2026 runs), the 13 October re-runs' scores, and the "
                     "15 October kept-land runs' scores, numbers only (the declared chance test was not "
                     "run on these stands), with, beside them on the same plots, the 13 Oct box runs' "
                     "stands (the box_runs rows: a descriptive comparison, not a declared score); and "
                     "R3's four sets, each with its declared chance test (register entry "
                     "field-r3-scores-the-record-once-they-exist: R3's scores are the record, the _r9 "
                     "scores the record from before the fixes, which are not in ui_data). The 15 "
                     "October scores here stay as history.",
            "reading": reading, "reading_for": "September 2026 runs (Phase 3)", "rows": rows}


def keptland_rows(tests: list[tuple[str, str]]) -> list[dict]:
    """The field check of the four descending-orbit kept-land runs (round 7,
    odisha_script/keptland_scores/keptland_s1desc_scores.json): every analysis, five rows each,
    numbers only. Each row names the four runs it belongs to; the box_runs analysis, the 13 Oct
    box runs' stands on the same plots, is part of their field check as a descriptive comparison,
    not a declared score, and its rows say so in their own stands label."""
    path = REPO / "odisha_script" / "keptland_scores" / "keptland_s1desc_scores.json"
    if not path.exists():
        return []
    stat = {"drawing_all_plots": "delin_all", "drawing_multi_plot": "delin_multi",
            "pair_precision": "prec", "labelling_district": "lab_wmean", "far_apart": "far_gap"}
    run_ids = sorted(KEPTLAND_S1DESC_RUNS)
    rows = []
    for a in json.loads(path.read_text())["analyses"]:
        for tid, title in tests:
            rows.append({"arm": "feature_vector", "stand_ceiling_ha": 3.0, "roi": "boxes",
                         "analysis": a["analysis"],
                         "stands": (BOX_RUNS_STANDS if a["analysis"] == "box_runs"
                                    else "15 Oct 2026 kept-land runs (descending radar)"),
                         "test": tid, "title": title, "score": a[stat[tid]],
                         "chance_percentile": None, "p": None, "p_holm": None,
                         "n_plots": a["counts"]["plots"],
                         "declaration": "odisha_script/PHASE_KEPTLAND_PREDECLARED.md",
                         "run_ids": run_ids})
    return rows


R3_STANDS = "R3 runs of 28 Oct 2026"
R3_SETS = (("feature_vector", 3.0), ("alphaearth", 3.0), ("feature_vector", 10.0),
           ("alphaearth", 10.0))


def r3_rows(tests: list[tuple[str, str]]) -> list[dict]:
    """The declared field check and chance test of R3's four sets (round 14, Task 8;
    odisha_script/keptland_scores/keptland_<set>_r14_scores.json and _chance.json). Every analysis
    of the scores file, five rows each, with the chance test's percentile, p and Holm p where the
    chance file has that analysis (the primary, S1 and S2); and C1, score 4 without Kendujhar,
    beside the primary, outside Holm and with no pass or fail
    (PHASE_KEPTLAND_AMENDMENT_chance_checks.md). Each row names the set's four runs, as its chance
    file does. The build stops if a chance file's observed score is not its scores file's."""
    stat = {"drawing_all_plots": "delin_all", "drawing_multi_plot": "delin_multi",
            "pair_precision": "prec", "labelling_district": "lab_wmean", "far_apart": "far_gap"}
    rows = []
    for arm, ceil in R3_SETS:
        stem = r3_set(arm, ceil)
        scores = json.loads((R3_SCORES / f"{stem}_scores.json").read_text())
        chance = json.loads((R3_SCORES / f"{stem}_chance.json").read_text())
        common = {"arm": arm, "stand_ceiling_ha": ceil, "roi": "boxes",
                  "declaration": "odisha_script/PHASE_KEPTLAND_PREDECLARED.md",
                  "run_ids": sorted(chance["runs"]), "set": stem}
        for a in scores["analyses"]:
            tested = chance["analyses"].get(a["analysis"], {}).get("scores", {})
            for tid, title in tests:
                c = tested.get(stat[tid])
                if c is not None and abs(c["observed"] - a[stat[tid]]) > 1e-12:
                    raise SystemExit(f"{stem}: {a['analysis']} {tid}: the chance test's observed "
                                     "score is not the field check's")
                rows.append({**common, "analysis": a["analysis"],
                             "stands": BOX_RUNS_STANDS if a["analysis"] == "box_runs" else R3_STANDS,
                             "test": tid, "title": title, "score": a[stat[tid]],
                             "chance_percentile": c["pctile"] if c else None,
                             "p": c["p"] if c else None, "p_holm": c["holm_p"] if c else None,
                             "n_plots": a["counts"]["plots"]})
        c1 = chance["checks"]["C1"]
        rows.append({**common, "analysis": "C1", "stands": R3_STANDS,
                     "test": "labelling_district", "title": "Labelling, without Kendujhar",
                     "score": c1["observed"], "chance_percentile": c1["pctile"], "p": c1["p"],
                     "p_holm": None, "outside_holm": True,
                     "n_plots": c1["plots_scored_observed"]})
    return rows


if __name__ == "__main__":
    main()
