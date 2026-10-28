"""Read-only (ee_read_only.forbid_writes): before the smoke test, which of _r14_check_c's and
_r14_check_d's cached assets exist, by the keys their configs give today: every cacheable output
of masking, data_load, the four feature stages and segmentation must exist (the second live check
cached them), and k_elbow's and clustering's must not (none was made). Prints JSON; exit 1 if any
expectation fails. Run from the repo root (or a run tree's root, which has the same configs)."""
import json
import sys

sys.path.insert(0, "scripts")
import ee_read_only  # noqa: E402
from fmu.config import load_config  # noqa: E402
from fmu.utils.caching import asset_exists, cache_key, cached_asset_path  # noqa: E402
from fmu.utils.gee import init_gee  # noqa: E402

init_gee()
refused = ee_read_only.forbid_writes()
OUTPUTS = {
    "masking": ("habitat_mask", "landcover_summary", "mask_provenance", "water_mask"),
    "data_load": ("s2_composite",), "features_optical": ("optical_features",),
    "features_radar": ("radar_features",), "features_structure": ("structure_features",),
    "features_static": ("static_features",), "segmentation": ("snic_clusters", "snic_means"),
    "k_elbow": ("k_elbow",), "clustering": ("cluster_labels", "feature_stack"),
}
MUST_NOT = {"k_elbow", "clustering"}
out, ok = {}, True
for s in ("c", "d"):
    cfg = load_config(f"configs/odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_{s}.yaml")
    rows = {}
    for stage, outputs in OUTPUTS.items():
        key = cache_key(cfg, stage, "per_step")
        for o in outputs:
            there = asset_exists(cached_asset_path(cfg.name, stage, o, key))
            expected = stage not in MUST_NOT
            ok &= there == expected
            rows[f"{stage}/{o}__{key}"] = {"exists": there, "as_expected": there == expected}
    out[cfg.name] = rows
print(json.dumps({"as_expected": ok, "replaced": len(refused), "assets": out}, indent=1))
sys.exit(0 if ok else 1)
