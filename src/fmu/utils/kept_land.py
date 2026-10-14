"""Segmenting on kept land only: the pieces `segmentation.mask_before_snic` needs.

"Kept land" is where the masking stage's `habitat_mask` is 1 (trees or scrub in
the land-cover map), less, with `segmentation.drop_kept_patches_below_min_area`,
the patches too small to be a stand. With `mask_before_snic` off, which is the
default, SNIC and the merge cover the whole ROI and the mask is applied at
clustering only. With it on, SNIC runs on the input stack with every other pixel
masked, so superpixels, and the stands the merge builds from them, lie on kept
land only.

Masking the stack is not enough on its own. SNIC grows each superpixel from a
seed, and its seeds are a regular grid. A superpixel grows through unmasked
pixels only (see below), so a patch of kept land that no grid point falls in, cut off from other kept land by masked pixels, would have no seed and
nothing could grow into it: its pixels would get no superpixel at all. Which
patches that hits would depend on where the grid happens to fall, not on the
land. So the seeds are given explicitly (`seeds_on_kept_land`): the grid, on
kept land, plus every pixel of each kept patch that holds no grid point. The
Earth Engine algorithm reference (bundled with earthengine-api as
`ee/tests/algorithms.json`) says of SNIC's `seeds`: "any non-zero valued pixels
are used as seed locations. Pixels that touch (as specified by 'connectivity')
are considered to belong to the same cluster." So each such patch becomes one
superpixel.

What the seeds cannot reach is measured rather than assumed:
`kept_land_coverage` reports how much kept land is left with no superpixel and
how much superpixel area lies off kept land. The merge stage puts both in
`merge_diagnostics` and warns when either is above zero.

Kept land stops at the ROI (`kept_land_in_roi`). The land-cover mask is read on
the analysis grid and clipped to the ROI with the same `reproject(grid).clip(roi)`
the segmentation stage gives its outputs, before anything else is made from it,
so SNIC's input, its seeds and the small-patch rule start from the same land,
the statistics are taken over it (in the projection of the stack's first band,
as those reductions always were), and the stage's own clip of its outputs takes
nothing away. Without
it, SNIC grew superpixels into a strip of kept land one pixel wide just outside
the ROI, where the cached mask's pixels reach past the ROI edge, and the clip of
the outputs then cut three of them in two on Kendujhar's box
(docs/reproducibility/snic_split_superpixels_kendujhar.json; Jaskaran's decision
of 15 Oct 2026, register entry spec-segmentation-mask-before-snic).

What `scripts/check_snic_on_kept_land.py` found on Earth Engine (14 Oct 2026,
docs/reproducibility/snic_on_kept_land_kendujhar.json, before the clip): SNIC
leaves a masked pixel unlabelled and grew no superpixel across masked land (the
three in two pieces were cut by the ROI edge); touching seed pixels are one
seed; `connectedComponents`' `maxSize` is an extent; and SNIC ignores `size`
once it is given seeds.
"""

from __future__ import annotations

from typing import Any

import ee

from fmu.utils.gee import safe_get_info


def _connectedness(connectivity: int) -> ee.Kernel:
    if connectivity not in (4, 8):
        raise ValueError(f"connectivity must be 4 or 8, got {connectivity}")
    return ee.Kernel.square(1) if connectivity == 8 else ee.Kernel.plus(1)


def kept_land(
    habitat_mask: ee.Image, *, min_patch_pixels: int = 0, connectivity: int = 8
) -> ee.Image:
    """1 on kept land, 0 elsewhere inside `habitat_mask`'s footprint.

    A masked pixel of `habitat_mask` (no land-cover data from either source)
    counts as not kept, as it does at clustering, where `updateMask` drops it.

    `min_patch_pixels` above 1 also leaves out each patch of kept land with fewer
    pixels than that, a patch being kept pixels joined by `connectivity` (8:
    edges and corners; 4: edges only), SNIC's own rule. `connectedPixelCount`
    counts a pixel's patch up to `min_patch_pixels`, so a patch at least that big
    reaches it and a smaller one does not.
    """
    kept = habitat_mask.select([0]).unmask(0).eq(1)
    if min_patch_pixels > 1:
        patch_size = kept.selfMask().connectedPixelCount(
            maxSize=min_patch_pixels, eightConnected=connectivity == 8
        )
        kept = kept.And(patch_size.gte(min_patch_pixels).unmask(0))
    return kept.rename("kept")


def kept_land_in_roi(
    habitat_mask: ee.Image,
    roi: ee.Geometry,
    grid: ee.Projection,
    *,
    min_patch_pixels: int = 0,
    connectivity: int = 8,
) -> ee.Image:
    """Kept land as segmentation.mask_before_snic uses it: inside the ROI only.

    `habitat_mask` is put on `grid` (the analysis grid) and clipped to `roi`, the
    same `reproject(grid).clip(roi)` the segmentation stage gives its outputs, so
    an edge pixel is kept land here exactly where it can carry a label there; then
    `kept_land`, so a small patch is measured on the land inside the ROI.

    Outside the clip the result is 0, not masked (`unmask(0, False)`). An image
    masked with it is then masked there by the documented rule that a 0 in a mask
    image masks; the reference does not say what Earth Engine does with a masked
    pixel of a mask image, and SNIC's input must not depend on it. `unmask` fills
    only where the mask is 0, so the partial masks the clip leaves along the ROI
    edge stay as they are. Reduce it over the ROI only: outside, it is a valid 0,
    which a count or a mean over a larger region would take in.
    """
    kept = kept_land(
        habitat_mask.reproject(grid).clip(roi),
        min_patch_pixels=min_patch_pixels,
        connectivity=connectivity,
    )
    return kept.unmask(0, False)


def seeds_on_kept_land(
    kept: ee.Image, *, size: int, connectivity: int, max_extent: int
) -> ee.Image:
    """SNIC seeds that leave no patch of kept land without one.

    - the square seed grid at `size` pixels, kept where it falls on kept land;
    - every pixel of a patch of kept land that no grid point falls in. A patch
      is a set of kept pixels joined by SNIC's own `connectivity`, so SNIC can
      grow over all of it, and its pixels, all seeds and all touching, are one
      seed to SNIC.

    Patches are found with `connectedComponents`, which leaves out any patch
    larger than `max_extent` (the stage passes SNIC's `neighborhood_size`, the
    margin SNIC adds around each tile, so a patch given seeds here fits inside
    that margin wherever a tile edge cuts it, `maxSize` being an extent, as the
    check found; see the module docstring). A patch too big to be found holds a
    grid point unless it is a long strip narrower than the grid spacing; if one
    exists, `kept_land_coverage` reports its area.

    Returns one 0/1 band, `seeds`, for SNIC's `seeds` argument.
    """
    connectedness = _connectedness(connectivity)
    on_grid = (
        ee.Algorithms.Image.Segmentation.seedGrid(size)
        .unmask(0)
        .gt(0)
        .And(kept)
        .rename("seeds")
    )
    patches = (
        kept.selfMask()
        .connectedComponents(connectedness, max_extent)
        .select("labels")
    )
    # Per patch: 1 if a grid point falls in it, 0 if none. Masked off kept land,
    # and where the patch was too big for connectedComponents, which then adds no
    # seed there.
    holds_grid_point = on_grid.addBands(patches).reduceConnectedComponents(
        ee.Reducer.max(), "labels", max_extent
    )
    without_grid_point = holds_grid_point.eq(0).unmask(0)
    return on_grid.Or(without_grid_point).rename("seeds")


def kept_land_coverage(
    labels: ee.Image,
    habitat_mask: ee.Image,
    roi: ee.Geometry,
    scale: int,
    *,
    min_patch_pixels: int,
    connectivity: int,
    context: str,
) -> dict[str, float]:
    """How the superpixels cover kept land, in hectares. One Earth Engine call.

    `labels` is the superpixel label image. Kept land is made from
    `habitat_mask` exactly as segmentation makes it (`kept_land_in_roi`, on the
    label image's grid, with the same `min_patch_pixels` and `connectivity`).
    Counted on the label image's own pixels: the reduction runs in its
    projection, transform included, so a cached label image is not resampled
    onto another grid. Areas are pixel counts x scale^2, as the merge counts its
    areas.
    """
    grid = labels.projection()
    all_kept = kept_land_in_roi(habitat_mask, roi, grid)
    kept = kept_land_in_roi(
        habitat_mask, roi, grid, min_patch_pixels=min_patch_pixels, connectivity=connectivity
    )
    labelled = labels.select([0]).mask().gt(0)
    stack = ee.Image.cat(
        [
            kept.rename("kept"),
            kept.And(labelled.Not()).rename("kept_unlabelled"),
            labelled.And(kept.Not()).rename("labelled_not_kept"),
            all_kept.And(kept.Not()).rename("small_patches"),
        ]
    )
    sums = safe_get_info(
        stack.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=roi,
            crs=labels.projection(),
            maxPixels=1e9,
        ),
        context=f"{context}: kept land and superpixels",
    )
    return tabulate_kept_land_coverage(sums, scale)


def tabulate_kept_land_coverage(sums: dict[str, Any], scale: int) -> dict[str, float]:
    """Turn the pixel sums of `kept_land_coverage` into hectares. Pure Python."""
    ha_per_pixel = scale * scale / 10_000.0

    def ha(key: str) -> float:
        return round(float(sums.get(key) or 0.0) * ha_per_pixel, 4)

    return {
        "kept_land_ha": ha("kept"),
        "small_patches_ha": ha("small_patches"),
        "kept_land_ha_without_superpixel": ha("kept_unlabelled"),
        "superpixel_ha_off_kept_land": ha("labelled_not_kept"),
    }
