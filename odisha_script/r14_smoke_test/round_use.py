"""Read-only: round 14's Earth Engine use since its start (26 Oct 2026 13:29 UTC), as every budget reading of
the round has read it (the record, Done, the cost estimate): Cloud Monitoring's hourly sums (batch, online) and
the task list (batch, cancelled tasks included), the tasks queued or running, and, with --folders, whether
each _r14 config's asset folder exists. Submits nothing (ee_read_only.forbid_writes). Prints JSON. Run from
the repo root or a run tree's root. (Committed with the smoke test's scripts, 27 Oct 2026; until then in the
session's scratch folder, quota/round_use.py.)"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, "scripts")
import ee  # noqa: E402
import google.auth.transport.requests  # noqa: E402

import ee_read_only  # noqa: E402

PROJECT = "replicating-paper"
ROUND_START = datetime(2026, 10, 26, 13, 29, tzinfo=UTC)
OCTOBER_LEFT_AT_START = 377.35

creds = ee.data.get_persistent_credentials()
ee.Initialize(credentials=creds, project=PROJECT)
refused = ee_read_only.forbid_writes()
creds.refresh(google.auth.transport.requests.Request())
now = datetime.now(UTC).replace(microsecond=0)
hdr = {"Authorization": f"Bearer {creds.token}", "x-goog-user-project": PROJECT}


def hourly(kind):
    params = {
        "filter": 'metric.type="earthengine.googleapis.com/project/cpu/usage_time" '
                  f'AND metric.label.compute_type="{kind}"',
        "interval.startTime": ROUND_START.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "interval.endTime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "aggregation.perSeriesAligner": "ALIGN_SUM",
        "aggregation.crossSeriesReducer": "REDUCE_SUM",
        "aggregation.alignmentPeriod": "3600s",
    }
    url = f"https://monitoring.googleapis.com/v3/projects/{PROJECT}/timeSeries?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=120) as r:
        resp = json.loads(r.read())
    return sum(float(p["value"].get("doubleValue", p["value"].get("int64Value", 0))) / 3600.0
               for ts in resp.get("timeSeries", []) for p in ts.get("points", []))


ops = ee.data.listOperations()
since, active = [], []
for op in ops:
    md = op.get("metadata", {})
    created = md.get("createTime")
    if created and datetime.fromisoformat(created.replace("Z", "+00:00")) >= ROUND_START:
        since.append(md)
    if md.get("state") in ("PENDING", "RUNNING", "CANCELLING"):
        active.append(md.get("description"))
task_batch = sum(float(m.get("batchEecuUsageSeconds", 0) or 0) for m in since) / 3600.0
mon_batch, mon_online = hourly("batch"), hourly("online")
use = max(mon_batch, task_batch) + mon_online
out = {
    "read_at_utc": now.isoformat(),
    "monitoring_batch_h": round(mon_batch, 4),
    "monitoring_online_h": round(mon_online, 4),
    "task_list_batch_h_since_round_start": round(task_batch, 4),
    "tasks_since_round_start": len(since),
    "tasks_since_by_state": {s: sum(1 for m in since if m.get("state") == s) for s in sorted({m.get("state") for m in since})},
    "queued_or_running": active,
    "round_use_h": round(use, 4),
    "october_left_h": round(OCTOBER_LEFT_AT_START - use, 4),
    "writes_refused": len(refused),
}
if "--folders" in sys.argv:
    from fmu.settings import get_settings
    from fmu.utils.caching import asset_exists

    root = get_settings().resolved_asset_root()
    names = sorted(p.stem for p in Path("configs").glob("*_r14*.yaml"))
    out["asset_root"] = root
    out["r14_folders_existing"] = [n for n in names if asset_exists(f"{root}/{n}")]
    out["r14_configs_checked"] = len(names)
print(json.dumps(out, indent=1))
