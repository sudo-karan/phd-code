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

**Every one of these reductions is unweighted and runs on the label image's own
projection, so they all count the same pixels.** Earth Engine takes a pixel into
an unweighted reduction over the ROI when its centre is in the ROI, with weight 1,
and into a weighted one (a reducer as it comes) when about 1/256 of it is,
weighted by the fraction inside. The histograms used to be weighted and the valid
counts were not, so at the ROI edge a superpixel's pixel count was a sum of
fractions, truncated, while its valid counts were whole pixels: some superpixels
got 0 pixels, and `frac_valid` came out above 1 (review B17, round 13). Each count
is now of whole pixels whose centre is in the ROI, and a valid count above its
superpixel's pixel count stops the merge (`extract_superpixel_attributes`).

Each reduction is given the label image's projection as `crs`, and no `scale`:
Earth Engine then counts on that projection exactly, its transform included.
Until round 14 the label histogram and the pair histograms were given a scale
alone, and the grouped reductions the label image's CRS name with a scale, from
which Earth Engine builds a grid of its own. On real data, in round 14's live
check (27 Oct 2026), three superpixels of 1,202 at the ROI's edge took one or two
pixels more on that grid than in the label histogram, and the check above stopped
the merge in both runs. So the label image must be on a grid at the analysis
scale (segmentation puts it on one): a pixel counts as `scale` x `scale` m.

Two things Earth Engine's unweighted reducers do that its guide does not say,
read on Earth Engine in round 13 on synthetic images: a frequencyHistogram counts
the region's masked pixels under the key "null", which the graph leaves out; and
a grouped reducer adds a band's masked pixels into the sum it gives a group,
though its count leaves them out, so each criterion band goes in unmasked beside
a band of where it has data, and a mean is the one sum over the other.

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

import math
from dataclasses import dataclass, field
from typing import Any

import ee

from fmu.utils.gee import LABEL_BAND, safe_get_info
from fmu.utils.logging import get_logger

log = get_logger(__name__)


# The band the grouped reducers group by. Shared with every other place that
# synthesises a label band -- see `fmu.utils.gee.LABEL_BAND` for why there is
# exactly one of these now.
_GROUP_BAND = LABEL_BAND
# The two bands summed per region for a criterion band's mean and valid count
# (extract_superpixel_attributes): the band with 0 where it has no data, and a
# band of 1 where it has data.
_SUM_OF_VALUES = "value"
_PIXELS_WITH_DATA = "has_data"
# The key under which an unweighted frequencyHistogram counts the masked pixels of
# the region (read on Earth Engine in round 13; a weighted one leaves them out).
_MASKED_KEY = "null"


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

    Every count is taken on the label image's own projection (`crs` that
    projection, no `scale`), as `extract_superpixel_attributes` takes its valid
    counts, so the label image must be on a grid at `scale`.

    Raises:
        TooManySuperpixelsError: more labels than `max_superpixels`. Past that
            the `remap` argument lists the merge produces stop being reasonable,
            and the failure should be loud rather than a silently enormous
            request.
        ValueError: the label image is not on a grid at `scale`: it carries Earth
            Engine's default projection, or its pixels are another size.
    """
    band = safe_get_info(labels.bandNames(), context=f"{context} band name")[0]
    label_image = labels.select([band])

    # The label image's own grid, on which every count of the merge is taken
    # (round 14): checked first, as nothing counted on another grid is of use.
    grid = label_image.projection()
    base_scale = safe_get_info(
        grid.nominalScale(), context=f"{context} label projection scale"
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
    if not math.isclose(base_scale, scale, rel_tol=0.01):
        # The counts are of the label image's own pixels, and an area is pixels x
        # scale^2. Until round 14 a coarser label image (30 m at 10 m, say) was
        # counted at `scale`; on its own grid each superpixel would get a ninth of
        # its area. 1% leaves room for float rounding and for a projection's own
        # scale factor (UTM's is 0.9996 on its central meridian); a label image on
        # another grid is two or three times coarser or finer.
        raise ValueError(
            f"{context}: label image reports a nominal scale of {base_scale:g} m "
            f"against an analysis scale of {scale} m. The merge counts pixels on the "
            f"label image's own grid and takes each as {scale} x {scale} m, so the "
            f"label image must be on a grid at the analysis scale, as segmentation "
            f"makes it: reproject it to the analysis grid (export.analysis_scale_m)."
        )

    hist = (
        safe_get_info(
            label_image.reduceRegion(
                # Unweighted: whole pixels whose centre is in the ROI, the pixels the
                # valid counts of extract_superpixel_attributes count (review B17).
                reducer=ee.Reducer.frequencyHistogram().unweighted(),
                geometry=roi,
                # On the label image's own projection, transform included, and no
                # scale, as every reduction here (round 14).
                crs=grid,
                # No bestEffort: a downsampled histogram would invent and drop
                # adjacencies rather than merely blurring a statistic.
                maxPixels=1e9,
            ),
            context=f"{context} label histogram",
        ).get(band)
        or {}
    )
    # Histogram keys are the label values as strings ("1234" or "1234.0"). An
    # unweighted histogram also counts the region's masked pixels, under the key
    # "null" (read on Earth Engine in round 13, on synthetic images): they are no
    # superpixel's, and are left out.
    hist = {k: v for k, v in hist.items() if k != _MASKED_KEY}
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

    # Whole numbers, read as floats: rounded, so float noise cannot lose a pixel.
    n_pixels = [round(float(hist[k])) for k in sorted(hist, key=lambda x: int(float(x)))]

    # Dense 0..n-1 relabel. Raw SNIC labels are a sparse spatial hash, so the
    # pair encoding below would need a modulus far larger than necessary and
    # could leave exact-integer range.
    dense_index = list(range(n))
    dense = label_image.remap(raw_labels, dense_index).rename("dense")

    # translate(units="pixels") needs a definite pixel grid: the label image's
    # own, at the analysis scale (checked above), on which the pairs are then
    # counted, so a pair is shifted and counted on one grid. Both arms must use
    # the same scale here or "adjacent" means different things in each. (Until
    # round 14 the grid was the label image's projection at `scale`, the same
    # grid for a label image at the analysis scale.)
    dense = dense.reproject(grid)

    edges: dict[tuple[int, int], int] = {}
    # Right and down only: 4-connectivity, each boundary pixel-pair counted once.
    for dx, dy, direction in ((-1, 0, "right"), (0, -1, "down")):
        neighbour = dense.translate(x=dx, y=dy, units="pixels", proj=grid)
        # The code reaches n^2 - 1, past 2^31 once n is over 46,340, and Earth
        # Engine gives multiply and add "the union of the input types": both
        # indices are cast to int64 before it is computed (review B34).
        pair = (
            dense.toInt64()
            .multiply(n)
            .add(neighbour.toInt64())
            .updateMask(dense.neq(neighbour))
            .rename("pair")
        )
        pair_hist = (
            safe_get_info(
                pair.reduceRegion(
                    # Unweighted, as the label histogram: each boundary pixel pair
                    # whose first pixel's centre is in the ROI, counted once, on
                    # the label image's own projection.
                    reducer=ee.Reducer.frequencyHistogram().unweighted(),
                    geometry=roi,
                    crs=grid,
                    maxPixels=1e9,
                ),
                context=f"{context} {direction}-neighbour pairs",
            ).get("pair")
            or {}
        )
        for key, count in pair_hist.items():
            # The masked pixels: a pixel and its neighbour of one superpixel, or one
            # of them with no superpixel (see the label histogram).
            if key == _MASKED_KEY:
                continue
            code = int(float(key))
            a, b = divmod(code, n)
            edge = (a, b) if a < b else (b, a)
            edges[edge] = edges.get(edge, 0) + round(float(count))

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

    `scale` is the analysis scale `graph` was counted at. The counts here are
    taken on the label image's own grid, which `extract_superpixel_graph` checks
    is at that scale.

    The reduction is unweighted, as the histograms of `extract_superpixel_graph`
    are, and runs on the label image's own projection, as they do (`crs` that
    projection, no `scale`), so a valid count and `graph.n_pixels` count the same
    pixels and their ratio, `frac_valid`, is at most 1 (review B17). It sums, per
    region, the band unmasked (0 where it has no data) and a band of 1 where it
    has data, and a mean is the one sum over the other: Earth Engine's grouped
    unweighted reducers add a band's masked pixels into the sum (and so the mean)
    they give a group, though their count leaves them out (read on Earth Engine in
    round 13, on synthetic images), so a masked band does not go in.

    Until round 14 the reduction was given the label image's CRS name and
    `scale`, a grid Earth Engine builds of its own, while the histograms counted
    on the label image's grid. On real data (round 14's live check, 27 Oct 2026)
    three superpixels of 1,202 at the ROI's edge took one or two pixels more on
    it, and the check below stopped the merge: "superpixel -1586256414 has 29
    valid canopy_height pixels but 28 pixels in the label histogram".

    Raises:
        ValueError: a band's valid count is above its superpixel's pixel count.
            The two reductions then counted different pixels, and every
            `frac_valid` the merge reports would be wrong.
    """
    band_names = safe_get_info(features.bandNames(), context=f"{context} bands")
    label_band = safe_get_info(labels.bandNames(), context=f"{context} label band")[0]
    if _GROUP_BAND in band_names:
        raise ValueError(
            f"{context}: a feature band is named {_GROUP_BAND!r}, which collides "
            f"with the band the grouped reduction groups by. Rename it."
        )
    label_image = labels.select([label_band]).rename(_GROUP_BAND)
    label_to_dense = {raw: i for i, raw in enumerate(graph.raw_labels)}

    # Pin the reduction to the *label* image's grid: its projection itself,
    # transform included, with no scale, as the histograms of
    # extract_superpixel_graph are pinned. `reduceRegion` defaults its CRS to the
    # first band's projection, which here is a feature band -- often an uncached
    # computed image carrying EE's WGS84 default, whose pixels are not square. The
    # counts below would then be geographic pixels while `graph.n_pixels` holds the
    # label grid's pixels, and `min_frac_valid` divides one by the other. The CRS
    # name and a scale, which this passed until round 14, are not enough: Earth
    # Engine builds a grid of its own from them, and at the ROI's edge it counted
    # other pixels than the label histogram (round 14's live check).
    grid = labels.projection()

    means: dict[int, dict[str, float | None]] = {}
    counts: dict[int, dict[str, int]] = {}

    # One reduction per band, deliberately. A single grouped reduction over an
    # N-band image needs `mean().repeat(N-1)` and returns parallel arrays rather
    # than per-band keys, which silently depends on band order. Two-band
    # [value, label] groups return {label, mean, count} unambiguously, and there
    # are only three or four criteria bands.
    for band in band_names:
        band_image = features.select([band])
        # No masked band into the grouped unweighted reduction (see the docstring):
        # the band with 0 where it has no data, and a band of where it has data.
        summed = (
            # Unmasked everywhere (sameFootprint false): unmask(0) alone leaves the band
            # masked outside its footprint (read on Earth Engine in round 13).
            band_image.unmask(0, False)
            .rename(_SUM_OF_VALUES)
            .addBands(band_image.mask().gt(0).unmask(0, False).rename(_PIXELS_WITH_DATA))
        )
        grouped = safe_get_info(
            summed.addBands(label_image)
            .reduceRegion(
                # Unweighted as a whole, as the histograms are: the counts are then
                # of the pixels graph.n_pixels counts, and each mean is over them.
                reducer=ee.Reducer.sum()
                .forEachBand(summed)
                .group(groupField=2, groupName="label")
                .unweighted(),
                geometry=roi,
                crs=grid,
                maxPixels=1e9,
            ),
            context=f"{context}: {band}",
        ).get("groups")

        for row in grouped or []:
            # A label the histogram did not see. Both reductions take the same
            # pixels, so this should not happen; skip rather than index out of
            # range if it does.
            dense = label_to_dense.get(int(row["label"]))
            if dense is None:
                continue
            # Whole numbers, read as floats: rounded, as the histograms' counts are.
            count = round(float(row.get(_PIXELS_WITH_DATA) or 0))
            value = float(row[_SUM_OF_VALUES]) / count if count else None
            if count > graph.n_pixels[dense]:
                raise ValueError(
                    f"{context}: superpixel {int(row['label'])} has {count} valid "
                    f"{band} pixels but {graph.n_pixels[dense]} pixels in the label "
                    f"histogram, so its frac_valid would be above 1. The two "
                    f"reductions must count the same pixels: both unweighted, on the "
                    f"label image's own projection. One of them is weighted, or they "
                    f"ran on different grids."
                )
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


def stand_geometry(
    labels: ee.Image,
    roi: ee.Geometry,
    scale: int,
    *,
    context: str = "stand geometry",
) -> dict[int, dict[str, float]]:
    """Per-region area, perimeter and Polsby-Popper compactness.

    The repo could not previously measure the thing it produces: there was no
    stand count, no area distribution, and no shape statistic anywhere in the
    metrics. Xiong et al. 2024, Pukkala 2018, Jia 2019 and Sun et al. 2021 all
    report stand geometry, and the pathology in the layer this replaces
    (dissolve-by-cluster-id: 6% of units holding 68% of the area) is invisible
    without it.

    Perimeter is counted in **pixel edges**: for each pixel of a region, the
    number of its four neighbours that belong to a different region or to no
    region at all (masked, or outside the ROI). Multiplied by `scale`, that is
    the length of the region's raster boundary.

    **Polsby-Popper (4*pi*A / P^2) from a raster boundary is not comparable to
    one measured from a smoothed vector outline.** A staircase boundary is
    longer than the shape it approximates, so these values run low -- a perfect
    raster disc scores well under 1.0. They are comparable *between regions at
    the same scale*, which is what ranking stands by shape needs, and they are
    the right thing to trend across arms that share `analysis_scale_m`. Do not
    quote them against a published vector-derived figure.
    """
    band = safe_get_info(labels.bandNames(), context=f"{context} band name")[0]
    label_image = labels.select([band])

    base_proj = label_image.projection()
    base_scale = safe_get_info(
        base_proj.nominalScale(), context=f"{context} projection scale"
    )
    if base_scale > 10 * scale:
        raise ValueError(
            f"{context}: label image reports a nominal scale of "
            f"{base_scale:.0f} m against an analysis scale of {scale} m -- EE's "
            f"default projection for an unbaked computed image, not a real "
            f"pixel grid. Perimeters measured in it would be meaningless."
        )
    proj = base_proj.atScale(scale)
    pinned = label_image.reproject(proj)

    # Four directions, unlike the adjacency graph's two: a perimeter counts
    # every outward edge of every pixel, so the left and up neighbours are
    # genuinely different edges rather than the same edge seen twice.
    boundary = ee.Image.constant(0)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        neighbour = pinned.translate(x=dx, y=dy, units="pixels", proj=proj)
        # unmask(1): a missing neighbour (ROI edge, masked pixel) is an outward
        # edge too, and dropping it would understate every boundary stand.
        boundary = boundary.add(pinned.neq(neighbour).unmask(1))
    boundary = boundary.updateMask(pinned.mask()).rename("edges")

    grouped = safe_get_info(
        boundary.addBands(pinned.rename(_GROUP_BAND)).reduceRegion(
            reducer=ee.Reducer.sum()
            .combine(ee.Reducer.count(), sharedInputs=True)
            .group(groupField=1, groupName="label"),
            geometry=roi,
            scale=scale,
            # Explicit, not inherited: `boundary` is built up from
            # `ee.Image.constant(0)`, which carries EE's default projection, so
            # the reduction would otherwise count perimeter pixels on a
            # geographic grid while `pinned` was shifted on the label grid.
            crs=proj.crs(),
            maxPixels=1e9,
        ),
        context=f"{context} grouped perimeter",
    ).get("groups")

    px_area = scale * scale
    out: dict[int, dict[str, float]] = {}
    for row in grouped or []:
        n_pixels = int(row.get("count") or 0)
        if not n_pixels:
            continue
        perimeter_m = float(row.get("sum") or 0.0) * scale
        area_m2 = n_pixels * px_area
        out[int(row["label"])] = {
            "n_pixels": n_pixels,
            "area_ha": area_m2 / 10_000.0,
            "perimeter_m": perimeter_m,
            "polsby_popper": (
                4.0 * math.pi * area_m2 / (perimeter_m * perimeter_m)
                if perimeter_m > 0
                else 0.0
            ),
        }
    return out


def summarize_stand_geometry(
    geometry: dict[int, dict[str, float]], *, min_area_ha: float
) -> dict[str, Any]:
    """Distribution summary of what `stand_geometry` measured.

    Reports the concentration statistic explicitly (`area_share_largest_decile`)
    because that is what makes the dissolve-by-cluster pathology legible: 505
    units where 6% held 68% of the area looks unremarkable in a mean or a median
    and is obvious in this one.
    """
    if not geometry:
        return {"n_stands": 0}

    areas = sorted(r["area_ha"] for r in geometry.values())
    pp = sorted(r["polsby_popper"] for r in geometry.values())
    total = sum(areas)

    def q(vals: list[float], p: float) -> float:
        return round(vals[min(len(vals) - 1, int(p * len(vals)))], 6)

    n_decile = max(1, len(areas) // 10)
    largest_decile_area = sum(areas[-n_decile:])
    below = [a for a in areas if a < min_area_ha]

    # Polsby-Popper is 4*pi*A/P^2, which is 1.0 for a circle and strictly below
    # it for every other planar shape -- a value above 1.0 is not a rounder
    # stand, it is arithmetic on an area and a perimeter that do not describe
    # the same footprint. The live baseline reported a max of 1.058.
    #
    # Not clamped. A clamp would put a plausible 1.0 in the output and delete
    # the only evidence that the two measurements disagree; the count is the
    # finding. It is reported rather than raised because the affected stands are
    # at the ROI edge, where reductions are already known to disagree slightly
    # (3595 vs 3594 adjacency pairs between two runs of the same config), and
    # the rest of the distribution is unaffected.
    impossible = [v for v in pp if v > 1.0]

    summary = {
        "n_stands": len(areas),
        "total_area_ha": round(total, 4),
        "area_ha_min": round(areas[0], 6),
        "area_ha_p10": q(areas, 0.10),
        "area_ha_median": q(areas, 0.50),
        "area_ha_p90": q(areas, 0.90),
        "area_ha_max": round(areas[-1], 6),
        "area_ha_mean": round(total / len(areas), 6),
        "stands_below_min_area": len(below),
        "frac_stands_below_min_area": round(len(below) / len(areas), 4),
        "area_in_undersized_stands_ha": round(sum(below), 4),
        # The concentration check. A healthy stand map does not put most of the
        # landscape in a handful of units.
        "area_share_largest_decile": round(largest_decile_area / total, 4)
        if total
        else 0.0,
        # Raster-boundary Polsby-Popper: comparable between stands at the same
        # scale, NOT comparable to a vector-derived figure. See stand_geometry.
        "polsby_popper_min": round(pp[0], 4),
        "polsby_popper_median": q(pp, 0.50),
        "polsby_popper_max": round(pp[-1], 4),
        "polsby_popper_above_one": len(impossible),
    }
    if impossible:
        log.warning(
            "  %d stand(s) report Polsby-Popper above 1.0 (max %.3f), which no "
            "planar shape can reach. Their area and perimeter were measured on "
            "footprints that disagree -- expected at the ROI edge, where the "
            "clip cuts a stand between the pixel count and the boundary count. "
            "Do not quote the compactness of those stands; the rest of the "
            "distribution is unaffected.",
            len(impossible),
            impossible[-1],
        )
    return summary
