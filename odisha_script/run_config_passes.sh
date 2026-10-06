#!/bin/bash
# Run one or more pipeline configs through segmentation -> clustering -> export on
# Earth Engine, in repeated cache passes, until every config has completed.
#
#   odisha_script/run_config_passes.sh <logfile> <config.yaml> [<config.yaml> ...]
#
# Why passes. On a cold cache the segmentation stage's RMS adjacent-distance step is
# computed on top of feature images that are not yet assets, and Earth Engine refuses
# it ("User memory limit exceeded" / "Computation timed out") for all but the smallest
# district. The failed attempt still starts the feature exports, so the NEXT pass reads
# them from cache and completes. A stage whose assets already exist returns at once, so
# re-running a finished config costs nothing: the loop is idempotent and self-healing.
# Phase 2 documented this as "three cache passes per config"; in September 2026 the
# 3 ha arm needed two.
#
# Each stage call waits for its own export tasks (--wait) before the next stage starts.
# The export stage refuses to run if an upstream asset is missing, so a pass that races
# Earth Engine fails safely and is repaired by the following pass.
#
# Run from the repo root (the pipeline reads .env from the working directory).
set -u
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
    for stage in segmentation clustering export; do
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
