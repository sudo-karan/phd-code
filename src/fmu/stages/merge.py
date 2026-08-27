"""Merge stage. Aggregates SNIC superpixels into forest stands.

Sits between `segmentation` and `clustering`. This is the stage that makes SNIC
a delineation method rather than a preprocessing step: **SNIC + merge produces
the stand**, and clustering is demoted to attaching a type label to a finished
stand.

Why it has to exist at all: every merging-family paper in the survey treats fine
segmentation as a *primitive*, not a stand -- Wu et al. 2013/2014 (seeded region
growing over SLIC), Olofsson et al. 2014 (region merging over Voronoi cells),
Xiong et al. 2024 (two explicit rules over multiresolution segments), Ye et al.
2025 (merge on structure/age/species over spectral micro-segments). Xiong states
the reason directly: segments from over-segmentation are too small for forest
management implementation and must be aggregated into continuous stands of
suitable size. The evidence in this repo agrees -- the layer this replaces
(dissolve-by-cluster-id) produced 505 units where 66% were under 0.5 ha holding
5.4% of the area while 6% held 68%, which is exactly the pathology Pukkala 2018,
Jia 2019 and Sun et al. 2021 describe.

How it runs. GEE has no native region-adjacency-graph merge, so:

  1. `fmu.utils.adjacency` brings down the graph -- a few thousand rows of
     (label, pixel count, neighbours, shared edge, attribute means, valid
     counts).
  2. `fmu.utils.region_merge` runs Xiong's two passes client-side as union-find,
     which is readable and unit-testable without a server.
  3. the result goes back up as `snic_clusters.remap(from, to)` -- an
     `ee.Image`, so no export, no asset ingestion, and the stage stays
     synchronous like every other one.

The merge rule is held **identical across arms**, unlike the segmentation
feature stack. "What makes two adjacent patches one stand" is a fact about
forestry, not about the sensor pipeline, so an embedding run still computes the
hand-crafted criteria bands. That is what leaves *delineation* as the only thing
differing between the arms, which is the thesis question; if each arm merged on
its own features, differences in stand geometry would confound "different
boundaries" with "different merge rules", and the thresholds would lose their
physical units along with their meaning.

Outputs:
  - stand_clusters:    integer stand ID per pixel, 0..n_stands-1
  - stand_attributes:  per-stand dict of area, criterion means and frac_valid
  - merge_diagnostics: pass counts, orphan causes, threshold calibration. Passed
                       through context (not just stage metadata) so the metrics
                       stage can fold it into metrics_<config>.json -- the
                       orphan split is a result, not a log line, and reading it
                       should not require digging through the manifest.
"""

from __future__ import annotations

from typing import Any

import ee

from fmu.config import Config
from fmu.stages.base import PipelineContext, Stage, StageResult, register_stage
from fmu.utils.adjacency import (
    extract_superpixel_attributes,
    extract_superpixel_graph,
)
from fmu.utils.components import assert_components_fit
from fmu.utils.gee import safe_call, safe_get_info
from fmu.utils.logging import get_logger
from fmu.utils.region_merge import calibrate_thresholds, merge_superpixels

log = get_logger(__name__)

# pixelLonLat()'s band names. Carried through the attribute reduction so stand
# centroids come free, and used as the merge's deterministic tie-break: the two
# arms' tessellations diverge run to run, so SNIC label order is not a stable
# thing to sort by, but a centroid is.
_LON_BAND = "longitude"
_LAT_BAND = "latitude"


@register_stage("merge")
class MergeStage(Stage):
    name = "merge"
    # Invariant subset only; the criteria bands' sources depend on
    # `merge.criteria`, so the real dependency check is in validate().
    required_inputs = {"roi", "snic_clusters"}
    produces = {"stand_clusters", "stand_attributes", "merge_diagnostics"}
    # `stand_clusters` is a remap of a cached image, so it is cheap to rebuild
    # and caching it would need the merge config hashed into the key (the
    # thresholds are the main thing being iterated on, so a stale cache would
    # silently poison exactly that). `stand_attributes` is a Python dict and is
    # not an ee.Image at all.
    cacheable_outputs = set()

    def validate(self, ctx: PipelineContext, config: Config) -> None:
        needed = {"roi", "snic_clusters"} | config.merge.input_sources()
        missing = needed - ctx.keys()
        if missing:
            raise KeyError(
                f"{self.name}: missing required context inputs: {sorted(missing)}. "
                f"Context has: {sorted(ctx.keys())}. These are required because "
                f"merge.criteria references them -- either add the producing "
                f"stage to the run, or change merge.criteria."
            )

    @safe_call("merging superpixels into stands")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        roi = ctx.get("roi")
        snic_clusters: ee.Image = ctx.get("snic_clusters")
        params = config.merge
        scale = config.export.analysis_scale_m
        warnings: list[str] = []

        # The cap is derived from merge.max_area_ha, so checking it against the
        # *input* superpixels is the weaker half; the output stands are checked
        # below, after the merge, which is where a violation would actually bite.
        max_component_px = config.max_component_pixels()
        assert_components_fit(
            snic_clusters, roi, scale, max_component_px, context="merge input"
        )

        graph = extract_superpixel_graph(
            snic_clusters,
            roi,
            scale,
            max_superpixels=params.max_superpixels,
            context="merge adjacency",
        )
        if graph.n_regions == 0:
            raise ValueError(
                "merge: the SNIC label image has no labels inside the ROI. "
                "Check that segmentation ran and that roi matches the one it used."
            )

        criteria_image = _criteria_image(ctx, params)
        means, valid_counts = extract_superpixel_attributes(
            criteria_image.addBands(ee.Image.pixelLonLat()),
            snic_clusters,
            graph,
            roi,
            scale,
            context="merge criteria",
        )
        centroids = {
            i: (
                float(m.get(_LON_BAND) or 0.0),
                float(m.get(_LAT_BAND) or 0.0),
            )
            for i, m in means.items()
        }

        tolerances = params.tolerances()
        calibration = calibrate_thresholds(graph, means, tolerances)
        _log_calibration(calibration)

        result = merge_superpixels(
            graph,
            means,
            valid_counts,
            criteria=tolerances,
            relax_factor=params.relax_factor,
            min_area_ha=params.min_area_ha,
            max_area_ha=params.max_area_ha,
            min_defined_criteria=params.min_defined_criteria,
            min_frac_valid=params.min_frac_valid,
            max_pass2_iterations=params.max_pass2_iterations,
            centroids=centroids,
        )

        # Back up to the server as a relabel of the SNIC image. No export, no
        # asset ingestion; `remap` takes the lookup table directly.
        stand_clusters = (
            snic_clusters.remap(graph.raw_labels, result.assignment)
            .rename("stand_clusters")
            .toInt32()
            .clip(roi)
        )

        d = result.diagnostics
        log.info(
            "  merged %d superpixels -> %d stands (%.2fx reduction)",
            d["n_superpixels"],
            d["n_stands"],
            d["reduction_factor"],
        )
        warnings.extend(_warnings_from(d, params))
        for w in warnings:
            log.warning("  %s", w)

        diagnostics = {
            **d,
            "adjacency": graph.summary(),
            "threshold_calibration": calibration,
            "warnings": warnings,
        }

        return StageResult(
            outputs={
                "stand_clusters": stand_clusters,
                "stand_attributes": result.stand_attributes,
                "merge_diagnostics": diagnostics,
            },
            metadata={
                "criteria": [
                    {"source": c.source, "band": c.band, "tolerance": c.tolerance}
                    for c in params.criteria
                ],
                "relax_factor": params.relax_factor,
                "min_area_ha": params.min_area_ha,
                "max_area_ha": params.max_area_ha,
                "min_defined_criteria": params.min_defined_criteria,
                "min_frac_valid": params.min_frac_valid,
                "adjacency": graph.summary(),
                # Where the configured thresholds actually land in this AOI's
                # own neighbour-difference distribution, including the joint
                # admit rate the per-band marginals do not describe.
                "threshold_calibration": calibration,
                **d,
            },
            warnings=warnings,
        )


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _criteria_image(ctx: PipelineContext, params: Any) -> ee.Image:
    """One image carrying every criterion band, named by band."""
    bands = []
    for c in params.criteria:
        source: ee.Image = ctx.get(c.source)
        bands.append(source.select(c.band).rename(c.band))
    return ee.Image.cat(bands)


def _log_calibration(calibration: dict[str, Any]) -> None:
    log.info(
        "  threshold calibration over %d adjacent pairs:", calibration["n_pairs"]
    )
    for band, row in calibration["per_band"].items():
        log.info(
            "    %-24s tol %-8s = p%-5.1f of pair differences "
            "(p50 %s, p75 %s, defined on %d pairs)",
            band,
            row["threshold"],
            row["percentile_of_threshold"],
            row["p50"],
            row["p75"],
            row["n_pairs_defined"],
        )
    log.info(
        "    joint admit rate (all criteria at once): %.1f%% of %d pairs. "
        "The gate is conjunctive, so this is NOT any of the marginals above.",
        calibration["joint_admit_rate_pct"],
        calibration["n_pairs_with_any_defined_criterion"],
    )


def _warnings_from(d: dict[str, Any], params: Any) -> list[str]:
    """Turn the merge diagnostics into things worth saying out loud.

    These land in the run manifest as stage warnings, so a bad threshold choice
    is legible from the record rather than requiring someone to reason it out
    of the numbers.
    """
    out: list[str] = []
    if d["orphans_area_blocked"]:
        out.append(
            f"{d['orphans_area_blocked']} stand(s) stayed below min_area_ha "
            f"({params.min_area_ha} ha) because every neighbour is already too "
            f"big to absorb them under max_area_ha ({params.max_area_ha} ha). "
            f"That is a signal max_area_ha is too tight, not that the forest is "
            f"heterogeneous."
        )
    if d["orphans_isolated"]:
        out.append(
            f"{d['orphans_isolated']} stand(s) have no 4-connected neighbour at "
            f"all and cannot be merged with anything."
        )
    if d["orphans_no_attribute_match"]:
        out.append(
            f"{d['orphans_no_attribute_match']} undersized stand(s) still have a "
            f"fitting neighbour, which means pass 2 ran out of its "
            f"{params.max_pass2_iterations} iterations rather than converging."
        )
    if d["stands_with_incomplete_criteria"]:
        out.append(
            f"{d['stands_with_incomplete_criteria']} stand(s) have at least one "
            f"criterion valid on under {params.min_frac_valid:.0%} of their "
            f"pixels; those bands are reported as null rather than as a mean "
            f"over territory that has no data."
        )
    if d["pass2_fallback_merges"]:
        out.append(
            f"{d['pass2_fallback_merges']} of {d['pass2_merges']} pass-2 merges "
            f"used the shared-edge fallback, i.e. no relaxed criterion could "
            f"justify them. These are the merges to look at first if stand "
            f"geometry looks wrong."
        )
    if d["n_stands"] == d["n_superpixels"]:
        out.append(
            "No superpixels merged at all. Either the thresholds are far too "
            "tight for this AOI, or the criteria bands are constant/undefined "
            "over it. Check threshold_calibration in the metadata."
        )
    return out
