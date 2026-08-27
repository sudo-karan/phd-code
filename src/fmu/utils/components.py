"""Guards around `reduceConnectedComponents`.

`ee.Image.reduceConnectedComponents(reducer, labelBand, maxSize)` does not clamp
at `maxSize` -- it **masks any component larger than it**. Those regions vanish
from the output with no error, no warning, and no trace in the manifest. That is
a silent data-loss mode, and it has already bitten this pipeline once: the
embedding config set 256 while the baseline set 1024, so 15 superpixels totalling
43.9 ha (3.8% of segmented area) were deleted in one arm of a two-arm comparison.

`Config.max_component_pixels()` derives the cap from `merge.max_area_ha` instead
of leaving it to be hand-set. This module checks the derivation actually holds
against the labels in hand, because a derived bound is only as good as its
premise -- and the premise (nothing exceeds `max_area_ha`) is exactly what a
merge bug would break.
"""

from __future__ import annotations

import ee

from fmu.utils.gee import LABEL_BAND, safe_get_info
from fmu.utils.logging import get_logger

log = get_logger(__name__)


class ComponentSizeError(RuntimeError):
    """A label image contains a component larger than the derived cap."""


def largest_component_pixels(
    labels: ee.Image, roi: ee.Geometry, scale: int, *, context: str = ""
) -> tuple[int, int]:
    """Return (largest label's pixel count, number of distinct labels).

    Deliberately measured with `frequencyHistogram` rather than
    `reduceConnectedComponents(count)`: the latter would need a `maxSize` of its
    own and so could not see the very components we are checking for. The
    histogram counts every pixel of every label with no cap at all.

    It counts pixels *per label*, not per connected component, so for a label
    appearing in two disjoint patches it returns their sum. That is an upper
    bound on any single component, which is the conservative direction for a
    safety check. (SNIC assigns a unique id per superpixel and the merge only
    joins adjacent regions, so in practice the two coincide.)
    """
    band = safe_get_info(labels.bandNames(), context=f"{context} band names")[0]
    hist = safe_get_info(
        labels.select([band]).reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=roi,
            scale=scale,
            # No bestEffort: a silently downsampled histogram would under-report
            # component sizes, which is the one direction this check must not
            # fail in.
            maxPixels=1e9,
        ),
        context=f"{context} component size histogram",
    ).get(band)

    if not hist:
        return 0, 0
    counts = [int(v) for v in hist.values()]
    return max(counts), len(counts)


def assert_components_fit(
    labels: ee.Image,
    roi: ee.Geometry,
    scale: int,
    max_size: int,
    *,
    context: str,
) -> dict[str, int]:
    """Fail loudly if any component would be masked by `maxSize`.

    Returns the measured stats so callers can put them in the manifest -- the
    headroom is worth recording even when the check passes, since it is the
    early warning that a threshold change is about to start deleting stands.

    Raises:
        ComponentSizeError: some component exceeds `max_size`.
    """
    largest, n_labels = largest_component_pixels(labels, roi, scale, context=context)
    if largest > max_size:
        raise ComponentSizeError(
            f"{context}: largest component is {largest} px but maxSize is "
            f"{max_size} px, so reduceConnectedComponents would silently DROP "
            f"it (and any other component above the cap) from the output. "
            f"maxSize is derived as ceil(merge.max_area_ha * 10000 / scale^2) "
            f"* 1.2, so a component above it means either merge.max_area_ha "
            f"({largest * scale * scale / 10_000:.2f} ha needed here) is being "
            f"violated upstream, or export.analysis_scale_m no longer matches "
            f"the labels."
        )
    log.info(
        "  %s: %d components, largest %d px, maxSize %d px (%.0f%% headroom)",
        context,
        n_labels,
        largest,
        max_size,
        100.0 * (max_size - largest) / max_size if max_size else 0.0,
    )
    return {
        "n_components": n_labels,
        "largest_component_px": largest,
        "max_component_px_cap": max_size,
    }


def explained_variance_r2(
    features: ee.Image,
    labels: ee.Image,
    roi: ee.Geometry,
    scale: int,
    max_size: int,
    *,
    mask: ee.Image | None = None,
    context: str = "explained variance",
) -> dict[str, dict[str, float]]:
    """Per-band R^2 = 1 - SS_within / SS_total over raster cells within regions.

    Xiong et al. 2024 Eq. 4-6, and the field's standard partition-quality
    measure precisely because it needs no ground truth: it asks how much of an
    attribute's variation the partition accounts for, not whether the partition
    matches a reference nobody has.

    **Computed at pixel level, deliberately.** Scoring at region level -- one row
    per region against the region mean -- makes any partition score 1.000 by
    construction, because the region mean *is* the row. The prototype behind
    this design took that shortcut and it is the single easiest way to produce
    a meaningless headline number.

    Two masking details that decide whether the number means anything:

      - SS_total and SS_within must be summed over **exactly the same pixels**,
        so the global mean is computed on the already-masked stack rather than
        on the raw image.
      - a pixel belonging to no region contributes to neither, so the region-mean
        mask drives both.

    Returns `{band: {r2, ss_within, ss_total, n_pixels}}`. Read every value
    alongside the region count: R^2 rises monotonically with it, and in the
    limit of one region per pixel it is 1.0 for any image at all.
    """
    band_names = safe_get_info(features.bandNames(), context=f"{context} bands")
    label_band = LABEL_BAND
    if label_band in band_names:
        raise ValueError(
            f"{context}: a feature band is named {label_band!r}, which collides "
            f"with the label band the region reduction groups by. Rename it."
        )

    region_means = (
        features.addBands(labels.rename(label_band))
        .reduceConnectedComponents(
            reducer=ee.Reducer.mean(), labelBand=label_band, maxSize=max_size
        )
        .select(band_names)
    )

    # One mask for both sums. updateMask with a matching band count applies
    # band-wise, so a band with no data in a region drops out of that band's
    # sums only.
    common = features.updateMask(region_means.mask())
    if mask is not None:
        common = common.updateMask(mask)

    global_means = safe_get_info(
        common.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=scale,
            maxPixels=1e9,
        ),
        context=f"{context} global means",
    )

    parts: list[ee.Image] = []
    for b in band_names:
        gm = global_means.get(b)
        if gm is None:
            continue
        x = common.select(b)
        parts.append(x.subtract(region_means.select(b)).pow(2).rename(f"{b}__within"))
        parts.append(x.subtract(ee.Number(gm)).pow(2).rename(f"{b}__total"))
        parts.append(x.multiply(0).add(1).rename(f"{b}__n"))

    if not parts:
        log.warning("  %s: no band had a defined global mean", context)
        return {}

    sums = safe_get_info(
        ee.Image.cat(parts).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=roi,
            scale=scale,
            maxPixels=1e9,
        ),
        context=f"{context} sums of squares",
    )

    out: dict[str, dict[str, float]] = {}
    for b in band_names:
        ss_total = sums.get(f"{b}__total")
        ss_within = sums.get(f"{b}__within")
        n = sums.get(f"{b}__n")
        if ss_total is None or ss_within is None or not ss_total:
            # A constant attribute has zero total variance, so there is nothing
            # for a partition to explain and R^2 is undefined -- not 1.0, which
            # is what the formula would hand back for 0/0.
            log.warning(
                "  %s: %s has zero total variance over the ROI; R^2 undefined.",
                context,
                b,
            )
            continue
        out[b] = {
            "r2": round(1.0 - float(ss_within) / float(ss_total), 6),
            "ss_within": float(ss_within),
            "ss_total": float(ss_total),
            "n_pixels": int(n or 0),
        }
    return out
