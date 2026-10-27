#!/bin/bash
# After the smoke test's batch has ended (the round 14 record, Done, the round resumed again; run
# from anywhere, the steps cd to the repo or the run tree):
#   1. tasks of the two configs queued or running (their Drive exports); with step w, wait until
#      none is, or until two hours after the batch ended (BATCH_END_EPOCH), whichever is first;
#   2. the one reading of the Drive states (scripts/drive_export_states.py, from the run tree): it
#      decides rule 2, and the steps after it run whatever it finds;
#   3. each run copied into the records (scripts/copy_run_results.py, export mode);
#   4. the copies hold the eight stage files and the elbow's run record (pass rule 3);
#   5. the cost files (scripts/eecu_by_stage.py; they count every task of the config to date);
#   6. each elbow table read back from its asset (pass rule 4; elbow_read_back.py);
#   7. the live check's script on the records, its Earth Engine parts run (pass rule 5);
#   8. reported only: the elbows beside the second live check's (smoke_vs_second_check.py);
#   9. the verdict, rules 1 to 6 (smoke_test_result.py; rule 6 worked there).
# Read-only on Earth Engine throughout. A step that fails stops the steps after it.
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
if [ "$step" = w ]; then
  echo "== w. wait: until no task of the two configs is queued or running, or two hours after the batch"
  : "${BATCH_END_EPOCH:?set BATCH_END_EPOCH to the end of the batch, in seconds since the epoch}"
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
  echo "== 2. Drive export states"
  ( cd $RT && PYTHONPATH=$RT/src $PY scripts/drive_export_states.py \
      $(for r in $RUNS; do echo odisha_script/phase2_vectors/${r}_run.json; done) ); \
    echo "drive_export_states exit $? (0 every task completed; 2 one not ended at the reading; 1 one failed, cancelled or without a task id)"
  for r in $RUNS; do $PY -c "import json; d=json.load(open('$RT/odisha_script/phase2_vectors/${r}_drive_exports.json')); print('$r', d.get('states'))"; done
fi
if [ "$step" = all ] || [ "$step" = 3 ]; then
  echo "== 3. copy each run into the records"
  mkdir -p $DEST $OFF
  for r in $RUNS; do
    ( cd $REPO && $PY scripts/copy_run_results.py $RT $r --dest $DEST --off-git $OFF ) || exit 3
  done
fi
if [ "$step" = all ] || [ "$step" = 4 ]; then
  echo "== 4. the stage files in the copies (pass rule 3)"
  bad=0
  for r in $RUNS; do
    for f in k_elbow.csv k_elbow_stand_table.csv k_elbow_fit_rows.csv k_elbow_types.csv k_elbow_preprocessing.json \
             clustering_stand_table.csv clustering_fit_rows.csv clustering_kmeans.json k_elbow_run.json; do
      if [ -e $DEST/${r}_$f ] || grep -q "\"${r}_$f\"" $DEST/${r}_files_off_git.json 2>/dev/null; then :; else
        echo "MISSING ${r}_$f"; bad=1; fi
    done
  done
  [ $bad = 0 ] && echo "all eight stage files and the elbow's run record, for both runs" || exit 4
fi
if [ "$step" = all ] || [ "$step" = 5 ]; then
  echo "== 5. the cost files"
  for r in $RUNS; do
    ( cd $REPO && $PY scripts/eecu_by_stage.py $r $LOG 602.5526 $DEST/cost_$r.json ) || exit 5
    $PY -c "import json; d=json.load(open('$DEST/cost_$r.json')); print('$r', 'batch', d['batch_total'], 'online', d['online_total'], 'total', d['total'])"
  done
fi
if [ "$step" = all ] || [ "$step" = 6 ]; then
  echo "== 6. the elbow tables read back (pass rule 4)"
  ( cd $REPO && $PY $HERE/elbow_read_back.py $DEST configs/$C.yaml configs/$D.yaml ) || exit 6
fi
if [ "$step" = all ] || [ "$step" = 7 ]; then
  echo "== 7. the live check's script on the records, Earth Engine parts run (pass rule 5)"
  ( cd $REPO && $PY odisha_script/r14_live_check.py --records $DEST \
      --config-a configs/$C.yaml --config-b configs/$D.yaml --out $DEST/r14_smoke_test_live_check_rules.json ); echo "exit $? (1 expected: criterion 0 fails)"
  $PY -c "
import json; r = json.load(open('$DEST/r14_smoke_test_live_check_rules.json'))
print({k: v['passes'] for k, v in r['criteria'].items()}, 'check:', r['passes'])"
fi
if [ "$step" = all ] || [ "$step" = 8 ]; then
  echo "== 8. reported only: the elbows beside the second live check's"
  ( cd $REPO && $PY $HERE/smoke_vs_second_check.py $DEST $REPO/docs/reproducibility/r14_runs/live_check_2 $C $D )
fi
if [ "$step" = all ] || [ "$step" = 9 ]; then
  echo "== 9. the verdict (rules 1 to 6)"
  ( cd $REPO && $PY $HERE/smoke_test_result.py $DEST $OFF $REPO/outputs/round14/logs/r14_smoke_test.state.json $C $D )
fi
