"""Read-only (ee_read_only.forbid_writes): every config folder under the fmu asset root, and in each
the k_elbow folder's assets if it has one. Answers whether any k elbow table exists anywhere, and
lists the _r14_check_c and _d folders' stages. Run from the repo root."""
import json
import sys
from pathlib import Path
from datetime import UTC, datetime

sys.path.insert(0, "scripts")
import ee  # noqa: E402

import ee_read_only  # noqa: E402
from fmu.utils.gee import init_gee  # noqa: E402

init_gee()
refused = ee_read_only.forbid_writes()
ROOT = "projects/replicating-paper/assets/fmu"


def children(parent):
    out, token = [], None
    while True:
        params = {"parent": parent, "pageSize": 1000}
        if token:
            params["pageToken"] = token
        page = ee.data.listAssets(params)
        out.extend(page.get("assets", []))
        token = page.get("nextPageToken")
        if not token:
            return out


print("started", datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "replaced", len(refused))
configs = children(ROOT)
folders = [a for a in configs if a["type"] == "FOLDER"]
print("config folders under the root:", len(folders), "other entries:", len(configs) - len(folders))
k_elbow_folders, tables = [], []
for f in folders:
    stages = children(f["name"])
    for s in stages:
        if s["name"].rsplit("/", 1)[-1] == "k_elbow":
            k_elbow_folders.append(s["name"])
            tables.extend(a["name"] for a in children(s["name"]))
    if f["name"].endswith(("_r14_check_c", "_r14_check_d")):
        print(f["name"].rsplit("/", 1)[-1], "stages:", sorted(s["name"].rsplit("/", 1)[-1] for s in stages))
print("k_elbow folders:", json.dumps(k_elbow_folders, indent=1))
print("assets in them:", json.dumps(tables, indent=1))
if len(sys.argv) > 1:  # a results-only file: what the listing found, no times
    result = {
        "what": "Every config folder under the fmu asset root, and the assets of its k_elbow folder, if it has "
                "one (read-only; the round 14 record, read-only calls 12 and 13)",
        "asset_root": ROOT,
        "config_folders": sorted(f["name"].rsplit("/", 1)[-1] for f in folders),
        "k_elbow_folders": sorted(k_elbow_folders),
        "k_elbow_assets": sorted(tables),
    }
    Path(sys.argv[1]).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print("wrote", sys.argv[1])
print("ended", datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
