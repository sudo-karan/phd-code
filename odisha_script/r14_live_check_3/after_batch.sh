#!/bin/bash
# After the third live check's batch has ended (Task 4, _r14_check_e and _r14_check_f; the round 14
# record, Done, the round resumed again; run from anywhere). The steps of the smoke test's
# after_smoke.sh (reviewed in the gate's review, part 11) for the third check, with the live check's
# own rules in place of the smoke test's. Every tool runs from the run tree, the batch's own commit
# (the gate's review, part 12): only the records it writes go to the main repo's folders.
#   1. tasks of the two configs queued or running (their Drive exports);
#   w. wait until none is, or until two hours after the batch ended (its end read from the wrapper:
#      its "batch r14_live_check_3 ended" line, and its state file's time), whichever is first; it
#      runs before step 2 whenever step 2 runs;
#   2. the one reading of the Drive states (scripts/drive_export_states.py), made once, its two
#      files made read-only; the Drive states are not among the check's criteria, and the steps
#      after it run whatever it finds;
#   3. each run copied into the records (scripts/copy_run_results.py, export mode);
#   4. the copies hold the eight stage files and the elbow's run record; if one is missing, a run of
#      all the steps stops here, for it to be copied in by the record's rule before the check;
#   5. the live check (odisha_script/r14_live_check.py, criteria 0 to 6, its Earth Engine parts
#      run), writing live_check_3/r14_live_check.json;
#   6. only if the check passed: each Drive export not ended at the one reading is cancelled, by its
#      task id (odisha_script/r14_smoke_test/cancel_drive_export.py; a throwaway copy's export, as
#      the step before Task 5 says); if it failed, nothing is cancelled (all Earth Engine work
#      stops; the record names them); if it was not decided, nothing is done until step 5 is;
#   7. the cost files (scripts/eecu_by_stage.py; from scratch, every task of each config is the
#      batch's; read after the cancels, so that they are charged), r (the two runs' charged cost
#      over the estimate, 7.94) and the first half's stop (200 - 1.2 x max(1, r) x 12.51: the round's
#      budget 200 by Jaskaran's answer to question 14 (b), the stop moved by as much);
#   8. every task of a check copy (_r14_check_a to _f) still queued or running, for the step before
#      Task 5.
# Read-only on Earth Engine but for step 6. Only the copy failing (step 3), the one reading not
# writing both files (step 2) or a missing stage file in a run of all the steps (step 4) stops the
# steps after it; the others report and go on.
#   after_batch.sh [step]
set -u
REPO=/Users/karan/Desktop/phd-code
RT=$REPO/outputs/round14/run_tree_4
PY=$REPO/.venv/bin/python
DEST=$REPO/docs/reproducibility/r14_runs/live_check_3
OFF=$REPO/outputs/round14/results/live_check_3
LOG=$REPO/outputs/round14/logs/r14_live_check_3.log
STATE=$REPO/outputs/round14/logs/r14_live_check_3.state.json
E=odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_e
F=odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_f
RUNS="$E $F"
step=${1:-all}

tasks() {  # tasks queued or running whose name begins with (or, with "any", holds) one of the names, read-only
  ( cd $RT && PYTHONPATH=$RT/src:$RT/scripts $PY -c "
import ee, ee_read_only, sys
ee.Initialize(credentials=ee.data.get_persistent_credentials(), project='replicating-paper')
ee.data.setDeadline(120_000)
ee_read_only.forbid_writes()
names, mode = sys.argv[1].split(), sys.argv[2]
def mine(d):
    d = str(d or '')
    return any(n in d for n in names) if mode == 'any' else any(d.startswith(n) for n in names)
act = [(o['metadata'].get('description'), o['metadata'].get('state')) for o in ee.data.listOperations()
       if o['metadata'].get('state') in ('PENDING', 'RUNNING', 'CANCELLING') and mine(o['metadata'].get('description'))]
print(len(act), act[:10])
" "$1" "$2" )
}

if [ "$step" = all ] || [ "$step" = 1 ]; then
  echo "== 1. tasks of the two configs queued or running"; tasks "$RUNS" prefix
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
    n=$(tasks "$RUNS" prefix 2>/dev/null | awk '{print $1}')
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
    for r in $RUNS; do [ -e $RT/odisha_script/phase2_vectors/${r}_drive_exports.json ] && chmod a-w $RT/odisha_script/phase2_vectors/${r}_drive_exports.json; done
    if [ $made = 1 ]; then echo "STOP: the reading wrote one of its two files (made read-only); the record must say how to go on"; exit 2; fi
    if [ $made = 0 ]; then echo "STOP: the reading wrote neither file; make it again (after_batch.sh 2)"; exit 2; fi
  fi
  for r in $RUNS; do $PY -c "import json; d=json.load(open('$RT/odisha_script/phase2_vectors/${r}_drive_exports.json')); print('$r', d.get('states'))"; done
fi
if [ "$step" = all ] || [ "$step" = 3 ]; then
  echo "== 3. copy each run into the records"
  mkdir -p $DEST $OFF
  for r in $RUNS; do
    ( cd $RT && PYTHONPATH=$RT/src $PY scripts/copy_run_results.py $RT $r --dest $DEST --off-git $OFF ) || { echo "STOP: the copy failed"; exit 3; }
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
  if [ $bad = 0 ]; then
    echo "all eight stage files and the elbow's run record, for both runs"
  elif [ "$step" = all ]; then
    echo "STOP: copy the missing file in by the record's rule (Done, the gate: after each export-mode copy), then run steps 5 to 8"; exit 4
  fi
fi
if [ "$step" = all ] || [ "$step" = 5 ]; then
  echo "== 5. the live check (criteria 0 to 6, Earth Engine parts run)"
  for attempt in 1 2 3; do
    [ $attempt -gt 1 ] && { echo "Earth Engine not reached: again in five minutes"; sleep 300; }
    ( cd $RT && PYTHONPATH=$RT/src $PY odisha_script/r14_live_check.py --records $DEST \
        --config-a configs/$E.yaml --config-b configs/$F.yaml ); rc=$?
    echo "r14_live_check exit $rc (0 passes; 1 fails; 3 nothing written: its result there already, or a record missing or unreadable; 4 Earth Engine not reached)"
    [ $rc -ne 4 ] && break
  done
  $PY -c "
import json; r = json.load(open('$DEST/r14_live_check.json'))
print({k: v['passes'] for k, v in r['criteria'].items()}, 'check:', r['passes'])" || echo "no result written"
fi
if [ "$step" = all ] || [ "$step" = 6 ]; then
  echo "== 6. the Drive exports not ended at the one reading: cancelled if the check passed"
  passed=$($PY -c "import json; print(json.load(open('$DEST/r14_live_check.json'))['passes'])" 2>/dev/null)
  if [ "$passed" = True ]; then
    for r in $RUNS; do
      for attempt in 1 2 3; do
        [ $attempt -gt 1 ] && { echo "Earth Engine not reached: again in five minutes"; sleep 300; }
        ( cd $RT && PYTHONPATH=$RT/src $PY odisha_script/r14_smoke_test/cancel_drive_export.py \
            $RT/odisha_script/phase2_vectors/${r}_drive_exports.json $DEST/r14_live_check_3_cancelled_exports_${r}.json ); rc=$?
        echo "cancel_drive_export exit $rc (0 none of them left queued or running; 1 one is; 2 refused; 3 its record there already, complete; 4 Earth Engine not reached)"
        [ $rc -ne 4 ] && break
      done
    done
  elif [ "$passed" = False ]; then
    echo "the check failed: nothing is cancelled; all Earth Engine work stops (the record names these):"
    for r in $RUNS; do $PY -c "
import json; d = json.load(open('$RT/odisha_script/phase2_vectors/${r}_drive_exports.json'))
print('$r', 'not ended at the reading:', [(k, v.get('task_id'), v.get('state')) for k, v in d['files'].items() if v.get('state') in ('READY', 'RUNNING')])"; done
  else
    echo "the check has no result (${passed:-none}): nothing is done here until step 5 has decided it"
  fi
fi
if [ "$step" = all ] || [ "$step" = 7 ]; then
  echo "== 7. the cost files, r and the first half's stop"
  mkdir -p $DEST
  for r in $RUNS; do
    if [ -e $DEST/cost_$r.json ]; then echo "the cost of $r was read already: not read again"; continue; fi
    ( cd $RT && PYTHONPATH=$RT/src $PY scripts/eecu_by_stage.py $r $LOG 602.5526 $DEST/cost_$r.json >/dev/null ) && \
      $PY -c "import json; d=json.load(open('$DEST/cost_$r.json')); print('$r', 'batch', d['batch_total'], 'online', d['online_total'], 'total', d['total'])" || \
      echo "the cost of $r could not be read (read it again: after_batch.sh 7)"
  done
  $PY -c "
import json
t = [json.load(open('$DEST/cost_' + r + '.json'))['total'] for r in '$RUNS'.split()]
r = sum(t) / 7.94
print(f'the third check charged {sum(t):.4f} EECU-hours ({t[0]:.4f} + {t[1]:.4f}); r = {r:.4f}; '
      f'the first half\'s stop: 200 - 1.2 x {max(1.0, r):.4f} x 12.51 = {200 - 1.2 * max(1.0, r) * 12.51:.4f}')
" || echo "r not worked: a cost file is missing"
fi
if [ "$step" = all ] || [ "$step" = 8 ]; then
  echo "== 8. tasks of any check copy (_r14_check_a to _f) queued or running (none may be, before Task 5)"
  tasks "_r14_check_" any
fi
