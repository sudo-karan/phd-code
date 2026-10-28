#!/bin/bash
# Before R3's second half (Task 7: clustering, profiling and export of the eighteen R3 configs, the
# elbows read back from the cache; label r14_second_half; the round 14 record, Done, the plan changed
# to finish today, and the gate's steps before Task 7), read-only on Earth Engine; no batch unless
# every check below holds:
#   preflight.sh <commit>
# <commit> is the pushed head of the work branch, at which every config carries Jaskaran's k (Task 7,
# item 1). First, before the run tree is touched: no batch process, watcher, stop or scorer is
# running; no log or state file of the label r14_second_half exists; R3's first half has ended (its
# "batch r14_first_half ended" line) and its records are whole: each of the eighteen has its k
# elbow's six files and its cost file in docs/reproducibility/r14_runs/first_half/, and the full
# elbow report's run record names the tile alone as having no record. Then the run tree,
# outputs/round14/run_tree_5 (the first half's, with the first half's run folders: the gate's step
# before Task 7, (ii), "the same run tree moved to the new commit"), is moved to <commit> if it is at
# another one (refused if it has modified tracked files; nothing in it is deleted). Then, from the
# run tree: the order (odisha_script/r14_second_half/order.py) gives the eighteen; the run tree is at
# <commit>, clean, with no untracked code by its own rule; its tests/test_r14_configs.py passes (k as
# Jaskaran gave it, the pins, and each k elbow key the first half's); (i) each config's k elbow step
# key is the one in its first half's <run>_k_elbow_run.json, so the elbow is read back, not computed
# again; (ii) the run tree holds a segmentation pass's run folder of each config (the export pass
# reads its snic_distance_scale); the k elbow's cached table of each config is on Earth Engine at that
# key, and no clustering asset of it exists yet (read-only); the quota (round_use.py) by the brief's
# rule for the batch's estimate, 5.02 (the record's 5.77 less the tile's 0.74), with the round's 200
# and October's floor of 100; no task of the eighteen or of a check copy queued or running. It prints
# r (the first half's eighteen cost files' total over their estimate, 76.58), the stop,
# 200 - 1.2 x max(1, r) x 0.80 (the second half's largest pass at estimate: AlphaEarth Dhenkanal
# 10 ha's clustering pass), and the forecast, 5.02 x max(1.5, 1.2 r). Exit 1 if a check fails.
set -u
C=${1:?the commit}
REPO=/Users/karan/Desktop/phd-code
RT=$REPO/outputs/round14/run_tree_5
PY=$REPO/.venv/bin/python
FH=$REPO/docs/reproducibility/r14_runs/first_half
LOGS=$REPO/outputs/round14/logs
TILE=odisha_v120_3ha_tile10km_angul_keptland_s1desc_r14
full=$(git -C $REPO rev-parse "$C") || exit 1
echo "commit $full"
echo "main HEAD $(git -C $REPO rev-parse HEAD)  origin $(git -C $REPO rev-parse origin/work/round14-r3)"
[ "$(git -C $REPO rev-parse origin/work/round14-r3)" = "$full" ] || { echo "REFUSED: <commit> is not the pushed head of the work branch"; exit 1; }
if pgrep -fl "[r]un_passes_safely|[r]un_config_passes|[o]disha_phase2_2_run_pipeline|[r]14_first_half/watch.py|[r]14_second_half/|[s]top_before_tile.py"; then
  echo "REFUSED: a batch process, a watcher, the stop or a scorer is running"; exit 1
fi
echo "no batch process, watcher, stop or scorer"
for f in $LOGS/r14_second_half.log $LOGS/r14_second_half.state.json; do
  [ -e $f ] && { echo "REFUSED: $f exists: this is not the label's first batch"; exit 1; }
done
grep -q '^\[run_passes_safely .*\] batch r14_first_half ended:' $LOGS/r14_first_half.log || { echo "REFUSED: R3's first half has not ended"; exit 1; }
NAMES=$(cd $REPO && $PY odisha_script/r14_second_half/order.py | xargs -n1 basename | sed 's/\.yaml$//')
[ "$(echo "$NAMES" | grep -c .)" = 18 ] || { echo "REFUSED: the order did not give eighteen configs"; exit 1; }
bad=0
for n in $NAMES; do
  for f in k_elbow.csv k_elbow_stand_table.csv k_elbow_fit_rows.csv k_elbow_types.csv k_elbow_preprocessing.json k_elbow_run.json; do
    [ -e $FH/${n}_$f ] || { echo "MISSING first_half/${n}_$f"; bad=1; }
  done
  [ -e $FH/cost_$n.json ] || { echo "MISSING first_half/cost_$n.json"; bad=1; }
done
[ $bad = 0 ] || { echo "REFUSED: the first half's records are not whole"; exit 1; }
$PY - "$REPO/odisha_script/keptland_scores/r14_elbow_run.json" "$TILE" <<'EOF' || { echo "REFUSED: the full elbow report is not there, or names other runs than the tile as missing"; exit 1; }
import json, sys
missing = json.load(open(sys.argv[1])).get("missing_runs")
print("the full elbow report's runs without a record:", missing)
sys.exit(0 if missing == [sys.argv[2]] else 1)
EOF
echo "the first half's records are whole: the eighteen's k elbow files and cost files, and the full report"
[ -d "$RT" ] || { echo "REFUSED: no run tree $RT"; exit 1; }
[ -z "$(git -C $RT status --porcelain --untracked-files=no)" ] || { echo "REFUSED: the run tree has modified tracked files"; exit 1; }
if [ "$(git -C $RT rev-parse HEAD)" != "$full" ]; then
  echo "run tree at $(git -C $RT rev-parse --short HEAD): moving it to $full (its run folders stay)"
  git -C "$RT" fetch -q "$REPO" && git -C "$RT" checkout -q --detach "$full" || { echo "COULD NOT MOVE THE RUN TREE"; exit 1; }
  echo "moved"
fi
echo "run tree HEAD $(git -C $RT rev-parse HEAD)"
[ "$(git -C $RT rev-parse HEAD)" = "$full" ] || { echo "RUN TREE NOT AT COMMIT"; exit 1; }
CONFIGS=$(cd $RT && $PY odisha_script/r14_second_half/order.py) || { echo "REFUSED: the run tree's order could not be read"; exit 1; }
[ "$(echo "$CONFIGS" | grep -c .)" = 18 ] || { echo "REFUSED: the run tree's order did not give eighteen configs"; exit 1; }
echo "the eighteen, in order (the run tree's order.py):"; for c in $CONFIGS; do echo "  $c"; done
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
( cd $RT && PYTHONPATH=$RT/src:$RT/scripts $PY - "$FH" $NAMES <<'EOF' ) || { echo "REFUSED: a k elbow key, a run folder, or an asset on Earth Engine"; exit 1; }
import json, sys
from pathlib import Path

import ee
import ee_read_only
from fmu.config import load_config
from fmu.utils.caching import cached_asset_path, step_keys

sys.path.insert(0, "scripts")
import copy_run_results as crr

fh, names = Path(sys.argv[1]), sys.argv[2:]
ee.Initialize(credentials=ee.data.get_persistent_credentials(), project="replicating-paper")
ee.data.setDeadline(120_000)
ee_read_only.forbid_writes()


def exists(path: str) -> bool:
    try:
        ee.data.getAsset(path)
        return True
    except ee.EEException as e:
        if "not found" in str(e).lower() or "does not exist" in str(e).lower():
            return False
        raise


ok = True
for n in names:
    keys = step_keys(load_config(Path("configs") / f"{n}.yaml"))
    first = json.loads((fh / f"{n}_k_elbow_run.json").read_text())["step_keys"]["k_elbow"]
    kinds = {k for _, k, _ in crr.run_folders(Path("."), n) if k is not None}
    elbow = cached_asset_path(n, "k_elbow", "k_elbow", keys["k_elbow"])
    clustering = [cached_asset_path(n, "clustering", o, keys["clustering"]) for o in ("cluster_labels", "feature_stack")]
    there = exists(elbow)
    stale = [p for p in clustering if exists(p)]
    good = keys["k_elbow"] == first and "segmentation" in kinds and there and not stale
    ok &= good
    print(f"{n}: k elbow key {keys['k_elbow']} (first half {first}); passes with run folders {sorted(kinds)}; "
          f"the elbow's table on Earth Engine: {there}; clustering assets already there: {stale or 'none'}"
          + ("" if good else "  <-- REFUSED"))
sys.exit(0 if ok else 1)
EOF
q=$( cd $RT && PYTHONPATH=$RT/src $PY odisha_script/r14_smoke_test/round_use.py --folders ) || { echo "REFUSED: the quota could not be read"; exit 1; }
echo "$q"
echo "$q" | $PY -c "
import json, sys
q = json.loads(sys.stdin.read())
names = '''$NAMES'''.split()
est, largest, first_est = 5.02, 0.80, 76.58
use, left = q['round_use_h'], q['october_left_h']
fits = use + est <= 200 and left - est >= 100
print(f'by the brief\'s rule: {use:.2f} + {est} = {use + est:.2f} within the round\'s 200: {use + est <= 200}; '
      f'October keeps {left - est:.2f}, at least 100: {left - est >= 100}')
charged = sum(json.load(open('$FH/cost_' + n + '.json'))['total'] for n in names)
r = charged / first_est
stop = 200 - 1.2 * max(1.0, r) * largest
print(f'the first half charged {charged:.4f} for the eighteen; r = {r:.4f}; the stop: {stop:.4f}; '
      f'the forecast: {est} x {max(1.5, 1.2 * r):.4f} = {est * max(1.5, 1.2 * r):.2f}, the round then at {use + est * max(1.5, 1.2 * r):.2f}')
active = [str(t or '') for t in q['queued_or_running']]
checks = [t for t in active if '_r14_check_' in t]
mine = [t for t in active if any(t.startswith(n + '_') for n in names)]
print('tasks of a check copy queued or running:', checks)
print('tasks of the eighteen queued or running:', mine)
sys.exit(0 if fits and not checks and not mine else 1)
" || { echo "REFUSED: the quota, or a task queued or running"; exit 1; }
echo "PREFLIGHT PASSED"
