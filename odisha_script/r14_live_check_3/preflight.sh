#!/bin/bash
# Before the third live check's batch (Task 4, _r14_check_e and _r14_check_f, from scratch; the
# round 14 record, Done, the round resumed again), read-only on Earth Engine; no batch unless every
# check below holds:
#   preflight.sh <commit> [run tree]
# The run tree (outputs/round14/run_tree_4 by default) is made at <commit> if it does not exist,
# with its own .env, or moved to <commit> if it is at another one (nothing in it is deleted); then:
# the main repo is clean and pushed at <commit>; the run tree is at <commit>, clean, with no
# untracked code by its own rule, holds no run folder or run record of the two configs, and its
# tests/test_r14_configs.py passes (the configs' keys are the pinned ones); no batch holds the lock;
# the quota (round_use.py) and the brief's rule for the batch's estimate, 7.94; and, as the runs are
# from scratch, neither config's asset folder exists. Exit 1 if a check fails.
set -u
C=$1
REPO=/Users/karan/Desktop/phd-code
RT=${2:-$REPO/outputs/round14/run_tree_4}
PY=$REPO/.venv/bin/python
ESTIMATE=7.94
E=odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_e
F=odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_f
full=$(git -C $REPO rev-parse "$C") || exit 1
echo "commit $full"
echo "main HEAD $(git -C $REPO rev-parse HEAD)  origin $(git -C $REPO rev-parse origin/work/round14-r3)"
[ "$(git -C $REPO rev-parse origin/work/round14-r3)" = "$full" ] || { echo "REFUSED: <commit> is not the pushed head of the work branch"; exit 1; }
echo "main tracked changes: $(git -C $REPO status --porcelain --untracked-files=no | wc -l | tr -d ' ')"
if [ ! -d "$RT" ]; then
  mkdir -p $REPO/outputs/round14/logs $REPO/outputs/round14/results
  git clone -q $REPO "$RT" && git -C "$RT" checkout -q --detach "$full" && cp $REPO/.env "$RT/.env" || { echo "COULD NOT MAKE THE RUN TREE"; exit 1; }
  echo "run tree made"
elif [ "$(git -C $RT rev-parse HEAD)" != "$full" ]; then
  echo "run tree at $(git -C $RT rev-parse --short HEAD): moving it to $full"
  [ -z "$(git -C $RT status --porcelain --untracked-files=no)" ] || { echo "REFUSED: the run tree has modified tracked files"; exit 1; }
  git -C "$RT" fetch -q "$REPO" && git -C "$RT" checkout -q --detach "$full" || { echo "COULD NOT MOVE THE RUN TREE"; exit 1; }
  echo "moved"
fi
# A run tree that holds run folders or run records of the two configs would mix them into the
# check's records (the copy tool takes every run folder of a config): refused.
if ls -d $RT/runs/*_check_[ef]* >/dev/null 2>&1 || ls $RT/odisha_script/phase2_vectors/*_check_[ef]_* >/dev/null 2>&1; then
  echo "REFUSED: the run tree holds run folders or run records of _check_e or _check_f"; exit 1
fi
echo "run tree HEAD $(git -C $RT rev-parse HEAD)"
[ "$(git -C $RT rev-parse HEAD)" = "$full" ] || { echo "RUN TREE NOT AT COMMIT"; exit 1; }
echo "run tree porcelain (tracked):"; git -C $RT status --porcelain --untracked-files=no
[ -z "$(git -C $RT status --porcelain --untracked-files=no)" ] || { echo "REFUSED: the run tree has modified tracked files"; exit 1; }
echo "run tree untracked (all):"; git -C $RT status --porcelain --untracked-files=all | grep '^??' | head
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
echo "lock:"; ls -la ~/.fmu/ 2>/dev/null || echo "  no ~/.fmu yet"
if pgrep -fl "[r]un_passes_safely|[r]un_config_passes|[o]disha_phase2_2_run_pipeline"; then
  echo "REFUSED: a batch process is running"; exit 1
fi
echo "no batch process"
q=$( cd $RT && PYTHONPATH=$RT/src $PY $REPO/odisha_script/r14_smoke_test/round_use.py --folders ) || { echo "REFUSED: the quota could not be read"; exit 1; }
echo "$q"
echo "$q" | $PY -c "
import json, sys
q = json.loads(sys.stdin.read())
use, left, est = q['round_use_h'], q['october_left_h'], $ESTIMATE
fits = use + est <= 150 and left - est >= 100
print(f'by the brief\'s rule: {use:.2f} + {est} = {use + est:.2f} within 150: {use + est <= 150}; '
      f'October keeps {left - est:.2f}, at least 100: {left - est >= 100}')
mine = [t for t in q['queued_or_running'] if t.startswith(('$E', '$F'))]
there = [n for n in q['r14_folders_existing'] if n in ('$E', '$F')]
print('tasks of the two configs queued or running:', mine)
print('asset folders of the two configs (from scratch: none):', there)
sys.exit(0 if fits and not mine and not there else 1)
" || { echo "REFUSED: the quota, a task of the two configs, or an asset folder of theirs"; exit 1; }
echo "PREFLIGHT PASSED"
