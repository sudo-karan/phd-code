"""Copy a run's masking, data-load and feature assets to a kept-land config, never segmentation or later.

    python scripts/reuse_upstream_assets.py                 # dry run: the plan, offline
    python scripts/reuse_upstream_assets.py --check         # and ask Earth Engine, read-only
    python scripts/reuse_upstream_assets.py --execute       # copy (needs Jaskaran's go)
    python scripts/reuse_upstream_assets.py --execute --resume   # finish a copy that stopped
        [--config configs/<new>.yaml ...] [--json <plan.json>] [--record <copies.json>]

Why. The cache fingerprint is one hash over the whole config, so each round-3 kept-land config
(Jaskaran's D1 to D4, 14 Oct 2026; docs/handoff/2026-10-14-round3.md) gets a new fingerprint and,
under its new name, an empty asset folder: a run would recompute masking, the composite and every
feature image, which no setting it changes can affect. This tool copies those assets from the run
of the config it copies, so that the run finds them as cache hits and computes only segmentation
and what follows. `ee.data.copyAsset` is immediate, not a queued task, and copies a source without
changing it.

THE PAIRS (`PAIRS`): each kept-land config, the run whose assets it reuses, and the record that
lists that run's assets. The source assets are taken from the record, by path, never from a
fingerprint recomputed from a config (as round 2 ruled for the demo set). For Sanjay Van the run is
the `_repro` run of the same content, the only run of it with assets at today's fingerprint: the
baseline's assets under its own name are from 27 Aug 2026, under another fingerprint, and the
AlphaEarth arm has none under its own name (docs/reproducibility.md).

THE GUARD. It refuses, for a pair, unless all of these hold:
  - the new config and the source config differ only in keys of `REUSE_SAFE_KEYS` and of
    `RECOMPUTE_KEYS`. Each key of `REUSE_SAFE_KEYS` is read by no stage before segmentation:
    `tests/test_reuse_upstream_assets.py` checks that none of their names appears in those stages'
    modules or in the fmu.utils modules they import. Each key of `RECOMPUTE_KEYS` is read by one
    stage before segmentation, the one it names, and by no other (the same test): where the
    configs differ in it, that stage's assets are not copied, and the new run computes them;
  - both run the same stages before segmentation, and only stages of `UPSTREAM_STAGES` are copied;
  - the record's run is the source config's (same config path), with the fingerprint the source
    config hashes to today, and every asset it lists sits at the path the cache layout gives;
  - the asset root of the record is the one the pipeline will read (`--check`, `--execute`).
With `--execute`, it also refuses unless every source exists and no destination does, for every
pair given, before it copies anything.

THE RECORD. `--execute` writes what it copied to `--record` (default
docs/reproducibility/keptland_reuse.json: results only, one entry per copy, rewritten after each
copy, so a copy that stops part way leaves a true record) and, beside it, `<name>_run.json` with
the command, the date, the git commit and whether the tree was dirty, and whether the copy
finished. The kept-land runs' manifests show the copied assets as plain cache hits; this record is
what ties them to their sources. If a copy stops part way, `--execute --resume` skips each
destination the record says was copied from the same source, and still refuses any other
destination that exists.

WHICH CODE. The tool puts its own checkout's src/ first on sys.path and refuses if fmu is imported
from anywhere else, so the fingerprints, stage lists and outputs it plans with are this checkout's,
as the batch's are (odisha_script/run_passes_safely.py does the same).

A cacheable output of a copied stage that the source never cached (for example `mask_provenance`
for the Sanjay Van `_repro` runs) is listed as such: the new run computes it live and caches it.

Run from the repo root (fmu reads .env from there). The dry run needs neither .env nor Earth
Engine.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))  # this checkout's fmu, not an editable install of another
RECORD = REPO / "docs" / "reproducibility" / "keptland_reuse.json"

# (new config, the config whose run's assets it reuses, the record listing that run's assets)
PAIRS: tuple[tuple[str, str, str], ...] = (
    ("configs/sanjay_van_baseline_keptland.yaml", "configs/sanjay_van_baseline_repro.yaml",
     "docs/demo/demo_set.json"),
    ("configs/sanjay_van_alphaearth_keptland.yaml", "configs/sanjay_van_alphaearth_repro.yaml",
     "docs/demo/demo_set.json"),
    *(
        (f"configs/odisha_v120_3ha_squares_{d}_keptland.yaml",
         f"configs/odisha_v120_3ha_squares_{d}.yaml", "docs/demo/demo_set_boxes.json")
        for d in ("kendujhar", "angul", "dhenkanal", "koraput")
    ),
)

# (block, key) pairs that no stage before segmentation reads. `("name", "")` is the config name,
# which is in the asset path (so the destination differs) but in no stage's output.
REUSE_SAFE_KEYS: frozenset[tuple[str, str]] = frozenset({
    ("name", ""),
    ("description", ""),
    ("export", "drive_folder"),
    ("segmentation", "mask_before_snic"),
    ("segmentation", "drop_kept_patches_below_min_area"),
    ("merge", "pass2_soft_ceiling"),
    ("merge", "pass2_skip_at_min_area"),
    ("clustering", "fit_excludes_stands_below_min_area"),
    ("metrics", "reference_config_name"),
})

# (block, key) pairs that one stage before segmentation reads, and which stage. A config may
# differ from its source in one of them; that stage's assets are then left out of the copies, and
# the new run computes them. features_static.cap_distance_to_water: Jaskaran, 15 Oct 2026 (round 6),
# spec-static-cap-distance-to-water. No other stage before segmentation reads static_features.
RECOMPUTE_KEYS: dict[tuple[str, str], str] = {
    ("features_static", "cap_distance_to_water"): "features_static",
}

# The only stages whose assets are copied. Segmentation and everything after it never are.
UPSTREAM_STAGES: tuple[str, ...] = (
    "masking",
    "data_load",
    "features_optical",
    "features_radar",
    "features_structure",
    "features_static",
    "features_embedding",
)


class RefusedError(Exception):
    """A pair the guard refuses, with the reason."""


@dataclass
class Copy:
    stage: str
    key: str
    source: str
    destination: str
    source_exists: bool | None = None
    destination_exists: bool | None = None


@dataclass
class Plan:
    config: str
    name: str
    fingerprint: str
    source_config: str
    source_name: str
    source_fingerprint: str
    record: str
    asset_root: str
    differences: list[str]
    copies: list[Copy] = field(default_factory=list)
    not_cached_in_source: list[str] = field(default_factory=list)
    # Assets of a stage that reads a key of RECOMPUTE_KEYS the configs differ in: not copied.
    computed_fresh: list[str] = field(default_factory=list)


def differences(old: dict[str, Any], new: dict[str, Any]) -> set[tuple[str, str]]:
    """(block, key) of every value that differs between two dumped configs; key "" for a block
    (or top-level field) that is not a mapping."""
    out: set[tuple[str, str]] = set()
    for block in sorted(set(old) | set(new)):
        a, b = old.get(block), new.get(block)
        if a == b:
            continue
        if isinstance(a, dict) and isinstance(b, dict):
            out |= {(block, k) for k in set(a) | set(b) if a.get(k) != b.get(k)}
        else:
            out.add((block, ""))
    return out


def _cacheable_outputs(stage_name: str) -> list[str]:
    import fmu.stages.data_load  # noqa: F401  (importing registers the stages)
    import fmu.stages.features_embedding  # noqa: F401
    import fmu.stages.features_optical  # noqa: F401
    import fmu.stages.features_radar  # noqa: F401
    import fmu.stages.features_static  # noqa: F401
    import fmu.stages.features_structure  # noqa: F401
    import fmu.stages.masking  # noqa: F401
    from fmu.pipeline import Pipeline
    from fmu.stages.base import get_stage_class

    return sorted(Pipeline._resolve_cacheable_outputs(get_stage_class(stage_name)()))


def _upstream(config: Any) -> list[str]:
    from fmu.pipeline import default_stage_names

    names = default_stage_names(config, through="clustering")
    before = names[: names.index("segmentation")]
    stray = [s for s in before if s not in UPSTREAM_STAGES]
    if stray:
        raise RefusedError(f"{config.name}: stages before segmentation outside UPSTREAM_STAGES: {stray}")
    return before


def plan_for(config: str, source_config: str, record: str, repo: Path = REPO) -> Plan:
    """The copies for one pair, or `RefusedError`. Offline: reads the two configs and the record."""
    from fmu.config import load_config
    from fmu.utils.caching import config_fingerprint

    new, src = load_config(repo / config), load_config(repo / source_config)
    diff = differences(src.model_dump(mode="json"), new.model_dump(mode="json"))
    unsafe = sorted(diff - REUSE_SAFE_KEYS - set(RECOMPUTE_KEYS))
    if unsafe:
        raise RefusedError(f"{new.name}: differs from {src.name} in {unsafe}, which is not in "
                      f"REUSE_SAFE_KEYS: a stage before segmentation may read it, so its assets "
                      f"must be computed, not copied")
    fresh = {RECOMPUTE_KEYS[d] for d in diff if d in RECOMPUTE_KEYS}
    if new.name == src.name:
        raise RefusedError(f"{new.name}: same name as its source; nothing to copy to")
    stages = _upstream(new)
    if stages != _upstream(src):
        raise RefusedError(f"{new.name}: runs other stages before segmentation than {src.name}")

    rec = json.loads((repo / record).read_text())
    runs = [r for r in rec["runs"] if r["config"] == source_config]
    if len(runs) != 1:
        raise RefusedError(f"{record}: {len(runs)} runs of {source_config}, not one")
    run = runs[0]
    root = rec["asset_root"]
    fp_src, fp_new = config_fingerprint(src), config_fingerprint(new)
    if run["fingerprint"] != fp_src:
        raise RefusedError(f"{src.name}: hashes to {fp_src} today, but the run in {record} saved its "
                      f"assets under {run['fingerprint']}")
    plan = Plan(config=config, name=new.name, fingerprint=fp_new, source_config=source_config,
                source_name=src.name, source_fingerprint=fp_src, record=record, asset_root=root,
                differences=[".".join(k for k in d if k) for d in sorted(diff)])
    listed = {(a["stage"], a["key"]): a["asset"] for a in run["assets"]}
    for stage in stages:
        for key in _cacheable_outputs(stage):
            if stage in fresh:
                plan.computed_fresh.append(f"{stage}/{key}")
                continue
            source = listed.get((stage, key))
            if source is None:
                plan.not_cached_in_source.append(f"{stage}/{key}")
                continue
            expected = f"{root}/{src.name}/{stage}/{key}__{fp_src}"
            if source != expected:
                raise RefusedError(f"{record}: {stage}/{key} of {src.name} is at {source}, not at "
                              f"{expected}")
            plan.copies.append(Copy(stage, key, source, f"{root}/{new.name}/{stage}/{key}__{fp_new}"))
    copied = {c.stage for c in plan.copies}
    assert copied <= set(UPSTREAM_STAGES), copied  # never segmentation or later
    assert not copied & fresh, copied & fresh  # never a stage that reads what differs
    return plan


def describe(plan: Plan) -> list[str]:
    lines = [f"{plan.name} ({plan.fingerprint}) <- {plan.source_name} ({plan.source_fingerprint}), "
             f"listed in {plan.record}",
             f"  configs differ in: {', '.join(plan.differences)}"]
    for c in plan.copies:
        state = ""
        if c.source_exists is not None:
            state = (f"  [source {'exists' if c.source_exists else 'MISSING'}, destination "
                     f"{'EXISTS' if c.destination_exists else 'absent'}]")
        lines.append(f"  copy {c.stage}/{c.key}: {c.source} -> {c.destination}{state}")
    for k in plan.not_cached_in_source:
        lines.append(f"  not cached in the source, computed live by the new run: {k}")
    for k in plan.computed_fresh:
        lines.append(f"  not copied, computed by the new run (it reads a key the configs differ in): {k}")
    lines.append(f"  {len(plan.copies)} asset(s) to copy")
    return lines


def check_fmu_is_this_checkouts() -> None:
    """Refuse if fmu is not imported from this checkout's src/ (see WHICH CODE above)."""
    import fmu

    here = Path(fmu.__file__).resolve()
    if (REPO / "src").resolve() not in here.parents:
        raise RefusedError(f"fmu is imported from {here}, not from {REPO / 'src'}: the plan would "
                           f"be made with another checkout's code")


def run_record_path(record: Path) -> Path:
    return record.with_name(record.stem + "_run.json")


def write_run_record(record: Path, argv: list[str], *, completed: bool) -> None:
    import datetime
    import shlex

    from fmu.utils.provenance import git_state

    run = {
        "result_file": record.name,
        "command_line": "python " + " ".join(shlex.quote(a) for a in ["scripts/reuse_upstream_assets.py", *argv]),
        "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "git": {k: v for k, v in git_state().items() if k != "root"},
        "completed": completed,
    }
    run_record_path(record).write_text(json.dumps(run, indent=1) + "\n")


def read_record(record: Path) -> dict[str, str]:
    """{destination: source} of the copies a record says were made; empty if there is none."""
    if not record.exists():
        return {}
    return {c["destination"]: c["source"] for c in json.loads(record.read_text())["copies"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", action="append", default=None,
                    help="only this kept-land config (repeatable); default: every pair in PAIRS")
    ap.add_argument("--check", action="store_true",
                    help="ask Earth Engine, read-only, whether each source and destination exists")
    ap.add_argument("--execute", action="store_true", help="copy the assets (implies --check)")
    ap.add_argument("--resume", action="store_true",
                    help="with --execute: skip the copies the record says were made")
    ap.add_argument("--json", type=Path, default=None,
                    help="write the plan here (after the copies, with --execute)")
    ap.add_argument("--record", type=Path, default=RECORD,
                    help="where --execute records the copies it makes")
    args = ap.parse_args(argv)
    argv = list(sys.argv[1:] if argv is None else argv)

    if args.resume and not args.execute:
        print("REFUSING: --resume goes with --execute")
        return 2
    pairs = [p for p in PAIRS if args.config is None or p[0] in args.config]
    unknown = sorted(set(args.config or []) - {p[0] for p in PAIRS})
    if unknown:
        print(f"REFUSING: not a kept-land config of PAIRS: {unknown}")
        return 2
    plans: list[Plan] = []
    try:
        check_fmu_is_this_checkouts()
        for config, source, record in pairs:
            plans.append(plan_for(config, source, record))
    except RefusedError as e:
        print(f"REFUSING: {e}")
        return 3

    if args.check or args.execute:
        import ee

        from fmu.settings import get_settings
        from fmu.utils.caching import asset_exists, ensure_parent_folders
        from fmu.utils.gee import init_gee

        root = get_settings().resolved_asset_root()
        for plan in plans:
            if plan.asset_root != root:
                print(f"REFUSING: {plan.record} lists assets under {plan.asset_root}, but the "
                      f"pipeline reads {root} (.env)")
                return 3
        init_gee()
        for plan in plans:
            for c in plan.copies:
                c.source_exists = asset_exists(c.source)
                c.destination_exists = asset_exists(c.destination)

    for plan in plans:
        print("\n".join(describe(plan)))
    total = sum(len(p.copies) for p in plans)
    print(f"{len(plans)} config(s), {total} asset(s) to copy"
          + ("" if args.execute else ("; nothing copied (dry run" + (", checked read-only)"
                                                                     if args.check else ")"))))

    def write_plan() -> None:
        if args.json:
            args.json.write_text(json.dumps([asdict(p) for p in plans], indent=1) + "\n")

    if not args.execute:
        write_plan()
        return 0

    done = read_record(args.record) if args.resume else {}
    if not args.resume and args.record.exists():
        print(f"REFUSING: {args.record} already records copies; use --resume to finish them, "
              f"or another --record")
        return 3
    # Copied before (the record says so) and still there: skipped. A recorded copy that is gone
    # is made again.
    already = {c.destination for p in plans for c in p.copies
               if done.get(c.destination) == c.source and c.destination_exists}
    missing = [c.source for p in plans for c in p.copies
               if c.destination not in already and not c.source_exists]
    present = [c.destination for p in plans for c in p.copies
               if c.destination not in already and c.destination_exists]
    if missing or present:
        print(f"REFUSING to copy: {len(missing)} source(s) missing, {len(present)} "
              f"destination(s) already there and not recorded as copied from their source; "
              f"nothing was copied")
        for x in missing:
            print(f"  missing: {x}")
        for x in present:
            print(f"  already there: {x}")
        return 3
    copies = [{"config": p.name, "stage": c.stage, "key": c.key, "source": c.source,
               "destination": c.destination}
              for p in plans for c in p.copies if c.destination in already]
    record = {"what": "Assets copied by scripts/reuse_upstream_assets.py, one entry per copy",
              "copies": copies}
    args.record.parent.mkdir(parents=True, exist_ok=True)
    write_run_record(args.record, argv, completed=False)
    n_new = 0
    for plan in plans:
        for c in plan.copies:
            if c.destination in already:
                print(f"  already copied {plan.name} {c.stage}/{c.key}")
                continue
            ensure_parent_folders(c.destination)
            ee.data.copyAsset(c.source, c.destination)
            copies.append({"config": plan.name, "stage": c.stage, "key": c.key,
                           "source": c.source, "destination": c.destination})
            args.record.write_text(json.dumps(record, indent=1) + "\n")
            c.destination_exists = True
            n_new += 1
            print(f"  copied {plan.name} {c.stage}/{c.key}")
    args.record.write_text(json.dumps(record, indent=1) + "\n")
    write_run_record(args.record, argv, completed=True)
    write_plan()
    print(f"copied {n_new} asset(s); {len(copies)} recorded in {args.record}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
