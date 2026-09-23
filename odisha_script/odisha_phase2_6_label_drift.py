"""
Phase 2, step 6 — are the cached k-means type labels what a fresh run produces, at the plots?

NEEDS LIVE EARTH ENGINE. Read-only: no exports, no assets written.

WHY
---
The clustering memory fix was verified by running the old and the new clustering code on the
same cached context: they gave pixel-identical labels. That run also showed that BOTH differ
from the cached `cluster_labels` asset for odisha_v120_handcrafted (pixel-weight neq 50216 of
77338; sample agreement 0.772 after matching cluster ids). The cached asset was computed in batch
from terrain features evaluated live, and the cached terrain features differ from that live
evaluation (elevation/slope/aspect scaling up to 0.48). So the type labels the export stage
attached to the stands are not exactly what re-running clustering on the cached inputs gives.

Only 6.3 (label agreement) reads the labels; 6.1 and 6.2 use stand identity, which the merge
fixes before clustering. This script measures the drift where 6.3 reads it -- at the pilot plots
-- so the size of the issue is a number rather than a pixel-level worry.

WHAT
----
Per hand-crafted arm: rebuild the cached context through merge (odisha_phase2_4_noise_null's
observed_context), run the committed ClusteringStage, and sample at the pilot plots:
  fresh   the new run's cluster_labels
  cached  the cached cluster_labels asset
Compared with the stand cluster_id in phase2_plots_joined.csv (which the export stage took from
the cached labels), raw and after Hungarian matching of cluster ids. ARI, NMI and Cramer's V are
invariant to relabelling, so only plots that change cluster AFTER matching can move 6.3.

Run from the repo root (fmu reads .env from the working directory):
      python odisha_script/odisha_phase2_6_label_drift.py
Writes: odisha_script/odisha_phase2_6_results.txt, odisha_script/odisha_phase2_6_plot_labels.csv
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import ee
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from fmu.config import load_config
from fmu.stages.clustering import ClusteringStage
from fmu.utils.caching import cached_asset_path, config_fingerprint
from fmu.utils.gee import init_gee, load_roi_geometry, safe_get_info

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from odisha_phase2_4_noise_null import observed_context, pilot_plots, plots_fc  # noqa: E402

ARMS = {"v120": "odisha_v120_handcrafted", "current": "odisha_current_handcrafted"}
JOINED = HERE / "phase2_plots_joined.csv"
RESULTS = HERE / "odisha_phase2_6_results.txt"
OUT_CSV = HERE / "odisha_phase2_6_plot_labels.csv"

_lines: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    _lines.append(s)


def main() -> int:
    logging.getLogger("fmu").setLevel(logging.WARNING)
    init_gee()
    joined = pd.read_csv(JOINED)
    rows = []
    for arm, name in ARMS.items():
        cfg = load_config(REPO / "configs" / f"{name}.yaml")
        roi = load_roi_geometry(cfg.roi.roi_file)
        ctx = observed_context(cfg, roi)
        fresh = ClusteringStage().run(ctx, cfg).outputs["cluster_labels"].rename("fresh")
        cached = ee.Image(cached_asset_path(cfg.name, "clustering", "cluster_labels",
                                            config_fingerprint(cfg))).rename("cached")
        plots = pilot_plots(REPO / cfg.roi.roi_file)
        got = safe_get_info(
            fresh.addBands(cached).reduceRegions(collection=plots_fc(plots),
                                                 reducer=ee.Reducer.first(), scale=10),
            context=f"{arm} labels at plots")
        s = (pd.DataFrame([f["properties"] for f in got["features"]])
             .merge(joined[["plot_key", "site_polygon", f"{arm}_merged_cluster"]], on="plot_key",
                    validate="1:1"))
        ok = s.dropna(subset=["fresh", "cached"]).copy()
        f_ = ok.fresh.round().astype(int).to_numpy()
        c_ = ok.cached.round().astype(int).to_numpy()
        tab = pd.crosstab(pd.Series(c_, name="cached"), pd.Series(f_, name="fresh"))
        r, c = linear_sum_assignment(-tab.to_numpy())
        mapping = {int(tab.index[i]): int(tab.columns[j]) for i, j in zip(r, c)}
        ok["cached_mapped"] = [mapping.get(v, -1) for v in c_]
        ok["moved_after_matching"] = ok.cached_mapped.to_numpy() != f_
        stand = ok[f"{arm}_merged_cluster"].to_numpy()

        say("=" * 90)
        say(f"{arm} ({name})")
        say("=" * 90)
        say(f"  plots with both labels: {len(ok)} of {len(s)}")
        say(f"  cached pixel label == exported stand cluster_id at the plot: {np.mean(c_ == stand):.3f}")
        say(f"  fresh vs cached at plots: raw agreement {np.mean(f_ == c_):.3f}; after Hungarian "
            f"matching {1 - ok.moved_after_matching.mean():.3f} "
            f"({int(ok.moved_after_matching.sum())} plot(s) change cluster after matching)")
        say(f"  cluster-id mapping cached -> fresh: {mapping}")
        say("  crosstab (rows cached, cols fresh):")
        for line in tab.to_string().splitlines():
            say("    " + line)
        moved = ok[ok.moved_after_matching]
        if len(moved):
            say("  plots that change cluster after matching:")
            for m in moved.itertuples():
                say(f"    {m.plot_key}  {m.site_polygon}  cached {int(m.cached)} -> fresh {int(m.fresh)}")
        for m in ok.itertuples():
            rows.append({"arm": arm, "plot_key": m.plot_key, "site_polygon": m.site_polygon,
                         "cached": int(round(m.cached)), "fresh": int(round(m.fresh)),
                         "cached_mapped_to_fresh_ids": int(m.cached_mapped),
                         "moved_after_matching": bool(m.moved_after_matching)})

    pd.DataFrame(rows).to_csv(OUT_CSV, index=False)
    RESULTS.write_text("\n".join(_lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
