"""Shared look for the Phase 3 summary figures.

One module so every figure in the deck speaks the same visual language: the
same colours, the same plain-language names for the five forest types, the same
text sizes. The palette follows the repo's existing decks (forest green ink,
amber accent) so the new slides sit beside the old ones without a seam.

Figures are drawn WITHOUT a title: the slide carries the title, and a title
baked into the image would duplicate it or disagree with it.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
FIG_DIR = HERE / "phase3_figures"
FIG_DIR.mkdir(exist_ok=True)

# ---- colours (hex without '#' is what the deck uses; matplotlib needs '#') ----
INK = "#1A1A1A"          # text, axes
MUTE = "#5F6F66"         # secondary text, tick labels
RULE = "#CBD8C4"         # light gridlines
FOREST = "#2C5F2D"       # the 3 hectare arm; "my method" when only one arm is shown
SLATE = "#6B7F8E"        # the 10 hectare arm
AMBER = "#A9631F"        # "our score" marker and the one thing to look at
CHANCE = "#C9CFCB"       # random-shift (chance) distributions and bands
CHANCE_EDGE = "#9AA39D"

# The five structural forest types from odisha_phase3_0_field_structure_types.py,
# keyed by the type number in odisha_phase3_0_field_types.csv, ordered from least
# to most forest so a light-to-dark ramp reads as "more forest".
TYPE_ORDER = [2, 4, 0, 1, 3]
TYPE_NAME = {
    2: "Scrub (almost no trees)",
    4: "Low forest, few trees",
    0: "Low forest, many trees",
    1: "Tall forest, few big trees",
    3: "Tall forest, many trees",
}
TYPE_SHORT = {2: "Scrub", 4: "Low, few trees", 0: "Low, many trees",
              1: "Tall, few big trees", 3: "Tall, many trees"}
TYPE_COLOUR = {2: "#CDB57E", 4: "#A9C38B", 0: "#6E9A5A", 1: "#3F7A4A", 3: "#1F4D2B"}

ARM_NAME = {"v120": "Stands up to 10 hectares", "v120_3ha": "Stands up to 3 hectares"}
ARM_COLOUR = {"v120": SLATE, "v120_3ha": FOREST}

DISTRICT_NAME = {"angul": "Angul", "dhenkanal": "Dhenkanal",
                 "kendujhar": "Kendujhar", "koraput": "Koraput"}

# Slide geometry the figures are drawn for (inches). The deck is 13.33 x 7.5.
FULL = (12.0, 4.9)       # full-width figure under a title
HALF = (5.9, 4.9)        # one of two side-by-side figures
TALL_HALF = (5.9, 5.6)
DPI = 220

ESRI_CREDIT = "Background imagery: Esri World Imagery (Esri, Maxar, Earthstar Geographics)"


def use() -> None:
    """Apply the shared matplotlib style. Call once at the top of a figure script."""
    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Calibri", "Carlito", "Arial", "Liberation Sans", "DejaVu Sans"],
        "font.size": 13,
        "axes.titlesize": 14,
        "axes.labelsize": 13,
        "xtick.labelsize": 12,
        "ytick.labelsize": 12,
        "legend.fontsize": 12,
        "axes.edgecolor": MUTE,
        "axes.labelcolor": INK,
        "xtick.color": MUTE,
        "ytick.color": MUTE,
        "text.color": INK,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": False,
        "grid.color": RULE,
        "grid.linewidth": 0.8,
        "legend.frameon": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
    })


def save(fig, name: str) -> Path:
    """Save to phase3_figures/<name>.png at deck resolution and close the figure."""
    out = FIG_DIR / f"{name}.png"
    fig.savefig(out, dpi=DPI, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    return out
