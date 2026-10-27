#!/bin/bash
# Start R3's first half (Task 5) and its stop-rule watcher, once preflight.sh <commit> has passed
# (the round 14 record, Done, R3's first half). From the run tree, so that the batch, the order and
# the watcher are the batch's commit:
#   launch.sh
# 1. The nineteen configs from the run tree's order.py (refused unless it gives nineteen).
# 2. The batch: run_passes_safely.py --label r14_first_half --through k_elbow, under nohup and
#    caffeinate -i, its log and state in outputs/round14/logs/.
# 3. The watcher (odisha_script/r14_first_half/watch.py, from the run tree), given the batch log's
#    length from before the batch started, so that it reads only this batch's lines; it waits up to
#    ten minutes for this label's wrapper.
# 4. Two minutes on: the wrapper's started line, the watcher alive, and its first reading.
set -u
REPO=/Users/karan/Desktop/phd-code
RT=$REPO/outputs/round14/run_tree_5
PY=$REPO/.venv/bin/python
LOGS=$REPO/outputs/round14/logs
LOG=$LOGS/r14_first_half.log
cd $RT || { echo "REFUSED: no run tree $RT"; exit 1; }
CONFIGS=$($PY odisha_script/r14_first_half/order.py) || { echo "REFUSED: the order could not be read"; exit 1; }
[ "$(echo "$CONFIGS" | grep -c .)" = 19 ] || { echo "REFUSED: the order did not give nineteen configs"; exit 1; }
if pgrep -fl "[r]un_passes_safely|[r]un_config_passes|[r]14_first_half/watch.py"; then
  echo "REFUSED: a batch process or a watcher is running"; exit 1
fi
FROM=$( [ -e $LOG ] && stat -f %z $LOG || echo 0 )
# The configs as separate words (bash splits the unquoted list on its newlines).
nohup caffeinate -i nice $PY odisha_script/run_passes_safely.py --label r14_first_half --run-tree $RT \
  --log-dir $LOGS --through k_elbow $CONFIGS > $LOGS/r14_first_half_console.log 2>&1 &
echo "batch started: pid $! ($(TZ=Asia/Kolkata date '+%Y-%m-%d %H:%M:%S IST'))"
nohup $PY odisha_script/r14_first_half/watch.py --label r14_first_half \
  --costs $REPO/docs/reproducibility/r14_runs/live_check_3 --batch-log $LOG \
  --quota-log $LOGS/r14_first_half_quota.log --from-byte $FROM > $LOGS/r14_first_half_watch_console.log 2>&1 &
echo "watcher started: pid $!"
sleep 120
echo "the wrapper's lines so far:"; grep '^\[run_passes_safely' $LOG | tail -3
echo "the watcher:"; pgrep -fl "[r]14_first_half/watch.py" || echo "  NOT RUNNING: start it again by hand (the record says how)"
tail -3 $LOGS/r14_first_half_quota.log
