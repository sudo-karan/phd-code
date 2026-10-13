"""The transparency contract: every step must have something to show for itself.

A stage declares display layers (context key, band, how to draw it, legend) and
summary numbers; the orchestrator writes both into the run manifest. See the top
of `fmu.stages.base`.

The contract is enforced stage by stage. `ENFORCED` names the stages that must
declare something today; `PENDING` names the ones that do not yet. Every
pipeline stage has to be in exactly one of the two, so a new stage cannot be
added without deciding, and a pending stage that gains a declaration has to be
moved to `ENFORCED` -- the list can only shrink.

What is tested here: which stages are bound, what masking and merge declare, the
arithmetic behind masking's numbers, what the eight stages the explorer shows
declare (data load, the five feature stages, segmentation, clustering) and that
the bands they name are bands those stages write, and that the orchestrator
carries a declaration into the manifest. The checks on a single declaration (a
legend entry, a layer, a stage class) are in test_stages_base.py; the cache
switches are in test_pipeline.py.

No Earth Engine: these are class-level declarations and pure-Python arithmetic.
Where a test needs a stage to "run", its Earth Engine half is replaced.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

# Importing the stage modules is what runs @register_stage.
import fmu.stages.clustering as clustering_module
import fmu.stages.data_load  # noqa: F401
import fmu.stages.export  # noqa: F401
import fmu.stages.features_embedding as embedding_module
import fmu.stages.features_optical as optical_module
import fmu.stages.features_radar as radar_module
import fmu.stages.features_static as static_module
import fmu.stages.features_structure as structure_module
import fmu.stages.masking as masking_module
import fmu.stages.merge  # noqa: F401
import fmu.stages.metrics  # noqa: F401
import fmu.stages.profiling  # noqa: F401
import fmu.stages.segmentation as segmentation_module
from fmu.config import (
    ClusteringParams,
    DataLoadParams,
    DatasetIDs,
    FeaturesStructureParams,
    MaskingParams,
    SegmentationParams,
    load_config,
)
from fmu.pipeline import Pipeline
from fmu.stages.base import (
    DisplayLayer,
    LegendEntry,
    PipelineContext,
    Stage,
    StageResult,
    SummaryNumber,
    _stage_registry,
    get_stage_class,
    register_stage,
    transparency_gaps,
)
from fmu.stages.masking import (
    _INDIASAT_REASON_CLASSES,
    _WORLDCOVER_REASON_CLASSES,
    REASON_BUILT_UP,
    REASON_CROPLAND,
    REASON_KEPT,
    REASON_NAMES,
    REASON_NO_DATA,
    REASON_OTHER,
    REASON_WATER,
    SOURCE_INDIASAT,
    SOURCE_NAMES,
    SOURCE_NONE,
    SOURCE_WORLDCOVER,
    MaskingStage,
    _reason_from_classes,
    tabulate_mask_provenance,
)

REPO_ROOT = Path(__file__).parent.parent

# Stages that must declare display layers or summary numbers: masking and merge
# from the start, and the eight more the explorer shows a step for.
ENFORCED = {
    "masking",
    "merge",
    "data_load",
    "features_optical",
    "features_radar",
    "features_structure",
    "features_static",
    "features_embedding",
    "segmentation",
    "clustering",
}

# Stages that do not yet. Listed in the PR as pending; move a name to ENFORCED
# when its stage declares something.
PENDING = {"profiling", "export", "metrics"}

# The pipeline's own stages, snapshotted at import, when every stage module
# above has registered. Other test modules empty the registry to test the
# registry itself, and may register stand-in stages of their own; only classes
# defined under fmu.stages count here.
_PIPELINE_STAGES = {
    name: cls
    for name, cls in _stage_registry.items()
    if cls.__module__.startswith("fmu.stages.")
}


@pytest.fixture(autouse=True)
def _restore_stage_registry():
    _stage_registry.clear()
    _stage_registry.update(_PIPELINE_STAGES)
    yield
    _stage_registry.clear()
    _stage_registry.update(_PIPELINE_STAGES)


# ---------------------------------------------------------------------
# Which stages the contract binds
# ---------------------------------------------------------------------


def test_every_stage_is_either_enforced_or_pending():
    assert not ENFORCED & PENDING
    listed = ENFORCED | PENDING
    assert set(_PIPELINE_STAGES) == listed, (
        "Every pipeline stage must be listed in ENFORCED or PENDING. "
        f"Unlisted: {sorted(set(_PIPELINE_STAGES) - listed)}. "
        f"Listed but not registered: {sorted(listed - set(_PIPELINE_STAGES))}."
    )


@pytest.mark.parametrize("name", sorted(ENFORCED))
def test_enforced_stage_declares_something(name: str):
    assert transparency_gaps(get_stage_class(name)) == []


@pytest.mark.parametrize("name", sorted(PENDING))
def test_pending_stage_is_really_pending(name: str):
    """A pending stage that now declares something belongs in ENFORCED."""
    cls = get_stage_class(name)
    assert not cls.display_layers and not cls.summary_numbers, (
        f"{name} now declares transparency outputs: move it from PENDING to "
        f"ENFORCED in this file."
    )


def test_the_check_fails_for_a_stage_that_declares_neither():
    """The rule itself, on a stand-in: this is what an enforced stage that
    declared nothing would trip."""

    class _Silent(Stage):
        name = "silent"
        produces = {"x"}

        def run(self, ctx: PipelineContext, config: Any) -> StageResult:
            return StageResult(outputs={"x": 1})

    gaps = transparency_gaps(_Silent)
    assert gaps and "neither display_layers nor summary_numbers" in gaps[0]


# ---------------------------------------------------------------------
# Masking: what it declares
# ---------------------------------------------------------------------


def _masking_layer(band: str) -> DisplayLayer:
    return next(layer for layer in MaskingStage.display_layers if layer.band == band)


def test_masking_declares_the_reason_and_source_layers():
    assert "mask_provenance" in MaskingStage.produces
    assert [(layer.key, layer.band) for layer in MaskingStage.display_layers] == [
        ("mask_provenance", "reason"),
        ("mask_provenance", "source"),
    ]


def test_masking_legend_says_it_is_a_habitat_mask():
    """The supervisor asked for the land-cover mask; it must not read as a
    forest mask, because it keeps shrubs and (in the fallback) grassland. The
    text sits in the legend note, which goes wherever the legend is drawn."""
    note = _masking_layer("reason").legend_note
    assert "habitat mask, not a strict forest mask" in note
    for kept in ("IndiaSAT Trees", "Shrubs/Scrub", "tree cover", "shrubland", "grassland"):
        assert kept in note
    assert "where IndiaSAT has no data" in note
    assert "docs/design_notes.md" in note
    # The kept class says so too, for a legend drawn without its note.
    kept_entry = next(e for e in _masking_layer("reason").legend if e.value == REASON_KEPT)
    assert "habitat" in kept_entry.label and "not only forest" in kept_entry.label


def test_the_section_the_legend_points_to_exists():
    """The note sends the reader to a section of docs/design_notes.md by name.
    If the section is renamed, the pointer has to follow."""
    note = _masking_layer("reason").legend_note
    heading = "Masking: IndiaSAT-primary, single-phase habitat"
    assert heading in note
    design_notes = (REPO_ROOT / "docs" / "design_notes.md").read_text()
    assert f"## {heading}\n" in design_notes


def test_the_classes_the_legend_names_are_the_schema_defaults():
    """The note says "by default it keeps" Trees and Shrubs/Scrub (IndiaSAT 6
    and 12) and tree cover, shrubland and grassland (WorldCover 10, 20, 30). If
    the defaults change, the wording has to change with them."""
    defaults = MaskingParams()
    assert defaults.indiasat_habitat_classes == [6, 12]
    assert defaults.keep_worldcover_classes == [10, 20, 30]
    assert "By default" in _masking_layer("reason").legend_note


def test_masking_legends_cover_every_code():
    assert {e.value for e in _masking_layer("reason").legend} == set(REASON_NAMES)
    assert {e.value for e in _masking_layer("source").legend} == set(SOURCE_NAMES)


def test_reason_and_source_codes_fit_the_summary_key():
    """The summary packs (disagrees, source, reason) into one integer as
    disagrees * 100 + source * 10 + reason, so each code needs one digit."""
    assert all(0 <= code <= 9 for code in REASON_NAMES)
    assert all(0 <= code <= 9 for code in SOURCE_NAMES)
    assert len(set(REASON_NAMES.values())) == len(REASON_NAMES)
    assert len(set(SOURCE_NAMES.values())) == len(SOURCE_NAMES)


@pytest.mark.parametrize(
    "groups", [_INDIASAT_REASON_CLASSES, _WORLDCOVER_REASON_CLASSES], ids=["indiasat", "worldcover"]
)
def test_reason_groups_are_removal_reasons_and_do_not_overlap(groups):
    assert set(groups) == {REASON_CROPLAND, REASON_BUILT_UP, REASON_WATER}
    classes = [c for members in groups.values() for c in members]
    assert len(classes) == len(set(classes)), "a class is listed under two reasons"


def test_indiasat_groups_match_the_documented_legend():
    """fmu.config.MaskingParams: water 2-4, crops 5/8-11, built-up 1. Barren (7)
    and orchard/plantation (13, docs/datasets.md) are in no group, so they come
    out as other non-habitat; the default habitat classes are in none either."""
    assert set(_INDIASAT_REASON_CLASSES[REASON_BUILT_UP]) == {1}
    assert set(_INDIASAT_REASON_CLASSES[REASON_WATER]) == {2, 3, 4}
    assert set(_INDIASAT_REASON_CLASSES[REASON_CROPLAND]) == {5, 8, 9, 10, 11}
    grouped = {c for members in _INDIASAT_REASON_CLASSES.values() for c in members}
    assert not grouped & {7, 13}
    assert not grouped & set(MaskingParams().indiasat_habitat_classes)


def test_worldcover_groups_match_the_dataset_class_table():
    """ESA WorldCover v200, from the class table on the Earth Engine asset:
    40 cropland, 50 built-up, 80 permanent water bodies. The repo itself only
    documents the kept classes, which are in no removal group."""
    assert set(_WORLDCOVER_REASON_CLASSES[REASON_CROPLAND]) == {40}
    assert set(_WORLDCOVER_REASON_CLASSES[REASON_BUILT_UP]) == {50}
    assert set(_WORLDCOVER_REASON_CLASSES[REASON_WATER]) == {80}
    grouped = {c for members in _WORLDCOVER_REASON_CLASSES.values() for c in members}
    assert not grouped & set(MaskingParams().keep_worldcover_classes)


class _RemapRecorder:
    """Stands in for an ee.Image: records the lookup table `remap` is given."""

    def remap(self, src: list[int], dst: list[int], default: int) -> _RemapRecorder:
        self.table = dict(zip(src, dst, strict=True))
        self.default = default
        return self


@pytest.mark.parametrize(
    "groups", [_INDIASAT_REASON_CLASSES, _WORLDCOVER_REASON_CLASSES], ids=["indiasat", "worldcover"]
)
def test_reason_remap_sends_each_class_to_its_reason_and_the_rest_to_other(groups):
    recorder = _RemapRecorder()
    assert _reason_from_classes(recorder, groups) is recorder  # type: ignore[arg-type]
    assert recorder.table == {
        cls: reason for reason, members in groups.items() for cls in members
    }
    assert recorder.default == REASON_OTHER
    # Kept and no-data are never produced by the class lookup: kept comes from
    # the habitat decision itself, no-data from the absence of both maps.
    assert REASON_KEPT not in recorder.table.values()
    assert REASON_NO_DATA not in recorder.table.values()


# ---------------------------------------------------------------------
# Masking summary arithmetic (the Earth Engine call returns area per key)
# ---------------------------------------------------------------------


def _key(reason: int, source: int, disagrees: int = 0) -> int:
    return disagrees * 100 + source * 10 + reason


def test_tabulate_mask_provenance_shares_and_sources():
    out = tabulate_mask_provenance(
        {
            _key(REASON_KEPT, SOURCE_INDIASAT): 60_000.0,
            _key(REASON_KEPT, SOURCE_WORLDCOVER): 10_000.0,
            _key(REASON_CROPLAND, SOURCE_INDIASAT): 20_000.0,
            _key(REASON_BUILT_UP, SOURCE_WORLDCOVER): 10_000.0,
        }
    )
    assert out["area_ha"] == 10.0
    assert out["share_kept"] == 0.7
    assert out["share_by_reason"] == {
        "no_data": 0.0, "kept": 0.7, "cropland": 0.2, "built_up": 0.1,
        "water": 0.0, "other_non_habitat": 0.0,
    }
    assert out["share_kept_by_source"] == {
        "none": 0.0, "indiasat": 0.6, "worldcover": 0.1,
    }
    assert out["share_decided_by_source"] == {
        "none": 0.0, "indiasat": 0.8, "worldcover": 0.2,
    }
    assert out["area_ha_by_reason_and_source"]["kept"] == {
        "none": 0.0, "indiasat": 6.0, "worldcover": 1.0,
    }
    assert out["area_ha_by_reason_and_source"]["built_up"]["worldcover"] == 1.0
    assert out["area_ha_reason_disagrees_with_habitat_mask"] == 0.0


def test_tabulate_mask_provenance_parts_add_up():
    out = tabulate_mask_provenance(
        {
            _key(REASON_KEPT, SOURCE_INDIASAT): 123_456.7,
            _key(REASON_WATER, SOURCE_INDIASAT): 7_654.3,
            _key(REASON_OTHER, SOURCE_WORLDCOVER): 1_111.1,
            _key(REASON_NO_DATA, SOURCE_NONE): 999.9,
        }
    )
    assert sum(out["share_by_reason"].values()) == pytest.approx(1.0, abs=1e-5)
    assert sum(out["share_decided_by_source"].values()) == pytest.approx(1.0, abs=1e-5)
    assert sum(out["share_kept_by_source"].values()) == pytest.approx(
        out["share_kept"], abs=1e-5
    )
    table = out["area_ha_by_reason_and_source"]
    assert sum(sum(row.values()) for row in table.values()) == pytest.approx(
        out["area_ha"], abs=1e-3
    )


def test_tabulate_mask_provenance_reports_disagreement():
    """Reason says kept on 10 ha, but on 1 of them the (older, cached)
    habitat_mask says not kept; and on 0.5 ha it is the other way round."""
    out = tabulate_mask_provenance(
        {
            _key(REASON_KEPT, SOURCE_INDIASAT): 90_000.0,
            _key(REASON_KEPT, SOURCE_INDIASAT, disagrees=1): 10_000.0,
            _key(REASON_CROPLAND, SOURCE_INDIASAT): 95_000.0,
            _key(REASON_CROPLAND, SOURCE_INDIASAT, disagrees=1): 5_000.0,
        }
    )
    assert out["area_ha"] == 20.0
    assert out["area_ha_reason_disagrees_with_habitat_mask"] == 1.5
    # The reason layer's own tally: 10 ha kept, 10 ha cropland.
    assert out["share_by_reason"]["kept"] == 0.5
    assert out["share_by_reason"]["cropland"] == 0.5
    # share_kept follows habitat_mask, the mask the pipeline actually uses:
    # 9 ha where both say kept, plus the 0.5 ha only the mask keeps.
    assert out["share_kept"] == 0.475
    assert out["share_kept_by_source"]["indiasat"] == 0.475


def test_tabulate_mask_provenance_empty_roi():
    out = tabulate_mask_provenance({})
    assert out["area_ha"] == 0.0 and out["share_kept"] == 0.0
    assert set(out["share_by_reason"]) == set(REASON_NAMES.values())
    assert set(out["share_decided_by_source"]) == set(SOURCE_NAMES.values())


@pytest.mark.parametrize("bad_key", [7, 31, 211])
def test_tabulate_mask_provenance_rejects_a_key_it_cannot_decode(bad_key: int):
    """Reason 7, source 3 and disagrees 2 do not exist. Summing them into the
    wrong row would be worse than saying so."""
    with pytest.raises(ValueError, match="does not decode"):
        tabulate_mask_provenance({bad_key: 1.0})


# ---------------------------------------------------------------------
# Masking: summarise() and the manifest
# ---------------------------------------------------------------------

# 100 ha, in square metres per (source, reason).
_CANNED_AREAS = {
    _key(REASON_KEPT, SOURCE_INDIASAT): 600_000.0,
    _key(REASON_CROPLAND, SOURCE_INDIASAT): 200_000.0,
    _key(REASON_BUILT_UP, SOURCE_INDIASAT): 100_000.0,
    _key(REASON_KEPT, SOURCE_WORLDCOVER): 50_000.0,
    _key(REASON_WATER, SOURCE_WORLDCOVER): 30_000.0,
    _key(REASON_NO_DATA, SOURCE_NONE): 20_000.0,
}
_CANNED_NUMBERS = {
    "area_ha": 100.0,
    "share_kept": 0.65,
    "share_by_reason": {
        "no_data": 0.02, "kept": 0.65, "cropland": 0.2, "built_up": 0.1,
        "water": 0.03, "other_non_habitat": 0.0,
    },
    "share_kept_by_source": {"none": 0.0, "indiasat": 0.6, "worldcover": 0.05},
    "share_decided_by_source": {"none": 0.02, "indiasat": 0.9, "worldcover": 0.08},
    "area_ha_by_reason_and_source": {
        "no_data": {"none": 2.0, "indiasat": 0.0, "worldcover": 0.0},
        "kept": {"none": 0.0, "indiasat": 60.0, "worldcover": 5.0},
        "cropland": {"none": 0.0, "indiasat": 20.0, "worldcover": 0.0},
        "built_up": {"none": 0.0, "indiasat": 10.0, "worldcover": 0.0},
        "water": {"none": 0.0, "indiasat": 0.0, "worldcover": 3.0},
        "other_non_habitat": {"none": 0.0, "indiasat": 0.0, "worldcover": 0.0},
    },
    "area_ha_reason_disagrees_with_habitat_mask": 0.0,
    "kept_classes": {"indiasat": [6, 12], "worldcover": [10, 20, 30]},
}


def _config():
    from fmu.config import Config, DateRange, DatesConfig, ROIConfig

    return Config(
        name="transparency_test",
        roi=ROIConfig(name="t", roi_file=Path("aois/t.geojson")),
        dates=DatesConfig(
            phenology=DateRange(start="2020-01-01", end="2024-12-31"),
            radar=DateRange(start="2020-01-01", end="2024-12-31"),
            optical_composite=DateRange(start="2023-01-01", end="2023-12-31"),
        ),
    )


@pytest.fixture
def masking_without_earth_engine(monkeypatch):
    """The masking stage with both Earth Engine halves replaced.

    `run()` hands back placeholders for the four outputs, and the area
    reduction returns `_CANNED_AREAS`. Everything between them is the real
    code: the declaration, `summarise()`, the tabulation, the orchestrator.
    Yields the list of calls the area reduction received.
    """
    calls: list[tuple[Any, ...]] = []

    def fake_run(self, ctx: PipelineContext, config: Any) -> StageResult:
        return StageResult(
            outputs={key: f"<{key}>" for key in MaskingStage.produces},
            metadata={"faked": True},
        )

    def fake_areas(mask_provenance, habitat_mask, roi, scale) -> dict[int, float]:
        calls.append((mask_provenance, habitat_mask, roi, scale))
        return dict(_CANNED_AREAS)

    monkeypatch.setattr(MaskingStage, "run", fake_run)
    monkeypatch.setattr(masking_module, "mask_provenance_areas", fake_areas)
    return calls


def test_masking_summarise_returns_exactly_the_declared_names(
    masking_without_earth_engine,
):
    ctx = PipelineContext()
    ctx.set("roi", "<roi>")
    ctx.set("mask_provenance", "<mask_provenance>")
    ctx.set("habitat_mask", "<habitat_mask>")
    config = _config()

    numbers = MaskingStage().summarise(ctx, config)

    assert set(numbers) == {s.name for s in MaskingStage.summary_numbers}
    assert numbers == _CANNED_NUMBERS
    # It read the images and the ROI from the context, at the analysis scale.
    assert masking_without_earth_engine == [
        ("<mask_provenance>", "<habitat_mask>", "<roi>", config.export.analysis_scale_m)
    ]


def test_kept_classes_follow_the_config(masking_without_earth_engine):
    """A config that keeps other classes says so in its own summary, which is
    what the legend note points the reader to."""
    ctx = PipelineContext()
    for key in ("roi", "mask_provenance", "habitat_mask"):
        ctx.set(key, f"<{key}>")
    config = _config()
    config.masking.indiasat_habitat_classes = [6, 12, 13]
    config.masking.keep_worldcover_classes = [10]

    numbers = MaskingStage().summarise(ctx, config)

    assert numbers["kept_classes"] == {"indiasat": [6, 12, 13], "worldcover": [10]}


def _stage_entry(tmp_path: Path, index: int = 0) -> dict[str, Any]:
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    return manifest["stages"][index]


def test_what_masking_declares_is_what_the_manifest_carries(
    masking_without_earth_engine, tmp_path: Path
):
    ctx = PipelineContext()
    ctx.set("roi", "<roi>")
    Pipeline(["masking"]).run(config=_config(), run_dir=tmp_path, initial_context=ctx)

    entry = _stage_entry(tmp_path)
    assert entry["name"] == "masking"
    assert entry["produced"] == sorted(MaskingStage.produces)
    assert entry["warnings"] == []
    record = entry["transparency"]
    assert "summary_error" not in record

    # Every declared layer, in order, field by field.
    assert len(record["display_layers"]) == len(MaskingStage.display_layers)
    for carried, declared in zip(
        record["display_layers"], MaskingStage.display_layers, strict=True
    ):
        assert carried["key"] == declared.key
        assert carried["band"] == declared.band
        assert carried["title"] == declared.title
        assert carried["description"] == declared.description
        assert carried["legend_note"] == declared.legend_note
        assert carried["legend"] == [
            {"value": e.value, "label": e.label, "color": e.color}
            for e in declared.legend
        ]
        # Masking's codes run 0..n with no gaps, so the palette is the legend's
        # colours in value order.
        by_value = sorted(declared.legend, key=lambda e: e.value)
        assert carried["vis"] == {
            "bands": [declared.band],
            "min": by_value[0].value,
            "max": by_value[-1].value,
            "palette": [e.color for e in by_value],
        }
        # Caching is off in this run, so there is no asset to point at.
        assert carried["asset"] is None and carried["asset_status"] is None

    # The habitat caveat reaches the manifest with the reason layer.
    reason = next(d for d in record["display_layers"] if d["band"] == "reason")
    assert "habitat mask, not a strict forest mask" in reason["legend_note"]

    # Every declared number, in order, with its description, unit and value.
    assert [
        (n["name"], n["description"], n["unit"]) for n in record["summary_numbers"]
    ] == [(s.name, s.description, s.unit) for s in MaskingStage.summary_numbers]
    assert {n["name"]: n["value"] for n in record["summary_numbers"]} == _CANNED_NUMBERS


# ---------------------------------------------------------------------
# The eight stages the explorer shows: what each declares
# ---------------------------------------------------------------------

# Stage -> its layers in order, each as (context key, bands). One band is a
# single-band layer; three are a colour composite (red, green, blue).
_DECLARED_LAYERS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "data_load": [("s2_composite", ("B4_median", "B3_median", "B2_median"))],
    "features_optical": [("optical_features", ("ndvi_amplitude_annual",))],
    "features_radar": [("radar_features", ("vv_minus_vh_median",))],
    "features_structure": [
        ("structure_features", ("canopy_height",)),
        ("structure_features", ("canopy_height_std",)),
    ],
    "features_static": [("static_features", ("elevation",))],
    "features_embedding": [("embedding_features", ("A00", "A01", "A02"))],
    "segmentation": [("snic_clusters", ("snic_clusters",))],
    "clustering": [("cluster_labels", ("cluster_id",))],
}

# The stages that declare layers only. Clustering also reports numbers.
_LAYERS_ONLY = sorted(set(_DECLARED_LAYERS) - {"clustering"})

_HEX = re.compile(r"[0-9a-fA-F]{6}")


def _layer_bands(layer: DisplayLayer) -> tuple[str, ...]:
    return layer.bands or (layer.band,)


def _layers(name: str) -> tuple[DisplayLayer, ...]:
    return get_stage_class(name).display_layers


def test_the_table_below_covers_the_eight_stages():
    assert set(_DECLARED_LAYERS) == ENFORCED - {"masking", "merge"}


@pytest.mark.parametrize("name", sorted(_DECLARED_LAYERS))
def test_stage_declares_these_layers(name: str):
    assert [
        (layer.key, _layer_bands(layer)) for layer in _layers(name)
    ] == _DECLARED_LAYERS[name]


@pytest.mark.parametrize("name", sorted(_DECLARED_LAYERS))
def test_every_declared_key_is_produced_and_cached(name: str):
    """A layer on a key the stage does not produce is already refused when the
    class is defined; this also asks that the key is one the cache holds, since
    a reader draws the layer from the cached asset."""
    cls = get_stage_class(name)
    for layer in cls.display_layers:
        assert layer.key in cls.produces
        assert layer.key in Pipeline._resolve_cacheable_outputs(cls())


@pytest.mark.parametrize("name", _LAYERS_ONLY)
def test_stage_declares_layers_only_so_a_run_makes_no_new_request(name: str):
    """A declaration costs nothing on a run. A summary would: the orchestrator
    calls summarise() on every run, and a whole-ROI reduction on these images is
    what ran out of memory in the re-runs."""
    cls = get_stage_class(name)
    assert cls.summary_numbers == ()
    assert cls.summarise is Stage.summarise


def test_true_colour_and_the_embedding_view_are_the_only_composites():
    composites = {
        name: [layer.key for layer in _layers(name) if layer.bands]
        for name in _DECLARED_LAYERS
    }
    assert composites == {
        **{name: [] for name in _DECLARED_LAYERS},
        "data_load": ["s2_composite"],
        "features_embedding": ["embedding_features"],
    }
    for name in ("data_load", "features_embedding"):
        (layer,) = _layers(name)
        vis = layer.vis_params()
        assert vis["bands"] == list(layer.bands)
        assert vis["min"] < vis["max"] and "palette" not in vis
        assert layer.to_manifest()["bands"] == list(layer.bands)


def test_true_colour_starts_from_the_documented_reflectance_stretch():
    (layer,) = _layers("data_load")
    assert layer.vis == {"min": 0, "max": 3000}
    assert "default median composite" in layer.description


@pytest.mark.parametrize(
    "name", ["features_optical", "features_radar", "features_structure", "features_static"]
)
def test_a_single_band_feature_layer_is_continuous_with_a_colour_scale(name: str):
    for layer in _layers(name):
        assert not layer.legend and not layer.bands
        assert set(layer.vis) == {"min", "max", "palette"}
        assert layer.vis["min"] < layer.vis["max"]
        assert len(layer.vis["palette"]) >= 2
        assert all(_HEX.fullmatch(c) for c in layer.vis["palette"])
        assert "bands" not in layer.to_manifest()


def test_feature_layers_say_their_unit_where_they_have_one():
    """`vis` goes to Earth Engine as it stands, so it holds no unit. The title
    is where a reader finds it."""
    titles = {
        layer.band: layer.title
        for name in _DECLARED_LAYERS
        for layer in _layers(name)
    }
    assert titles["canopy_height"].endswith(", m")
    assert titles["canopy_height_std"].endswith(", m")
    assert titles["elevation"].endswith(", m")
    assert titles["vv_minus_vh_median"].endswith(", dB")


def test_what_a_layer_says_of_segmentation_and_merge_is_said_of_the_defaults():
    """A description is the same text in every run's manifest, and the bands a
    run segments and merges on are config values. What a layer says of them
    holds for the defaults, read here from the schema, and has to say so."""
    described = {
        layer.band: layer.description
        for name in _DECLARED_LAYERS
        for layer in _layers(name)
    }
    snic = {b.band for b in SegmentationParams().input_bands}
    merged = {c.band for c in _config().merge.criteria}
    for band in ("canopy_height", "ndvi_amplitude_annual"):
        assert band in snic and band in merged
        assert "drawn on by default" in described[band], band
        assert "the merge compares by default" in described[band], band
    assert len(merged) == 2
    # The spread is in neither default, and is a merge criterion of some configs.
    assert "canopy_height_std" not in snic | merged
    assert any(
        "canopy_height_std" in {c.band for c in cfg.merge.criteria}
        for cfg in _shipped_configs()
    )
    assert "merge criterion" in described["canopy_height_std"]
    # True colour is what segmentation reads only with the hand-crafted bands.
    assert "With the default hand-crafted bands" in described["B4_median"]
    assert "segments on the embedding" in described["B4_median"]


def test_no_declaration_names_a_site():
    """src/fmu/ is site-neutral, and a layer's text goes into the manifest of
    every site."""
    for name in sorted(ENFORCED):
        for layer in _layers(name):
            text = " ".join((layer.title, layer.description, layer.legend_note))
            for site in ("Odisha", "Sanjay Van"):
                assert site not in text, f"{name} {layer.key}.{layer.band}: {site}"


def test_canopy_height_says_which_product_it_is_and_points_to_its_field_check():
    """ETH canopy height stays in the pipeline (the supervisor's decision), and
    is shown as what it is: a modelled map for 2020. The note sends the reader
    to a section of docs/datasets.md by name; if it is renamed, the pointer has
    to follow."""
    layer = next(
        layer for layer in _layers("features_structure") if layer.band == "canopy_height"
    )
    assert "ETH" in layer.title and "2020" in layer.title
    assert "ETH Global Canopy Height" in layer.description
    heading = "ETH Global Canopy Height 2020"
    assert heading in layer.legend_note and "docs/datasets.md" in layer.legend_note
    assert f"## {heading}\n" in (REPO_ROOT / "docs" / "datasets.md").read_text()


def test_the_window_the_height_spread_names_is_the_schema_default():
    layer = next(
        layer
        for layer in _layers("features_structure")
        if layer.band == "canopy_height_std"
    )
    assert FeaturesStructureParams().neighborhood_kernel_size == 3
    assert "3 by 3 pixels by default" in layer.description


def test_the_embedding_view_says_it_is_three_bands_of_sixty_four():
    (layer,) = _layers("features_embedding")
    assert "three of its 64 bands" in layer.title
    assert "first three of the 64 bands" in layer.description
    assert "principal components" in layer.description
    assert "exporter" in layer.description


def test_superpixels_are_declared_as_outlines_without_a_legend():
    """A superpixel label is an arbitrary 32-bit number, far past what a legend
    can span, and its value means nothing as a colour."""
    (layer,) = _layers("segmentation")
    assert layer.legend == ()
    assert set(layer.vis) == {"style", "palette"}
    assert layer.vis["style"] == "outline"
    (colour,) = layer.vis["palette"]
    assert _HEX.fullmatch(colour)
    assert layer.vis_params()["bands"] == ["snic_clusters"]


def _stand_types() -> DisplayLayer:
    (layer,) = _layers("clustering")
    return layer


def test_stand_types_have_a_legend_for_types_zero_to_nine():
    legend = _stand_types().legend
    assert [e.value for e in legend] == list(range(10))
    assert [e.label for e in legend] == [f"Stand type {i}" for i in range(10)]
    colours = [e.color.upper() for e in legend]
    assert len(set(colours)) == len(colours)
    # No type is drawn in the colour a legend gap is drawn in.
    assert "000000" not in colours
    # The first six, in the order the early ui_data build coloured stand types.
    assert colours[:6] == ["E69F00", "56B4E9", "009E73", "F0E442", "0072B2", "D55E00"]
    # Types 0..9 with no gaps: the palette is the legend's colours in order.
    assert _stand_types().vis_params() == {
        "bands": ["cluster_id"],
        "min": 0,
        "max": 9,
        "palette": [e.color for e in legend],
    }


def test_stand_type_note_says_what_a_type_number_does_not_mean():
    note = _stand_types().legend_note
    for said in (
        "first k",
        "clustering.k",
        "mean nothing across runs",
        "outside the habitat mask",
        "no data in one of the feature bands",
        "no type",
    ):
        assert said in note, said


def test_the_legend_has_a_colour_for_every_type_a_config_can_ask_for_today():
    """The legend stops at type 9. The default k and every config under
    configs/ must fit; a config with a larger k needs a longer legend first."""
    n_types = len(_stand_types().legend)
    assert ClusteringParams().k <= n_types
    for cfg in _shipped_configs():
        assert cfg.clustering.k <= n_types, cfg.name


# ---------------------------------------------------------------------
# The bands a declaration names are bands the stage writes
#
# A declaration is static; band names are not. They depend on the compositing
# reducer, the vegetation index and three switches. The declarations name the
# bands of the defaults, so (1) the defaults must give those bands, read here
# from the stage code itself, and (2) no config under configs/ may set a value
# for which the declaration would name a band that is not there.
# ---------------------------------------------------------------------


def _shipped_configs() -> list[Any]:
    paths = sorted((REPO_ROOT / "configs").glob("*.yaml"))
    assert paths, "no configs found under configs/"
    return [load_config(path) for path in paths]


# The one config under configs/ on the NIRv index. Its optical bands are named
# nirv_*, so the features_optical declaration names a band its runs do not
# have, and the layer's description says so. It is not one of the 14 demo
# runs. Do not add to this set to make a new config pass: a second index in
# real use is the point at which the declaration has to follow the config.
_NIRV_CONFIGS = {"sanjay_van_nirv_dual"}


def test_the_nirv_exception_is_exactly_the_configs_on_that_index():
    on_nirv = {
        cfg.name for cfg in _shipped_configs() if cfg.features_optical.index == "nirv"
    }
    assert on_nirv == _NIRV_CONFIGS
    (layer,) = _layers("features_optical")
    assert "nirv_amplitude_annual" in layer.description


# The one config under configs/ whose embedding is not AlphaEarth: an uploaded
# Tessera image, 128 channels (docs/datasets.md). The features_embedding layer
# is titled and described as AlphaEarth's and names A00, A01, A02, so it does
# not describe this config's runs, and the layer's description says so. Its
# asset id is still a placeholder and it is not one of the 14 demo runs. Do not
# add to this set to make a new config pass: a second embedding in real use is
# the point at which the declaration has to follow the config.
_OTHER_EMBEDDING_CONFIGS = {"sanjay_van_tessera"}


def _alphaearth() -> str:
    """The schema's default `datasets.embedding`, which is AlphaEarth."""
    return DatasetIDs().embedding


def test_the_embedding_exception_is_exactly_the_configs_on_another_embedding():
    """Only a run in embedding mode runs features_embedding, so only there can
    the layer be wrong."""
    assert _alphaearth() == "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"
    on_another = {
        cfg.name
        for cfg in _shipped_configs()
        if cfg.clustering.feature_source == "embedding"
        and cfg.datasets.embedding != _alphaearth()
    }
    assert on_another == _OTHER_EMBEDDING_CONFIGS
    (layer,) = _layers("features_embedding")
    assert "AlphaEarth" in layer.title
    assert "default AlphaEarth embedding" in layer.description
    assert "another embedding" in layer.description


def test_the_other_embedding_is_documented_as_not_alphaearth():
    """What makes the exception an exception: the dataset notes give Tessera
    another channel count than the 64 the layer states."""
    datasets = (REPO_ROOT / "docs" / "datasets.md").read_text()
    assert "Tessera is a 128-channel" in datasets
    assert "a 64-band annual ImageCollection" in datasets


def test_the_docs_name_every_config_a_declaration_does_not_fit():
    outputs = (REPO_ROOT / "docs" / "outputs.md").read_text()
    for name in _NIRV_CONFIGS | _OTHER_EMBEDDING_CONFIGS:
        assert f"`{name}`" in outputs, name


def test_every_shipped_config_writes_the_bands_the_declarations_name():
    reducer = DataLoadParams().s2_composite_reducer
    assert reducer == "median"
    for cfg in _shipped_configs():
        assert cfg.data_load.s2_composite_reducer == "median", (
            f"{cfg.name}: data_load declares the true-colour bands of the median "
            f"composite (B4_median, B3_median, B2_median); under "
            f"{cfg.data_load.s2_composite_reducer!r} they do not exist."
        )
        if cfg.name not in _NIRV_CONFIGS:
            assert cfg.features_optical.index == "ndvi", (
                f"{cfg.name}: features_optical declares ndvi_amplitude_annual; "
                f"under index 'nirv' the band is nirv_amplitude_annual."
            )
        assert cfg.features_radar.include_cross_pol_contrast, (
            f"{cfg.name}: features_radar declares vv_minus_vh_median."
        )
        assert cfg.features_structure.include_neighborhood_stats, (
            f"{cfg.name}: features_structure declares canopy_height_std."
        )
        assert cfg.features_embedding.band_names is None, (
            f"{cfg.name}: features_embedding declares A00, A01 and A02; a config "
            f"that restricts band_names may not keep them."
        )
        if (
            cfg.clustering.feature_source == "embedding"
            and cfg.name not in _OTHER_EMBEDDING_CONFIGS
        ):
            assert cfg.datasets.embedding == _alphaearth(), (
                f"{cfg.name}: features_embedding declares three of AlphaEarth's "
                f"64 bands; {cfg.datasets.embedding!r} is another embedding."
            )


def test_true_colour_bands_are_red_green_blue_of_the_default_composite():
    """Earth Engine names a reduced band `<band>_<reducer>`. The same naming is
    what the default segmentation stack relies on for its red band."""
    suffix = DataLoadParams().s2_composite_reducer
    (layer,) = _layers("data_load")
    assert layer.bands == tuple(f"{b}_{suffix}" for b in ("B4", "B3", "B2"))
    default_snic = {
        (b.source, b.band) for b in SegmentationParams().input_bands
    }
    assert ("s2_composite", layer.band) in default_snic


class _BandNames(list):
    """What a traced image's bandNames() returns."""


class _Traced:
    """Stands in for an Earth Engine image, collection or anything else, and
    keeps one thing: the band names the stage code gives it. `rename` sets
    them, `select` narrows to them, every other call passes them through."""

    def __init__(self, bands: Any = ()) -> None:
        self.bands = list(bands)

    def rename(self, *names: Any) -> _Traced:
        flat = names[0] if len(names) == 1 and isinstance(names[0], list) else names
        return _Traced(flat)

    def select(self, selectors: Any, *_: Any) -> _Traced:
        picked = selectors if isinstance(selectors, list) else [selectors]
        # A band picked by position has no name until it is renamed.
        return _Traced(b for b in picked if isinstance(b, str))

    def bandNames(self) -> _BandNames:  # noqa: N802 - mirrors the ee API
        return _BandNames(self.bands)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *args, **kwargs: _Traced(self.bands)


class _TracedImageNamespace:
    """`ee.Image`: called as a constructor, and for `cat` and `constant`."""

    def __call__(self, *args: Any, **kwargs: Any) -> _Traced:
        return _Traced()

    @staticmethod
    def cat(images: list[_Traced]) -> _Traced:
        return _Traced(b for image in images for b in image.bands)

    @staticmethod
    def constant(*args: Any, **kwargs: Any) -> _Traced:
        return _Traced()


class _AnythingElse:
    """`ee.Reducer`, `ee.Kernel`, `ee.Terrain`, `ee.Algorithms...`: any
    attribute, and calling it gives a traced object with no bands yet."""

    def __getattr__(self, name: str) -> _AnythingElse:
        return _AnythingElse()

    def __call__(self, *args: Any, **kwargs: Any) -> _Traced:
        return _Traced()


class _TracingEE:
    Image = _TracedImageNamespace()

    def __getattr__(self, name: str) -> _AnythingElse:
        return _AnythingElse()


def _traced_get_info(obj: Any, context: str = "") -> Any:
    """Band names come back as the names traced so far; any other request
    (a count, a grid scale) as 1."""
    return list(obj) if isinstance(obj, _BandNames) else 1


def _trace(monkeypatch, module: Any) -> None:
    monkeypatch.setattr(module, "ee", _TracingEE())
    monkeypatch.setattr(module, "safe_get_info", _traced_get_info)


def _traced_outputs(monkeypatch, module: Any, name: str, config: Any) -> dict[str, list[str]]:
    """Run a stage's own run() on traced stand-ins; return its band names by key."""
    _trace(monkeypatch, module)
    cls = get_stage_class(name)
    ctx = PipelineContext()
    for key in cls.required_inputs:
        ctx.set(key, _Traced())
    result = cls().run(ctx, config)
    return {key: image.bands for key, image in result.outputs.items()}


_FEATURE_MODULES = {
    "features_optical": optical_module,
    "features_radar": radar_module,
    "features_structure": structure_module,
    "features_static": static_module,
}


@pytest.mark.parametrize("name", sorted(_FEATURE_MODULES))
def test_a_declared_feature_band_is_one_the_stage_writes_by_default(
    monkeypatch, name: str
):
    written = _traced_outputs(monkeypatch, _FEATURE_MODULES[name], name, _config())
    for layer in _layers(name):
        assert set(_layer_bands(layer)) <= set(written[layer.key]), (
            f"{name} declares {layer.key}.{layer.band}, but with the default "
            f"config it writes {written[layer.key]}"
        )
    # The trace is of the real code: it also finds the bands the default
    # segmentation stack and the default merge criteria read from this stage.
    (key,) = get_stage_class(name).produces
    read_downstream = {
        b.band for b in SegmentationParams().input_bands if b.source == key
    } | {c.band for c in _config().merge.criteria if c.source == key}
    assert read_downstream <= set(written[key])


def test_the_trace_follows_the_config_and_so_would_catch_a_missing_band(monkeypatch):
    """With the neighbourhood statistics off the spread band is not written, and
    the trace says so: this is the case the config test above guards against."""
    config = _config()
    config.features_structure.include_neighborhood_stats = False
    written = _traced_outputs(monkeypatch, structure_module, "features_structure", config)
    assert written == {"structure_features": ["canopy_height"]}


def test_the_embedding_bands_are_three_of_the_documented_sixty_four():
    """The embedding's band names come from the dataset, not from this code.
    docs/datasets.md and the schema give them as A00..A63."""
    (layer,) = _layers("features_embedding")
    documented = [f"A{i:02d}" for i in range(64)]
    assert list(layer.bands) == documented[:3]
    assert "`A00`..`A63`" in (REPO_ROOT / "docs" / "datasets.md").read_text()
    assert "A00..A63" in (embedding_module.__doc__ or "")


def test_the_superpixel_band_is_the_one_segmentation_writes(monkeypatch):
    _trace(monkeypatch, segmentation_module)
    monkeypatch.setattr(segmentation_module, "_analysis_grid", lambda roi, scale: _Traced())
    config = _config()
    # The two normalisations reduce over the ROI and change no band name.
    config.segmentation.normalize_inputs = False
    config.segmentation.normalize_distance_scale = False
    ctx = PipelineContext()
    for key in {"roi"} | config.segmentation.input_sources():
        ctx.set(key, _Traced())

    result = segmentation_module.SegmentationStage().run(ctx, config)

    (layer,) = _layers("segmentation")
    assert result.outputs[layer.key].bands == [layer.band]


def test_the_stand_type_band_is_the_one_k_means_writes(monkeypatch):
    _trace(monkeypatch, clustering_module)
    monkeypatch.setattr(
        clustering_module, "_sample_one_point_per_unit", lambda *a, **k: _Traced()
    )
    monkeypatch.setattr(clustering_module, "_count_units", lambda *a, **k: 1)

    labels, _coverage = clustering_module._train_and_apply_kmeans(
        scaled_stack=_Traced(),
        active_bands=["a"],
        unit_labels=_Traced(),
        habitat_mask=_Traced(),
        roi=_Traced(),
        scale=10,
        k=1,
        seed=0,
        unit_key="stand_clusters",
    )

    assert labels.bands == [_stand_types().band]


# ---------------------------------------------------------------------
# Clustering: summary numbers, read from the image's own metadata
# ---------------------------------------------------------------------

# clustering_metadata as a run wrote it (sanjay_van_baseline, 27 Aug 2026),
# cut down to the keys the summary reads and two it does not.
_CANNED_METADATA = {
    "k": 6,
    "n_training_units": 289,
    "n_units_total": 327,
    "n_units_in_habitat": 289,
    "n_units_outside_habitat": 38,
    "n_units_dropped_null_band": 0,
    "training_unit_key": "stand_clusters",
    "seed": 42,
}
_CANNED_COUNTS = {
    "k": 6,
    "units_total": 327,
    "units_in_habitat": 289,
    "units_fitted": 289,
    "units_dropped_missing_band": 0,
}


class _LabelsWithProperty:
    """Stands in for cluster_labels: hands back its properties and counts the
    requests, so a test can say the summary made one."""

    def __init__(self, properties: dict[str, Any]) -> None:
        self.properties = properties
        self.asked: list[str] = []

    def get(self, name: str) -> Any:
        self.asked.append(name)
        return self.properties.get(name)


@pytest.fixture
def property_reads(monkeypatch):
    """safe_get_info in the clustering module returns what it is handed (the
    stand-in above already resolved the property). Yields the request contexts."""
    contexts: list[str] = []

    def fake_get_info(obj: Any, context: str = "") -> Any:
        contexts.append(context)
        return obj

    monkeypatch.setattr(clustering_module, "safe_get_info", fake_get_info)
    return contexts


def _ctx_with_labels(labels: Any) -> PipelineContext:
    ctx = PipelineContext()
    ctx.set("cluster_labels", labels)
    return ctx


def test_clustering_summarise_returns_exactly_the_declared_names(property_reads):
    labels = _LabelsWithProperty({"clustering_metadata": json.dumps(_CANNED_METADATA)})

    numbers = clustering_module.ClusteringStage().summarise(
        _ctx_with_labels(labels), _config()
    )

    declared = clustering_module.ClusteringStage.summary_numbers
    assert set(numbers) == {s.name for s in declared}
    assert numbers == _CANNED_COUNTS
    # One small request, for the one property, and nothing else.
    assert labels.asked == ["clustering_metadata"]
    assert len(property_reads) == 1


def test_the_unit_counts_say_they_are_not_counts_of_exported_stands():
    """The counts are distinct labels on the analysis grid. The stand layer the
    same run exports has another number of polygons and more typed stands (all
    14 re-runs of 13 Oct 2026), so a description that called them stands, or
    said the rest get no type, would be contradicted by the export."""
    said = {s.name: s.description for s in clustering_module.ClusteringStage.summary_numbers}
    for name in ("units_total", "units_in_habitat"):
        assert "Distinct unit labels" in said[name], name
        assert "analysis grid" in said[name], name
        assert "exported stand layer" in said[name], name
    assert "given no type" not in said["units_in_habitat"]
    outputs = (REPO_ROOT / "docs" / "outputs.md").read_text()
    assert "not counts of the polygons in the exported stand layer" in outputs


def test_clustering_numbers_account_for_every_unit():
    """Total = outside habitat + in habitat; in habitat = fitted + dropped. The
    summary gives four of the five, and the fifth follows."""
    numbers = clustering_module.tabulate_clustering_metadata(
        {**_CANNED_METADATA, "n_training_units": 287, "n_units_dropped_null_band": 2}
    )
    assert numbers["units_in_habitat"] == (
        numbers["units_fitted"] + numbers["units_dropped_missing_band"]
    )
    assert numbers["units_total"] - numbers["units_in_habitat"] == (
        _CANNED_METADATA["n_units_outside_habitat"]
    )


def test_clustering_summary_reads_k_from_the_image_not_the_config(property_reads):
    """After a cache hit the image is what the run carries; its own record of k
    is the one that describes it."""
    labels = _LabelsWithProperty(
        {"clustering_metadata": json.dumps({**_CANNED_METADATA, "k": 5})}
    )
    config = _config()
    assert config.clustering.k != 5
    numbers = clustering_module.ClusteringStage().summarise(
        _ctx_with_labels(labels), config
    )
    assert numbers["k"] == 5


def test_an_image_without_the_property_is_an_error_not_a_row_of_zeros(property_reads):
    with pytest.raises(ValueError, match="no 'clustering_metadata' property"):
        clustering_module.ClusteringStage().summarise(
            _ctx_with_labels(_LabelsWithProperty({})), _config()
        )


def test_metadata_from_before_the_coverage_counts_is_an_error_too():
    """An asset made before the fit reported its coverage has k and the row
    count only (sanjay_van_baseline, first run of 27 Aug 2026). A missing count
    must not come out as zero."""
    old = {"k": 6, "n_training_units": 289, "training_unit_key": "stand_clusters"}
    with pytest.raises(ValueError, match="n_units_dropped_null_band"):
        clustering_module.tabulate_clustering_metadata(old)


@pytest.fixture
def clustering_without_earth_engine(monkeypatch, property_reads):
    """The clustering stage with run() replaced: it hands back a labels image
    that carries the canned metadata, as the real one does. The declaration,
    summarise() and the orchestrator are the real code."""
    labels = _LabelsWithProperty({"clustering_metadata": json.dumps(_CANNED_METADATA)})

    def fake_run(self, ctx: PipelineContext, config: Any) -> StageResult:
        return StageResult(
            outputs={"cluster_labels": labels, "feature_stack": "<feature_stack>"}
        )

    monkeypatch.setattr(clustering_module.ClusteringStage, "validate", lambda *a: None)
    monkeypatch.setattr(clustering_module.ClusteringStage, "run", fake_run)
    return labels


def test_what_clustering_declares_is_what_the_manifest_carries(
    clustering_without_earth_engine, tmp_path: Path
):
    Pipeline(["clustering"]).run(config=_config(), run_dir=tmp_path)

    entry = _stage_entry(tmp_path)
    assert entry["name"] == "clustering" and entry["warnings"] == []
    record = entry["transparency"]
    assert "summary_error" not in record
    (carried,) = record["display_layers"]
    assert (carried["key"], carried["band"]) == ("cluster_labels", "cluster_id")
    assert "bands" not in carried
    assert [e["label"] for e in carried["legend"]] == [
        f"Stand type {i}" for i in range(10)
    ]
    assert carried["legend_note"] == _stand_types().legend_note
    assert {n["name"]: n["value"] for n in record["summary_numbers"]} == _CANNED_COUNTS
    assert all(n["unit"] == "count" for n in record["summary_numbers"])


def test_a_composite_reaches_the_manifest_with_its_three_bands(
    monkeypatch, tmp_path: Path
):
    """The embedding view, through the orchestrator: `bands` is written, and
    `vis.bands` names the same three."""
    cls = embedding_module.FeaturesEmbeddingStage
    monkeypatch.setattr(
        cls,
        "run",
        lambda self, ctx, config: StageResult(
            outputs={"embedding_features": "<embedding>"}
        ),
    )
    ctx = PipelineContext()
    ctx.set("roi", "<roi>")
    Pipeline(["features_embedding"]).run(
        config=_config(), run_dir=tmp_path, initial_context=ctx
    )

    record = _stage_entry(tmp_path)["transparency"]
    assert record["summary_numbers"] == []
    (carried,) = record["display_layers"]
    assert carried["band"] == "A00"
    assert carried["bands"] == ["A00", "A01", "A02"]
    assert carried["vis"] == {"bands": ["A00", "A01", "A02"], "min": -0.3, "max": 0.3}
    assert carried["legend"] == []


# ---------------------------------------------------------------------
# The orchestrator writes any stage's declaration into the manifest
# ---------------------------------------------------------------------


def _declaring_stage(summarise_impl):
    @register_stage("declaring")
    class _Declaring(Stage):
        name = "declaring"
        produces = {"layer"}
        cacheable_outputs: set[str] = set()
        display_layers = (
            DisplayLayer(
                "layer", "b", "A layer", "what it shows",
                legend=(LegendEntry(0, "out", "000000"), LegendEntry(1, "in", "ffffff")),
                legend_note="read this with the legend",
            ),
        )
        summary_numbers = (SummaryNumber("share_in", "share of the area in", "fraction"),)

        def run(self, ctx: PipelineContext, config: Any) -> StageResult:
            return StageResult(outputs={"layer": "an image"})

        def summarise(self, ctx: PipelineContext, config: Any) -> dict[str, Any]:
            return summarise_impl(ctx)

    return _Declaring


def test_manifest_carries_layers_and_summary_numbers(tmp_path: Path):
    _declaring_stage(lambda ctx: {"share_in": 0.25})
    Pipeline(["declaring"]).run(config=_config(), run_dir=tmp_path)
    t = _stage_entry(tmp_path)["transparency"]
    assert t["display_layers"] == [
        {
            "key": "layer",
            "band": "b",
            "title": "A layer",
            "description": "what it shows",
            "vis": {"bands": ["b"], "min": 0, "max": 1, "palette": ["000000", "ffffff"]},
            "legend": [
                {"value": 0, "label": "out", "color": "000000"},
                {"value": 1, "label": "in", "color": "ffffff"},
            ],
            "legend_note": "read this with the legend",
            "asset": None,  # caching is off
            "asset_status": None,
        }
    ]
    assert t["summary_numbers"] == [
        {
            "name": "share_in",
            "description": "share of the area in",
            "unit": "fraction",
            "value": 0.25,
        }
    ]


def test_summarise_reads_the_context_after_the_stage_ran(tmp_path: Path):
    _declaring_stage(lambda ctx: {"share_in": len(ctx.get("layer"))})
    Pipeline(["declaring"]).run(config=_config(), run_dir=tmp_path)
    t = _stage_entry(tmp_path)["transparency"]
    assert t["summary_numbers"][0]["value"] == len("an image")


def test_a_failed_summary_is_recorded_not_fatal(tmp_path: Path):
    """An Earth Engine memory limit on the reduction must not cost the run: the
    stage's products are already made."""

    def boom(ctx):
        raise RuntimeError("user memory limit exceeded")

    _declaring_stage(boom)
    result = Pipeline(["declaring"]).run(config=_config(), run_dir=tmp_path)
    entry = _stage_entry(tmp_path)
    assert "RuntimeError: user memory limit exceeded" in entry["transparency"]["summary_error"]
    assert entry["transparency"]["summary_numbers"] == []
    assert any("summary numbers not computed" in w for w in entry["warnings"])
    # The stage's output is in the context and on the record all the same.
    assert entry["produced"] == ["layer"]
    assert result.context is not None and result.context.get("layer") == "an image"
    # The layers do not depend on the summary and are still written.
    assert entry["transparency"]["display_layers"][0]["key"] == "layer"


@pytest.mark.parametrize(
    "returned",
    [{"something_else": 1}, {"share_in": 0.5, "extra": 1}, {}, [0.5]],
    ids=["other_name", "extra_name", "nothing", "not_a_dict"],
)
def test_a_summary_with_the_wrong_names_is_recorded_not_fatal(tmp_path: Path, returned):
    """Same rule as a summary that raises: by now the products are made, and
    with caching on their exports are submitted. The test that makes a wrong
    summarise() fail loudly is the per-stage one above."""
    _declaring_stage(lambda ctx: returned)
    Pipeline(["declaring"]).run(config=_config(), run_dir=tmp_path)
    entry = _stage_entry(tmp_path)
    assert "summarise() returned" in entry["transparency"]["summary_error"]
    assert "share_in" in entry["transparency"]["summary_error"]
    assert entry["transparency"]["summary_numbers"] == []
    assert any("summary numbers not computed" in w for w in entry["warnings"])


def test_a_later_stage_still_runs_after_a_failed_summary(tmp_path: Path):
    def boom(ctx):
        raise RuntimeError("computation timed out")

    _declaring_stage(boom)

    @register_stage("after")
    class _After(Stage):
        name = "after"
        required_inputs = {"layer"}
        produces = {"seen"}
        cacheable_outputs: set[str] = set()

        def run(self, ctx: PipelineContext, config: Any) -> StageResult:
            return StageResult(outputs={"seen": ctx.get("layer")})

    result = Pipeline(["declaring", "after"]).run(config=_config(), run_dir=tmp_path)
    assert result.context is not None and result.context.get("seen") == "an image"
    assert _stage_entry(tmp_path, 1)["name"] == "after"


def test_summaries_can_be_switched_off(tmp_path: Path):
    def boom(ctx):
        raise AssertionError("summarise must not be called")

    _declaring_stage(boom)
    Pipeline(["declaring"], summaries=False).run(config=_config(), run_dir=tmp_path)
    entry = _stage_entry(tmp_path)
    t = entry["transparency"]
    assert t["summary_numbers"] == [] and "summary_skipped" in t
    assert "summary_error" not in t and entry["warnings"] == []
    # The layers are a declaration, not a computation, and are still written.
    assert len(t["display_layers"]) == 1
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["summaries"] is False


def test_the_manifest_says_summaries_were_on(tmp_path: Path):
    _declaring_stage(lambda ctx: {"share_in": 1.0})
    Pipeline(["declaring"]).run(config=_config(), run_dir=tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["summaries"] is True


def test_a_stage_that_declares_nothing_gets_an_empty_record(tmp_path: Path):
    @register_stage("plain")
    class _Plain(Stage):
        name = "plain"
        produces = {"x"}
        cacheable_outputs: set[str] = set()

        def run(self, ctx: PipelineContext, config: Any) -> StageResult:
            return StageResult(outputs={"x": 1})

    Pipeline(["plain"]).run(config=_config(), run_dir=tmp_path)
    assert _stage_entry(tmp_path)["transparency"] == {
        "display_layers": [],
        "summary_numbers": [],
    }
