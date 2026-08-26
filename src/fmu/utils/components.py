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

from fmu.utils.gee import safe_get_info
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
