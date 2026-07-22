"""Generate a mentor-facing report from a finished fmu run.

Reads the artifacts a pipeline run leaves behind — `cluster_profiles.csv`,
`export_manifest_<config>.json`, `metrics_<config>.json`, and the exported
`stands_dissolved` / `stands_snic` vectors — and produces:

  - a set of PNG figures (stand map, cluster fingerprint, feature separating
    power, cluster composition, phenology curves, sensor signatures), and
  - a single self-contained HTML dashboard that embeds them.

Everything is derived from the committed outputs; no Earth Engine access is
needed. Single-config by default; pass --reference to add a baseline-vs-variant
comparison (confusion matrix + agreement metrics).

Usage:
    # single-config report
    python scripts/report.py --config sanjay_van_baseline
    # 2-way comparison (variant vs baseline)
    python scripts/report.py --config sanjay_van_nirv_dual \
        --reference sanjay_van_baseline
    # N-way comparison (baseline vs several versions, side by side)
    python scripts/report.py --multi --reference sanjay_van_baseline \
        --configs sanjay_van_alphaearth sanjay_van_tessera
"""

from __future__ import annotations

import argparse
import base64
import glob
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch
from shapely.geometry import shape

# --------------------------------------------------------------------------
# Palette (dataviz reference instance, light surface). Validated with
# scripts/validate_palette.js — worst adjacent CVD ΔE 9.1, normal-vision 19.6;
# the three sub-3:1 hues are always shipped with a legend + direct labels.
# --------------------------------------------------------------------------
CLUSTER_COLORS = ["#2a78d6", "#008300", "#e87ba4", "#eda100", "#1baf7a", "#eb6834"]
SURFACE = "#fcfcfb"
PLANE = "#f9f9f7"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
# Diverging (blue<->red) for the z-scored fingerprint; gray midpoint.
DIVERGE = matplotlib.colors.LinearSegmentedColormap.from_list(
    "fmu_div", ["#184f95", "#5598e7", "#f0efec", "#eb6834", "#b3311a"]
)
# Sequential blue for magnitude (separating power, confusion).
SEQ = matplotlib.colors.LinearSegmentedColormap.from_list(
    "fmu_seq", ["#eef4fc", "#86b6ef", "#2a78d6", "#104281"]
)


def _style() -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Arial", "sans-serif"],
        "font.size": 11,
        "text.color": INK,
        "axes.labelcolor": INK2,
        "axes.edgecolor": AXIS,
        "axes.titlecolor": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.titlesize": 14,
    })


def cluster_color(cid: int) -> str:
    return CLUSTER_COLORS[int(cid) % len(CLUSTER_COLORS)]


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

# Feature bands that are computed but NOT clustered (deck: diagnostics only).
_DIAGNOSTIC = {"annual_rainfall", "ndvi_residual_variance", "nirv_residual_variance"}

# Human-readable labels; unmatched bands fall back to the raw name.
_LABELS = {
    "ndvi_mean": "NDVI level", "nirv_mean": "NIRv level",
    "ndvi_amplitude_annual": "Seasonal amplitude", "nirv_amplitude_annual": "Seasonal amplitude",
    "ndvi_amplitude_semi": "Semi-annual amplitude", "nirv_amplitude_semi": "Semi-annual amplitude",
    "ndvi_trend": "Greening trend", "nirv_trend": "Greening trend",
    "ndvi_phase_annual_sin": "Phase (sin)", "nirv_phase_annual_sin": "Phase (sin)",
    "ndvi_phase_annual_cos": "Phase (cos)", "nirv_phase_annual_cos": "Phase (cos)",
    "ndvi_phase_semi_sin": "Semi phase (sin)", "nirv_phase_semi_sin": "Semi phase (sin)",
    "ndvi_phase_semi_cos": "Semi phase (cos)", "nirv_phase_semi_cos": "Semi phase (cos)",
    "canopy_height": "Canopy height", "canopy_height_std": "Canopy roughness",
    "canopy_height_max": "Canopy max (3x3)",
    "elevation": "Elevation", "slope": "Slope",
    "aspect_sin": "Aspect (sin)", "aspect_cos": "Aspect (cos)",
    "distance_to_water": "Distance to water",
    "vv_p10": "VV p10", "vv_p50": "VV median", "vv_p90": "VV p90",
    "vh_p10": "VH p10", "vh_p50": "VH median", "vh_p90": "VH p90",
    "vv_iqr": "VV spread", "vh_iqr": "VH spread",
    "vv_minus_vh_median": "Cross-pol (VV-VH)",
}


def label(band: str) -> str:
    return _LABELS.get(band, band.replace("_", " "))


@dataclass
class ConfigRun:
    name: str
    profiles: pd.DataFrame          # one row per cluster, *_mean/_p25/_p50/_p75
    dist: pd.DataFrame              # cluster_id, area_ha, percent_of_habitat, pixel_count
    manifest: dict[str, Any]
    metrics: dict[str, Any]
    dissolved_path: Path | None
    snic_path: Path | None
    index: str                      # "ndvi" or "nirv"
    clustered_bands: list[str]      # feature bands that fed k-means
    feature_source: str = "handcrafted"  # "handcrafted" or "embedding"

    @property
    def k(self) -> int:
        return len(self.profiles)


def _first(paths: list[str]) -> Path | None:
    return Path(sorted(paths)[-1]) if paths else None


def discover(config: str, runs_root: Path, vectors_dir: Path) -> ConfigRun:
    prof_p = _first(glob.glob(str(runs_root / f"{config}_*" / "cluster_profiles.csv")))
    man_p = _first(glob.glob(str(runs_root / f"{config}_*" / f"export_manifest_{config}.json")))
    met_p = _first(glob.glob(str(runs_root / f"{config}_*" / f"metrics_{config}.json")))
    if prof_p is None:
        raise SystemExit(f"No cluster_profiles.csv found under {runs_root}/{config}_*/")

    profiles = pd.read_csv(prof_p).sort_values("cluster_id").reset_index(drop=True)
    manifest = json.loads(man_p.read_text()) if man_p else {}
    metrics = json.loads(met_p.read_text()) if met_p else {}

    dist_rows = manifest.get("clustering", {}).get("cluster_distribution")
    if dist_rows:
        dist = pd.DataFrame(dist_rows).sort_values("cluster_id").reset_index(drop=True)
    else:  # fall back to the profiles' own pixel_count/area_ha
        dist = profiles[["cluster_id", "pixel_count", "area_ha"]].copy()
        total = dist["pixel_count"].sum()
        dist["percent_of_habitat"] = 100.0 * dist["pixel_count"] / max(total, 1)

    index = "nirv" if any(c.startswith("nirv_") for c in profiles.columns) else "ndvi"

    # Clustered bands = every *_mean column minus id/size and the diagnostics.
    mean_cols = [c[:-5] for c in profiles.columns if c.endswith("_mean")]
    clustered = [b for b in mean_cols if b not in _DIAGNOSTIC]

    # feature_source from the config snapshot; absent in pre-embedding manifests,
    # so default to handcrafted.
    feature_source = (
        manifest.get("config_snapshot", {})
        .get("clustering", {})
        .get("feature_source", "handcrafted")
    )

    dissolved = vectors_dir / f"{config}_stands_dissolved.geojson"
    snic = vectors_dir / f"{config}_stands_snic.geojson"
    return ConfigRun(
        name=config, profiles=profiles, dist=dist, manifest=manifest, metrics=metrics,
        dissolved_path=dissolved if dissolved.exists() else None,
        snic_path=snic if snic.exists() else None,
        index=index, clustered_bands=clustered, feature_source=feature_source,
    )


def _feature_label(run: ConfigRun) -> str:
    """Human-readable description of what fed k-means, for the summary cards."""
    if run.feature_source != "embedding":
        harm = (
            run.manifest.get("config_snapshot", {})
            .get("features_optical", {})
            .get("harmonic_mode", "?")
        )
        return f"{run.index.upper()} / {harm} harmonic"
    emb = (
        run.manifest.get("config_snapshot", {})
        .get("datasets", {})
        .get("embedding", "")
    )
    n = len(run.clustered_bands)
    if "SATELLITE_EMBEDDING" in emb:
        return f"AlphaEarth embedding ({n}-band)"
    if "tessera" in emb.lower():
        return f"Tessera embedding ({n}-band)"
    return f"Pretrained embedding ({n}-band)"


# --------------------------------------------------------------------------
# Figures. Each returns the saved PNG path.
# --------------------------------------------------------------------------

def _save(fig: plt.Figure, out: Path, name: str) -> Path:
    p = out / f"{name}.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


def fig_stand_map(run: ConfigRun, out: Path) -> Path | None:
    if run.dissolved_path is None:
        return None
    data = json.loads(run.dissolved_path.read_text())
    fig, ax = plt.subplots(figsize=(7.2, 7.2))
    labelled: set[int] = set()
    for feat in data["features"]:
        cid = int(feat["properties"]["cluster_id"])
        geom = shape(feat["geometry"])
        polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        for poly in polys:
            xs, ys = poly.exterior.xy
            ax.fill(xs, ys, facecolor=cluster_color(cid), edgecolor=SURFACE,
                    linewidth=0.2)
        if cid not in labelled and geom.area > 0:  # one direct label per cluster
            c = geom.representative_point()
            ax.annotate(str(cid), (c.x, c.y), color="white", fontsize=9,
                        fontweight="bold", ha="center", va="center",
                        path_effects=None)
            labelled.add(cid)
    ax.set_aspect("equal")
    ax.set_title(f"Forest-stand map — {run.name}\ndissolved management units, coloured by stand type", loc="left")
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])
    handles = [Patch(facecolor=cluster_color(c), label=f"Stand type {c}")
               for c in sorted(run.dist["cluster_id"].astype(int))]
    ax.legend(handles=handles, loc="lower left", frameon=False, fontsize=9,
              ncol=3, bbox_to_anchor=(0, -0.09))
    return _save(fig, out, "stand_map")


def _zscored_means(run: ConfigRun) -> tuple[np.ndarray, list[str]]:
    bands = run.clustered_bands
    means = np.array([[run.profiles[f"{b}_mean"].iloc[i] for b in bands]
                      for i in range(run.k)], dtype=float)
    mu = means.mean(axis=0)
    sd = means.std(axis=0)
    sd[sd == 0] = 1.0
    return (means - mu) / sd, bands


def fig_fingerprint(run: ConfigRun, out: Path) -> Path:
    z, bands = _zscored_means(run)
    fig, ax = plt.subplots(figsize=(max(7, 0.42 * len(bands)), 4.6))
    vmax = float(np.abs(z).max()) or 1.0
    im = ax.imshow(z, cmap=DIVERGE, vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(bands)))
    ax.set_xticklabels([label(b) for b in bands], rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(run.k))
    ax.set_yticklabels([f"Stand {i}" for i in range(run.k)])
    for i in range(run.k):  # colour the tick labels by cluster identity
        ax.get_yticklabels()[i].set_color(cluster_color(i))
        ax.get_yticklabels()[i].set_fontweight("bold")
    ax.grid(False)
    ax.set_title(f"Cluster fingerprint — {run.name}\nper-stand mean, z-scored across stands (blue = low, orange = high)", loc="left")
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cb.set_label("z-score", color=INK2)
    cb.outline.set_visible(False)
    return _save(fig, out, "fingerprint")


def fig_separating_power(run: ConfigRun, out: Path) -> Path:
    bands = run.clustered_bands
    w = run.dist.set_index("cluster_id")["pixel_count"].reindex(
        run.profiles["cluster_id"]).to_numpy(float)
    w = w / w.sum()
    ratios = []
    for b in bands:
        m = run.profiles[f"{b}_mean"].to_numpy(float)
        between = math.sqrt(float(np.sum(w * (m - np.sum(w * m)) ** 2)))
        iqr = (run.profiles[f"{b}_p75"] - run.profiles[f"{b}_p25"]).to_numpy(float)
        within = float(np.sum(w * (iqr / 1.349)))
        ratios.append(between / (between + within + 1e-9))
    order = np.argsort(ratios)
    fig, ax = plt.subplots(figsize=(7, max(3.5, 0.32 * len(bands))))
    y = np.arange(len(bands))
    vals = np.array(ratios)[order]
    ax.barh(y, vals, color=[SEQ(0.35 + 0.6 * v) for v in vals], height=0.72)
    ax.set_yticks(y)
    ax.set_yticklabels([label(bands[i]) for i in order], fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_xlabel("between-stand separation ratio  (0 = overlapping, 1 = fully separated)")
    ax.grid(axis="y", visible=False)
    for yi, v in zip(y, vals, strict=False):
        ax.text(v + 0.01, yi, f"{v:.2f}", va="center", fontsize=7.5, color=INK2)
    ax.set_title(f"What separates the stands — {run.name}\nhigher = the feature drives the partition", loc="left")
    return _save(fig, out, "separating_power")


def fig_sizes(run: ConfigRun, out: Path) -> Path:
    d = run.dist.sort_values("cluster_id")
    fig, ax = plt.subplots(figsize=(7, 3.6))
    cids = d["cluster_id"].astype(int).to_numpy()
    areas = d["area_ha"].to_numpy(float)
    ax.bar(cids, areas, color=[cluster_color(c) for c in cids], width=0.72)
    ax.set_xticks(cids)
    ax.set_xticklabels([f"Stand {c}" for c in cids])
    ax.set_ylabel("Area (hectares)")
    ax.grid(axis="x", visible=False)
    pct = d.get("percent_of_habitat")
    for c, a, p in zip(cids, areas, (pct if pct is not None else [None] * len(cids)), strict=False):
        txt = f"{a:.0f} ha" + (f"\n{p:.0f}%" if p is not None else "")
        ax.text(c, a, txt, ha="center", va="bottom", fontsize=8, color=INK2)
    ax.margins(y=0.18)
    ax.set_title(f"Stand composition — {run.name}\narea of each stand type across the AOI", loc="left")
    return _save(fig, out, "sizes")


def fig_phenology(run: ConfigRun, out: Path) -> Path | None:
    p = run.index
    need = [f"{p}_mean_mean", f"{p}_amplitude_annual_mean",
            f"{p}_phase_annual_sin_mean", f"{p}_phase_annual_cos_mean"]
    if not all(c in run.profiles.columns for c in need):
        return None
    dual = f"{p}_amplitude_semi_mean" in run.profiles.columns
    t = np.linspace(0, 1, 200)
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for i in range(run.k):
        row = run.profiles.iloc[i]
        mean = row[f"{p}_mean_mean"]
        a1 = row[f"{p}_amplitude_annual_mean"]
        phi1 = math.atan2(row[f"{p}_phase_annual_sin_mean"], row[f"{p}_phase_annual_cos_mean"])
        y = mean + a1 * np.cos(2 * math.pi * t - phi1)
        if dual:
            a2 = row[f"{p}_amplitude_semi_mean"]
            phi2 = math.atan2(row[f"{p}_phase_semi_sin_mean"], row[f"{p}_phase_semi_cos_mean"])
            y = y + a2 * np.cos(4 * math.pi * t - phi2)
        ax.plot(t * 12, y, color=cluster_color(i), linewidth=2, label=f"Stand {i}")
    ax.set_xlim(0, 12)
    ax.set_xticks(range(0, 13, 2))
    ax.set_xlabel("Month")
    ax.set_ylabel(f"{p.upper()} (reconstructed seasonal cycle)")
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.16))
    harm = "dual harmonic" if dual else "single harmonic"
    ax.set_title(f"Phenology signature — {run.name}\nper-stand seasonal {p.upper()} curve ({harm})", loc="left")
    return _save(fig, out, "phenology")


def fig_signatures(run: ConfigRun, out: Path) -> Path | None:
    groups = [
        ("Structure (m)", ["canopy_height", "canopy_height_std", "canopy_height_max"]),
        ("Terrain", ["elevation", "slope", "distance_to_water"]),
        ("Radar (dB)", ["vv_p50", "vh_p50", "vv_minus_vh_median"]),
    ]
    # Keep only groups whose bands exist in this config's profiles. Embedding
    # configs carry none of these (their bands are the raw embedding dims), so
    # the figure is skipped entirely rather than drawn empty.
    present = [
        (title, [b for b in bands if f"{b}_mean" in run.profiles.columns])
        for title, bands in groups
    ]
    present = [(t, b) for t, b in present if b]
    if not present:
        return None
    fig, axes = plt.subplots(1, len(present), figsize=(3.9 * len(present), 3.8), squeeze=False)
    for ax, (title, bands) in zip(axes[0], present, strict=False):
        x = np.arange(len(bands))
        width = 0.8 / run.k
        for i in range(run.k):
            vals = [run.profiles[f"{b}_p50"].iloc[i] for b in bands]
            ax.bar(x + i * width, vals, width=width, color=cluster_color(i))
        ax.set_xticks(x + width * (run.k - 1) / 2)
        ax.set_xticklabels([label(b) for b in bands], rotation=20, ha="right", fontsize=8)
        ax.set_title(title, fontsize=11, loc="left")
        ax.grid(axis="x", visible=False)
    fig.suptitle(f"Sensor signatures — {run.name}   (per-stand median)", x=0.02, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return _save(fig, out, "signatures")


def fig_confusion(cur: ConfigRun, out: Path) -> Path | None:
    cm = cur.metrics.get("confusion_matrix")
    if not cm:
        return None
    cm = np.array(cm, dtype=float)
    ref = cur.metrics.get("reference_config", "reference")
    corr = cur.metrics.get("correspondence", {})
    row_norm = cm / cm.sum(axis=1, keepdims=True).clip(min=1)
    fig, ax = plt.subplots(figsize=(5.6, 5.0))
    ax.imshow(row_norm, cmap=SEQ, vmin=0, vmax=1, aspect="equal")
    ax.set_xlabel(f"{ref} (reference) stand")
    ax.set_ylabel(f"{cur.name} stand")
    ax.set_xticks(range(cm.shape[1]))
    ax.set_yticks(range(cm.shape[0]))
    ax.grid(False)
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            if cm[i, j] > 0:
                ax.text(j, i, f"{row_norm[i, j]*100:.0f}", ha="center", va="center",
                        fontsize=8, color="white" if row_norm[i, j] > 0.5 else INK2)
    for i, j in corr.items():  # Hungarian match = green ring
        ax.add_patch(plt.Rectangle((int(j) - 0.5, int(i) - 0.5), 1, 1, fill=False,
                                   edgecolor="#008300", linewidth=2.2))
    ax.set_title("Baseline vs variant — cluster overlap\nrow-normalised %, green ring = best match", loc="left")
    return _save(fig, out, "confusion")


def fig_confidence(cur: ConfigRun, out: Path) -> Path | None:
    """Confidence gauge from the metrics `confidence_summary` (scalars only).

    Mean stand confidence = area-weighted agreement between this config's stands
    and the reference's; high-confidence area = share of the map in stands that
    agree at/above the threshold. Consensus/stability, NOT correctness — there
    is no ground-truth stand map to score against. Returns None if the run's
    metrics JSON predates the confidence layer (older runs degrade silently).
    """
    cs = cur.metrics.get("confidence_summary")
    if not cs or cs.get("mean") is None:
        return None
    thr = float(cs.get("high_threshold", 0.8))
    labels = ["Mean stand\nconfidence"]
    vals = [float(cs["mean"])]
    if cs.get("frac_area_ge_high") is not None:
        labels.append(f"Area ≥{int(thr * 100)}%\nagreement")
        vals.append(float(cs["frac_area_ge_high"]))
    fig, ax = plt.subplots(figsize=(6.4, 1.3 + 0.7 * len(vals)))
    y = np.arange(len(vals))
    ax.barh(y, vals, color=[SEQ(0.4 + 0.5 * v) for v in vals], height=0.55)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlim(0, 1)
    ax.invert_yaxis()
    ax.set_xlabel("fraction  (0 = never agree, 1 = always agree)")
    for yi, v in zip(y, vals, strict=False):
        ax.text(v + 0.015, yi, f"{v * 100:.0f}%", va="center", fontsize=9, color=INK2)
    ax.grid(axis="y", visible=False)
    ref = cur.metrics.get("reference_config", "baseline")
    ax.set_title(f"Stand confidence — {cur.name} vs {ref}\nwhere the two representations agree on the stand (consensus, not correctness)", loc="left")
    return _save(fig, out, "confidence")


# --------------------------------------------------------------------------
# HTML assembly (self-contained: PNGs embedded as base64)
# --------------------------------------------------------------------------

def _b64(p: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def _cfg_summary(run: ConfigRun) -> dict[str, str]:
    snap = run.manifest.get("config_snapshot", {})
    roi = run.manifest.get("roi", {})
    dates = snap.get("dates", {}).get("phenology", {})
    summary = {
        "features": _feature_label(run),
        "k": str(run.k),
        "bands": str(len(run.clustered_bands)),
        "roi": f"{roi.get('name', '?')} ({roi.get('area_km2', '?')} km²)",
        "window": f"{dates.get('start', '?')} → {dates.get('end', '?')}",
    }
    return summary


def build_html(title: str, sections: list[tuple[str, str, list[Path]]],
               summary: dict[str, str], metrics_rows: list[tuple[str, str]]) -> str:
    cards = "".join(
        f'<div class="kv"><div class="k">{k}</div><div class="v">{v}</div></div>'
        for k, v in summary.items()
    )
    mtable = ""
    if metrics_rows:
        rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in metrics_rows)
        mtable = f'<table class="metrics"><tbody>{rows}</tbody></table>'
    body = ""
    for heading, blurb, figs in sections:
        imgs = "".join(f'<figure><img src="{_b64(p)}" alt="{p.stem}"></figure>'
                       for p in figs if p is not None)
        body += f'<section><h2>{heading}</h2><p class="blurb">{blurb}</p>{imgs}</section>'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>
:root{{color-scheme:light}}
*{{box-sizing:border-box}}
body{{margin:0;background:{PLANE};color:{INK};
 font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.5}}
.wrap{{max-width:960px;margin:0 auto;padding:32px 20px 80px}}
h1{{font-size:26px;margin:0 0 4px}}
.sub{{color:{INK2};margin:0 0 24px}}
.cards{{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:28px}}
.kv{{background:{SURFACE};border:1px solid rgba(11,11,11,.10);border-radius:10px;
 padding:10px 14px;min-width:120px}}
.kv .k{{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:{MUTED}}}
.kv .v{{font-size:16px;font-weight:600;margin-top:2px}}
section{{background:{SURFACE};border:1px solid rgba(11,11,11,.10);border-radius:14px;
 padding:22px 24px;margin-bottom:22px}}
h2{{font-size:18px;margin:0 0 4px}}
.blurb{{color:{INK2};margin:0 0 16px;font-size:14px}}
figure{{margin:0 0 14px;text-align:center}}
img{{max-width:100%;height:auto;border-radius:8px}}
table.metrics{{border-collapse:collapse;font-size:14px;margin-top:4px}}
table.metrics td{{padding:6px 18px 6px 0;border-bottom:1px solid {GRID}}}
table.metrics td:last-child{{font-weight:600;font-variant-numeric:tabular-nums}}
footer{{color:{MUTED};font-size:12px;margin-top:30px}}
</style></head><body><div class="wrap">
<h1>{title}</h1>
<p class="sub">Forest Monitoring Units — unsupervised stand delineation. Figures derived from the exported run artifacts.</p>
<div class="cards">{cards}</div>
{mtable}
{body}
<footer>Generated by scripts/report.py from cluster_profiles.csv, export_manifest, metrics JSON, and the stands_dissolved / stands_snic vectors. Colours follow the validated categorical palette; stand identity is carried by legend + direct labels, not colour alone.</footer>
</div></body></html>"""


# --------------------------------------------------------------------------
# Comparison report (standalone: baseline vs variant, side by side)
# --------------------------------------------------------------------------

def _cards_html(summary: dict[str, str]) -> str:
    return "".join(
        f'<div class="kv"><div class="k">{k}</div><div class="v">{v}</div></div>'
        for k, v in summary.items()
    )


def comparison_metrics_rows(cur: ConfigRun) -> list[tuple[str, str]]:
    """ARI / NMI / agreement / both silhouettes, from the variant's metrics JSON."""
    m = cur.metrics
    rows: list[tuple[str, str]] = []
    for key, lbl in [
        ("ari", "Adjusted Rand Index"),
        ("nmi", "Normalized Mutual Info"),
        ("agreement_rate", "Agreement (Hungarian-aligned)"),
        ("silhouette_current", "Silhouette — variant"),
        ("silhouette_reference", "Silhouette — baseline"),
    ]:
        if m.get(key) is not None:
            v = m[key]
            if key == "agreement_rate":
                rows.append((lbl, f"{v * 100:.0f}%"))
            elif "silhouette" in key:
                rows.append((lbl, f"{v:+.3f}"))
            else:
                rows.append((lbl, f"{v:.3f}"))
    cs = m.get("confidence_summary")
    if cs:
        if cs.get("mean") is not None:
            rows.append(("Mean stand confidence", f"{cs['mean'] * 100:.0f}%"))
        if cs.get("frac_area_ge_high") is not None:
            thr = int(float(cs.get("high_threshold", 0.8)) * 100)
            rows.append((f"High-confidence area (≥{thr}%)", f"{cs['frac_area_ge_high'] * 100:.0f}%"))
    return rows


def build_comparison_html(
    cur: ConfigRun, ref: ConfigRun, cur_sum: dict[str, str], ref_sum: dict[str, str],
    pairs: list[tuple[str, str, Path | None, Path | None]],
    conf_fig: Path | None, metrics_rows: list[tuple[str, str]],
    conf_gauge: Path | None = None,
) -> str:
    title = f"FMU comparison — {ref.name} vs {cur.name}"
    mtable = ""
    if metrics_rows:
        rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in metrics_rows)
        mtable = f'<table class="metrics"><tbody>{rows}</tbody></table>'
    gauge_html = ""
    if conf_gauge is not None:
        gauge_html = (
            '<figure style="margin-top:14px"><img src="'
            f'{_b64(conf_gauge)}" alt="confidence"></figure>'
        )
    conf_html = ""
    if conf_fig is not None:
        conf_html = (
            '<section><h2>Where the stands overlap</h2>'
            '<p class="blurb">Row-normalised confusion between the two partitions; the green '
            "ring marks each variant stand's best-matching baseline stand (Hungarian alignment). "
            'This is the key: stand colours are per-config, so use this — not colour — to read the correspondence.</p>'
            f'<figure><img src="{_b64(conf_fig)}" alt="confusion"></figure></section>'
        )
    pair_html = ""
    for heading, blurb, rfig, cfig in pairs:
        cols = ""
        if rfig is not None:
            cols += f'<figure><figcaption>{ref.name}</figcaption><img src="{_b64(rfig)}"></figure>'
        if cfig is not None:
            cols += f'<figure><figcaption>{cur.name}</figcaption><img src="{_b64(cfig)}"></figure>'
        if cols:
            pair_html += (
                f'<section><h2>{heading}</h2><p class="blurb">{blurb}</p>'
                f'<div class="pair">{cols}</div></section>'
            )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>
:root{{color-scheme:light}}
*{{box-sizing:border-box}}
body{{margin:0;background:{PLANE};color:{INK};
 font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.5}}
.wrap{{max-width:1040px;margin:0 auto;padding:32px 20px 80px}}
h1{{font-size:26px;margin:0 0 4px}}
.sub{{color:{INK2};margin:0 0 24px}}
.cfgwrap{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:26px}}
.cfghead{{font-weight:700;font-size:15px;margin-bottom:8px}}
.cards{{display:flex;flex-wrap:wrap;gap:8px}}
.kv{{background:{SURFACE};border:1px solid rgba(11,11,11,.10);border-radius:10px;
 padding:8px 12px;min-width:96px}}
.kv .k{{font-size:10px;text-transform:uppercase;letter-spacing:.04em;color:{MUTED}}}
.kv .v{{font-size:15px;font-weight:600;margin-top:2px}}
section{{background:{SURFACE};border:1px solid rgba(11,11,11,.10);border-radius:14px;
 padding:22px 24px;margin-bottom:22px}}
h2{{font-size:18px;margin:0 0 4px}}
.blurb{{color:{INK2};margin:0 0 16px;font-size:14px}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:18px;align-items:start}}
@media (max-width:720px){{.pair,.cfgwrap{{grid-template-columns:1fr}}}}
figure{{margin:0;text-align:center}}
figcaption{{font-size:12px;color:{MUTED};margin-bottom:6px;font-weight:600}}
img{{max-width:100%;height:auto;border-radius:8px}}
table.metrics{{border-collapse:collapse;font-size:14px;margin-top:4px}}
table.metrics td{{padding:6px 18px 6px 0;border-bottom:1px solid {GRID}}}
table.metrics td:last-child{{font-weight:600;font-variant-numeric:tabular-nums}}
footer{{color:{MUTED};font-size:12px;margin-top:30px}}
</style></head><body><div class="wrap">
<h1>{title}</h1>
<p class="sub">Same AOI, same segmentation, same k={cur.k} — only the clustering feature vector differs
 ({ref.name} vs {cur.name}; see the per-config summaries below). Any difference below is the
 feature representation alone.</p>
<div class="cfgwrap">
 <div><div class="cfghead" style="color:{CLUSTER_COLORS[0]}">{ref.name} (reference)</div><div class="cards">{_cards_html(ref_sum)}</div></div>
 <div><div class="cfghead" style="color:{CLUSTER_COLORS[5]}">{cur.name} (variant)</div><div class="cards">{_cards_html(cur_sum)}</div></div>
</div>
<section><h2>Agreement metrics</h2><p class="blurb">How similar the two clusterings are overall — 1.0 would be identical partitions. Confidence rolls the per-pixel agreement up to stands: consensus between the two representations, not correctness (there is no ground-truth stand map to score against).</p>{mtable}{gauge_html}</section>
{conf_html}
{pair_html}
<footer>Generated by scripts/report.py (comparison mode). Stand colours are per-config and NOT comparable across panels; the overlap matrix gives the true correspondence.</footer>
</div></body></html>"""


def comparison_report(cur: ConfigRun, ref: ConfigRun, out: Path) -> Path:
    cur_dir = out / f"_{cur.name}"
    ref_dir = out / f"_{ref.name}"
    cur_dir.mkdir(parents=True, exist_ok=True)
    ref_dir.mkdir(parents=True, exist_ok=True)
    pairs: list[tuple[str, str, Path | None, Path | None]] = [
        ("Stand maps",
         "The management-unit map each config produces. Stand colours/IDs are per-config — the same colour is a different stand in each panel; read the overlap matrix above for the correspondence.",
         fig_stand_map(ref, ref_dir), fig_stand_map(cur, cur_dir)),
        ("Composition",
         "Area of each stand type across the AOI, per config.",
         fig_sizes(ref, ref_dir), fig_sizes(cur, cur_dir)),
        ("Phenology",
         "Reconstructed seasonal greenness per stand — baseline single-harmonic NDVI vs variant dual-harmonic NIRv.",
         fig_phenology(ref, ref_dir), fig_phenology(cur, cur_dir)),
        ("Cluster fingerprint",
         "Per-stand feature means, z-scored across stands within each config (blue = low, orange = high).",
         fig_fingerprint(ref, ref_dir), fig_fingerprint(cur, cur_dir)),
    ]
    conf = fig_confusion(cur, out)
    conf_gauge = fig_confidence(cur, out)
    html = build_comparison_html(
        cur, ref, _cfg_summary(cur), _cfg_summary(ref), pairs, conf,
        comparison_metrics_rows(cur), conf_gauge,
    )
    path = out / "report.html"
    path.write_text(html)
    return path


# --------------------------------------------------------------------------
# Multi-config comparison (N versions: baseline + AlphaEarth + Tessera + ...)
# --------------------------------------------------------------------------

def fig_silhouette_bars(configs: list[ConfigRun], out: Path) -> Path | None:
    """Intrinsic silhouette per config, side by side.

    Silhouette is intrinsic (no reference needed), so it is the one number that
    is directly comparable across ALL versions at once — higher = tighter,
    better-separated stands. This is the headline "which representation
    separates the forest better" figure.
    """
    names, vals = [], []
    for r in configs:
        s = r.metrics.get("silhouette_current")
        if s is None:
            continue
        names.append(r.name)
        vals.append(float(s))
    if len(names) < 2:
        return None
    fig, ax = plt.subplots(figsize=(max(5.0, 1.7 * len(names)), 3.9))
    x = np.arange(len(names))
    ax.bar(x, vals, color=[cluster_color(i) for i in range(len(names))], width=0.6)
    ax.axhline(0, color=AXIS, lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=15, ha="right", fontsize=9)
    ax.set_ylabel("silhouette (intrinsic separation)")
    ax.grid(axis="x", visible=False)
    for xi, v in zip(x, vals, strict=False):
        ax.text(xi, v, f"{v:+.3f}", ha="center",
                va="bottom" if v >= 0 else "top", fontsize=8.5, color=INK2)
    ax.set_title("Cluster separation by feature source\nintrinsic silhouette — higher = tighter, better-separated stands (directly comparable across versions)", loc="left")
    return _save(fig, out, "silhouette_bars")


def _multi_metrics_table_html(ref: ConfigRun, variants: list[ConfigRun]) -> str:
    """Metrics matrix: rows = metrics, columns = configs (ref first).

    Silhouette is intrinsic (shown for every config). ARI / NMI / agreement /
    confidence are measured against the reference, so the reference column shows
    "— (reference)" for those rows.
    """
    configs = [ref, *variants]

    def sil(r: ConfigRun) -> str:
        s = r.metrics.get("silhouette_current")
        return f"{float(s):+.3f}" if s is not None else "—"

    def cmp_cells(key: str, pct: bool) -> str:
        cells = "<td>— (reference)</td>"
        for v in variants:
            val = v.metrics.get(key)
            if val is None:
                cells += "<td>—</td>"
            elif pct:
                cells += f"<td>{val * 100:.0f}%</td>"
            else:
                cells += f"<td>{val:.3f}</td>"
        return cells

    def conf_cells(field: str) -> str:
        cells = "<td>— (reference)</td>"
        for v in variants:
            val = (v.metrics.get("confidence_summary") or {}).get(field)
            cells += f"<td>{val * 100:.0f}%</td>" if val is not None else "<td>—</td>"
        return cells

    rows = [
        f"<tr><th>Silhouette (intrinsic)</th>{''.join(f'<td>{sil(c)}</td>' for c in configs)}</tr>",
        f"<tr><th>ARI vs {ref.name}</th>{cmp_cells('ari', False)}</tr>",
        f"<tr><th>NMI vs {ref.name}</th>{cmp_cells('nmi', False)}</tr>",
        f"<tr><th>Agreement vs {ref.name}</th>{cmp_cells('agreement_rate', True)}</tr>",
        f"<tr><th>Mean stand confidence</th>{conf_cells('mean')}</tr>",
        f"<tr><th>High-confidence area (≥80%)</th>{conf_cells('frac_area_ge_high')}</tr>",
    ]
    header = "<th></th>" + "".join(f"<th>{c.name}</th>" for c in configs)
    return (
        f'<table class="matrix"><thead><tr>{header}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def _fig_grid(items: list[tuple[str, Path | None]]) -> str:
    cells = "".join(
        f'<figure><figcaption>{cap}</figcaption><img src="{_b64(p)}"></figure>'
        for cap, p in items if p is not None
    )
    return f'<div class="grid">{cells}</div>'


def build_multi_html(
    ref: ConfigRun, variants: list[ConfigRun], sil_fig: Path | None,
    stand_maps: list[tuple[str, Path | None]], comp_figs: list[tuple[str, Path | None]],
    per_variant: list[tuple[ConfigRun, Path | None, Path | None]],
) -> str:
    configs = [ref, *variants]
    title = f"FMU comparison — {ref.name} vs {', '.join(v.name for v in variants)}"
    cfg_cards = "".join(
        f'<div class="cfg"><div class="cfghead">{c.name}'
        f'{" (reference)" if c is ref else ""}</div>'
        f'<div class="cards">{_cards_html(_cfg_summary(c))}</div></div>'
        for c in configs
    )
    sil_html = ""
    if sil_fig is not None:
        sil_html = (
            '<section><h2>Which representation separates the stands better</h2>'
            '<p class="blurb">Intrinsic silhouette per version — needs no reference, so it is '
            'directly comparable across all of them. Higher = tighter, better-separated stands. '
            'This is the cleanest single-number answer to "hand-crafted vs pretrained".</p>'
            f'<figure><img src="{_b64(sil_fig)}"></figure></section>'
        )
    per_variant_html = ""
    for v, conf, gauge in per_variant:
        cols = _fig_grid([("overlap vs " + ref.name, conf), ("per-stand confidence", gauge)])
        if conf is None and gauge is None:
            continue
        per_variant_html += (
            f'<section><h2>{v.name} vs {ref.name}</h2>'
            '<p class="blurb">Row-normalised overlap (green ring = each variant stand\'s '
            'best-matching reference stand, Hungarian-aligned) and the per-stand confidence '
            'gauge (consensus between the two representations, not correctness).</p>'
            f'{cols}</section>'
        )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>
:root{{color-scheme:light}}
*{{box-sizing:border-box}}
body{{margin:0;background:{PLANE};color:{INK};
 font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.5}}
.wrap{{max-width:1120px;margin:0 auto;padding:32px 20px 80px}}
h1{{font-size:26px;margin:0 0 4px}}
.sub{{color:{INK2};margin:0 0 24px}}
.cfgwrap{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-bottom:26px}}
.cfghead{{font-weight:700;font-size:15px;margin-bottom:8px}}
.cards{{display:flex;flex-wrap:wrap;gap:8px}}
.kv{{background:{SURFACE};border:1px solid rgba(11,11,11,.10);border-radius:10px;
 padding:8px 12px;min-width:92px}}
.kv .k{{font-size:10px;text-transform:uppercase;letter-spacing:.04em;color:{MUTED}}}
.kv .v{{font-size:14px;font-weight:600;margin-top:2px}}
section{{background:{SURFACE};border:1px solid rgba(11,11,11,.10);border-radius:14px;
 padding:22px 24px;margin-bottom:22px}}
h2{{font-size:18px;margin:0 0 4px}}
.blurb{{color:{INK2};margin:0 0 16px;font-size:14px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;align-items:start}}
figure{{margin:0;text-align:center}}
figcaption{{font-size:12px;color:{MUTED};margin-bottom:6px;font-weight:600}}
img{{max-width:100%;height:auto;border-radius:8px}}
table.matrix{{border-collapse:collapse;font-size:14px;width:100%;overflow-x:auto;display:block}}
table.matrix th,table.matrix td{{padding:8px 14px;border-bottom:1px solid {GRID};text-align:right;font-variant-numeric:tabular-nums}}
table.matrix thead th{{border-bottom:2px solid {AXIS};color:{INK}}}
table.matrix tbody th{{text-align:left;font-weight:600;color:{INK2}}}
footer{{color:{MUTED};font-size:12px;margin-top:30px}}
</style></head><body><div class="wrap">
<h1>{title}</h1>
<p class="sub">Same AOI, same segmentation, same k={ref.k} across every version — only the clustering
 feature vector differs. Agreement and confidence are measured against <b>{ref.name}</b>; silhouette
 is intrinsic and directly comparable. No ground-truth stand map exists, so these compare
 representations (consensus + separation), not correctness.</p>
<div class="cfgwrap">{cfg_cards}</div>
<section><h2>Metrics at a glance</h2><p class="blurb">One row per metric, one column per version. Silhouette is intrinsic (all versions); ARI / NMI / agreement / confidence are each version measured against the reference.</p>{_multi_metrics_table_html(ref, variants)}</section>
{sil_html}
<section><h2>Stand maps</h2><p class="blurb">The management-unit map each version produces. Stand colours/IDs are per-config — the same colour is a different stand in each panel; use the overlap matrices below for the correspondence.</p>{_fig_grid(stand_maps)}</section>
<section><h2>Composition</h2><p class="blurb">Area of each stand type across the AOI, per version.</p>{_fig_grid(comp_figs)}</section>
{per_variant_html}
<footer>Generated by scripts/report.py (multi mode). Stand colours are per-config and NOT comparable across panels; silhouette (intrinsic) and the overlap matrices carry the cross-version story.</footer>
</div></body></html>"""


def multi_report(ref: ConfigRun, variants: list[ConfigRun], out: Path) -> Path:
    configs = [ref, *variants]
    dirs = {c.name: out / f"_{c.name}" for c in configs}
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    # The reference's silhouette may live only in a variant's metrics JSON (as
    # silhouette_reference) if the baseline was never run through metrics itself.
    if ref.metrics.get("silhouette_current") is None:
        for v in variants:
            sr = v.metrics.get("silhouette_reference")
            if sr is not None:
                ref.metrics["silhouette_current"] = sr
                break

    sil_fig = fig_silhouette_bars(configs, out)
    stand_maps = [(c.name, fig_stand_map(c, dirs[c.name])) for c in configs]
    comp_figs = [(c.name, fig_sizes(c, dirs[c.name])) for c in configs]
    per_variant = [
        (v, fig_confusion(v, dirs[v.name]), fig_confidence(v, dirs[v.name]))
        for v in variants
    ]
    html = build_multi_html(ref, variants, sil_fig, stand_maps, comp_figs, per_variant)
    path = out / "report.html"
    path.write_text(html)
    return path


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def single_config_sections(run: ConfigRun, out: Path) -> list[tuple[str, str, list[Path]]]:
    secs: list[tuple[str, str, list[Path]]] = []
    m = fig_stand_map(run, out)
    if m:
        secs.append(("The stand map", "One polygon per connected same-cluster management unit — the layer a forester opens. Colour = stand type; numbers label each type.", [m]))
    secs.append(("What defines each stand", "Left: each stand's mean feature values, z-scored across stands (blue = below average, orange = above). Right: how strongly each feature separates the stands.",
                 [fig_fingerprint(run, out), fig_separating_power(run, out)]))
    secs.append(("Composition", "Area of each stand type across the AOI.", [fig_sizes(run, out)]))
    ph = fig_phenology(run, out)
    if ph:
        secs.append(("Phenology", "Reconstructed seasonal greenness cycle per stand, from the fitted harmonic coefficients.", [ph]))
    sig = fig_signatures(run, out)
    if sig:  # absent for embedding configs (no structural/terrain/radar bands)
        secs.append(("Sensor signatures", "Per-stand median values across the structural, terrain, and radar features.", [sig]))
    return secs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None, help="config name, e.g. sanjay_van_baseline (single/compare modes)")
    ap.add_argument("--reference", default=None, help="reference config (comparison / multi baseline)")
    ap.add_argument("--compare", action="store_true",
                    help="build a STANDALONE 2-way comparison report (--config = variant, --reference = baseline)")
    ap.add_argument("--multi", action="store_true",
                    help="build a STANDALONE N-way comparison: --reference = baseline, --configs = versions to compare")
    ap.add_argument("--configs", nargs="+", default=None,
                    help="variant configs for --multi (each compared against --reference)")
    ap.add_argument("--runs-root", default="runs", type=Path)
    ap.add_argument("--vectors-dir", default="fmu_exports_clean", type=Path)
    ap.add_argument("--out", default="reports", type=Path)
    args = ap.parse_args()

    _style()

    # Standalone N-way comparison: baseline + each variant (e.g. baseline,
    # AlphaEarth, Tessera), side by side.
    if args.multi:
        if not args.reference or not args.configs:
            raise SystemExit("--multi requires --reference (baseline) and --configs v1 [v2 ...]")
        ref = discover(args.reference, args.runs_root, args.vectors_dir)
        variants = [discover(c, args.runs_root, args.vectors_dir) for c in args.configs]
        out = args.out / f"multi_{args.reference}"
        out.mkdir(parents=True, exist_ok=True)
        path = multi_report(ref, variants, out)
        print(f"Wrote {path}")
        print(f"Figures in {out}/")
        return

    # Standalone comparison report: baseline vs variant, side by side.
    if args.compare:
        if not args.config:
            raise SystemExit("--compare requires --config (the variant) and --reference (the baseline)")
        if not args.reference:
            raise SystemExit("--compare requires --reference (the baseline config)")
        cur = discover(args.config, args.runs_root, args.vectors_dir)
        ref = discover(args.reference, args.runs_root, args.vectors_dir)
        out = args.out / f"comparison_{args.config}_vs_{args.reference}"
        out.mkdir(parents=True, exist_ok=True)
        path = comparison_report(cur, ref, out)
        print(f"Wrote {path}")
        print(f"Figures in {out}/")
        return

    # Single-config report.
    if not args.config:
        raise SystemExit("--config is required (single-config report). Use --compare or --multi for comparisons.")
    run = discover(args.config, args.runs_root, args.vectors_dir)
    out = args.out / args.config
    out.mkdir(parents=True, exist_ok=True)

    sections = single_config_sections(run, out)

    metrics_rows: list[tuple[str, str]] = []
    sil = run.metrics.get("silhouette_current")
    if sil is not None:
        metrics_rows.append(("Silhouette (this run)", f"{sil:+.3f}"))

    if args.reference:
        conf = fig_confusion(run, out)  # uses this run's metrics vs its reference
        conf_gauge = fig_confidence(run, out)
        cmp_figs = [f for f in [conf, conf_gauge] if f]
        for key, lbl in [("ari", "Adjusted Rand Index"), ("nmi", "Normalized Mutual Info"),
                         ("agreement_rate", "Agreement (Hungarian-aligned)"),
                         ("silhouette_reference", f"Silhouette ({args.reference})")]:
            if key in run.metrics:
                v = run.metrics[key]
                metrics_rows.append((lbl, f"{v:.3f}" if key != "agreement_rate" else f"{v*100:.0f}%"))
        cs = run.metrics.get("confidence_summary")
        if cs:
            if cs.get("mean") is not None:
                metrics_rows.append(("Mean stand confidence", f"{cs['mean'] * 100:.0f}%"))
            if cs.get("frac_area_ge_high") is not None:
                thr = int(float(cs.get("high_threshold", 0.8)) * 100)
                metrics_rows.append((f"High-confidence area (≥{thr}%)", f"{cs['frac_area_ge_high'] * 100:.0f}%"))
        if cmp_figs:
            sections.append((f"Reference vs this run ({args.reference} → {args.config})",
                             "Segmentation is fixed across both runs, so any difference is the feature representation alone. The matrix shows how this run's stands map onto the reference's after Hungarian alignment; the gauge summarises where the two representations agree on the stand (consensus, not correctness).",
                             cmp_figs))

    summary = _cfg_summary(run)
    html = build_html(f"FMU report — {args.config}", sections, summary, metrics_rows)
    html_path = out / "report.html"
    html_path.write_text(html)
    print(f"Wrote {html_path}")
    print(f"Figures in {out}/")


if __name__ == "__main__":
    main()
