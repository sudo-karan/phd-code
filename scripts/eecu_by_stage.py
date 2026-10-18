"""One batch run's Earth Engine cost: EECU-hours by stage (batch) and by pass (online), per 1,000 ha.

    python scripts/eecu_by_stage.py CONFIG_NAME WRAPPER_LOG AREA_HA OUT.json

Read-only: it reads the task list and Cloud Monitoring and submits nothing. Round 9's Task I (run
in round 10) measures with it what one config costs per 1,000 ha (docs/handoff/2026-10-18-round10.md).

- Batch: every task in ee.data.listOperations() whose description begins with CONFIG_NAME + "_",
  failed ones included, summed by the stage its description names: <config>_<stage>_<output> for
  the cache exports, and for the export stage's Drive files <config>_features_raw,
  _features_scaled, _cluster_labels and <config>_stands_*.
- Online: Cloud Monitoring's online series (earthengine.googleapis.com/project/cpu/usage_time,
  compute_type online) over each pass's span: from the pass's start line in the wrapper log
  (odisha_script/run_passes_safely.py) to the next pass's start, the last pass to the batch's end
  line. It is all of the project's online use in that span, whoever made it, and it cannot be
  split between the stages of one pass.

OUT.json holds results only (no dates or times); OUT_run.json beside it holds the pass spans,
when the figures were read and the git commit, as a run record does.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT = "replicating-paper"
IST = timedelta(hours=5, minutes=30)  # the wrapper log's clock is the Mac's, IST
STAGES = ("masking", "data_load", "features_optical", "features_radar", "features_structure",
          "features_static", "features_embedding", "segmentation", "clustering", "k_elbow")
EXPORT_FILES = ("features_raw", "features_scaled", "cluster_labels")


def stage_of(output: str) -> str:
    """The stage a task belongs to, from its description after '<config>_'."""
    if output in EXPORT_FILES or output.startswith("stands_"):
        return "export"
    for stage in STAGES:
        if output.startswith(stage + "_"):
            return stage
    return "other: " + output


def pass_spans(log_text: str, config: str) -> list[tuple[str, datetime, datetime]]:
    """(pass, start, end) in UTC for each pass of CONFIG in a wrapper log, in order."""
    day = re.search(r"\[run_passes_safely (\d{4}-\d{2}-\d{2}) ", log_text)
    if not day:
        raise ValueError("not a run_passes_safely log")
    starts = re.findall(rf"##### PASS\d+ {re.escape(config)} :: (\w+) :: (\d\d:\d\d:\d\d) #####", log_text)
    ends = re.findall(r"\[run_passes_safely (\d{4}-\d{2}-\d{2} \d\d:\d\d:\d\d)\] batch \S+ ended", log_text)
    if not starts or not ends:
        raise ValueError(f"no pass of {config}, or no end line, in the log")

    def utc(stamp: str) -> datetime:
        return (datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S") - IST).replace(tzinfo=UTC)

    bounds = [utc(f"{day.group(1)} {t}") for _, t in starts] + [utc(ends[-1])]
    return [(name, bounds[i], bounds[i + 1]) for i, (name, _) in enumerate(starts)]


def batch_by_stage(operations: list[dict], config: str) -> tuple[dict[str, float], dict[str, list[dict]]]:
    hours: dict[str, float] = collections.defaultdict(float)
    tasks: dict[str, list[dict]] = collections.defaultdict(list)
    for op in operations:
        md = op.get("metadata", {})
        desc = md.get("description", "")
        if not desc.startswith(config + "_"):
            continue
        output = desc[len(config) + 1:]
        stage = stage_of(output)
        eecu = float(md.get("batchEecuUsageSeconds", 0) or 0) / 3600.0
        hours[stage] += eecu
        tasks[stage].append({"output": output, "state": md.get("state"), "eecu_h": round(eecu, 4)})
    return dict(hours), dict(tasks)


def online_hours(token: str, start: datetime, end: datetime) -> float:  # pragma: no cover - network
    params = {
        "filter": 'metric.type="earthengine.googleapis.com/project/cpu/usage_time" '
                  'AND metric.label.compute_type="online"',
        "interval.startTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "interval.endTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "aggregation.perSeriesAligner": "ALIGN_SUM",
        "aggregation.crossSeriesReducer": "REDUCE_SUM",
        "aggregation.alignmentPeriod": f"{max(60, int((end - start).total_seconds()))}s",
    }
    url = f"https://monitoring.googleapis.com/v3/projects/{PROJECT}/timeSeries?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "x-goog-user-project": PROJECT})
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read())
    total = 0.0
    for ts in resp.get("timeSeries", []):
        for p in ts.get("points", []):
            v = p["value"]
            total += float(v.get("doubleValue", v.get("int64Value", 0))) / 3600.0
    return total


def summary(config: str, area_ha: float, batch: dict[str, float], online: list[tuple[str, float]],
            tasks: dict[str, list[dict]]) -> dict[str, Any]:
    per = 1000.0 / area_ha
    batch_total = sum(batch.values())
    online_total = sum(h for _, h in online)
    return {
        "what": "One run's Earth Engine cost, EECU-hours (scripts/eecu_by_stage.py): batch by stage from the task "
                "list, online by pass from Cloud Monitoring, and each per 1,000 ha of the ROI.",
        "config": config,
        "area_ha": area_ha,
        "batch_eecu_h": {k: round(v, 4) for k, v in sorted(batch.items())},
        "batch_eecu_h_per_1000_ha": {k: round(v * per, 4) for k, v in sorted(batch.items())},
        "online_eecu_h_by_pass": [{"pass": name, "eecu_h": round(h, 4), "per_1000_ha": round(h * per, 4)}
                                  for name, h in online],
        "batch_total": round(batch_total, 4),
        "online_total": round(online_total, 4),
        "total": round(batch_total + online_total, 4),
        "total_per_1000_ha": round((batch_total + online_total) * per, 4),
        "tasks": {k: sorted(v, key=lambda t: t["output"]) for k, v in sorted(tasks.items())},
    }


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - Earth Engine and network
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("config")
    ap.add_argument("log", type=Path)
    ap.add_argument("area_ha", type=float)
    ap.add_argument("out", type=Path)
    args = ap.parse_args(argv)

    import ee
    import google.auth.transport.requests

    creds = ee.data.get_persistent_credentials()
    ee.Initialize(credentials=creds, project=PROJECT)
    creds.refresh(google.auth.transport.requests.Request())
    spans = pass_spans(args.log.read_text(), args.config)
    batch, tasks = batch_by_stage(ee.data.listOperations(), args.config)
    online = [(name, online_hours(creds.token, a, b)) for name, a, b in spans]
    result = summary(args.config, args.area_ha, batch, online, tasks)
    args.out.write_text(json.dumps(result, indent=1) + "\n")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                                capture_output=True, text=True).stdout.strip())
    record = {
        "result_file": args.out.name,
        "command_line": " ".join(["python", "scripts/eecu_by_stage.py", *sys.argv[1:]]),
        "read_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pass_spans_utc": [{"pass": n, "from": a.isoformat(), "to": b.isoformat()} for n, a, b in spans],
        "git": {"commit": commit, "tracked_files_modified": dirty},
    }
    args.out.with_name(args.out.stem + "_run.json").write_text(json.dumps(record, indent=1) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "tasks"}, indent=1))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
