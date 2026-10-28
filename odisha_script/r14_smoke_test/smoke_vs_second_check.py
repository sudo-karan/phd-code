"""Offline, reported only (the smoke test, the round 14 record): each run's elbow from the smoke
test beside the one the second live check made from the same cached assets. The elbow's file and
the types at every k compared byte for byte (SHA-256), the table of units and the rows after the
preprocessing by the live check's own compare_table. Writes
<smoke records>/r14_smoke_test_elbows_beside_the_second_check.json (results only).

    python smoke_vs_second_check.py <smoke records> <second check records> <run> [<run> ...]
"""
import importlib.util
import json
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("r14_live_check", "odisha_script/r14_live_check.py")
assert spec is not None and spec.loader is not None
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

smoke, second, runs = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
out = {"what": "Reported, not part of the smoke test's pass: its elbows beside the second live check's",
       "runs": {}}
for run in runs:
    res = {}
    for name in ("k_elbow.csv", "k_elbow_types.csv"):
        a, b = (smoke / f"{run}_{name}").read_bytes(), (second / f"{run}_{name}").read_bytes()
        res[name] = {"identical": a == b, "sha256": [check.sha256(a), check.sha256(b)]}
    for name in ("k_elbow_stand_table.csv", "k_elbow_fit_rows.csv"):
        res[name] = check.compare_table((smoke / f"{run}_{name}").read_text(),
                                        (second / f"{run}_{name}").read_text())
    res["knee"] = [check.knee_of((smoke / f"{run}_k_elbow.csv").read_text()),
                   check.knee_of((second / f"{run}_k_elbow.csv").read_text())]
    out["runs"][run] = res
(smoke / "r14_smoke_test_elbows_beside_the_second_check.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
print(json.dumps(out, indent=1, sort_keys=True)[:4000])
