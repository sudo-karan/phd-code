"""Pull the superpixel region-adjacency graph out of Earth Engine.

The merge stage needs a graph, not a raster: which superpixels touch which, how
long their shared boundary is, and each one's attribute means. GEE has no native
region-adjacency-graph merge, so the graph comes down once (a few thousand rows)
and the merge runs client-side as union-find. The result goes back up as
`snic_clusters.remap(from_labels, to_labels)` -- an `ee.Image`, no export, no
asset ingestion, and the stage stays synchronous.

Server round-trips, all small:

  1. `frequencyHistogram` over the labels -> the label set and each one's pixel
     count. Doubles as the component-size check's input.
  2. two `frequencyHistogram`s over encoded (label, right-neighbour) and
     (label, down-neighbour) pairs -> the edge set and shared boundary lengths.
  3. one grouped `reduceRegion` per criterion band -> per-superpixel means and
     valid-pixel counts.

**Adjacency is 4-connected, deliberately, even though SNIC runs
`connectivity: 8`.** A diagonal contact between two superpixels has zero shared
boundary length, so counting it would inflate the pass-2 shared-edge tie-break
with pairs that do not actually share an edge. Only the right and down shifts
are taken, which counts each boundary pixel-pair exactly once (the left and up
shifts would re-count the same segments from the other side).

Shared edge length is `matching boundary pixel count x analysis_scale_m`: each
adjacent pair straddles one pixel edge.

Expect fewer edges than the shapely prototype reported (3569 pairs, mean degree
5.7 on the committed baseline vectors). That prototype tested polygon
intersection, which treats a corner touch as adjacency; this does not, on
purpose.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import ee

from fmu.utils.gee import safe_get_info
from fmu.utils.logging import get_logger

log = get_logger(__name__)


class TooManySuperpixelsError(RuntimeError):
    """The label count is past the point where a client-side graph is sane."""


@dataclass
class SuperpixelGraph:
    """A region-adjacency graph over dense indices `0 .. n_regions - 1`.

    Dense indices, not raw SNIC labels: SNIC numbers clusters with a spatial
    hash rather than `0..N`, so raw labels are sparse and unbounded. Everything
    downstream (union-find, the pair encoding, `remap`) wants a dense range.
    `raw_labels[i]` recovers the SNIC label for dense index `i`.
    """

    raw_labels: list[int]
    n_pixels: list[int]
    # (i, j) with i < j -> count of 4-adjacent pixel pairs across the boundary.
    edges: dict[tuple[int, int], int] = field(default_factory=dict)
    scale_m: int = 10

    @property
    def n_regions(self) -> int:
        return len(self.raw_labels)

    def neighbours(self) -> dict[int, set[int]]:
        adj: dict[int, set[int]] = {i: set() for i in range(self.n_regions)}
        for i, j in self.edges:
            adj[i].add(j)
            adj[j].add(i)
        return adj

    def shared_edge_m(self, i: int, j: int) -> float:
        """Length of the shared boundary between two regions, in metres."""
        key = (i, j) if i < j else (j, i)
        return self.edges.get(key, 0) * float(self.scale_m)

    def area_ha(self, i: int) -> float:
        return self.n_pixels[i] * self.scale_m * self.scale_m / 10_000.0

    def summary(self) -> dict[str, float | int]:
        degrees = [len(v) for v in self.neighbours().values()]
        return {
            "n_regions": self.n_regions,
            "n_edges": len(self.edges),
            "mean_degree": round(sum(degrees) / len(degrees), 3) if degrees else 0.0,
            "n_isolated": sum(1 for d in degrees if d == 0),
        }


def extract_superpixel_graph(
    labels: ee.Image,
    roi: ee.Geometry,
    scale: int,
    *,
    max_superpixels: int = 50_000,
    context: str = "superpixel graph",
) -> SuperpixelGraph:
    """Build the 4-connected region-adjacency graph for a label image.

    Raises:
        TooManySuperpixelsError: more labels than `max_superpixels`. Past that
            the `remap` argument lists the merge produces stop being reasonable,
            and the failure should be loud rather than a silently enormous
            request.
    """
    band = safe_get_info(labels.bandNames(), context=f"{context} band name")[0]
    label_image = labels.select([band])

    hist = (
        safe_get_info(
            label_image.reduceRegion(
                reducer=ee.Reducer.frequencyHistogram(),
                geometry=roi,
                scale=scale,
                # No bestEffort: a downsampled histogram would invent and drop
                # adjacencies rather than merely blurring a statistic.
                maxPixels=1e9,
            ),
            context=f"{context} label histogram",
        ).get(band)
        or {}
    )
    # Histogram keys are the label values as strings ("1234" or "1234.0").
    raw_labels = sorted(int(float(k)) for k in hist)
    n = len(raw_labels)
    if n > max_superpixels:
        raise TooManySuperpixelsError(
            f"{context}: {n} superpixels exceeds max_superpixels "
            f"({max_superpixels}). The merge runs client-side over a "
            f"{{label -> stand}} lookup table applied with remap(), and remap "
            f"argument lists this long stop being reasonable. Raise "
            f"merge.max_superpixels if you mean it, or coarsen segmentation.size."
        )
    if n == 0:
        log.warning("  %s: no labels found in the ROI", context)
        return SuperpixelGraph(raw_labels=[], n_pixels=[], scale_m=scale)

    n_pixels = [int(float(hist[k])) for k in sorted(hist, key=lambda x: int(float(x)))]

    # Dense 0..n-1 relabel. Raw SNIC labels are a sparse spatial hash, so the
    # pair encoding below would need a modulus far larger than necessary and
    # could leave exact-integer range.
    dense_index = list(range(n))
    dense = label_image.remap(raw_labels, dense_index).rename("dense")

    # translate(units="pixels") needs a definite pixel grid, so pin the
    # projection to the analysis scale. Both arms must use the same scale here
    # or "adjacent" means different things in each.
    base_proj = label_image.projection()
    base_scale = safe_get_info(
        base_proj.nominalScale(), context=f"{context} label projection scale"
    )
    if base_scale > 10 * scale:
        # EE hands an unbaked computed image a default WGS84 1-degree
        # projection. Reprojecting *that* to `scale` yields a valid grid in the
        # wrong CRS, so adjacency would be measured on a resampled raster and
        # silently return the wrong neighbours. Fail instead.
        raise ValueError(
            f"{context}: label image reports a nominal scale of "
            f"{base_scale:.0f} m against an analysis scale of {scale} m. That "
            f"is EE's default projection for an unbaked computed image, not a "
            f"real pixel grid -- shifting by 'pixels' in it would measure "
            f"adjacency on a resampled raster. Pass a label image with a real "
            f"projection (a cached asset, or one reprojected by its producer)."
        )
    proj = base_proj.atScale(scale)
    dense = dense.reproject(proj)

    edges: dict[tuple[int, int], int] = {}
    # Right and down only: 4-connectivity, each boundary pixel-pair counted once.
    for dx, dy, direction in ((-1, 0, "right"), (0, -1, "down")):
        neighbour = dense.translate(x=dx, y=dy, units="pixels", proj=proj)
        pair = (
            dense.multiply(n)
            .add(neighbour)
            .updateMask(dense.neq(neighbour))
            .toInt64()
            .rename("pair")
        )
        pair_hist = (
            safe_get_info(
                pair.reduceRegion(
                    reducer=ee.Reducer.frequencyHistogram(),
                    geometry=roi,
                    scale=scale,
                    maxPixels=1e9,
                ),
                context=f"{context} {direction}-neighbour pairs",
            ).get("pair")
            or {}
        )
        for key, count in pair_hist.items():
            code = int(float(key))
            a, b = divmod(code, n)
            edge = (a, b) if a < b else (b, a)
            edges[edge] = edges.get(edge, 0) + int(float(count))

    graph = SuperpixelGraph(
        raw_labels=raw_labels, n_pixels=n_pixels, edges=edges, scale_m=scale
    )
    s = graph.summary()
    log.info(
        "  %s: %d regions, %d adjacent pairs, mean degree %.2f, %d isolated",
        context,
        s["n_regions"],
        s["n_edges"],
        s["mean_degree"],
        s["n_isolated"],
    )
    if s["n_isolated"]:
        log.warning(
            "  %s: %d region(s) have no 4-connected neighbour. They cannot be "
            "merged and will be reported as orphans.",
            context,
            s["n_isolated"],
        )
    return graph


def extract_superpixel_attributes(
    features: ee.Image,
    labels: ee.Image,
    graph: SuperpixelGraph,
    roi: ee.Geometry,
    scale: int,
    *,
    context: str = "superpixel attributes",
) -> tuple[dict[int, dict[str, float | None]], dict[int, dict[str, int]]]:
    """Per-region band means and valid-pixel counts, keyed by dense index.

    Returns `(means, valid_counts)`. A band's mean is `None` where the region has
    no valid pixel for it -- that is a real state, not a zero: 14 of the 1249
    superpixels in the committed baseline run have no `canopy_height` at all
    (ETH no-data), and giving them 0.0 m would invent a clear-cut. A region
    missing from both dicts entirely had no valid pixel for any band.

    `valid_counts` is what the merge must weight attribute means by, rather than
    total pixel count. Weighting by total lets a null-canopy region merging into
    a defined-canopy one inherit a canopy height for territory that never
    measured one.
    """
    band_names = safe_get_info(features.bandNames(), context=f"{context} bands")
    label_band = safe_get_info(labels.bandNames(), context=f"{context} label band")[0]
    label_image = labels.select([label_band]).rename("_label")
    label_to_dense = {raw: i for i, raw in enumerate(graph.raw_labels)}

    means: dict[int, dict[str, float | None]] = {}
    counts: dict[int, dict[str, int]] = {}

    # One reduction per band, deliberately. A single grouped reduction over an
    # N-band image needs `mean().repeat(N-1)` and returns parallel arrays rather
    # than per-band keys, which silently depends on band order. Two-band
    # [value, label] groups return {label, mean, count} unambiguously, and there
    # are only three or four criteria bands.
    for band in band_names:
        grouped = safe_get_info(
            features.select([band])
            .addBands(label_image)
            .reduceRegion(
                reducer=ee.Reducer.mean()
                .combine(ee.Reducer.count(), sharedInputs=True)
                .group(groupField=1, groupName="label"),
                geometry=roi,
                scale=scale,
                maxPixels=1e9,
            ),
            context=f"{context}: {band}",
        ).get("groups")

        for row in grouped or []:
            # A label the histogram did not see: different reductions can
            # disagree at the very edge of the ROI. Skip rather than index out
            # of range.
            dense = label_to_dense.get(int(row["label"]))
            if dense is None:
                continue
            value = row.get("mean")
            count = int(row.get("count") or 0)
            # count == 0 means the region has no valid pixel for this band. That
            # is a real state, not a zero -- leave the band out of `means`
            # entirely so a caller cannot mistake "no data" for a measurement.
            means.setdefault(dense, {})[band] = (
                None if value is None or count == 0 else float(value)
            )
            counts.setdefault(dense, {})[band] = count

    missing = [i for i in range(graph.n_regions) if i not in means]
    if missing:
        log.warning(
            "  %s: %d region(s) returned no attribute row; treated as having no "
            "defined criteria (they fall to the merge's pass 2).",
            context,
            len(missing),
        )
    return means, counts
