"""The eighteen R3 configs of the second half, in the first half's declared order (the brief's groups,
within each by config file name; odisha_script/r14_first_half/order.py) with the 10 km tile left
out: Jaskaran dropped it from R3 on 28 Oct 2026, to run later (the round 14 record, Done, the plan
changed to finish today). The hand-crafted 3 ha boxes; Sanjay Van, both arms; the AlphaEarth 3 ha
boxes; the 10 ha boxes, AlphaEarth's four, then the hand-crafted four. So each set of four boxes
ends together, and is scored as soon as it does (register process-r14-score-each-set-as-exported).
Prints their paths, relative to the repo root, one per line; exits 1 if they are not exactly
configs/*_r14.yaml less the tile.

    python odisha_script/r14_second_half/order.py   (from the repo root or a run tree's root)
"""
import sys
from pathlib import Path

DISTRICTS = ("angul", "dhenkanal", "kendujhar", "koraput")
TILE = "odisha_v120_3ha_tile10km_angul_keptland_s1desc_r14"
GROUPS = [
    sorted(f"odisha_v120_3ha_squares_{d}_keptland_s1desc_r14" for d in DISTRICTS),
    sorted(("sanjay_van_alphaearth_keptland_r14", "sanjay_van_baseline_keptland_r14")),
    sorted(f"odisha_alphaearth_3ha_squares_{d}_keptland_r14" for d in DISTRICTS),
    sorted(f"odisha_alphaearth_10ha_squares_{d}_keptland_r14" for d in DISTRICTS)
    + sorted(f"odisha_v120_10ha_squares_{d}_keptland_s1desc_r14" for d in DISTRICTS),
]
ORDER = [name for group in GROUPS for name in group]

on_disk = sorted(p.stem for p in Path("configs").glob("*_r14.yaml") if p.stem != TILE)
if sorted(ORDER) != on_disk or len(ORDER) != 18:
    sys.exit(f"the order's configs {sorted(ORDER)} are not configs/*_r14.yaml less the tile {on_disk}")
print("\n".join(f"configs/{name}.yaml" for name in ORDER))
