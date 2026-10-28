#!/bin/bash
# Before the smoke test's batch (the round 14 record, Done, the round resumed again), read-only on
# Earth Engine; no batch unless every check below holds:
#   preflight_smoke.sh <commit> [run tree]
# The run tree (outputs/round14/run_tree_3 by default) is made at <commit> if it does not exist,
# with its own .env, or moved to <commit> if it is at another one (nothing in it is deleted); then:
# the main repo is clean and pushed at <commit>; the run tree is at <commit>, clean, with no
# untracked code by its own rule, and its tests/test_r14_configs.py passes (the configs' keys are
# the pinned ones); no batch holds the lock; the quota (round_use.py); the two configs' assets as
# the smoke test needs them (smoke_assets.py); and the listing of read-only call 12 made again,
# kept as a results file (list_k_elbow_assets.py).
set -u
C=$1
REPO=/Users/karan/Desktop/phd-code
RT=${2:-$REPO/outputs/round14/run_tree_3}
PY=$REPO/.venv/bin/python
HERE=$REPO/odisha_script/r14_smoke_test
full=$(git -C $REPO rev-parse "$C") || exit 1
echo "commit $full"
echo "main HEAD $(git -C $REPO rev-parse HEAD)  origin $(git -C $REPO rev-parse origin/work/round14-r3)"
echo "main tracked changes: $(git -C $REPO status --porcelain --untracked-files=no | wc -l | tr -d ' ')"
if [ ! -d "$RT" ]; then
  mkdir -p $REPO/outputs/round14/logs $REPO/outputs/round14/results
  git clone -q $REPO "$RT" && git -C "$RT" checkout -q --detach "$full" && cp $REPO/.env "$RT/.env"
  echo "run tree made"
elif [ "$(git -C $RT rev-parse HEAD)" != "$full" ]; then
  echo "run tree at $(git -C $RT rev-parse --short HEAD): moving it to $full"
  [ -z "$(git -C $RT status --porcelain --untracked-files=no)" ] || { echo "REFUSED: the run tree has modified tracked files"; exit 1; }
  git -C "$RT" fetch -q "$REPO" && git -C "$RT" checkout -q --detach "$full" || { echo "COULD NOT MOVE THE RUN TREE"; exit 1; }
  echo "moved"
fi
# A run tree that holds an earlier batch's run folders or run records would mix them into the
# smoke test's records (the copy tool takes every run folder of a config): refused.
if [ -n "$(ls -A $RT/runs 2>/dev/null)" ] || ls $RT/odisha_script/phase2_vectors/*_check_[cd]_* >/dev/null 2>&1; then
  echo "REFUSED: the run tree holds run folders or run records of an earlier batch"; exit 1
fi
echo "run tree HEAD $(git -C $RT rev-parse HEAD)"
[ "$(git -C $RT rev-parse HEAD)" = "$full" ] || { echo "RUN TREE NOT AT COMMIT"; exit 1; }
echo "run tree porcelain (tracked):"; git -C $RT status --porcelain --untracked-files=no
[ -z "$(git -C $RT status --porcelain --untracked-files=no)" ] || { echo "REFUSED: the run tree has modified tracked files"; exit 1; }
echo "run tree untracked (all):"; git -C $RT status --porcelain --untracked-files=all | grep '^??' | head
echo "run tree .env ignored: $(git -C $RT check-ignore .env)"
( cd $RT && PYTHONPATH=$RT/src $PY -c "
from pathlib import Path
from fmu.utils.provenance import untracked_code
print('untracked code by the run tree rule:', untracked_code(Path('.')))
" )
( cd $RT && PYTHONPATH=$RT/src $PY -m pytest -q -p no:cacheprovider tests/test_r14_configs.py 2>&1 | tail -2 )
echo "lock:"; ls -la ~/.fmu/ 2>/dev/null || echo "  no ~/.fmu yet"
pgrep -fl "[r]un_passes_safely|[r]un_config_passes|[o]disha_phase2_2_run_pipeline" || echo "no batch process"
( cd $RT && PYTHONPATH=$RT/src $PY $HERE/round_use.py --folders )
echo "the two configs' assets:"
( cd $RT && PYTHONPATH=$RT/src $PY $HERE/smoke_assets.py | $PY -c "
import json, sys; d = json.load(sys.stdin); print('as expected:', d['as_expected'])
for run, rows in d['assets'].items():
    print(' ', run, sum(r['exists'] for r in rows.values()), 'of', len(rows), 'exist;', [k for k, r in rows.items() if not r['as_expected']] or 'all as expected')" )
echo "the listing of read-only call 12, again, kept as a results file:"
mkdir -p $REPO/docs/reproducibility/r14_runs/smoke_test
( cd $REPO && $PY $HERE/list_k_elbow_assets.py $REPO/docs/reproducibility/r14_runs/smoke_test/r14_k_elbow_assets_before.json | tail -6 )
