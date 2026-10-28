#!/bin/bash
# Start R3's second half (Task 7) once preflight.sh <commit> has passed (the round 14 record, Done,
# the plan changed to finish today): the batch, its stop-rule watcher and the scorer, each from the
# run tree, so that the batch, the order, the watcher and the scoring code are the batch's commit:
#   launch.sh
# 1. The eighteen configs from the run tree's order.py (refused unless it gives eighteen).
# 2. The batch: run_passes_safely.py --label r14_second_half (every stage, through export: features,
#    segmentation and the k elbow are read back from the cache, clustering and export compute),
#    under nohup and caffeinate -i, its log and state in outputs/round14/logs/, in a session of its
#    own.
# 3. The watcher (odisha_script/r14_first_half/watch.py, the same rule; Done, the cost estimate: "For
#    the second half, likewise, with its own largest pass"): r from the first half's eighteen cost
#    files over their estimate, 76.58; the largest pass 0.80 (AlphaEarth Dhenkanal 10 ha's clustering
#    pass); given the batch log's length from before the batch started.
# 4. The scorer (odisha_script/r14_second_half/score_as_exported.py; register
#    process-r14-score-each-set-as-exported): each set copied and scored as soon as its four runs'
#    export passes have ended with exit 0, its chance test started in a process of its own.
# 5. Two minutes on: the wrapper's pid (from the lock) alive, its lines, the console's last lines,
#    the watcher and the scorer alive, and their first lines.
set -u
REPO=/Users/karan/Desktop/phd-code
RT=$REPO/outputs/round14/run_tree_5
PY=$REPO/.venv/bin/python
LOGS=$REPO/outputs/round14/logs
LOG=$LOGS/r14_second_half.log
cd $RT || { echo "REFUSED: no run tree $RT"; exit 1; }
CONFIGS=$($PY odisha_script/r14_second_half/order.py) || { echo "REFUSED: the order could not be read"; exit 1; }
[ "$(echo "$CONFIGS" | grep -c .)" = 18 ] || { echo "REFUSED: the order did not give eighteen configs"; exit 1; }
RUNS=$(echo "$CONFIGS" | xargs -n1 basename | sed 's/\.yaml$//')
if pgrep -fl "[r]un_passes_safely|[r]un_config_passes|[r]14_first_half/watch.py|[r]14_second_half/score_as_exported.py"; then
  echo "REFUSED: a batch process, a watcher or a scorer is running"; exit 1
fi
detach() {  # "$@" in a session of its own, its parent gone (launchd adopts it)
  ( $PY -c 'import os, sys; os.setsid(); os.execvp(sys.argv[1], sys.argv[1:])' "$@" & )
}
FROM=$( [ -e $LOG ] && stat -f %z $LOG || echo 0 )
echo "the batch log's length before the batch: $FROM bytes (watch.py and score_as_exported.py --from-byte $FROM, to start them again by hand)"
# The configs as separate words (bash splits the unquoted list on its newlines).
detach nohup caffeinate -i nice $PY odisha_script/run_passes_safely.py --label r14_second_half --run-tree $RT \
  --log-dir $LOGS $CONFIGS >> $LOGS/r14_second_half_console.log 2>&1
echo "batch started ($(TZ=Asia/Kolkata date '+%Y-%m-%d %H:%M:%S IST'))"
detach nohup $PY odisha_script/r14_first_half/watch.py --label r14_second_half \
  --costs $REPO/docs/reproducibility/r14_runs/first_half --runs $RUNS --estimate 76.58 --largest-pass 0.80 \
  --batch-log $LOG --quota-log $LOGS/r14_second_half_quota.log --from-byte $FROM \
  >> $LOGS/r14_second_half_watch_console.log 2>&1
echo "watcher started"
detach nohup $PY odisha_script/r14_second_half/score_as_exported.py --batch-log $LOG --from-byte $FROM \
  --out $LOGS/r14_second_half_scorer.log >> $LOGS/r14_second_half_scorer_console.log 2>&1
echo "scorer started"
sleep 120
pid=$(cat ~/.fmu/run_passes_safely.lock 2>/dev/null)
echo "the wrapper (the lock's pid $pid):"; ps -o pid=,command= -p "$pid" 2>/dev/null | cut -c1-160 || echo "  NOT ALIVE"
echo "the wrapper's lines so far:"; grep '^\[run_passes_safely' $LOG | tail -3
echo "the console's last lines:"; tail -3 $LOGS/r14_second_half_console.log
echo "the watcher:"; pgrep -fl "[r]14_first_half/watch.py" | cut -c1-160 || echo "  NOT RUNNING: start it again by hand (the record says how)"
tail -3 $LOGS/r14_second_half_quota.log
echo "the scorer:"; pgrep -fl "[r]14_second_half/score_as_exported.py" | cut -c1-160 || echo "  NOT RUNNING: start it again by hand (the record says how)"
tail -3 $LOGS/r14_second_half_scorer.log
