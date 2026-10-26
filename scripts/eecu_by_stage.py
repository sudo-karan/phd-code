"""One batch run's Earth Engine cost: EECU-hours by stage (batch) and by pass (online), per 1,000 ha.

    python scripts/eecu_by_stage.py CONFIG_NAME WRAPPER_LOG AREA_HA OUT.json

Read-only: it reads the task list and Cloud Monitoring and submits nothing. Round 9's Task I (run
in round 10) measures with it what one config costs per 1,000 ha (docs/handoff/2026-10-18-round10.md).

- Batch: every task in ee.data.listOperations() whose description is CONFIG_NAME + "_" and one
  of the names the config's tasks take, failed ones included, summed by the stage the name
  belongs to: <stage>_<output> for the cache exports (CACHED), and for the export stage's Drive
  files features_raw, features_scaled, cluster_labels and stands_<layer>_<format>. A task of
  another config whose name begins with this one's (<config>_repro, <config>_r9_check) is left
  out (round 13, review B26: a bare prefix charged it to this one).
- Online: Cloud Monitoring's online series (earthengine.googleapis.com/project/cpu/usage_time,
  compute_type online) over each pass's span: from the pass's stage header in the wrapper log
  (odisha_script/run_passes_safely.py) to the next stage header of any config, or to the end of
  its batch, whichever comes first. A batch whose wrapper left no "batch ... ended" line (killed
  outright, or a crash) has no end in the log, and its last pass is refused rather than run to the
  next batch's start (round 13). Each header carries its date since round 13; a header of an
  older log carries the time of day only, and is dated by the line before it (B26: every pass
  took the date of the log's first line). It is all of the project's online use in that span,
  whoever made it, and it cannot be split between the stages of one pass.

OUT.json holds results only (no dates or times); OUT_run.json beside it holds the pass spans,
when the figures were read and the git block of every run record (fmu.utils.provenance.git_state:
the commit of the checkout this script is in, whether tracked files were modified or, since round
14, untracked code was there, and which), read before anything is written. Until round 13 it read
git in the working directory after writing OUT.json, as `tracked_files_modified` (review C38): run
from another repository it named that one's commit, and measured again into a committed cost file
it counted the new numbers as a modified tracked file.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT = "replicating-paper"
IST = timedelta(hours=5, minutes=30)  # the wrapper log's clock is the Mac's, IST
# What each step caches, by stage: its tasks are described "<config>_<stage>_<output>"
# (fmu.pipeline), and tests/test_eecu_by_stage.py checks this against the stages' cacheable outputs.
CACHED = {
    "masking": ("habitat_mask", "landcover_summary", "mask_provenance", "water_mask"),
    "data_load": ("s2_composite",),
    "features_optical": ("optical_features",),
    "features_radar": ("radar_features",),
    "features_structure": ("structure_features",),
    "features_static": ("static_features",),
    "features_embedding": ("embedding_features",),
    "segmentation": ("snic_clusters", "snic_means"),
    "clustering": ("cluster_labels", "feature_stack"),
    "k_elbow": ("k_elbow",),
}
# The export stage's Drive files, "<config>_<file>": three rasters, and each vector layer in each format.
EXPORT_FILES = ("features_raw", "features_scaled", "cluster_labels") + tuple(
    f"stands_{layer}_{fmt}" for layer in ("merged", "snic", "dissolved") for fmt in ("shp", "geojson"))
OUTPUTS = {f"{stage}_{key}": stage for stage, keys in CACHED.items() for key in keys} | {
    f: "export" for f in EXPORT_FILES}
# A stage header of run_config_passes.sh: with the date since round 13, the time of day only before.
HEADER = re.compile(r"##### PASS\d+ (\S+) :: (\w+) :: (?:(\d{4}-\d{2}-\d{2}) )?(\d\d:\d\d:\d\d) #####")
WRAPPER_LINE = re.compile(r"\[run_passes_safely (\d{4}-\d{2}-\d{2} \d\d:\d\d:\d\d)\] (.*)")
BATCH_EDGE = re.compile(r"batch \S+ (started|ended)\b")


def stage_of(output: str) -> str | None:
    """The stage a task belongs to, from its description after '<config>_'; None if that is no
    name a task of the config takes (a task of a config whose name begins with this one's)."""
    return OUTPUTS.get(output)


def pass_spans(log_text: str, config: str) -> list[tuple[str, datetime, datetime]]:
    """(pass, start, end) in UTC for each pass of CONFIG in a wrapper log, in order.

    A pass runs from its stage header to the next stage header of any config, or to the end of its
    batch (the wrapper's "batch ... ended" line), whichever comes first. A pass that the next
    batch's "started" line would end is refused: its batch has no end line, and the gap to the next
    batch can be hours. A header without a date is dated by the line before it, a day later past
    midnight.
    """
    events: list[tuple[str | None, str, datetime]] = []  # (config, pass, when); None: a batch's edge
    last: datetime | None = None
    for line in log_text.splitlines():
        line = line.strip()
        if m := WRAPPER_LINE.fullmatch(line):
            last = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            if BATCH_EDGE.match(m.group(2)):
                events.append((None, m.group(2), last))
        elif m := HEADER.fullmatch(line):
            name, stage, day, clock = m.groups()
            if day:
                when = datetime.strptime(f"{day} {clock}", "%Y-%m-%d %H:%M:%S")
            elif last is None:
                raise ValueError("not a run_passes_safely log")
            else:
                when = datetime.combine(last.date(), datetime.strptime(clock, "%H:%M:%S").time())
                if when < last:
                    when += timedelta(days=1)
            last = when
            events.append((name, stage, when))
    if last is None:
        raise ValueError("not a run_passes_safely log")

    def utc(local: datetime) -> datetime:
        return (local - IST).replace(tzinfo=UTC)

    spans = []
    for i, (name, stage, when) in enumerate(events):
        if name != config:
            continue
        if i + 1 == len(events):
            raise ValueError(f"no line after {config}'s {stage} pass ends it in the log")
        after, what, end = events[i + 1]
        if after is None and (edge := BATCH_EDGE.match(what)) and edge.group(1) == "started":
            raise ValueError(f"no line of its own batch ends {config}'s {stage} pass: the batch has "
                             f"no 'ended' line (its wrapper was killed or crashed)")
        spans.append((stage, utc(when), utc(end)))
    if not spans:
        raise ValueError(f"no pass of {config} in the log")
    return spans


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
        if stage is None:
            continue
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

    # Which code: this script's checkout, as it is before anything is written (review C38).
    from fmu.utils.provenance import git_state

    git = {k: v for k, v in git_state(Path(__file__).resolve().parent).items() if k != "root"}

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
    record = {
        "result_file": args.out.name,
        "command_line": " ".join(["python", "scripts/eecu_by_stage.py", *(sys.argv[1:] if argv is None else argv)]),
        "read_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pass_spans_utc": [{"pass": n, "from": a.isoformat(), "to": b.isoformat()} for n, a, b in spans],
        "git": git,
    }
    args.out.with_name(args.out.stem + "_run.json").write_text(json.dumps(record, indent=1) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "tasks"}, indent=1))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
