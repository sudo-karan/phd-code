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
    `torus_shift`
        The torus-shift test for plots that form one contiguous grid (a
        stem-mapped plot cut into quadrats): the stand map moved over the
        fixed field grid by every whole quadrat, every shift enumerated. A
        test, not a metric: it returns the caller's statistic on every map.

Reference polygons (compartment maps and the like)
    `segmentation_accuracy`
        Over-segmentation, under-segmentation and their combination, per
        reference polygon and summarised; boundary precision, recall and F
        within a distance tolerance.
    `stand_overlap`
        Overlap of the stand map with reference stands as two delineation
        papers measure it: OLO, OLU and their mean, each reference stand
        matched to the stand it overlaps most; and the IoU of each stand with
        its reference, with the shares over 0.5 and 0.7.

A reference height raster (a lidar canopy height model)
    `reference_height`
        The share of the raster's variation that lies between stands,
        R2 = 1 - SS_within / SS_total, pixel-weighted, reported with the share
        of height pixels in no stand; `stand_raster` puts the stand polygons
        on the raster's grid by pixel centre.

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

Sources
    The docstrings of this package name papers by author and year. Their DOIs,
    whether each DOI was checked against Crossref, how much of each paper was
    read and what it supports are in the references tables of
    `docs/evaluation_metrics.md` ("Cited", and "Considered and not cited" for
    Moran 1950, which is named in `unsupervised` only as the origin of
    Moran's I). Two of the papers named here are UNVERIFIED: Mantel (1967),
    for which no DOI is registered, and Holm (1979), for which no Crossref
    record was found. The three modules added in round 9 (`reference_height`,
    `stand_overlap`, `torus_shift`) give the DOI, the Crossref check and what
    each paper supports in their own docstrings (Harms et al. 2001, Xiong et
    al. 2024, Vatandaslar et al. 2025). Listed here since 20 Oct 2026 (review
    C24); before, this description named the original seven modules only.

Modules are imported by name, for example
`from fmu.evaluation import agreement`. Nothing is imported here, so the
package imports cleanly whichever of its modules are present.
"""
