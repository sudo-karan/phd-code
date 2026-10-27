"""Copy the records of a first-half config that the batch did not finish (cut by the stop, or not
finished after the wrapper's passes) into the first half's records: every pass's manifest that
exists, and each run folder's fmu.log and input_images.json, with scripts/copy_run_results.py's own
copy() and its passes needed set to the kinds that ran, as the first two live checks' records were
copied (docs/reproducibility/r14_runs/README.md). The same checks for times, the same 5 MB rule.
Offline. A config with no run folder has nothing to copy, and says so.

    python odisha_script/r14_first_half/copy_unfinished.py <run tree> <run> --dest D --off-git O
        (from the run tree's root, so that the copy tool is the batch's)
"""
import argparse
import importlib.util
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("tree", type=Path)
ap.add_argument("run_id")
ap.add_argument("--dest", type=Path, required=True)
ap.add_argument("--off-git", type=Path, required=True)
args = ap.parse_args()

tool = Path(__file__).resolve().parents[2] / "scripts" / "copy_run_results.py"
spec = importlib.util.spec_from_file_location("copy_run_results", tool)
assert spec is not None and spec.loader is not None
crr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crr)

kinds = sorted({k for _, k, _ in crr.run_folders(args.tree, args.run_id) if k is not None})
folders = len(crr.run_folders(args.tree, args.run_id))
if folders == 0:
    print(f"{args.run_id}: no run folder in {args.tree / 'runs'}: nothing to copy (not started)")
    raise SystemExit(0)
crr.NEEDED["unfinished"] = tuple(kinds)
done = crr.copy(args.tree, args.run_id, args.dest, args.off_git, through="unfinished")
print(f"{args.run_id}: {folders} run folder(s), the passes that wrote a manifest: {kinds or 'none'}; "
      f"{len(done['in_repo'])} file(s) in the repo, {len(done['off_git'])} off git")
