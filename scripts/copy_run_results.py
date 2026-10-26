"""Copy a batch run's results and manifests into the repo, without timings; files over 5 MB stay off git.

    python scripts/copy_run_results.py <run tree> <run_id> [--dest docs/reproducibility/keptland_runs]
        [--off-git outputs/<round>/results] [--through export|k_elbow]

Round 14 (round 14 brief, "Keep every run's data"): it also copies, when the run tree has them,
<run>_raster_at_plots.csv; the stages' result files beside the layers (<run>_clustering_*.csv and
.json, <run>_k_elbow*.csv and .json, written by the runner from the run folders); the record of
how the Drive exports ended (<run>_drive_exports.json and its _run.json, scripts/drive_export_states.py);
and, for every run folder of the run, its fmu.log as <run>_log_<kind>[_n].txt (a log, which may
hold times, so the results check leaves it out; a folder with no manifest, a pass that failed, as
<run>_log_failed_<n>.txt) and its input_images.json as <run>_input_images_<kind>[_n].json. A pass
that ends at the k elbow (round 14) is a kind of its own, k_elbow. With --through k_elbow, for a
batch that stopped after the elbow, it needs the features, segmentation and k_elbow passes, and
copies <run>_k_elbow_run.json and the k elbow's files in place of the layers and <run>_run.json,
which no such batch writes.

What it copies, from the run tree (a clean clone a batch ran from):
  - odisha_script/phase2_vectors/<run>_stands_merged.geojson, _stands_snic.geojson,
    _stands_dissolved.geojson: as they are;
  - <run>_run.json: the run record, without "run_dir" (a path holding the run's date and time);
  - <run>_read_back.json, if there is one: what odisha_script/odisha_read_back_export.py read back
    against the layers of a run that wrote its own record (round 13, review C30);
  - runs/<run>_<date>_<time>/manifest.json of each pass, as <run>_manifest_<features|segmentation|
    clustering|export>.json, without "run_dir", "total_elapsed_sec", each stage's "elapsed_sec", the
    export manifest's "run_timestamp" and each Drive export's "submitted_at". A run folder whose
    manifest ends at profiling is the read-back tool's own (odisha_script/odisha_read_back_export.py),
    not a pass, and is skipped, as is one with no manifest (a pass that failed before writing it). The
    features pass (round 9) is the one whose manifest ends at a feature stage; a run made before round
    9 has none. A kind of pass with more than one manifest (a config that needed a second wrapper
    pass, after a later stage raised, writes the earlier kinds again, every asset a hit) keeps the
    last under <run>_manifest_<kind>.json, as before, and each earlier one as
    <run>_manifest_<kind>_<n>.json, n = 1, 2, ... in the order they ran: the pass that computed the
    cache, with its export tasks, is among them. Until round 13 only the last was copied (review C35).
Until round 14 <run>_raster_at_plots.csv was not copied: it samples the stand rasters at the field
plots, which joins plots to stands outside the declared field check. The round 14 brief asks for it
kept with the run's other files; no declared score reads it.

Files over 5 MB (docs/decisions.yaml, spec-files-over-5-mb-off-git) are written to --off-git, never
into --dest; --dest gets <run>_files_off_git.json instead: for each such file its name, size in
bytes, SHA-256 and where it is, and its Drive copy ("drive"), once one is checked and recorded, which
a later copy of the same file keeps. Results only: the check at the end refuses a key naming a time or a
value holding a date and time in what it wrote to --dest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
# Bytes: over this, a file stays off git. 5 MB read strictly, 5,000,000 bytes (not 5 MiB), so a
# file over 5 MB on any reading is kept off.
LIMIT = 5_000_000
DROP = {"run_dir", "total_elapsed_sec", "elapsed_sec", "run_timestamp", "submitted_at"}
TIME_WORDS = ("time", "elapsed", "date", "duration", "started", "finished", "_sec")
SETTINGS = ("dates", "time_reference")  # config keys that are settings, not timings
STAMP = re.compile(r"20\d\d-\d\d-\d\dT\d\d:|20\d{6}_\d{6}")
LAYERS = ("stands_merged", "stands_snic", "stands_dissolved")
PASSES = ("segmentation", "clustering", "export")
# The passes a run needs, by how far its batch went (round 14): a full batch, or one that stopped
# after the k elbow. A pass ending at k_elbow is a kind of its own either way.
NEEDED = {"export": PASSES, "k_elbow": ("features", "segmentation", "k_elbow")}
KINDS = ("features", "segmentation", "k_elbow", "clustering", "export")
# The stages' result files beside the layers (StageResult.files, copied there by the runner).
STAGE_FILES = ("clustering_stand_table.csv", "clustering_fit_rows.csv", "clustering_kmeans.json",
               "k_elbow.csv", "k_elbow_stand_table.csv", "k_elbow_fit_rows.csv", "k_elbow_types.csv",
               "k_elbow_preprocessing.json")
# The first pass of a run since round 9 caches the feature stages and ends at one of them.
FEATURE_PASS_ENDS = ("masking", "data_load", "features_optical", "features_radar",
                     "features_structure", "features_static", "features_embedding")


def strip(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: strip(v) for k, v in obj.items() if k not in DROP}
    if isinstance(obj, list):
        return [strip(v) for v in obj]
    return obj


def time_keys(obj: Any, path: str = "") -> list[str]:
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}/{k}"
            if any(w in k.lower() for w in TIME_WORDS) and k not in SETTINGS:
                found.append(p)
            found += time_keys(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found += time_keys(v, f"{path}[{i}]")
    return found


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_folders(tree: Path, run_id: str) -> list[tuple[Path, str | None, dict | None]]:
    """Every run folder of the run, in the order they ran: (folder, kind, manifest), kind None for
    a folder with no manifest (a pass that failed) and the read-back tool's own folder left out."""
    out: list[tuple[Path, str | None, dict | None]] = []
    for d in sorted((tree / "runs").glob(f"{run_id}_2*")):
        if not (d / "manifest.json").exists():
            # A pass that failed before writing its manifest (the first-pass memory limit on a
            # cold cache, for one): its fmu.log is kept (round 14); a later pass of its kind counts.
            print(f"  {d.name}: no manifest (a pass that failed); its log is kept")
            out.append((d, None, None))
            continue
        manifest = json.loads((d / "manifest.json").read_text())
        last = manifest["stages"][-1]["name"]
        if last == "profiling":
            continue  # the read-back tool's own run folder, not a pass
        if last in FEATURE_PASS_ENDS:
            last = "features"
        elif last not in KINDS:
            raise SystemExit(f"{d}: a pass ending at {last}")
        out.append((d, last, manifest))
    return out


def passes(tree: Path, run_id: str, through: str = "export") -> dict[str, list[tuple[str, dict]]]:
    """Every manifest of each pass kind, by the stage it ends at, in the order the passes ran."""
    out: dict[str, list[tuple[str, dict]]] = {}
    for d, kind, manifest in run_folders(tree, run_id):
        if kind is not None and manifest is not None:
            out.setdefault(kind, []).append((d.name, strip(manifest)))
    missing = [k for k in NEEDED[through] if k not in out]
    if missing:
        raise SystemExit(f"{run_id}: no {missing} pass in {tree / 'runs'}")
    return out


def numbered(kinds: list[str | None]) -> list[str]:
    """The suffix of each folder's files: its kind, and _n for every one of a kind but the last
    (as the manifests are named); a folder that failed, failed_<n>."""
    names: list[str] = []
    failed = 0
    for i, kind in enumerate(kinds):
        if kind is None:
            failed += 1
            names.append(f"failed_{failed}")
            continue
        same = [j for j, k in enumerate(kinds) if k == kind]
        names.append(kind if i == same[-1] else f"{kind}_{same.index(i) + 1}")
    return names


def copy(tree: Path, run_id: str, dest: Path, off_git: Path, through: str = "export") -> dict[str, Any]:
    """Write the run's files; return what went where."""
    vec = tree / "odisha_script" / "phase2_vectors"
    files: dict[str, bytes] = {}
    # Logs, image lists and the record of a read of Drive: kept, but not results, so the
    # check for times below leaves them out.
    not_results: set[str] = set()
    if through == "export":
        for layer in LAYERS:
            files[f"{run_id}_{layer}.geojson"] = (vec / f"{run_id}_{layer}.geojson").read_bytes()
        run = strip(json.loads((vec / f"{run_id}_run.json").read_text()))
        files[f"{run_id}_run.json"] = (json.dumps(run, indent=1, default=str) + "\n").encode()
        read_back = vec / f"{run_id}_read_back.json"
        if read_back.exists():
            files[read_back.name] = (json.dumps(strip(json.loads(read_back.read_text())), indent=1,
                                                default=str) + "\n").encode()
        at_plots = vec / f"{run_id}_raster_at_plots.csv"
        if at_plots.exists():
            files[at_plots.name] = at_plots.read_bytes()
        for name in (f"{run_id}_drive_exports.json", f"{run_id}_drive_exports_run.json"):
            if (vec / name).exists():
                files[name] = (vec / name).read_bytes()
                if name.endswith("_run.json"):
                    not_results.add(name)
    else:
        record = vec / f"{run_id}_k_elbow_run.json"
        if not record.exists():
            raise SystemExit(f"{run_id}: no {record.name} in {vec}")
        files[record.name] = (json.dumps(strip(json.loads(record.read_text())), indent=1,
                                         default=str) + "\n").encode()
    for name in STAGE_FILES:
        if (vec / f"{run_id}_{name}").exists():
            files[f"{run_id}_{name}"] = (vec / f"{run_id}_{name}").read_bytes()
    if through == "k_elbow" and f"{run_id}_k_elbow_fit_rows.csv" not in files:
        raise SystemExit(f"{run_id}: no k elbow files in {vec}")
    folders = run_folders(tree, run_id)
    for (d, _, _), suffix in zip(folders, numbered([k for _, k, _ in folders]), strict=True):
        if (d / "fmu.log").exists():
            files[f"{run_id}_log_{suffix}.txt"] = (d / "fmu.log").read_bytes()
            not_results.add(f"{run_id}_log_{suffix}.txt")
        if (d / "input_images.json").exists():
            files[f"{run_id}_input_images_{suffix}.json"] = (d / "input_images.json").read_bytes()
            not_results.add(f"{run_id}_input_images_{suffix}.json")
    for kind, manifests in passes(tree, run_id, through).items():
        # The last under the kind's own name, as before; the earlier ones numbered (review C35).
        *earlier, (_, last) = manifests
        files[f"{run_id}_manifest_{kind}.json"] = (json.dumps(last, indent=1, default=str)
                                                    + "\n").encode()
        for n, (_, manifest) in enumerate(earlier, start=1):
            files[f"{run_id}_manifest_{kind}_{n}.json"] = (json.dumps(manifest, indent=1, default=str)
                                                            + "\n").encode()
    dest.mkdir(parents=True, exist_ok=True)
    off: list[dict[str, Any]] = []
    for name, data in files.items():
        if name not in not_results:
            if name.endswith(".json"):
                left = time_keys(json.loads(data))
                if left:
                    raise SystemExit(f"{name}: keys naming a time left: {left[:5]}")
            if STAMP.search(data.decode(errors="replace")):
                raise SystemExit(f"{name}: a value holding a date and time is left")
        if len(data) > LIMIT:
            off_git.mkdir(parents=True, exist_ok=True)
            (off_git / name).write_bytes(data)
            off.append({"file": name, "bytes": len(data), "sha256": sha256(data),
                        "where": str((off_git / name).resolve())})
            stale = dest / name
            if stale.exists():
                stale.unlink()
        else:
            (dest / name).write_bytes(data)
    record = dest / f"{run_id}_files_off_git.json"
    # A Drive copy recorded before (round 8) stays recorded while the file is the same one.
    before = ({f["file"]: f for f in json.loads(record.read_text())["files"]}
              if record.exists() else {})
    for f in off:
        old = before.get(f["file"])
        if old and old.get("sha256") == f["sha256"] and old.get("drive"):
            f["drive"] = old["drive"]
    if off:
        record.write_text(json.dumps({
            "what": f"The files of {run_id} over 5 MB, kept off git "
                    "(docs/decisions.yaml, spec-files-over-5-mb-off-git): name, size, SHA-256, where.",
            "files": off}, indent=1) + "\n")
    elif record.exists():
        record.unlink()
    return {"in_repo": sorted(n for n in files if n not in {f["file"] for f in off}),
            "off_git": off}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tree", type=Path)
    ap.add_argument("run_id")
    ap.add_argument("--dest", type=Path, default=REPO / "docs" / "reproducibility" / "keptland_runs")
    ap.add_argument("--off-git", type=Path, required=True,
                    help="where files over 5 MB go: a git-ignored folder on the Mac")
    ap.add_argument("--through", choices=tuple(NEEDED), default="export",
                    help="how far the run's batch went (round 14): export, or k_elbow")
    args = ap.parse_args(argv)
    done = copy(args.tree, args.run_id, args.dest, args.off_git, args.through)
    for name in done["in_repo"]:
        print(f"  {name}: {(args.dest / name).stat().st_size / 1e6:.2f} MB, in the repo")
    for f in done["off_git"]:
        print(f"  {f['file']}: {f['bytes'] / 1e6:.2f} MB, OFF GIT at {f['where']}, sha256 {f['sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
