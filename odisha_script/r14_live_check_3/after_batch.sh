#!/bin/bash
# After the third live check's batch has ended (Task 4, _r14_check_e and _r14_check_f; the round 14
# record, Done, the round resumed again; run from anywhere, the steps cd to the repo or the run
# tree). The steps of the smoke test's after_smoke.sh (reviewed in the gate's review, part 11) for
# the third check, with the live check's own rules in place of the smoke test's:
#   1. tasks of the two configs queued or running (their Drive exports);
#   w. wait until none is, or until two hours after the batch ended (its end read from the wrapper:
#      its "batch r14_live_check_3 ended" line, and its state file's time), whichever is first; it
#      runs before step 2 whenever step 2 runs;
#   2. the one reading of the Drive states (scripts/drive_export_states.py, from the run tree),
#      made once, its two files made read-only; the Drive states are not among the check's
#      criteria, and the steps after it run whatever it finds;
#   3. each run copied into the records (scripts/copy_run_results.py, export mode);
#   4. the copies hold the eight stage files and the elbow's run record;
#   5. the cost files (scripts/eecu_by_stage.py; from scratch, every task of each config is the
#      batch's), r (the two runs' charged cost over the estimate, 7.94) and the first half's stop
#      (150 - 1.2 x max(1, r) x 12.51), written to the log;
#   6. the live check (odisha_script/r14_live_check.py, criteria 0 to 6, its Earth Engine parts
#      run), writing live_check_3/r14_live_check.json;
#   7. only if the check passes: each Drive export not ended at the one reading is cancelled, by its
#      task id (cancel_drive_export.py; a throwaway copy's export, as the step before Task 5 says);
#      if the check fails, nothing is cancelled (all Earth Engine work stops; the record names them).
# Read-only on Earth Engine but for step 7. Only the copy failing (step 3), or the one reading not
# writing both files (step 2), stops the steps after it; the others report and go on.
#   after_batch.sh [step]
set -u
REPO=/Users/karan/Desktop/phd-code
RT=$REPO/outputs/round14/run_tree_4
PY=$REPO/.venv/bin/python
HERE=$REPO/odisha_script/r14_smoke_test  # the round's judging scripts, committed
DEST=$REPO/docs/reproducibility/r14_runs/live_check_3
OFF=$REPO/outputs/round14/results/live_check_3
LOG=$REPO/outputs/round14/logs/r14_live_check_3.log
STATE=$REPO/outputs/round14/logs/r14_live_check_3.state.json
E=odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_e
F=odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_f
RUNS="$E $F"
step=${1:-all}

active() {  # tasks of the two configs queued or running, read-only
  ( cd $REPO && PYTHONPATH=$REPO/src:$REPO/scripts $PY -c "
import ee, ee_read_only
ee.Initialize(credentials=ee.data.get_persistent_credentials(), project='replicating-paper')
ee_read_only.forbid_writes()
names = '$RUNS'.split()
act = [(o['metadata'].get('description'), o['metadata'].get('state')) for o in ee.data.listOperations()
       if o['metadata'].get('state') in ('PENDING', 'RUNNING', 'CANCELLING')
       and any(str(o['metadata'].get('description', '')).startswith(n) for n in names)]
print(len(act), act[:10])
" )
}

if [ "$step" = all ] || [ "$step" = 1 ]; then
  echo "== 1. tasks of the two configs queued or running"; active
fi
if [ "$step" = all ] || [ "$step" = w ] || [ "$step" = 2 ]; then
  echo "== w. wait: until no task of the two configs is queued or running, or two hours after the batch"
  last=$(grep '^\[run_passes_safely' $LOG 2>/dev/null | tail -1)
  case "$last" in
    *"batch r14_live_check_3 ended"*) ;;
    *) echo "STOP: the batch has not ended (its log's last wrapper line: ${last:-none})"; exit 2 ;;
  esac
  [ -e $STATE ] || { echo "STOP: no state file $STATE"; exit 2; }
  BATCH_END_EPOCH=$(stat -f %m $STATE)
  echo "the batch ended at $(date -r $BATCH_END_EPOCH '+%Y-%m-%d %H:%M:%S %Z') (its state file); the line: $last"
  while :; do
    n=$(active 2>/dev/null | awk '{print $1}')
    now=$(date +%s)
    echo "$(date -u +%H:%M:%SZ) queued or running: ${n:-?}"
    if [ "${n:-1}" = 0 ]; then echo "none queued or running"; break; fi
    if [ $((now - BATCH_END_EPOCH)) -ge 7200 ]; then echo "two hours after the batch ended"; break; fi
    sleep 60
  done
fi
if [ "$step" = all ] || [ "$step" = 2 ]; then
  echo "== 2. the one reading of the Drive states"
  made=0
  for r in $RUNS; do [ -e $RT/odisha_script/phase2_vectors/${r}_drive_exports.json ] && made=$((made + 1)); done
  if [ $made = 2 ]; then
    echo "the reading was made already (both files there): not made again"
  elif [ $made = 1 ]; then
    echo "STOP: one of the reading's two files is there and the other not; nothing is read again until the record says how"; exit 2
  else
    ( cd $RT && PYTHONPATH=$RT/src $PY scripts/drive_export_states.py \
        $(for r in $RUNS; do echo odisha_script/phase2_vectors/${r}_run.json; done) )
    rc=$?
    echo "drive_export_states exit $rc (0 every task completed; 2 one not ended at the reading; 1 one failed, cancelled, unknown or without a task id; 3 or 4 nothing written)"
    made=0
    for r in $RUNS; do [ -e $RT/odisha_script/phase2_vectors/${r}_drive_exports.json ] && made=$((made + 1)); done
    if [ $made != 2 ]; then echo "STOP: the reading did not write both files ($made of 2); make it again"; exit 2; fi
    for r in $RUNS; do chmod a-w $RT/odisha_script/phase2_vectors/${r}_drive_exports.json; done
  fi
  for r in $RUNS; do $PY -c "import json; d=json.load(open('$RT/odisha_script/phase2_vectors/${r}_drive_exports.json')); print('$r', d.get('states'))"; done
fi
if [ "$step" = all ] || [ "$step" = 3 ]; then
  echo "== 3. copy each run into the records"
  mkdir -p $DEST $OFF
  for r in $RUNS; do
    ( cd $REPO && $PY scripts/copy_run_results.py $RT $r --dest $DEST --off-git $OFF ) || { echo "STOP: the copy failed"; exit 3; }
  done
fi
if [ "$step" = all ] || [ "$step" = 4 ]; then
  echo "== 4. the stage files in the copies"
  bad=0
  for r in $RUNS; do
    for f in k_elbow.csv k_elbow_stand_table.csv k_elbow_fit_rows.csv k_elbow_types.csv k_elbow_preprocessing.json \
             clustering_stand_table.csv clustering_fit_rows.csv clustering_kmeans.json k_elbow_run.json; do
      if [ -e $DEST/${r}_$f ] || [ -e $OFF/${r}_$f ]; then :; else echo "MISSING ${r}_$f"; bad=1; fi
    done
  done
  [ $bad = 0 ] && echo "all eight stage files and the elbow's run record, for both runs"
fi
if [ "$step" = all ] || [ "$step" = 5 ]; then
  echo "== 5. the cost files, r and the first half's stop"
  for r in $RUNS; do
    if [ -e $DEST/cost_$r.json ]; then echo "the cost of $r was read already: not read again"; continue; fi
    ( cd $REPO && $PY scripts/eecu_by_stage.py $r $LOG 602.5526 $DEST/cost_$r.json ) && \
      $PY -c "import json; d=json.load(open('$DEST/cost_$r.json')); print('$r', 'batch', d['batch_total'], 'online', d['online_total'], 'total', d['total'])" || \
      echo "the cost of $r could not be read (read it again later)"
  done
  $PY -c "
import json
t = [json.load(open('$DEST/cost_' + r + '.json'))['total'] for r in '$RUNS'.split()]
r = sum(t) / 7.94
print(f'the third check charged {sum(t):.4f} EECU-hours ({t[0]:.4f} + {t[1]:.4f}); r = {r:.4f}; '
      f'the first half\'s stop: 150 - 1.2 x {max(1.0, r):.4f} x 12.51 = {150 - 1.2 * max(1.0, r) * 12.51:.4f}')
" || echo "r not worked: a cost file is missing"
fi
if [ "$step" = all ] || [ "$step" = 6 ]; then
  echo "== 6. the live check (criteria 0 to 6, Earth Engine parts run)"
  for attempt in 1 2 3; do
    [ $attempt -gt 1 ] && { echo "Earth Engine not reached: again in five minutes"; sleep 300; }
    ( cd $REPO && $PY odisha_script/r14_live_check.py --records $DEST \
        --config-a configs/$E.yaml --config-b configs/$F.yaml ); rc=$?
    echo "r14_live_check exit $rc (0 passes; 1 fails; 3 its result there already; 4 Earth Engine not reached)"
    [ $rc -ne 4 ] && break
  done
  $PY -c "
import json; r = json.load(open('$DEST/r14_live_check.json'))
print({k: v['passes'] for k, v in r['criteria'].items()}, 'check:', r['passes'])" || echo "no result written"
fi
if [ "$step" = all ] || [ "$step" = 7 ]; then
  echo "== 7. the Drive exports not ended at the one reading: cancelled if the check passes"
  passed=$($PY -c "import json; print(json.load(open('$DEST/r14_live_check.json'))['passes'])" 2>/dev/null)
  if [ "$passed" != True ]; then
    echo "the check did not pass (or has no result): nothing is cancelled; all Earth Engine work stops"
    for r in $RUNS; do $PY -c "
import json; d = json.load(open('$RT/odisha_script/phase2_vectors/${r}_drive_exports.json'))
print('$r', 'not ended at the reading:', [(k, v['task_id'], v['state']) for k, v in d['files'].items() if v.get('state') in ('READY', 'RUNNING')])"; done
  else
    for r in $RUNS; do
      ( cd $REPO && PYTHONPATH=$REPO/src $PY $HERE/cancel_drive_export.py \
          $RT/odisha_script/phase2_vectors/${r}_drive_exports.json $DEST/r14_live_check_3_cancelled_exports_${r}.json )
      echo "cancel_drive_export exit $? (0 none of them left queued or running; 1 one is; 3 its result there already)"
    done
  fi
fi
