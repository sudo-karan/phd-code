"""Embedding features stage. A single pretrained per-pixel embedding image,
used in place of the hand-crafted feature stack when
`clustering.feature_source == "embedding"`.

The field has moved from hand-engineering multi-sensor feature stacks toward
clustering pretrained per-pixel embeddings. This stage supplies that arm:

  - AlphaEarth Satellite Embedding (GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL): a
    64-band annual ImageCollection (one image per year, bands A00..A63). It is
    collapsed to one image over the feature window (mean by default), matching
    the 2017-2022 averaging the hand-crafted arm rests on. Google's own
    documentation recommends grouping these embeddings with unsupervised
    clustering, which is exactly what the clustering stage does.
  - Tessera (or any other pretrained embedding): once uploaded to Earth Engine
    as a single Image, it is loaded as-is (no collapse). Point
    `datasets.embedding` at the uploaded asset id.

The stage is source-agnostic: it inspects the asset type and either collapses a
collection or loads a single image. Output is one multi-band image on the
`embedding_features` context key, cacheable like every other feature image.

The whole point of the experiment is comparability, so the embedding image is
NOT masked or otherwise altered here — segmentation is held fixed, only the
clustering feature vector changes.
"""

from __future__ import annotations

import ee

from fmu.config import Config
from fmu.stages.base import PipelineContext, Stage, StageResult, register_stage
from fmu.utils.gee import safe_call, safe_get_info
from fmu.utils.logging import get_logger

log = get_logger(__name__)


@register_stage("features_embedding")
class FeaturesEmbeddingStage(Stage):
    name = "features_embedding"
    required_inputs = {"roi"}
    produces = {"embedding_features"}
    cacheable_outputs = {"embedding_features"}

    @safe_call("computing embedding features")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        roi = ctx.get("roi")
        params = config.features_embedding
        asset = config.datasets.embedding
        # Reuse the unified 2017-2022 time-series window (the same support the
        # hand-crafted features rest on) to collapse the annual embeddings.
        window = config.dates.phenology

        # Determine the asset type so we can handle a single uploaded image
        # (Tessera) and an annual collection (AlphaEarth) with one code path.
        # Same tolerant getAsset pattern as the masking stage.
        try:
            asset_type = ee.data.getAsset(asset).get("type")
        except Exception:  # noqa: BLE001 - fall through to the collection path
            asset_type = None

        if asset_type == "IMAGE":
            # Single uploaded embedding (Tessera): load as-is, no collapse.
            embedding = ee.Image(asset)
            collapse_note = "single image (loaded as-is)"
            n_images = 1
        else:
            # Annual ImageCollection (AlphaEarth) or unknown: filter to the
            # feature window and collapse to one image. advance(1, "day") makes
            # the end date inclusive (filterDate's upper bound is exclusive).
            end_exclusive = ee.Date(str(window.end)).advance(1, "day")
            ic = (
                ee.ImageCollection(asset)
                .filterBounds(roi)
                .filterDate(str(window.start), end_exclusive)
            )
            n_images = safe_get_info(ic.size(), context="embedding collection size")
            if not n_images:
                raise ee.EEException(
                    f"No embedding images found in {asset!r} over "
                    f"[{window.start}, {window.end}] intersecting the ROI. "
                    "Check datasets.embedding and the dates.phenology window."
                )
            embedding = ic.mean() if params.collapse_reducer == "mean" else ic.median()
            collapse_note = f"{params.collapse_reducer} over {n_images} annual image(s)"

        # Optional band restriction (default: keep every embedding dimension).
        if params.band_names is not None:
            embedding = embedding.select(params.band_names)

        embedding_features = embedding.clip(roi)

        band_names = safe_get_info(
            embedding_features.bandNames(), context="embedding_features band names"
        )
        log.info(
            "  embedding_features: %d bands from %s (%s)",
            len(band_names),
            asset,
            collapse_note,
        )

        return StageResult(
            outputs={"embedding_features": embedding_features},
            metadata={
                "embedding_dataset": asset,
                "source_type": asset_type or "unknown->collection",
                "collapse": collapse_note,
                "collapse_reducer": params.collapse_reducer,
                "window": [str(window.start), str(window.end)],
                "n_source_images": n_images,
                "n_bands": len(band_names),
                "output_bands": band_names,
            },
        )
