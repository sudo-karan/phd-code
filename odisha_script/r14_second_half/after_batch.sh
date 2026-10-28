#!/bin/bash
# After R3's second half (Task 7, label r14_second_half, the eighteen through export; the round 14
# record, Done, R3's second half): the steps that finish its records. Every tool runs from the run
# tree, the batch's commit, but the copies' destination and the cost files are the main repo's. Run it
# under caffeinate -i (the wait can take two hours, and the Mac sleeps).
#   1. tasks of the eighteen queued or running (their Drive exports);
#   w. wait until none is, or until two hours after the batch ended (its "batch r14_second_half
#      ended" line, and its state file's time), whichever is first; it runs before step 2 whenever
#      step 2 runs;
#   s. wait until the scorer and every field check and chance test have ended (they read the copies,
#      and the scorer copies each set as it is exported), up to an hour; it runs before steps 2 and 3
#      whenever they run;
#   2. the one reading of the Drive states (scripts/drive_export_states.py, from the run tree), made
#      once for the finished configs (a reading already made is not made again) and then made
#      read-only;
#   3. each finished config copied again into docs/reproducibility/r14_runs/second_half/
#      (scripts/copy_run_results.py, export mode; a file over 5 MB into
#      outputs/round14/results/second_half/), now with its Drive states (<run>_drive_exports.json):
#      the scorer copied each as its set was exported, before the reading;
#   4. the copies hold each finished config's stage files: the clustering's three, the k elbow's five
#      and its run record, and the Drive states;
#   5. the cost files (scripts/eecu_by_stage.py, into second_half/cost_<run>.json, each read only when
#      no task of the config is queued or running, and not before half an hour after the batch ended,
#      for Cloud Monitoring's online series to be complete), for every config the batch started (a
#      stage header in its log), finished or not: each holds the config's batch tasks to date, both
#      halves', and the online use over this batch's passes only (the script reads online use over the
#      passes of the log it is given). So each config's second-half share is its batch total less its
#      first-half cost file's batch total, plus its own online total; written, with the sum beside
#      the estimate, 5.02, to second_half/second_half_cost_shares.json (results only), once every
#      config the batch started has its share, and never written over.
# Before every step but 1, the batch must have ended (its ended line), and its state file must be the
# second half's: the label, through export, the five stages, the eighteen configs, the run tree's
# commit, and the run tree unchanged. Read-only on Earth Engine throughout (steps 1, w, 2 and 5); the
# copies are offline. A step that fails stops the steps after it in a run of all the steps.
#   caffeinate -i after_batch.sh [step]
set -u
set -o pipefail
REPO=/Users/karan/Desktop/phd-code
RT=$REPO/outputs/round14/run_tree_5
PY=$REPO/.venv/bin/python
DEST=$REPO/docs/reproducibility/r14_runs/second_half
OFF=$REPO/outputs/round14/results/second_half
FH=$REPO/docs/reproducibility/r14_runs/first_half
LOG=$REPO/outputs/round14/logs/r14_second_half.log
STATE=$REPO/outputs/round14/logs/r14_second_half.state.json
RUNS=$(cd $RT && $PY odisha_script/r14_second_half/order.py | xargs -n1 basename | sed 's/\.yaml$//') || { echo "STOP: the order could not be read"; exit 2; }
[ "$(echo "$RUNS" | grep -c .)" = 18 ] || { echo "STOP: the order did not give eighteen configs"; exit 2; }
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
    *_angul_*) echo 602.5526 ;;
    *_dhenkanal_*) echo 1372.5856 ;;
    *_kendujhar_*) echo 1330.3763 ;;
    *_koraput_*) echo 4942.4534 ;;
    sanjay_van_*) echo 1301.6942 ;;
    *) echo "" ;;
  esac
}

guard() {  # the batch has ended, and its state file is the second half's
  last=$(grep '^\[run_passes_safely' $LOG 2>/dev/null | tail -1)
  case "$last" in
    *"batch r14_second_half ended"*) ;;
    *) echo "STOP: the batch has not ended (its log's last wrapper line: ${last:-none})"; exit 2 ;;
  esac
  $PY - "$STATE" "$RUNS" "$(git -C $RT rev-parse HEAD)" <<'EOF' || { echo "STOP: the state file is not the second half's"; exit 2; }
import json, sys
try:
    s = json.load(open(sys.argv[1]))
except (OSError, ValueError) as e:
    sys.exit(f"the state file could not be read: {e!r}")
want = {"label": "r14_second_half", "through": "export",
        "stages": ["features", "segmentation", "k_elbow", "clustering", "export"]}
bad = {k: s.get(k) for k, v in want.items() if s.get(k) != v}
if sorted(s.get("configs", [])) != sorted(sys.argv[2].split()):
    bad["configs"] = len(s.get("configs", []))
if (s.get("git") or {}).get("commit") != sys.argv[3]:
    bad["commit"] = (s.get("git") or {}).get("commit")
if s.get("run_tree_changed"):
    bad["run_tree_changed"] = s.get("run_tree_changed")
print("the state file:", "the second half's" if not bad else f"NOT the second half's: {bad}")
sys.exit(1 if bad else 0)
EOF
}

finished() {  # the configs this label's batches through export finished, in the order; then each
  # config not finished, with the state file's reason, on lines of their own
  $PY - "$STATE" "$RUNS" <<'EOF'
import json, sys
s = json.load(open(sys.argv[1]))
batches = [b for b in [*s.get("earlier_batches", []), s] if b.get("through", s.get("through")) == "export"]
done = set().union(*(set(b.get("done", [])) for b in batches))
names = sys.argv[2].split()
print(" ".join(n for n in names if n in done))
for n in names:
    if n in done:
        continue
    if n in s.get("needs_attention", {}):
        print(f"  NOT FINISHED: {n}: needs attention: {s['needs_attention'][n]}")
    elif n in s.get("not_finished", []):
        print(f"  NOT FINISHED: {n}: not finished after the batch's passes")
    else:
        print(f"  NOT FINISHED: {n}: not reached")
EOF
}

started() {  # the configs the batch started: a stage header in its log
  for r in $RUNS; do grep -q "^##### PASS[0-9]* $r :: " $LOG && echo $r; done
}

wait_scoring() {  # until the scorer and every field check and chance test have ended, up to an hour
  for i in $(seq 1 60); do
    pgrep -fl "[s]core_as_exported.py|[o]disha_keptland_chance.py|[o]disha_keptland_score.py" >/dev/null || return 0
    [ $i = 1 ] && echo "the scorer or a field check or chance test is running: waiting for it (up to an hour)"
    sleep 60
  done
  echo "STOP: the scorer or a field check or chance test still runs after an hour"; exit 3
}

if [ "$step" = all ] || [ "$step" = 1 ]; then
  echo "== 1. tasks of the eighteen queued or running"; tasks "$RUNS"
fi
[ "$step" = 1 ] && exit 0
guard
FIN=$(finished) || { echo "STOP: the state file could not be read"; exit 2; }
DONE=$(echo "$FIN" | head -1)
echo "finished: $(echo $DONE | wc -w | tr -d ' ') of 18"
echo "$FIN" | tail -n +2
if [ "$step" = all ] || [ "$step" = w ] || [ "$step" = 2 ]; then
  echo "== w. wait: until no task of the eighteen is queued or running, or two hours after the batch"
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
if [ "$step" = all ] || [ "$step" = s ] || [ "$step" = 2 ] || [ "$step" = 3 ]; then
  echo "== s. wait for the scorer and its tests to end"; wait_scoring; echo "none running"
fi
# The one reading of the Drive states: made once. A reading already made (its files in the run tree)
# is not made again, as a later one would replace it; a partial one stops here, for the record to say how.
if [ "$step" = all ] || [ "$step" = 2 ]; then
  echo "== 2. the one reading of the Drive states"
  n=$(echo $DONE | wc -w | tr -d ' ')
  [ "$n" != 0 ] || { echo "STOP: no config finished: nothing to read"; exit 2; }
  made=0
  for r in $DONE; do [ -e $RT/odisha_script/phase2_vectors/${r}_drive_exports.json ] && made=$((made + 1)); done
  if [ $made = "$n" ]; then
    echo "the reading was made already (all $n files there): not made again"
  elif [ $made != 0 ]; then
    for r in $DONE; do f=$RT/odisha_script/phase2_vectors/${r}_drive_exports.json; [ -e $f ] && chmod a-w $f $RT/odisha_script/phase2_vectors/${r}_drive_exports_run.json 2>/dev/null; done
    echo "STOP: $made of the reading's $n files are there (made read-only); it is not made again until the record says how"; exit 2
  else
    ( cd $RT && PYTHONPATH=$RT/src $PY scripts/drive_export_states.py \
        $(for r in $DONE; do echo odisha_script/phase2_vectors/${r}_run.json; done) )
    rc=$?
    echo "drive_export_states exit $rc (0 every task completed; 2 one not ended at the reading; 1 one failed, cancelled, unknown or without a task id; 3 or 4 nothing written)"
    made=0
    for r in $DONE; do [ -e $RT/odisha_script/phase2_vectors/${r}_drive_exports.json ] && made=$((made + 1)); done
    [ $made = 0 ] && { echo "STOP: the reading wrote nothing; it can be made again"; exit 2; }
    [ $made = "$n" ] || { echo "STOP: the reading wrote $made of $n files; it is not made again until the record says how"; }
  fi
  # Made once: its files made read-only, so that no later run, by hand or not, replaces them.
  for r in $DONE; do chmod a-w $RT/odisha_script/phase2_vectors/${r}_drive_exports.json $RT/odisha_script/phase2_vectors/${r}_drive_exports_run.json 2>/dev/null; done
  [ $made = "$n" ] || exit 2
  for r in $DONE; do $PY -c "import json; d=json.load(open('$RT/odisha_script/phase2_vectors/${r}_drive_exports.json')); print('$r', d.get('states'))"; done
fi
if [ "$step" = all ] || [ "$step" = 3 ]; then
  echo "== 3. each finished config copied again, with its Drive states"
  mkdir -p $DEST $OFF
  for r in $DONE; do
    out=$( cd $RT && PYTHONPATH=$RT/src $PY scripts/copy_run_results.py $RT $r --dest $DEST --off-git $OFF ) || \
      { echo "STOP: the copy of $r failed"; exit 3; }
    echo "$out" | grep 'OFF GIT' || true  # the files that went off git, with their SHA-256
  done
  echo "copied: $(echo $DONE | wc -w | tr -d ' ')"
fi
if [ "$step" = all ] || [ "$step" = 4 ]; then
  echo "== 4. the stage files and the Drive states in the copies"
  bad=0
  for r in $DONE; do
    for f in clustering_stand_table.csv clustering_fit_rows.csv clustering_kmeans.json k_elbow.csv \
             k_elbow_stand_table.csv k_elbow_fit_rows.csv k_elbow_types.csv k_elbow_preprocessing.json \
             k_elbow_run.json drive_exports.json; do
      [ -e $DEST/${r}_$f ] || [ -e $OFF/${r}_$f ] || { echo "MISSING ${r}_$f"; bad=1; }
    done
  done
  [ $bad = 0 ] || { echo "STOP: files missing"; exit 4; }
  echo "every stage file and the Drive states, for every finished config"
fi
if [ "$step" = all ] || [ "$step" = 5 ]; then
  echo "== 5. the cost files, and each config's second-half share"
  BATCH_END_EPOCH=$(stat -f %m $STATE)
  wait_s=$((BATCH_END_EPOCH + 1800 - $(date +%s)))
  if [ $wait_s -gt 0 ]; then echo "waiting $wait_s s, to half an hour after the batch ended"; sleep $wait_s; fi
  STARTED=$(started)
  echo "started in this batch: $(echo $STARTED | wc -w | tr -d ' ') of 18"
  for r in $STARTED; do
    if [ -e $DEST/cost_$r.json ]; then echo "the cost of $r was read already: not read again"; continue; fi
    a=$(area $r); [ -n "$a" ] || { echo "STOP: no area for $r"; exit 5; }
    n=$(tasks "$r" 2>/dev/null | awk '{print $1}')
    [ "${n:-1}" = 0 ] || { echo "the cost of $r is not read now: ${n:-?} task(s) queued or running (or not read)"; continue; }
    ( cd $RT && PYTHONPATH=$RT/src $PY scripts/eecu_by_stage.py $r $LOG $a $DEST/cost_$r.json >/dev/null ) || \
      echo "the cost of $r could not be read (read it again with this step)"
  done
  $PY - "$DEST" "$FH" "$DONE" $STARTED <<'EOF'
import json, sys
from pathlib import Path
dest, fh, done, runs = Path(sys.argv[1]), Path(sys.argv[2]), set(sys.argv[3].split()), sys.argv[4:]
out, rows = dest / "second_half_cost_shares.json", {}
for r in runs:
    two, one = dest / f"cost_{r}.json", fh / f"cost_{r}.json"
    if not (two.exists() and one.exists()):
        print(f"{r}: no {'second' if not two.exists() else 'first'}-half cost file: no share")
        continue
    a, b = json.loads(two.read_text()), json.loads(one.read_text())
    share = a["batch_total"] - b["batch_total"] + a["online_total"]
    rows[r] = {"finished": r in done, "batch_total_to_date": a["batch_total"],
               "first_half_batch_total": b["batch_total"], "second_half_online_total": a["online_total"],
               "second_half_share": round(share, 4)}
    print(f"{r}: batch to date {a['batch_total']}, first half's batch {b['batch_total']}, this batch's online "
          f"{a['online_total']}: the second half's share {share:.4f}" + ("" if r in done else " (NOT FINISHED)"))
total = round(sum(v["second_half_share"] for v in rows.values()), 4)
print(f"{len(rows)} of the {len(runs)} configs the batch started: {total} EECU-hours (the estimate for all "
      f"eighteen, 5.02)")
if runs and len(rows) == len(runs):
    if out.exists():
        print(f"{out.name} is there already: not written again")
    else:
        out.write_text(json.dumps({"configs": rows, "sum": total, "estimate_for_the_eighteen": 5.02},
                                  indent=1) + "\n")
        print(f"wrote {out}")
else:
    print(f"{out.name} not written: {len(runs) - len(rows)} config(s) without a share")
EOF
fi
