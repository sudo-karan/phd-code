#!/bin/bash
# After the smoke test's batch has ended (the round 14 record, Done, the round resumed again; run
# from anywhere, the steps cd to the repo or the run tree):
#   1. tasks of the two configs queued or running (their Drive exports);
#   w. wait until none is, or until two hours after the batch ended (its end read from the wrapper:
#      its "batch r14_smoke_test ended" line, and its state file's time), whichever is first; it runs
#      before step 2 whenever step 2 runs;
#   2. the one reading of the Drive states (scripts/drive_export_states.py, from the run tree): it
#      decides rule 2, and the steps after it run whatever it finds;
#   3. each run copied into the records (scripts/copy_run_results.py, export mode);
#   4. the copies hold the eight stage files and the elbow's run record (pass rule 3);
#   5. the cost files (scripts/eecu_by_stage.py; they count every task of the config to date);
#   6. each elbow table read back from its asset (pass rule 4; elbow_read_back.py);
#   7. the live check's script on the records, its Earth Engine parts run (pass rule 5);
#   8. reported only: the elbows beside the second live check's (smoke_vs_second_check.py);
#   9. the verdict, rules 1 to 6 (smoke_test_result.py; rule 6 worked there).
# Read-only on Earth Engine throughout. Only the copy failing (step 3), or the one reading writing
# nothing (step 2, exit 3 or 4), stops the steps after it; the others report and go on, a rule that
# fails being written, named, in the verdict.
#   after_smoke.sh [step]
set -u
REPO=/Users/karan/Desktop/phd-code
RT=$REPO/outputs/round14/run_tree_3
PY=$REPO/.venv/bin/python
HERE=$REPO/odisha_script/r14_smoke_test  # this folder: the round's judging scripts, committed
DEST=$REPO/docs/reproducibility/r14_runs/smoke_test
OFF=$REPO/outputs/round14/results/smoke_test
LOG=$REPO/outputs/round14/logs/r14_smoke_test.log
C=odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_c
D=odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_d
RUNS="$C $D"
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
# The wait comes before the one reading whenever the reading is made (the gate's review, part 11).
# The batch's end is the wrapper's own: its log's last line says the batch ended, and its state file
# was last written then; no time is given by hand.
STATE=$REPO/outputs/round14/logs/r14_smoke_test.state.json
if [ "$step" = all ] || [ "$step" = w ] || [ "$step" = 2 ]; then
  echo "== w. wait: until no task of the two configs is queued or running, or two hours after the batch"
  last=$(grep '^\[run_passes_safely' $LOG 2>/dev/null | tail -1)
  case "$last" in
    *"batch r14_smoke_test ended"*) ;;
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
# The one reading of the Drive states: made once. A reading already made (its file in the run
# tree) is not made again, as a second one, after the round's cancellations, would replace it;
# one that wrote nothing (exit 3 or 4) stops here, to be made again.
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
    # Made once: the two files made read-only, so that no later run, by hand or not, replaces them.
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
# Steps 4 to 9 report and go on: a rule that fails is written, named, in the verdict (step 9).
if [ "$step" = all ] || [ "$step" = 4 ]; then
  echo "== 4. the stage files in the copies (pass rule 3)"
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
  echo "== 5. the cost files (reported only)"
  for r in $RUNS; do
    if [ -e $DEST/cost_$r.json ]; then echo "the cost of $r was read already: not read again"; continue; fi
    ( cd $REPO && $PY scripts/eecu_by_stage.py $r $LOG 602.5526 $DEST/cost_$r.json ) && \
      $PY -c "import json; d=json.load(open('$DEST/cost_$r.json')); print('$r', 'batch', d['batch_total'], 'online', d['online_total'], 'total', d['total'])" || \
      echo "the cost of $r could not be read (reported only; read it again later)"
  done
fi
# A read-only step that did not reach Earth Engine (exit 4) is run again, unchanged, up to twice, five
# minutes apart;
# its first complete result counts (each refuses to write over its results, exit 3).
if [ "$step" = all ] || [ "$step" = 6 ]; then
  echo "== 6. the elbow tables read back (pass rule 4)"
  for attempt in 1 2 3; do
    [ $attempt -gt 1 ] && { echo "Earth Engine not reached: again in five minutes"; sleep 300; }
    ( cd $REPO && $PY $HERE/elbow_read_back.py $DEST configs/$C.yaml configs/$D.yaml ); rc=$?
    echo "elbow_read_back exit $rc (0 passes; 1 fails; 3 its result there already; 4 Earth Engine not reached)"
    [ $rc -ne 4 ] && break
  done
fi
if [ "$step" = all ] || [ "$step" = 7 ]; then
  echo "== 7. the live check's script on the records, Earth Engine parts run (pass rule 5)"
  for attempt in 1 2 3; do
    [ $attempt -gt 1 ] && { echo "Earth Engine not reached: again in five minutes"; sleep 300; }
    ( cd $REPO && $PY odisha_script/r14_live_check.py --records $DEST \
        --config-a configs/$C.yaml --config-b configs/$D.yaml --out $DEST/r14_smoke_test_live_check_rules.json ); rc=$?
    echo "r14_live_check exit $rc (1 expected: criterion 0 fails; 3 its result there already; 4 Earth Engine not reached)"
    [ $rc -ne 4 ] && break
  done
  $PY -c "
import json; r = json.load(open('$DEST/r14_smoke_test_live_check_rules.json'))
print({k: v['passes'] for k, v in r['criteria'].items()}, 'check:', r['passes'])" || echo "no result written"
fi
if [ "$step" = all ] || [ "$step" = 8 ]; then
  echo "== 8. reported only: the elbows beside the second live check's"
  ( cd $REPO && $PY $HERE/smoke_vs_second_check.py $DEST $REPO/docs/reproducibility/r14_runs/live_check_2 $C $D ) || echo "not written"
fi
if [ "$step" = all ] || [ "$step" = 9 ]; then
  echo "== 9. the verdict (rules 1 to 6)"
  ( cd $REPO && $PY $HERE/smoke_test_result.py $DEST $OFF $REPO/outputs/round14/logs/r14_smoke_test.state.json $C $D )
fi
