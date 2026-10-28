"""Optical features stage. Harmonic regression on a vegetation index
(NDVI or NIRv) over the S2 phenology window. Produces per-pixel phenology
metrics as a single multi-band ee.Image.

The regression model, per pixel, is:

    y(t) = a + b·cos(2π·t) + c·sin(2π·t)
         + [d·cos(4π·t) + e·sin(4π·t)]   # if harmonic_mode == "dual"
         + [f·t]                          # if include_trend
         + ε

where t is years since `features_optical.time_reference` (default
2017-01-01; configurable per DEC-???). Moving the reference by D years
leaves amplitude, trend and the residual variance as they are and shifts
`phase_*` by the same angle at every pixel. With `include_trend` on (every
shipped config) it also changes `mean` by trend x D, by a different amount
at each pixel, because `mean` is the intercept a: the value of the
de-seasonalised trend line a + f·t on `time_reference`, not the average over
the window (with the 2017-2022 window and the default reference, the window's
average of the fitted curve is about a + 3f). `mean` is a clustering band,
and each sin and cos of a phase is scaled by its own spread (review A2,
B13), so the reference date can change the clustering. Corrected in round
13 (review C9), in this text only; what the stage computes is unchanged.

With `features_optical.mean_over_window` on (round 14; review C9, round 13's
question 31, answered (c)), `mean` is instead the fitted curve's mean over the
dates window [dates.phenology.start, dates.phenology.end + 1 day), computed
analytically (`window_mean_weights`): a weighted sum of the coefficients, the
same whatever `time_reference` is. For a window of a whole number of years it is
a + f x the window's middle; the 2017-2022 window is 5.9988 of Earth Engine's
years (of 365.2425 days), so its harmonic terms are not quite zero, at most
about 2e-4 times the amplitude. Off, nothing changes.

Derived metrics (per DEC-002; derived metrics, not raw coefficients):
- mean = a                           # the trend line's value on time_reference
                                     # (the window mean with mean_over_window on)
- amplitude_annual = sqrt(b² + c²)
- phase_annual = atan2(c, b)        # radians, measured from time_reference
- amplitude_semi = sqrt(d² + e²)    # dual only
- phase_semi = atan2(e, d)          # dual only
- trend = f                          # if include_trend
- residual_variance = var(residuals) (square of the regression RMS residual)
- obs_count = number of valid S2 observations per pixel

Features are computed over the full ROI; the habitat_mask is applied at
clustering (DEC-014). Output cacheable as a single multi-band asset.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

import ee

from fmu.config import Config
from fmu.stages.base import (
    DisplayLayer,
    PipelineContext,
    Stage,
    StageResult,
    register_stage,
)
from fmu.utils.gee import safe_call, safe_get_info
from fmu.utils.logging import get_logger

log = get_logger(__name__)


@register_stage("features_optical")
class FeaturesOpticalStage(Stage):
    name = "features_optical"
    required_inputs = {"s2_collection", "roi"}
    produces = {"optical_features"}
    cacheable_outputs = {"optical_features"}

    # Transparency: one band, the one segmentation and the merge read by
    # default, not all seven. A declaration is static and the band name is
    # not: it carries the index prefix. `ndvi` is the default and the name
    # declared; under `index: nirv` the band is `nirv_amplitude_annual` and
    # this layer names a band the run does not have. tests/
    # test_transparency_contract.py lists the one config under configs/ on
    # NIRv and fails for any other.
    #
    # Stretch 0 to 0.4. Zero is exact: the amplitude is sqrt(b^2 + c^2). The
    # upper end is a starting value: the stand means of the 14 runs of 13 Oct
    # 2026 lie between 0.01 and 0.26 (the colour scales of the early ui_data
    # build of that day, scripts/build_ui_early_data.py), and pixels reach
    # further than the means of their stands. The palette is the one that
    # build drew this band in.
    display_layers = (
        DisplayLayer(
            key="optical_features",
            band="ndvi_amplitude_annual",
            title="Seasonal swing in greenness (NDVI annual amplitude)",
            description=(
                "How far greenness rises and falls over a year: the amplitude "
                "of the annual cycle fitted to every cloud-free Sentinel-2 "
                "NDVI observation in the phenology window. It has no unit. "
                "Low values are vegetation that stays the same all year "
                "(evergreen cover, or bare ground); high values are vegetation "
                "that greens up and dries out (deciduous trees, grass, crops). "
                "It is one of the bands the superpixels are drawn on by "
                "default and one of the two the merge compares by default; a "
                "config can name other merge criteria. The band name "
                "is that of the default NDVI index; a config on the NIRv index "
                "writes nirv_amplitude_annual in its place."
            ),
            vis={
                "min": 0,
                "max": 0.4,
                "palette": ["fff7ec", "fdd49e", "fc8d59", "d7301f", "7f0000"],
            },
        ),
    )

    def input_collections(self, ctx: PipelineContext, config: Config) -> dict[str, Any]:
        """The cloud-masked Sentinel-2 collection the harmonic fit reads (data_load's)."""
        return {"s2_phenology": ctx.get("s2_collection")}

    @safe_call("computing optical phenology features")
    def run(self, ctx: PipelineContext, config: Config) -> StageResult:
        s2: ee.ImageCollection = ctx.get("s2_collection")
        params = config.features_optical
        prefix = params.index  # "ndvi" or "nirv"
        time_reference = params.time_reference  # datetime.date

        # 1. Add the vegetation index as 'y' band
        with_index = s2.map(lambda img: _add_index(img, params.index))

        # 2. Add regression bands (constant, harmonics, trend)
        regression_band_names = _build_regression_band_names(
            params.harmonic_mode, params.include_trend
        )
        with_regression = with_index.map(
            lambda img: _add_regression_bands(
                img, params.harmonic_mode, params.include_trend, time_reference
            )
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

        # With features_optical.mean_over_window on (round 14): the weights that make the
        # mean band the fitted curve's mean over the dates window, the window data_load
        # filtered the collection by (its key covers dates.phenology, upstream of this one).
        mean_weights: dict[str, float] | None = None
        if params.mean_over_window:
            window = config.dates.phenology
            t0, t1 = window_years(window.start, window.end, time_reference)
            mean_weights = window_mean_weights(
                t0, t1, harmonic_mode=params.harmonic_mode, include_trend=params.include_trend
            )

        # 5. Build the derived-metrics multi-band image
        output_bands = _derive_metrics(
            coefficients=coefficients,
            residuals_image=regression_result.select("residuals"),
            obs_count_image=with_index.select("y").count(),
            prefix=prefix,
            harmonic_mode=params.harmonic_mode,
            include_trend=params.include_trend,
            mean_weights=mean_weights,
        )

        # 6. Concatenate, clip to ROI for cleanliness
        optical_features = ee.Image.cat(output_bands).clip(ctx.get("roi"))

        # Diagnostic; log the output band names
        band_names = safe_get_info(
            optical_features.bandNames(), context="optical_features band names"
        )
        log.info("  optical_features bands (%d): %s", len(band_names), band_names)
        log.info("  time_reference: %s", time_reference.isoformat())

        return StageResult(
            outputs={"optical_features": optical_features},
            metadata={
                "index": params.index,
                "harmonic_mode": params.harmonic_mode,
                "include_trend": params.include_trend,
                "time_reference": time_reference.isoformat(),
                "num_regression_terms": num_x,
                "output_bands": band_names,
                # On every run, on or off; the window and the weights only when on.
                "mean_over_window": params.mean_over_window,
                **(
                    {
                        "mean_window": (
                            f"{config.dates.phenology.start.isoformat()} to "
                            f"{config.dates.phenology.end.isoformat()}"
                        ),
                        "mean_weights": mean_weights,
                    }
                    if mean_weights is not None
                    else {}
                ),
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
    img: ee.Image,
    harmonic_mode: str,
    include_trend: bool,
    time_reference: date,
) -> ee.Image:
    """Add the regression independent-variable bands to an image:
    constant, cos_annual, sin_annual, [cos_semi, sin_semi], [t].

    `time_reference` is the date used as t=0. Cross-config phase
    comparability requires all configs use the same reference; see
    `FeaturesOpticalParams.time_reference` in config.py for the
    rationale.
    """
    image_date = ee.Date(img.get("system:time_start"))
    years = image_date.difference(ee.Date(time_reference.isoformat()), "year")

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
# The window mean (round 14): pure Python
# ---------------------------------------------------------------------

# Earth Engine's "year" in ee.Date.difference, the unit of the regression's t: the average
# Gregorian year, 365.2425 days. Read on Earth Engine on 26 Oct 2026 (read-only): from
# 2017-01-01 to 2023-01-01 is 5.99875425231182 years, 2017 to 2018 is 0.9993360575508052,
# 2020 to 2021 is 1.0020739645577939.
DAYS_PER_YEAR = 365.2425


def years_since(day: date, reference: date) -> float:
    """t of a date's start (UTC midnight): years since `reference`, as ee.Date.difference gives them."""
    return (day - reference).days / DAYS_PER_YEAR


def window_years(start: date, end: date, reference: date) -> tuple[float, float]:
    """The dates window [start, end + 1 day) in t: data_load includes the end date (review A4)."""
    return years_since(start, reference), years_since(end + timedelta(days=1), reference)


def window_mean_weights(
    t0: float, t1: float, *, harmonic_mode: str, include_trend: bool
) -> dict[str, float]:
    """The fitted curve's mean over [t0, t1], as weights on the regression's coefficients.

    The mean of a + b cos(wt) + c sin(wt) [+ d cos(2wt) + e sin(2wt)] [+ f t] over the window,
    w = 2 pi, T = t1 - t0, is a + b (sin w t1 - sin w t0) / (wT) + c (cos w t0 - cos w t1) / (wT)
    [+ d (sin 2w t1 - sin 2w t0) / (2wT) + e (cos 2w t0 - cos 2w t1) / (2wT)] [+ f (t0 + t1) / 2]:
    the integral over the window divided by its length. Keyed by the regression bands
    (_build_regression_band_names), the constant first, with weight 1. For a whole number of
    years the harmonic weights are 0 and the mean is a + f x the window's middle.
    """
    span = t1 - t0
    if span <= 0:
        raise ValueError(f"window mean: the window [{t0}, {t1}] is empty")
    w = 2 * math.pi
    weights = {
        "constant": 1.0,
        "cos_annual": (math.sin(w * t1) - math.sin(w * t0)) / (w * span),
        "sin_annual": (math.cos(w * t0) - math.cos(w * t1)) / (w * span),
    }
    if harmonic_mode == "dual":
        weights["cos_semi"] = (math.sin(2 * w * t1) - math.sin(2 * w * t0)) / (2 * w * span)
        weights["sin_semi"] = (math.cos(2 * w * t0) - math.cos(2 * w * t1)) / (2 * w * span)
    if include_trend:
        weights["t"] = (t0 + t1) / 2
    return weights


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
    mean_weights: dict[str, float] | None = None,
) -> list[ee.Image]:
    """Convert raw coefficients into the named per-pixel feature bands."""
    bands: list[ee.Image] = []

    # Mean = intercept (constant term). With the trend term in the fit this is
    # the trend line's value on time_reference (t = 0), not the window's
    # average (review C9; the name is kept). With mean_over_window on (round 14),
    # the window's average: the coefficients weighted by window_mean_weights.
    if mean_weights is None:
        mean = coefficients.select("constant").rename(f"{prefix}_mean")
    else:
        total = coefficients.select("constant")
        for name, weight in mean_weights.items():
            if name != "constant":
                total = total.add(coefficients.select(name).multiply(weight))
        mean = total.rename(f"{prefix}_mean")
    bands.append(mean)

    # Annual harmonic to amplitude + phase
    b = coefficients.select("cos_annual")
    c = coefficients.select("sin_annual")
    amp_annual = b.hypot(c).rename(f"{prefix}_amplitude_annual")
    phase_annual = c.atan2(b).rename(f"{prefix}_phase_annual")
    bands.extend([amp_annual, phase_annual])

    # Semi-annual harmonic to amplitude + phase (if dual)
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

    # Residual variance; diagnostic for how well-fit each pixel is by the harmonic.
    # ee.Reducer.linearRegression emits the ROOT-mean-square of the residuals;
    # square it to get var(residuals) (the mean residual is ~0 given the constant
    # term), matching the deck's definition residual_variance = var(residuals).
    residual_variance = (
        residuals_image.arrayFlatten([["residuals"]])
        .pow(2)
        .rename(f"{prefix}_residual_variance")
    )
    bands.append(residual_variance)

    # Observation count; metadata for downstream confidence weighting
    obs_count = obs_count_image.toInt32().rename(f"{prefix}_obs_count")
    bands.append(obs_count)

    return bands
