#!/bin/bash
# Run one or more pipeline configs through features -> segmentation -> clustering -> export
# on Earth Engine, in repeated cache passes, until every config has completed.
#
#   odisha_script/run_config_passes.sh <logfile> <config.yaml> [<config.yaml> ...]
#
# Started only by odisha_script/run_passes_safely.py, which sets RUN_PASSES_SAFELY=1; on its own
# it refuses to start (round 12). See docs/running.md.
#
# Why passes. On a cold cache the segmentation stage's RMS adjacent-distance step is
# computed on top of feature images that are not yet assets, and Earth Engine refuses
# it ("User memory limit exceeded" / "Computation timed out") for all but the smallest
# district. The failed attempt still starts the feature exports, so the NEXT pass reads
# them from cache and completes. A stage whose assets already exist returns at once, so a pass
# repeats only what is missing; the export stage, which caches nothing, sends its Drive files
# again every time it runs.
# Phase 2 documented this as "three cache passes per config"; in September 2026 the
# 3 ha arm needed two.
#
# Each stage call waits for its own export tasks (--wait) before the next stage starts.
# Every call but the first refuses to run while an upstream asset is missing (exit 3), so a
# pass that races Earth Engine fails safely and is repaired by the following pass. The first
# call, "features" (round 9), caches every feature image the config needs before segmentation
# reads any of them, so no later call computes a feature image live.
#
# The wrapper runs it from the run tree's root (the pipeline reads .env from the working directory).
set -u
# The wrapper, before every pass, waits until no task of the configs it is about to run is queued
# or running; started on its own, the pass loop below can submit a second copy of every export
# still queued from an earlier start. So it refuses to run unless the wrapper started it. Nothing
# is read or written before this check.
if [ "${RUN_PASSES_SAFELY:-}" != "1" ]; then
  echo "REFUSING: run_config_passes.sh is started only by odisha_script/run_passes_safely.py (docs/running.md)" >&2
  exit 96
fi
MAX_PASSES=${MAX_PASSES:-3}
LOG=$1; shift
PY=${PYTHON:-.venv/bin/python}
RUNNER=odisha_script/odisha_phase2_2_run_pipeline.py

echo "=== run_config_passes started $(date) :: $# config(s), up to $MAX_PASSES passes ===" >> "$LOG"
for pass in $(seq 1 "$MAX_PASSES"); do
  echo "" >> "$LOG"; echo "=== PASS $pass  $(date) ===" >> "$LOG"
  allok=1
  for cfg in "$@"; do
    name=$(basename "$cfg" .yaml)
    for stage in features segmentation clustering export; do
      echo "" >> "$LOG"; echo "##### PASS$pass $name :: $stage :: $(date +%H:%M:%S) #####" >> "$LOG"
      if [ "$stage" = "export" ]; then
        "$PY" "$RUNNER" --config "$cfg" --through export >> "$LOG" 2>&1
      else
        "$PY" "$RUNNER" --config "$cfg" --through "$stage" --wait >> "$LOG" 2>&1
      fi
      rc=$?
      echo "--- PASS$pass $name $stage exit=$rc ---" >> "$LOG"
      if [ $rc -ne 0 ]; then allok=0; echo "!!! PASS$pass $name failed at $stage" >> "$LOG"; break; fi
    done
  done
  if [ $allok -eq 1 ]; then
    echo "=== ALL CONFIGS COMPLETE on pass $pass  $(date) ===" >> "$LOG"
    echo "=== run_config_passes FINISHED ok ===" >> "$LOG"; exit 0
  fi
  sleep 60
done
echo "=== run_config_passes FINISHED with failures after $MAX_PASSES passes  $(date) ===" >> "$LOG"
exit 1
