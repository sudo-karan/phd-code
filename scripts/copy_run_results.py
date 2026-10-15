"""Copy a batch run's results and manifests into the repo, without timings; files over 5 MB stay off git.

    python scripts/copy_run_results.py <run tree> <run_id> [--dest docs/reproducibility/keptland_runs]
        [--off-git outputs/<round>/results]

What it copies, from the run tree (a clean clone a batch ran from):
  - odisha_script/phase2_vectors/<run>_stands_merged.geojson, _stands_snic.geojson,
    _stands_dissolved.geojson: as they are;
  - <run>_run.json: the run record, without "run_dir" (a path holding the run's date and time);
  - runs/<run>_<date>_<time>/manifest.json of each pass, as <run>_manifest_<segmentation|clustering|
    export>.json, without "run_dir", "total_elapsed_sec", each stage's "elapsed_sec", the export
    manifest's "run_timestamp" and each Drive export's "submitted_at". A run folder whose manifest
    ends at profiling is the read-back tool's own (odisha_script/odisha_read_back_export.py), not a
    pass, and is skipped, as is one with no manifest (a pass that failed before writing it).
<run>_raster_at_plots.csv is not copied: it samples the stand rasters at the field plots, which joins
plots to stands outside the declared field check.

Files over 5 MB (docs/decisions.yaml, spec-files-over-5-mb-off-git) are written to --off-git, never
into --dest; --dest gets <run>_files_off_git.json instead: for each such file its name, size in
bytes, SHA-256 and where it is. Results only: the check at the end refuses a key naming a time or a
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


def passes(tree: Path, run_id: str) -> dict[str, tuple[str, dict]]:
    """The last manifest of each pass kind, by the stage it ends at."""
    out = {}
    for d in sorted((tree / "runs").glob(f"{run_id}_2*")):
        if not (d / "manifest.json").exists():
            # A pass that failed before writing its manifest (the first-pass memory limit on a
            # cold cache, for one): its fmu.log stays on the Mac; a later pass of its kind counts.
            print(f"  {d.name}: no manifest (a pass that failed), skipped")
            continue
        manifest = json.loads((d / "manifest.json").read_text())
        last = manifest["stages"][-1]["name"]
        if last == "profiling":
            continue  # the read-back tool's own run folder, not a pass
        if last not in PASSES:
            raise SystemExit(f"{d}: a pass ending at {last}")
        out[last] = (d.name, strip(manifest))
    missing = [k for k in PASSES if k not in out]
    if missing:
        raise SystemExit(f"{run_id}: no {missing} pass in {tree / 'runs'}")
    return out


def copy(tree: Path, run_id: str, dest: Path, off_git: Path) -> dict[str, Any]:
    """Write the run's files; return what went where."""
    vec = tree / "odisha_script" / "phase2_vectors"
    files: dict[str, bytes] = {}
    for layer in LAYERS:
        files[f"{run_id}_{layer}.geojson"] = (vec / f"{run_id}_{layer}.geojson").read_bytes()
    run = strip(json.loads((vec / f"{run_id}_run.json").read_text()))
    files[f"{run_id}_run.json"] = (json.dumps(run, indent=1, default=str) + "\n").encode()
    for kind, (_, manifest) in passes(tree, run_id).items():
        files[f"{run_id}_manifest_{kind}.json"] = (json.dumps(manifest, indent=1, default=str)
                                                    + "\n").encode()
    dest.mkdir(parents=True, exist_ok=True)
    off: list[dict[str, Any]] = []
    for name, data in files.items():
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
    args = ap.parse_args(argv)
    done = copy(args.tree, args.run_id, args.dest, args.off_git)
    for name in done["in_repo"]:
        print(f"  {name}: {(args.dest / name).stat().st_size / 1e6:.2f} MB, in the repo")
    for f in done["off_git"]:
        print(f"  {f['file']}: {f['bytes'] / 1e6:.2f} MB, OFF GIT at {f['where']}, sha256 {f['sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
