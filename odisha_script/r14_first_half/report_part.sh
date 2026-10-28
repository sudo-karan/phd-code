#!/bin/bash
# The elbow report in parts, while R3's first half runs (Jaskaran's order of 28 Oct 2026: "Write the
# elbow report in parts: first Sanjay Van and the 3 ha boxes (both arms) as soon as they are done,
# then the 10 ha boxes, then the tile."):
#   report_part.sh 1     the hand-crafted 3 ha boxes, Sanjay Van (both arms), the AlphaEarth 3 ha
#                        boxes: the declared order's first ten
#   report_part.sh 2     the 10 ha boxes, both arms: the next eight
# The tile, the order's last, completes the full report, made after the batch by after_batch.sh
# (step 5, r14_elbow). For each config of the part, its k elbow pass must have ended with exit 0 in
# the batch log ("--- PASS<n> <config> k_elbow exit=0 ---"), and no task of it may be queued or
# running; then its records are copied (scripts/copy_run_results.py --through k_elbow) and its cost
# read (scripts/eecu_by_stage.py), and the report is written over every record so far
# (odisha_script/r14_elbow_report.py --allow-missing --stem r14_elbow_part<n>, into the main repo's
# odisha_script/keptland_scores/), the configs not yet done named in it as missing. Every tool runs
# from the run tree, the batch's commit; only the records go to the main repo. Read-only on Earth
# Engine; nothing is committed here.
set -u
set -o pipefail
REPO=/Users/karan/Desktop/phd-code
RT=$REPO/outputs/round14/run_tree_5
PY=$REPO/.venv/bin/python
DEST=$REPO/docs/reproducibility/r14_runs/first_half
OFF=$REPO/outputs/round14/results/first_half
LOG=$REPO/outputs/round14/logs/r14_first_half.log
part=${1:?part 1 or 2}
ALL=$(cd $RT && $PY odisha_script/r14_first_half/order.py | xargs -n1 basename | sed 's/\.yaml$//') || { echo "STOP: the order could not be read"; exit 2; }
[ "$(echo "$ALL" | grep -c .)" = 19 ] || { echo "STOP: the order did not give nineteen configs"; exit 2; }
case "$part" in
  1) RUNS=$(echo "$ALL" | sed -n 1,10p) ;;
  2) RUNS=$(echo "$ALL" | sed -n 11,18p) ;;
  *) echo "STOP: part 1 or 2 (the tile completes the full report, after_batch.sh 5)"; exit 2 ;;
esac
echo "part $part: $(echo "$RUNS" | grep -c .) configs"

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

notyet=0
for r in $RUNS; do
  if grep -q "^--- PASS[0-9]* $r k_elbow exit=0 ---" $LOG; then echo "  done: $r"; else echo "  NOT YET: $r"; notyet=1; fi
done
[ $notyet = 0 ] || { echo "STOP: the part's configs are not all done; run it again when they are"; exit 3; }
n=$(tasks "$RUNS" 2>/dev/null | awk '{print $1}')
[ "${n:-1}" = 0 ] || { echo "STOP: ${n:-?} task(s) of the part's configs queued or running (or not read); run it again later"; exit 3; }
mkdir -p $DEST $OFF
for r in $RUNS; do
  ( cd $RT && PYTHONPATH=$RT/src $PY scripts/copy_run_results.py $RT $r --through k_elbow --dest $DEST --off-git $OFF >/dev/null ) || { echo "STOP: the copy of $r failed"; exit 4; }
  for f in k_elbow.csv k_elbow_stand_table.csv k_elbow_fit_rows.csv k_elbow_types.csv k_elbow_preprocessing.json k_elbow_run.json; do
    [ -e $DEST/${r}_$f ] || [ -e $OFF/${r}_$f ] || { echo "STOP: ${r}_$f is missing after the copy"; exit 4; }
  done
  if [ -e $DEST/cost_$r.json ]; then echo "  the cost of $r was read already"; else
    ( cd $RT && PYTHONPATH=$RT/src $PY scripts/eecu_by_stage.py $r $LOG $(area $r) $DEST/cost_$r.json >/dev/null ) && \
      $PY -c "import json; d=json.load(open('$DEST/cost_$r.json')); print('  $r', 'cost', d['total'])" || \
      echo "  the cost of $r could not be read (read it again with after_batch.sh 4 after the batch)"
  fi
done
( cd $RT && PYTHONPATH=$RT/src $PY odisha_script/r14_elbow_report.py --records $DEST \
    --out-dir $REPO/odisha_script/keptland_scores --stem r14_elbow_part$part --allow-missing ); rc=$?
echo "r14_elbow_report exit $rc (part $part: odisha_script/keptland_scores/r14_elbow_part${part}*)"
exit $rc
