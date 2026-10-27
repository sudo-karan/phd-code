#!/bin/bash
# Start R3's first half (Task 5) and its stop-rule watcher, once preflight.sh <commit> has passed
# (the round 14 record, Done, the order changed). From the run tree, so that the batch, the order and
# the watcher are the batch's commit:
#   launch.sh
# 1. The nineteen configs from the run tree's order.py (refused unless it gives nineteen).
# 2. The batch: run_passes_safely.py --label r14_first_half --through k_elbow, under nohup and
#    caffeinate -i, its log and state in outputs/round14/logs/, in a session of its own (so that a
#    signal to the command that launched it does not reach it).
# 3. The watcher (odisha_script/r14_first_half/watch.py, from the run tree), the same way, given the
#    batch log's length from before the batch started (printed here: to start the watcher again by
#    hand, give it as --from-byte), so that it reads only this batch's lines; it waits up to ten
#    minutes for this label's wrapper. Its r is the second live check's (live_check_2): by
#    Jaskaran's order of 28 Oct 2026 the first half runs before the third check.
# 4. Two minutes on: the wrapper's pid (from the lock) alive, its lines, the console's last lines,
#    the watcher alive, and its first reading.
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
detach() {  # "$@" in a session of its own, its parent gone (launchd adopts it)
  ( $PY -c 'import os, sys; os.setsid(); os.execvp(sys.argv[1], sys.argv[1:])' "$@" & )
}
FROM=$( [ -e $LOG ] && stat -f %z $LOG || echo 0 )
echo "the batch log's length before the batch: $FROM bytes (watch.py --from-byte $FROM, to start the watcher again by hand)"
# The configs as separate words (bash splits the unquoted list on its newlines).
detach nohup caffeinate -i nice $PY odisha_script/run_passes_safely.py --label r14_first_half --run-tree $RT \
  --log-dir $LOGS --through k_elbow $CONFIGS >> $LOGS/r14_first_half_console.log 2>&1
echo "batch started ($(TZ=Asia/Kolkata date '+%Y-%m-%d %H:%M:%S IST'))"
detach nohup $PY odisha_script/r14_first_half/watch.py --label r14_first_half \
  --costs $REPO/docs/reproducibility/r14_runs/live_check_2 \
  --runs odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_c odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_d \
  --batch-log $LOG --quota-log $LOGS/r14_first_half_quota.log --from-byte $FROM \
  >> $LOGS/r14_first_half_watch_console.log 2>&1
echo "watcher started"
sleep 120
pid=$(cat ~/.fmu/run_passes_safely.lock 2>/dev/null)
echo "the wrapper (the lock's pid $pid):"; ps -o pid=,command= -p "$pid" 2>/dev/null | cut -c1-160 || echo "  NOT ALIVE"
echo "the wrapper's lines so far:"; grep '^\[run_passes_safely' $LOG | tail -3
echo "the console's last lines:"; tail -3 $LOGS/r14_first_half_console.log
echo "the watcher:"; pgrep -fl "[r]14_first_half/watch.py" | cut -c1-160 || echo "  NOT RUNNING: start it again by hand (the record says how)"
tail -3 $LOGS/r14_first_half_quota.log
