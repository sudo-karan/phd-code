"""Optical features stage. Harmonic regression on a vegetation index
(NDVI or NIRv) over the S2 phenology window. Produces per-pixel phenology
metrics as a single multi-band ee.Image.

The regression model, per pixel, is:

    y(t) = a + b·cos(2π·t) + c·sin(2π·t)
         + [d·cos(4π·t) + e·sin(4π·t)]   # if harmonic_mode == "dual"
         + [f·t]                          # if include_trend
         + ε

where t is years since 2017-01-01.

Derived metrics (per DEC-002 — derived metrics, not raw coefficients):
- mean = a
- amplitude_annual = sqrt(b² + c²)
- phase_annual = atan2(c, b)        # radians
- amplitude_semi = sqrt(d² + e²)    # dual only
- phase_semi = atan2(e, d)          # dual only
- trend = f                          # if include_trend
- residual_variance = RMS of regression residuals
- obs_count = number of valid S2 observations per pixel

Features are computed over the full ROI; the habitat_mask is applied at
clustering (DEC-014). Output cacheable as a single multi-band asset.
"""

from __future__ import annotations

import math

import ee

from fmu.config import Config
from fmu.stages.base import PipelineContext, Stage, StageResult, register_stage
from fmu.utils.gee import safe_call, safe_get_info
from fmu.utils.logging import get_logger

log = get_logger(__name__)


# Reference date for the time variable t (years since this date).
# Arbitrary choice — shifts phase by a constant, which doesn't affect clustering.
_TIME_REFERENCE = "2017-01-01"


@register_stage("features_optical")
class FeaturesOpticalStage(Stage):
    name = "features_optical"
    required_inputs = {"s2_collection", "roi"}
    produces = {"optical_features"}
    cacheable_outputs = {"optical_features"}

    @safe_call("computing optical phenology features")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        s2: ee.ImageCollection = ctx.get("s2_collection")
        params = config.features_optical
        prefix = params.index  # "ndvi" or "nirv"

        # 1. Add the vegetation index as 'y' band
        with_index = s2.map(lambda img: _add_index(img, params.index))

        # 2. Add regression bands (constant, harmonics, trend)
        regression_band_names = _build_regression_band_names(
            params.harmonic_mode, params.include_trend
        )
        with_regression = with_index.map(
            lambda img: _add_regression_bands(img, params.harmonic_mode, params.include_trend)
        )

        # 3. Fit per-pixel linear regression
        num_x = len(regression_band_names)
        regression_input = with_regression.select(regression_band_names + ["y"])
        regression_result = regression_input.reduce(
            ee.Reducer.linearRegression(numX=num_x, numY=1)
        )

        # 4. Extract individual coefficients from the 2-D coefficients array
        coefficients = (
            regression_result.select("coefficients")
            .arrayProject([0])
            .arrayFlatten([regression_band_names])
        )

        # 5. Build the derived-metrics multi-band image
        output_bands = _derive_metrics(
            coefficients=coefficients,
            residuals_image=regression_result.select("residuals"),
            obs_count_image=with_index.select("y").count(),
            prefix=prefix,
            harmonic_mode=params.harmonic_mode,
            include_trend=params.include_trend,
        )

        # 6. Concatenate, clip to ROI for cleanliness
        optical_features = ee.Image.cat(output_bands).clip(ctx.get("roi"))

        # Diagnostic — log the output band names
        band_names = safe_get_info(
            optical_features.bandNames(), context="optical_features band names"
        )
        log.info("  optical_features bands (%d): %s", len(band_names), band_names)

        return StageResult(
            outputs={"optical_features": optical_features},
            metadata={
                "index": params.index,
                "harmonic_mode": params.harmonic_mode,
                "include_trend": params.include_trend,
                "num_regression_terms": num_x,
                "output_bands": band_names,
            },
        )


# ---------------------------------------------------------------------
# Per-image helpers (mapped over the S2 collection)
# ---------------------------------------------------------------------


def _add_index(img: ee.Image, index_name: str) -> ee.Image:
    """Compute NDVI or NIRv from a Sentinel-2 image; add as band 'y'.

    Note on NIRv units: per Badgley et al. (2017), NIRv = NDVI × NIR_reflectance,
    where NIR_reflectance is the actual reflectance (0 to 1). Sentinel-2 SR
    stores reflectance as integers scaled by 10000, so we divide back before
    multiplying. This makes NIRv ∈ [0, 1] like NDVI, not scaled-up values.
    """
    nir_stored = img.select("B8")
    red_stored = img.select("B4")
    ndvi = nir_stored.subtract(red_stored).divide(nir_stored.add(red_stored))
    if index_name == "nirv":
        nir_reflectance = nir_stored.divide(10000)
        y = nir_reflectance.multiply(ndvi).rename("y")
    else:
        y = ndvi.rename("y")
    return img.addBands(y)


def _add_regression_bands(
    img: ee.Image, harmonic_mode: str, include_trend: bool
) -> ee.Image:
    """Add the regression independent-variable bands to an image:
    constant, cos_annual, sin_annual, [cos_semi, sin_semi], [t].
    """
    date = ee.Date(img.get("system:time_start"))
    years = date.difference(ee.Date(_TIME_REFERENCE), "year")

    t_band = ee.Image.constant(years).float().rename("t")
    constant_band = ee.Image.constant(1).float().rename("constant")
    cos_annual = t_band.multiply(2 * math.pi).cos().rename("cos_annual")
    sin_annual = t_band.multiply(2 * math.pi).sin().rename("sin_annual")
    bands_to_add = [constant_band, cos_annual, sin_annual]

    if harmonic_mode == "dual":
        cos_semi = t_band.multiply(4 * math.pi).cos().rename("cos_semi")
        sin_semi = t_band.multiply(4 * math.pi).sin().rename("sin_semi")
        bands_to_add.extend([cos_semi, sin_semi])

    if include_trend:
        bands_to_add.append(t_band)

    return img.addBands(ee.Image.cat(bands_to_add))


# ---------------------------------------------------------------------
# Server-side helpers (operate on the regression result)
# ---------------------------------------------------------------------


def _build_regression_band_names(harmonic_mode: str, include_trend: bool) -> list[str]:
    """Names of the X bands fed into ee.Reducer.linearRegression, in order."""
    names = ["constant", "cos_annual", "sin_annual"]
    if harmonic_mode == "dual":
        names.extend(["cos_semi", "sin_semi"])
    if include_trend:
        names.append("t")
    return names


def _derive_metrics(
    *,
    coefficients: ee.Image,
    residuals_image: ee.Image,
    obs_count_image: ee.Image,
    prefix: str,
    harmonic_mode: str,
    include_trend: bool,
) -> list[ee.Image]:
    """Convert raw coefficients into the named per-pixel feature bands."""
    bands: list[ee.Image] = []

    # Mean = intercept (constant term)
    mean = coefficients.select("constant").rename(f"{prefix}_mean")
    bands.append(mean)

    # Annual harmonic → amplitude + phase
    b = coefficients.select("cos_annual")
    c = coefficients.select("sin_annual")
    amp_annual = b.hypot(c).rename(f"{prefix}_amplitude_annual")
    phase_annual = c.atan2(b).rename(f"{prefix}_phase_annual")
    bands.extend([amp_annual, phase_annual])

    # Semi-annual harmonic → amplitude + phase (if dual)
    if harmonic_mode == "dual":
        d = coefficients.select("cos_semi")
        e = coefficients.select("sin_semi")
        amp_semi = d.hypot(e).rename(f"{prefix}_amplitude_semi")
        phase_semi = e.atan2(d).rename(f"{prefix}_phase_semi")
        bands.extend([amp_semi, phase_semi])

    # Trend coefficient (per-year change)
    if include_trend:
        trend = coefficients.select("t").rename(f"{prefix}_trend")
        bands.append(trend)

    # Residual variance — diagnostic for how well-fit each pixel is by the harmonic
    residual_variance = residuals_image.arrayFlatten([["residuals"]]).rename(
        f"{prefix}_residual_variance"
    )
    bands.append(residual_variance)

    # Observation count — metadata for downstream confidence weighting
    obs_count = obs_count_image.toInt32().rename(f"{prefix}_obs_count")
    bands.append(obs_count)

    return bands
