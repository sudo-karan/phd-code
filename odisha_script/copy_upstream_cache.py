"""Reuse cached upstream assets when a config change provably cannot affect them.

    python odisha_script/copy_upstream_cache.py --config configs/X.yaml [--from-ref main] [--execute]

The cache fingerprint is deliberately coarse: change any cache-relevant block of a
config and EVERY stage gets a new cache key, so the whole pipeline recomputes. That
is the right default -- a narrow dependency map that is wrong silently reuses a
stale asset -- but it means changing the number of stand types (clustering.k)
recomputes masking, the composites, all feature stages and segmentation, none of
which can read k.

This script makes the one safe exception explicit instead of doing it by hand. It
copies the upstream assets from the old fingerprint to the new one, so the next
pass finds them as cache hits and only clustering recomputes. Copying is immediate
and is not a queued Earth Engine task.

THE GUARD. It refuses unless the config at --from-ref and the config on disk differ
in nothing but the keys in SAFE_KEYS. Those are keys read only at or after the
clustering stage (checked by grep when this was written: clustering.k appears in
stages/clustering.py, profiling.py and metrics.py and nowhere upstream). Add a key
here only after checking the same thing for it.

What is copied: every cacheable output of every stage before clustering (merge is
not cached and recomputes each pass). What is not: clustering's own outputs.

Default is a dry run that prints the plan; --execute performs the copies.
Run from the repo root (the pipeline reads .env from the working directory).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import ee  # noqa: E402
from odisha_phase2_2_run_pipeline import (  # noqa: E402
    Pipeline, asset_exists, cached_asset_path, config_fingerprint, default_stage_names,
    get_stage_class, init_gee, load_config,
)

# (block, key) pairs that no stage before clustering reads.
SAFE_KEYS = {("clustering", "k")}
NOT_COPIED = {"merge", "clustering"}


def differences(old: dict, new: dict) -> set[tuple[str, str]]:
    out = set()
    for block in sorted(set(old) | set(new)):
        a, b = old.get(block), new.get(block)
        if a == b:
            continue
        if isinstance(a, dict) and isinstance(b, dict):
            out |= {(block, k) for k in set(a) | set(b) if a.get(k) != b.get(k)}
        else:
            out.add((block, ""))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--from-ref", default="main", help="git ref holding the config whose assets exist")
    ap.add_argument("--execute", action="store_true", help="perform the copies (default: dry run)")
    args = ap.parse_args()

    new = load_config(args.config)
    shown = subprocess.run(["git", "show", f"{args.from_ref}:{args.config}"], capture_output=True, text=True)
    if shown.returncode != 0:
        print(f"cannot read {args.config} at {args.from_ref}: {shown.stderr.strip()}")
        return 2
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / Path(args.config).name
        tmp.write_text(shown.stdout)
        old = load_config(tmp)

    diff = differences(old.model_dump(mode="json"), new.model_dump(mode="json"))
    fp_old, fp_new = config_fingerprint(old), config_fingerprint(new)
    print(f"{new.name}: {args.from_ref} fingerprint {fp_old} -> working tree {fp_new}")
    print(f"  config differences: {sorted(diff) if diff else 'none'}")
    if old.name != new.name:
        print("  REFUSING: the config name differs, so the asset folders differ")
        return 3
    unsafe = diff - SAFE_KEYS
    if unsafe:
        print(f"  REFUSING: {sorted(unsafe)} is not in SAFE_KEYS {sorted(SAFE_KEYS)}; an upstream stage "
              f"may read it, so its assets must be recomputed, not copied")
        return 3
    if fp_old == fp_new:
        print("  fingerprints are equal: nothing to copy")
        return 0

    init_gee()
    plan, missing = [], []
    for name in default_stage_names(new, through="clustering"):
        if name in NOT_COPIED:
            continue
        stage = get_stage_class(name)()
        for key in sorted(Pipeline._resolve_cacheable_outputs(stage)):
            src = cached_asset_path(new.name, name, key, fp_old)
            dst = cached_asset_path(new.name, name, key, fp_new)
            if asset_exists(dst):
                print(f"  already present  {name}/{key}")
            elif not asset_exists(src):
                missing.append(src)
                print(f"  SOURCE MISSING   {name}/{key}")
            else:
                plan.append((name, key, src, dst))
    if missing:
        print(f"  REFUSING: {len(missing)} source asset(s) missing; a partial copy would leave a run that "
              f"recomputes some stages on top of copies of others")
        return 3
    for name, key, src, dst in plan:
        if args.execute:
            ee.data.copyAsset(src, dst)
            print(f"  copied           {name}/{key}")
        else:
            print(f"  would copy       {name}/{key}")
    print(f"  {'copied' if args.execute else 'dry run:'} {len(plan)} asset(s)"
          + ("" if args.execute else "  (re-run with --execute)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
