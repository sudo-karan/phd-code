"""Which inputs did a run draw its superpixels from: features read from the cache, or computed live?

    python scripts/segmentation_route.py --config configs/<name>.yaml [configs/<other>.yaml ...]
        --runs-dir runs [--runs-dir <another folder of run folders> ...] [--out <file.json>]
        [--stage clustering --output cluster_labels]

Offline. It reads the manifest.json every pipeline run leaves in its run folder; no Earth Engine.

Why this exists. With caching on, a stage whose output is not cached runs live and its output is
exported. So the run that makes a config's superpixel asset feeds segmentation either with
feature images still being computed on the fly (nothing was cached yet), or with the cached
feature assets (an earlier pass got that far and this one read them back). The two do not give
the same superpixels (docs/reproducibility.md, "Superpixels depend on whether the features were
cached when SNIC ran"). Which one a run took is in its manifest: the segmentation stage shows
`snic_clusters` as "miss-exported" (computed in this run, export submitted), and the stages
before it show their outputs as "hit" (read from the cache) or "miss-exported" (computed live).

What it prints. For each config, every run in the folders given that

  - ran that config (the manifest's config name),
  - computed `snic_clusters` and submitted its export, and
  - wrote it under the config's CURRENT fingerprint (the fingerprint is in the asset name, so
    a run made before the config's content changed is left out),

with the route it took:

  cached   every output of the stages before segmentation was read from the cache
  live     none was
  mixed    some were; the statuses are listed

A config with no such run is reported as "not recorded": its superpixel asset was made by a run
whose folder is not in the folders given. Run folders are local and ignored by git, so the
answer is only as complete as the folders are.

The same question for another stage. `--stage clustering --output cluster_labels` asks it of the
run that made a config's stand types: were the outputs of the stages before clustering read from
the cache, or computed live? The stands a run exports are merged again in the export pass, from
whatever that pass reads, so stand types fitted in a pass that computed a feature stage live were
fitted on other inputs than the exported stands were made from (docs/demo/remerge/README.md).

The result holds run folder names, which carry the date and time the run started. They are
there as the name of the evidence, not as a run time of this script: the same folders give the
same file.

Run from the repo root.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SEGMENTATION = "segmentation"
SUPERPIXELS = "snic_clusters"
# mask_provenance feeds nothing downstream and was added later, so its status says nothing
# about what segmentation read.
IGNORED_OUTPUTS = {"mask_provenance"}


def route_of(stages: list[dict[str, Any]], stage_name: str = SEGMENTATION,
             output: str = SUPERPIXELS) -> tuple[str, dict[str, str]] | None:
    """The route one run took, from the `stages` list of its manifest.

    None when the run did not compute `output` (by default `snic_clusters`) in `stage_name` and
    submit its export (it read the asset back, computed it without exporting, or never reached
    that stage).
    """
    inputs: dict[str, str] = {}
    for stage in stages:
        status = stage.get("cache_status") or {}
        if stage.get("name") == stage_name:
            if status.get(output) != "miss-exported":
                return None
            states = set(inputs.values())
            if states == {"hit"}:
                return "cached", inputs
            if "hit" not in states:
                return "live", inputs
            return "mixed", inputs
        for key, state in status.items():
            if key not in IGNORED_OUTPUTS:
                inputs[f"{stage.get('name')}/{key}"] = state
    return None


def exported_fingerprint(stages: list[dict[str, Any]], stage_name: str = SEGMENTATION,
                         output: str = SUPERPIXELS) -> str | None:
    """The fingerprint in the name of the asset this run exported for `output`, if it exported one."""
    for stage in stages:
        if stage.get("name") != stage_name:
            continue
        for task in stage.get("export_tasks") or []:
            found = re.search(rf"/{re.escape(output)}__([0-9a-f]+)$", str(task.get("asset_path", "")))
            if found:
                return found.group(1)
    return None


def routes(config_name: str, fingerprint: str, runs_dirs: list[Path], stage_name: str = SEGMENTATION,
           output: str = SUPERPIXELS) -> dict[str, Any]:
    """Every run of `config_name` in `runs_dirs` that made its `output` asset under `fingerprint`."""
    found: list[dict[str, Any]] = []
    unreadable: list[str] = []
    for runs_dir in runs_dirs:
        for manifest in sorted(runs_dir.glob("*/manifest.json")):
            try:
                record = json.loads(manifest.read_text())
            except (OSError, ValueError):
                unreadable.append(str(manifest))
                continue
            if record.get("config_name") != config_name:
                continue
            stages = record.get("stages") or []
            took = route_of(stages, stage_name, output)
            if took is None or exported_fingerprint(stages, stage_name, output) != fingerprint:
                continue
            route, inputs = took
            found.append({"run": manifest.parent.name, "route": route, "inputs": inputs})
    found.sort(key=lambda r: r["run"])
    asked = {} if (stage_name, output) == (SEGMENTATION, SUPERPIXELS) else {"stage": stage_name, "output": output}
    return {
        "config": config_name,
        "fingerprint": fingerprint,
        **asked,
        # The last run to export the asset is the one whose superpixels the cache holds,
        # unless an earlier export was still in the queue; all are listed.
        "route": found[-1]["route"] if found else "not recorded",
        "runs": found,
        "unreadable_manifests": unreadable,
    }


def describe(result: dict[str, Any]) -> list[str]:
    """Plain lines for one config. Pure Python, so it is testable offline."""
    head = f"{result['config']} (fingerprint {result['fingerprint']}): "
    if not result["runs"]:
        what = f"`{result['output']}`" if "output" in result else "superpixel"
        return [head + f"not recorded: no run in these folders made its {what} asset"]
    lines = []
    for run in result["runs"]:
        line = f"{head}{run['route']:6s} in run {run['run']}"
        if run["route"] == "mixed":
            line += "  " + ", ".join(f"{k}={v}" for k, v in sorted(run["inputs"].items()))
        lines.append(line)
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", type=Path, nargs="+", required=True, help="config file(s)")
    ap.add_argument("--runs-dir", type=Path, action="append", required=True,
                    help="a folder of run folders, each with a manifest.json. Repeatable.")
    ap.add_argument("--out", type=Path, default=None, help="write the result here as JSON")
    ap.add_argument("--stage", default=SEGMENTATION, help="the stage whose inputs are asked about (default segmentation)")
    ap.add_argument("--output", default=SUPERPIXELS, help="the output of that stage a run must have made (default snic_clusters)")
    args = ap.parse_args()

    from fmu.config import load_config
    from fmu.utils.caching import config_fingerprint

    missing = [str(d) for d in args.runs_dir if not d.is_dir()]
    if missing:
        raise SystemExit(f"not a folder: {missing}")
    results = []
    for path in args.config:
        cfg = load_config(path)
        result = routes(cfg.name, config_fingerprint(cfg), args.runs_dir, args.stage, args.output)
        results.append(result)
        print("\n".join(describe(result)))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=1) + "\n")
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
