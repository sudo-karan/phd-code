#!/bin/bash
# After R3's first half (Task 5, label r14_first_half, the nineteen _r14 configs through k_elbow;
# the round 14 record): the steps before the elbow report, then the report (Task 6). Every tool runs
# from the run tree, the batch's own commit; only the records go to the main repo's folders.
#   1. tasks of the nineteen queued or running (after a stop, the tasks already submitted run on);
#   w. wait until none is, or until two hours after the batch ended (its end read from the wrapper:
#      its "batch r14_first_half ended" line, and its state file's time), whichever is first;
#   2. each config's records copied into docs/reproducibility/r14_runs/first_half/ (files over 5 MB
#      into outputs/round14/results/first_half/): the configs the batch finished with
#      scripts/copy_run_results.py --through k_elbow; the others (cut by the stop, not finished
#      after the wrapper's passes, or not reached) with copy_unfinished.py, every pass's manifest
#      and log that exists; each of those named with the state file's reason, for Blocked;
#   3. each finished config's k elbow files and run record are there;
#   4. the cost files (scripts/eecu_by_stage.py, each config's area as rounds 10 and 12 took it;
#      Sanjay Van's, 1,301.6942 ha, its outline's geodesic area), each read only when no task of the
#      config is queued or running (so that it is whole), and not for a config that never started;
#   5. the elbow report (odisha_script/r14_elbow_report.py, into odisha_script/keptland_scores/ of
#      the main repo), only when step 3 finds every file: with --allow-missing if a config was not
#      finished, and then the report must name exactly those.
# Before every step but 1, the batch must have ended (its ended line), and its state file must be the
# first half's: the label, through k_elbow, the stages features, segmentation and k_elbow, the
# nineteen configs, and the run tree's commit. Read-only on Earth Engine throughout (steps 1, w and
# 4); the copies and the report are offline. A step that fails stops the steps after it in a run of
# all the steps.
#   after_batch.sh [step]
set -u
set -o pipefail
REPO=/Users/karan/Desktop/phd-code
RT=$REPO/outputs/round14/run_tree_5
PY=$REPO/.venv/bin/python
DEST=$REPO/docs/reproducibility/r14_runs/first_half
OFF=$REPO/outputs/round14/results/first_half
LOG=$REPO/outputs/round14/logs/r14_first_half.log
STATE=$REPO/outputs/round14/logs/r14_first_half.state.json
RUNS=$(cd $RT && $PY odisha_script/r14_first_half/order.py | xargs -n1 basename | sed 's/\.yaml$//') || { echo "STOP: the order could not be read"; exit 2; }
[ "$(echo "$RUNS" | grep -c .)" = 19 ] || { echo "STOP: the order did not give nineteen configs"; exit 2; }
step=${1:-all}

tasks() {  # tasks queued or running of the configs named in $1, read-only (a check copy's task is
  # not counted as the Angul config's, though its name begins with it)
  ( cd $RT && PYTHONPATH=$RT/src:$RT/scripts $PY -c "
import ee, ee_read_only, sys
ee.Initialize(credentials=ee.data.get_persistent_credentials(), project='replicating-paper')
ee.data.setDeadline(120_000)
ee_read_only.forbid_writes()
names = sys.argv[1].split()
def mine(d):
    d = str(d or '')
    return any(d.startswith(n + '_') and not d[len(n) + 1:].startswith('check_') for n in names)
act = [(o['metadata'].get('description'), o['metadata'].get('state')) for o in ee.data.listOperations()
       if o['metadata'].get('state') in ('PENDING', 'RUNNING', 'CANCELLING') and mine(o['metadata'].get('description'))]
print(len(act), act[:10])
" "$1" )
}

area() {  # each config's area, ha, as the round's cost files take it
  case "$1" in
    *tile10km*) echo 10000.0 ;;
    *_angul_*) echo 602.5526 ;;
    *_dhenkanal_*) echo 1372.5856 ;;
    *_kendujhar_*) echo 1330.3763 ;;
    *_koraput_*) echo 4942.4534 ;;
    sanjay_van_*) echo 1301.6942 ;;
    *) echo "" ;;
  esac
}

guard() {  # the batch has ended, and its state file is the first half's
  last=$(grep '^\[run_passes_safely' $LOG 2>/dev/null | tail -1)
  case "$last" in
    *"batch r14_first_half ended"*) ;;
    *) echo "STOP: the batch has not ended (its log's last wrapper line: ${last:-none})"; exit 2 ;;
  esac
  $PY - "$STATE" "$RUNS" "$(git -C $RT rev-parse HEAD)" <<'EOF' || { echo "STOP: the state file is not the first half's"; exit 2; }
import json, sys
try:
    s = json.load(open(sys.argv[1]))
except (OSError, ValueError) as e:
    sys.exit(f"the state file could not be read: {e!r}")
want = {"label": "r14_first_half", "through": "k_elbow", "stages": ["features", "segmentation", "k_elbow"]}
bad = {k: s.get(k) for k, v in want.items() if s.get(k) != v}
if sorted(s.get("configs", [])) != sorted(sys.argv[2].split()):
    bad["configs"] = len(s.get("configs", []))
if s.get("git", {}).get("commit") != sys.argv[3]:
    bad["commit"] = s.get("git", {}).get("commit")
print("the state file:", "the first half's" if not bad else f"NOT the first half's: {bad}")
sys.exit(1 if bad else 0)
EOF
}

done_and_not() {  # DONE: finished in this label's batches; NOT_DONE: the rest, each with its reason
  $PY - "$STATE" "$RUNS" <<'EOF'
import json, sys
s = json.load(open(sys.argv[1]))
batches = [*s.get("earlier_batches", []), s]
done = set().union(*(set(b.get("done", [])) for b in batches))
for n in sys.argv[2].split():
    if n in done:
        print("DONE", n)
    elif n in s.get("needs_attention", {}):
        print("NOT", n, "needs attention:", s["needs_attention"][n])
    elif n in s.get("not_finished", []):
        print("NOT", n, "not finished after the batch's passes (or cut by the stop)")
    else:
        print("NOT", n, "not reached")
EOF
}

if [ "$step" = all ] || [ "$step" = 1 ]; then
  echo "== 1. tasks of the nineteen queued or running"; tasks "$RUNS"
fi
if [ "$step" = all ] || [ "$step" = w ]; then
  guard
  echo "== w. wait: until no task of the nineteen is queued or running, or two hours after the batch"
  BATCH_END_EPOCH=$(stat -f %m $STATE)
  echo "the batch ended at $(date -r $BATCH_END_EPOCH '+%Y-%m-%d %H:%M:%S %Z') (its state file)"
  while :; do
    n=$(tasks "$RUNS" 2>/dev/null | awk '{print $1}')
    now=$(date +%s)
    echo "$(date -u +%H:%M:%SZ) queued or running: ${n:-?}"
    if [ "${n:-1}" = 0 ]; then echo "none queued or running"; break; fi
    if [ $((now - BATCH_END_EPOCH)) -ge 7200 ]; then echo "two hours after the batch ended"; tasks "$RUNS"; break; fi
    sleep 60
  done
fi
if [ "$step" = all ] || [ "$step" = 2 ]; then
  guard
  echo "== 2. each config's records copied"
  mkdir -p $DEST $OFF
  states=$(done_and_not) || { echo "STOP: the state file could not be read"; exit 2; }
  for r in $(echo "$states" | awk '$1 == "DONE" {print $2}'); do
    ( cd $RT && PYTHONPATH=$RT/src $PY scripts/copy_run_results.py $RT $r --through k_elbow --dest $DEST --off-git $OFF ) || { echo "STOP: the copy of $r failed"; exit 3; }
  done
  for r in $(echo "$states" | awk '$1 == "NOT" {print $2}'); do
    ( cd $RT && PYTHONPATH=$RT/src $PY odisha_script/r14_first_half/copy_unfinished.py $RT $r --dest $DEST --off-git $OFF ) || { echo "STOP: the copy of the unfinished $r failed"; exit 3; }
  done
  echo "finished: $(echo "$states" | grep -c '^DONE') of 19"
  echo "$states" | grep '^NOT' | sed 's/^NOT /  NOT FINISHED (Blocked): /' || true
fi
if [ "$step" = all ] || [ "$step" = 3 ]; then
  guard
  echo "== 3. the k elbow's files and run record of each finished config"
  bad=0
  for r in $(done_and_not | awk '$1 == "DONE" {print $2}'); do
    for f in k_elbow.csv k_elbow_stand_table.csv k_elbow_fit_rows.csv k_elbow_types.csv k_elbow_preprocessing.json k_elbow_run.json; do
      if [ -e $DEST/${r}_$f ] || [ -e $OFF/${r}_$f ]; then :; else echo "MISSING ${r}_$f"; bad=1; fi
    done
  done
  if [ $bad = 0 ]; then echo "all six files of every finished config"; else
    echo "STOP: copy each missing file in by the record's rule, then run steps 3 to 5 again"; exit 4; fi
fi
if [ "$step" = all ] || [ "$step" = 4 ]; then
  guard
  echo "== 4. the cost files (each read only when no task of its config is queued or running)"
  mkdir -p $DEST
  for r in $RUNS; do
    if [ -e $DEST/cost_$r.json ]; then echo "the cost of $r was read already: not read again"; continue; fi
    if ! grep -q "^##### PASS[0-9]* $r :: " $LOG; then echo "$r: not started: no cost"; continue; fi
    a=$(area $r); [ -n "$a" ] || { echo "$r: no area"; continue; }
    n=$(tasks "$r" 2>/dev/null | awk '{print $1}')
    if [ "${n:-1}" != 0 ]; then echo "$r: not read: ${n:-?} task(s) of it queued or running (or not read); read it again later (after_batch.sh 4)"; continue; fi
    ( cd $RT && PYTHONPATH=$RT/src $PY scripts/eecu_by_stage.py $r $LOG $a $DEST/cost_$r.json >/dev/null ) && \
      $PY -c "import json; d=json.load(open('$DEST/cost_$r.json')); print('$r', 'batch', d['batch_total'], 'online', d['online_total'], 'total', d['total'])" || \
      echo "the cost of $r could not be read (read it again later: after_batch.sh 4)"
  done
fi
if [ "$step" = all ] || [ "$step" = 5 ]; then
  guard
  echo "== 5. the elbow report (Task 6)"
  for r in $(done_and_not | awk '$1 == "DONE" {print $2}'); do
    for f in k_elbow.csv k_elbow_stand_table.csv k_elbow_preprocessing.json; do
      [ -e $DEST/${r}_$f ] || [ -e $OFF/${r}_$f ] || { echo "STOP: ${r}_$f is missing (step 3)"; exit 4; }
    done
  done
  NOT_DONE=$(done_and_not | awk '$1 == "NOT" {print $2}')
  allow=""; [ -n "$NOT_DONE" ] && allow="--allow-missing"
  ( cd $RT && PYTHONPATH=$RT/src $PY odisha_script/r14_elbow_report.py --records $DEST \
      --out-dir $REPO/odisha_script/keptland_scores $allow ); rc=$?
  echo "r14_elbow_report exit $rc${allow:+ (with --allow-missing: configs not finished)}"
  [ $rc = 0 ] && $PY - "$REPO/odisha_script/keptland_scores/r14_elbow_run.json" "$NOT_DONE" <<'EOF'
import json, sys
missing = sorted(json.load(open(sys.argv[1])).get("missing_runs", []))
want = sorted(sys.argv[2].split())
print("the report's runs without a record:", missing or "none", "| the configs not finished:", want or "none",
      "| the same:", missing == want)
sys.exit(0 if missing == want else 1)
EOF
fi
