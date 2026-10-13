"""Evaluation of a stand map against whatever reference data a site has.

A general, offline package: no Earth Engine, no site-specific code. Every
function takes arrays (stand ids, stand types, plot coordinates, measurements,
optional village and district ids, optional reference polygons, rasters), so
the same code serves any site.

It is organised by what reference data a site has.

Field plots with measurements
    `agreement`
        Rand index and adjusted Rand index between two groupings of the plots.
        Drawing: field type against stand. Labelling: field type against stand
        type, worked out inside each district and pooled.
    `pairs`
        The pair-level comparison. For each pair of plots the map makes one of
        three claims (same stand; different stand but same type; different
        type). The claim is compared with how different the two plots are in
        the field, inside each village and distance band, with every stratum
        reported beside the pooled number.
    `permutation`
        The significance test and the established matrix tests: Mantel and
        partial Mantel, ANOSIM, PERMANOVA; chance by permuting plots, freely
        or inside villages; Holm's correction for several tests.
    `spatial_null`
        Chance that keeps the shape of the map and the layout of the plots and
        breaks only their alignment: the rotation null (each village's plots
        moved rigidly over the map) and the torus translation for gridded
        maps. These produce relabelled plots for `permutation` to test an
        established statistic with. They return no score of their own.

Reference polygons (compartment maps and the like)
    `segmentation_accuracy`
        Over-segmentation, under-segmentation and their combination, per
        reference polygon and summarised; boundary precision, recall and F
        within a distance tolerance.

No reference data
    `unsupervised`
        How alike places are inside a stand compared with across stands, on
        layers the pipeline did not use: explained variance, area-weighted
        variance, Moran's I between adjacent stands, and the Global Score
        built from them.

Checking the methods themselves
    `synthetic`
        Planted stand maps with known answers: does each metric recover the
        planted map, how often does each test raise a false alarm when the map
        is unrelated to the field, and how often does it detect a planted
        effect.

Shared helpers (label codes, robust scaling, pair indexing, distance bands,
the permutation p-value) are in `_common`.

Modules are imported by name, for example
`from fmu.evaluation import agreement`. Nothing is imported here, so the
package imports cleanly whichever of its modules are present.
"""
