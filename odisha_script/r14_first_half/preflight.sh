#!/bin/bash
# Before R3's first half (Task 5: the nineteen _r14 configs through k_elbow, one batch; the round 14
# record, Done, the cost estimate and the step before Task 5), read-only on Earth Engine; no batch
# unless every check below holds:
#   preflight.sh <commit> [run tree]
# First, before the run tree is touched: <commit> is the pushed head of the work branch (as the
# main repo last fetched it); no batch process and no watcher is running; no log or state file of
# the label r14_first_half exists (this is the label's first batch: a batch resumed under it is
# started by hand, as the record says); the run tree, if it exists, holds no run folder or run
# record of the nineteen. Then the run tree (outputs/round14/run_tree_5 by default) is made at
# <commit> if it does not exist, with its own .env, or moved to <commit> if it is at another one and
# has no run folder at all (nothing in it is deleted). Then, from the run tree: the order
# (odisha_script/r14_first_half/order.py) gives the nineteen; the run tree is at <commit>, clean,
# with no untracked code by its own rule; its tests/test_r14_configs.py passes (the keys are the
# pinned ones); the second live check's two cost files are there (live_check_2: by Jaskaran's order
# of 28 Oct 2026 the first half runs before the third live check, so r is the second check's); the
# quota (round_use.py) and the brief's rule for the batch's estimate, 79.80, with the round's budget
# 200 (Jaskaran's answer to question 14 (b), 28 Oct 2026; October's floor of 100 kept); no task of
# the nineteen or of any check copy (_check_a to _check_f) queued or running; no asset folder of the
# nineteen (from scratch). It prints r (the second check's charged cost over 7.94), the stop,
# 200 - 1.2 x max(1, r) x 12.51, and the forecast, the estimate times the larger of 1.5 and 1.2 r.
# Exit 1 if a check fails.
set -u
C=$1
REPO=/Users/karan/Desktop/phd-code
RT=${2:-$REPO/outputs/round14/run_tree_5}
PY=$REPO/.venv/bin/python
L2=$REPO/docs/reproducibility/r14_runs/live_check_2
LOGS=$REPO/outputs/round14/logs
full=$(git -C $REPO rev-parse "$C") || exit 1
echo "commit $full"
echo "main HEAD $(git -C $REPO rev-parse HEAD)  origin $(git -C $REPO rev-parse origin/work/round14-r3)"
[ "$(git -C $REPO rev-parse origin/work/round14-r3)" = "$full" ] || { echo "REFUSED: <commit> is not the pushed head of the work branch"; exit 1; }
if pgrep -fl "[r]un_passes_safely|[r]un_config_passes|[o]disha_phase2_2_run_pipeline|[r]14_first_half/watch.py"; then
  echo "REFUSED: a batch process or a watcher is running"; exit 1
fi
echo "no batch process, no watcher"
for f in $LOGS/r14_first_half.log $LOGS/r14_first_half.state.json; do
  [ -e $f ] && { echo "REFUSED: $f exists: this is not the label's first batch"; exit 1; }
done
NAMES=$(cd $REPO && $PY odisha_script/r14_first_half/order.py | xargs -n1 basename | sed 's/\.yaml$//')
[ "$(echo "$NAMES" | grep -c .)" = 19 ] || { echo "REFUSED: the order did not give nineteen configs"; exit 1; }
for n in $NAMES; do
  if ls -d $RT/runs/${n}_2* >/dev/null 2>&1 || ls $RT/odisha_script/phase2_vectors/${n}_* 2>/dev/null | grep -qv "_r14_check_"; then
    echo "REFUSED: the run tree holds run folders or run records of $n"; exit 1
  fi
done
if [ ! -d "$RT" ]; then
  mkdir -p $LOGS $REPO/outputs/round14/results
  git clone -q $REPO "$RT" && git -C "$RT" checkout -q --detach "$full" && cp $REPO/.env "$RT/.env" || { echo "COULD NOT MAKE THE RUN TREE"; exit 1; }
  echo "run tree made"
elif [ "$(git -C $RT rev-parse HEAD)" != "$full" ]; then
  echo "run tree at $(git -C $RT rev-parse --short HEAD): moving it to $full"
  [ -z "$(ls -A $RT/runs 2>/dev/null)" ] || { echo "REFUSED: the run tree holds run folders of an earlier batch; it is not moved"; exit 1; }
  [ -z "$(git -C $RT status --porcelain --untracked-files=no)" ] || { echo "REFUSED: the run tree has modified tracked files"; exit 1; }
  git -C "$RT" fetch -q "$REPO" && git -C "$RT" checkout -q --detach "$full" || { echo "COULD NOT MOVE THE RUN TREE"; exit 1; }
  echo "moved"
fi
echo "run tree HEAD $(git -C $RT rev-parse HEAD)"
[ "$(git -C $RT rev-parse HEAD)" = "$full" ] || { echo "RUN TREE NOT AT COMMIT"; exit 1; }
CONFIGS=$(cd $RT && $PY odisha_script/r14_first_half/order.py) || { echo "REFUSED: the run tree's order could not be read"; exit 1; }
[ "$(echo "$CONFIGS" | grep -c .)" = 19 ] || { echo "REFUSED: the run tree's order did not give nineteen configs"; exit 1; }
echo "the nineteen, in the declared order (the run tree's order.py):"; for c in $CONFIGS; do echo "  $c"; done
[ -z "$(git -C $RT status --porcelain --untracked-files=no)" ] || { echo "REFUSED: the run tree has modified tracked files"; exit 1; }
echo "run tree .env ignored: $(git -C $RT check-ignore .env)"
uc=$( cd $RT && PYTHONPATH=$RT/src $PY -c "
from pathlib import Path
from fmu.utils.provenance import untracked_code
print(len(untracked_code(Path('.'))))
" )
echo "untracked code by the run tree rule: $uc"
[ "$uc" = 0 ] || { echo "REFUSED: the run tree holds untracked code"; exit 1; }
( cd $RT && PYTHONPATH=$RT/src $PY -m pytest -q -p no:cacheprovider tests/test_r14_configs.py 2>&1 | tail -2 )
( cd $RT && PYTHONPATH=$RT/src $PY -m pytest -q -p no:cacheprovider tests/test_r14_configs.py >/dev/null 2>&1 ) || { echo "REFUSED: tests/test_r14_configs.py fails in the run tree"; exit 1; }
for s in c d; do
  [ -e $L2/cost_odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_$s.json ] || { echo "REFUSED: the second check's cost file of _check_$s is missing"; exit 1; }
done
q=$( cd $RT && PYTHONPATH=$RT/src $PY odisha_script/r14_smoke_test/round_use.py --folders ) || { echo "REFUSED: the quota could not be read"; exit 1; }
echo "$q"
echo "$q" | $PY -c "
import json, sys
q = json.loads(sys.stdin.read())
names = '''$NAMES'''.split()
est = 79.80
use, left = q['round_use_h'], q['october_left_h']
fits = use + est <= 200 and left - est >= 100
print(f'by the brief\'s rule: {use:.2f} + {est} = {use + est:.2f} within the round\'s 200: {use + est <= 200}; '
      f'October keeps {left - est:.2f}, at least 100: {left - est >= 100}')
cost = [json.load(open('$L2/cost_odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_' + s + '.json'))['total'] for s in 'cd']
r = sum(cost) / 7.94
stop = 200 - 1.2 * max(1.0, r) * 12.51
print(f'the second check charged {sum(cost):.4f}; r = {r:.4f}; the stop: {stop:.4f}; '
      f'the forecast: {est} x {max(1.5, 1.2 * r):.4f} = {est * max(1.5, 1.2 * r):.2f}, the round then at {use + est * max(1.5, 1.2 * r):.2f}')
active = [str(t or '') for t in q['queued_or_running']]
checks = [t for t in active if '_r14_check_' in t]
mine = [t for t in active if any(t.startswith(n + '_') for n in names)]
there = [n for n in q['r14_folders_existing'] if n in names]
print('tasks of a check copy queued or running:', checks)
print('tasks of the nineteen queued or running:', mine)
print('asset folders of the nineteen (from scratch: none):', there)
sys.exit(0 if fits and not checks and not mine and not there else 1)
" || { echo "REFUSED: the quota, a task queued or running, or an asset folder of the nineteen"; exit 1; }
echo "PREFLIGHT PASSED"
