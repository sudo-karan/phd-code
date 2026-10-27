"""Read-only (ee_read_only.forbid_writes): the smoke test's pass rule 4 (the round 14 record, Done,
the round resumed again). For each run, its k elbow table read back from its asset as the runner
reads it on a cache hit (read_k_elbow of load_cached_table of the path the config's key gives),
against the elbow the step computed: the stage metadata of each of the run's k elbow manifests
whose k_elbow output is "miss-exported" (at least one; two if the table's export failed in one
pass and was sent again in a later one), and the k_elbow of <run>_k_elbow_run.json, which must say
k_elbow_computed_in_this_pass true. ks, n_rows, n_bands and elbow_k the same; inertia,
ari_median and ari_min agreeing by the live check's rule (its own agree()); the key the one the
run recorded. Writes <records>/r14_smoke_test_elbow_read_back.json (results only, no times); times
go to the log (stdout). Exit 0 if every run passes, 1 if not.

    python elbow_read_back.py <records folder> <config.yaml> [<config.yaml> ...]   (from the repo root)
"""
import importlib.util
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, "scripts")
import ee_read_only  # noqa: E402
from fmu.config import load_config  # noqa: E402
from fmu.stages.k_elbow import read_k_elbow  # noqa: E402
from fmu.utils.caching import cache_key, cached_asset_path, load_cached_table  # noqa: E402
from fmu.utils.gee import init_gee  # noqa: E402

spec = importlib.util.spec_from_file_location("r14_live_check", "odisha_script/r14_live_check.py")
assert spec is not None and spec.loader is not None
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

EXACT = ("ks", "n_rows", "n_bands", "elbow_k")
CLOSE = ("inertia", "ari_median", "ari_min")
MANIFEST = re.compile(r"_manifest_k_elbow(?:_\d+)?\.json$")


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def compare(computed: dict, back: dict) -> dict:
    same = {k: back.get(k) == computed.get(k) for k in EXACT}
    close = {}
    for k in CLOSE:
        a, b = computed.get(k), back.get(k)
        paired = isinstance(a, list) and isinstance(b, list) and len(a) == len(b) and len(a) > 0
        close[k] = {
            "agree": paired and all(check.agree(x, y) for x, y in zip(a, b, strict=True)),
            "identical": a == b,
            "largest_relative_difference": (max(check.relative_difference(float(x), float(y))
                                                for x, y in zip(a, b, strict=True)) if paired else None),
        }
    return {"same": same, "agree": close,
            "passes": all(same.values()) and all(v["agree"] for v in close.values())}


records, configs = Path(sys.argv[1]), sys.argv[2:]
print("started", now())
init_gee()
replaced = ee_read_only.forbid_writes()
out = {"what": "The smoke test's pass rule 4: each run's k elbow table read back from its asset "
               "(read_k_elbow of load_cached_table) against the elbow its k elbow pass computed, "
               "as its manifest's stage metadata and as its run record",
       "runs": {}}
for path in configs:
    cfg = load_config(path)
    run = cfg.name
    record = json.loads((records / f"{run}_k_elbow_run.json").read_text())
    computing = []
    for m in sorted(records.glob(f"{run}_manifest_k_elbow*.json")):
        if not MANIFEST.search(m.name):
            continue
        manifest = json.loads(m.read_text())
        for stage in manifest.get("stages") or []:
            if stage.get("name") == "k_elbow" and (stage.get("cache_status") or {}).get("k_elbow") == "miss-exported":
                computing.append((m.name, stage))
    key = cache_key(cfg, "k_elbow", "per_step")
    asset = cached_asset_path(cfg.name, "k_elbow", "k_elbow", key)
    back = read_k_elbow(load_cached_table(asset))
    res = {
        "asset": asset,
        "key_is_the_one_the_run_recorded": key == record["step_keys"]["k_elbow"],
        "run_record_says_computed_in_its_pass": record.get("k_elbow_computed_in_this_pass") is True,
        "computing_manifests": [name for name, _ in computing],
        "read_back": back,
        "against_the_run_record": compare(record["k_elbow"], back),
    }
    res["against_each_computing_manifest"] = {
        name: {"key_is_the_one_the_config_gives": stage.get("cache_key") == key,
               **compare(stage.get("metadata") or {}, back)}
        for name, stage in computing
    }
    ok_manifest = bool(computing) and all(
        r["key_is_the_one_the_config_gives"] and r["passes"]
        for r in res["against_each_computing_manifest"].values())
    res["passes"] = (res["key_is_the_one_the_run_recorded"] and res["run_record_says_computed_in_its_pass"]
                     and res["against_the_run_record"]["passes"] and ok_manifest)
    out["runs"][run] = res
out["passes"] = bool(out["runs"]) and all(r["passes"] for r in out["runs"].values())
(records / "r14_smoke_test_elbow_read_back.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
print(json.dumps(out, indent=1, sort_keys=True))
print("ended", now(), "calls replaced by forbid_writes:", len(replaced))
sys.exit(0 if out["passes"] else 1)
